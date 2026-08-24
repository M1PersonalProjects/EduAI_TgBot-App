import json
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from database import db
from logger_config import logger
from services.ai import openai_client, parse_chat_completion
from bot.messages import answer_plain, send_plain_to_chat
from services.tutor_policy import task_grading_prompt
from services.educational_context import build_context_from_metadata
from services.assignment_source import TEACHER, normalize_assignment_source

router = Router()



class QuestStates(StatesGroup):
    waiting_for_answer = State()


@router.message(Command(commands=["cancel"]))
@router.message(F.text.lower() == "отмена")
@router.message(F.text == "/cancel")
async def cancel_quest(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("У тебя сейчас нет activeных заданий.")
        return
    await state.clear()
    await message.answer("Выполнение задания прервано. Ты можешь взять новый /quest в любое время.")


@router.message(F.text == "/quest")
@router.message(F.text == "🚀 Запустить квест")
async def start_quest(message: Message, state: FSMContext):
    user_id = message.from_user.id
    await state.clear()

    async with db.pool.acquire() as conn:
        student = await conn.fetchrow("SELECT parent_id FROM users WHERE tg_id = $1 AND role = 'student'", user_id)

    if not student:
        await message.answer("Тренировочные квесты доступны только для пользователей с ролью Ученик.")
        return
    status_msg = await message.answer("🎲 *ИИ-Тьютор проверяет твои задания...* ⏳", parse_mode="Markdown")
    async with db.pool.acquire() as conn:
        parent_task = await conn.fetchrow(
            """
            SELECT task_id, topic_context, questions_json, student_answers_json,
                   parent_id, parent_comment, assignment_source, subject, topic
            FROM tasks_history
            WHERE student_id = $1 AND assignment_source = 'teacher'
              AND status IN ('created'::task_status, 'in_progress'::task_status)
            ORDER BY created_at ASC
            LIMIT 1
            """,
            user_id
        )
    if parent_task:
        try:
            topic = json.loads(parent_task["topic_context"]) if isinstance(parent_task["topic_context"], str) else parent_task["topic_context"]
            quest = json.loads(parent_task["questions_json"]) if isinstance(parent_task["questions_json"], str) else parent_task["questions_json"]

            history_feedback = ""
            if parent_task["student_answers_json"]:
                old_ans = json.loads(parent_task["student_answers_json"]) if isinstance(parent_task["student_answers_json"], str) else parent_task["student_answers_json"]
                history_feedback = (
                    f"\n\n⚠️ Твой прошлый ответ: {old_ans.get('provided_answer')}\n"
                    f"❌ Подсказка учителя: {old_ans.get('verification_feedback')}"
                )
            try:
                parent_comment_value = parent_task["parent_comment"]
            except (KeyError, TypeError):
                # Backward compatibility: old DB rows/test fixtures may not expose
                # the newly public parent_comment field yet. Treat it as empty.
                parent_comment_value = None
            parent_comment = (parent_comment_value or "").strip()
            parent_comment_block = (
                f"\n\n💬 Комментарий от Учителя:\n{parent_comment}"
                if parent_comment else ""
            )
            async with db.pool.acquire() as conn:
                await conn.execute("UPDATE tasks_history SET status = 'in_progress'::task_status WHERE task_id = $1", parent_task["task_id"])
            quest_items = quest.get("items") or []
            if quest_items:
                question_blocks = [
                    f"{index}. {item.get('question_text') or ''}"
                    for index, item in enumerate(quest_items, start=1)
                    if (item.get("question_text") or "").strip()
                ]
                active_question = "\n\n".join(question_blocks)
            else:
                active_question = quest.get("question_text") or ""
            await state.update_data(
                active_task_id=parent_task["task_id"],
                question_text=active_question,
                parent_id=parent_task["parent_id"],
                assignment_source="teacher",
                quest_subject=parent_task.get("subject") if hasattr(parent_task, "get") else None,
                quest_topic=parent_task.get("topic") if hasattr(parent_task, "get") else None,
                quest_title=quest.get("title") or "Задание от Учителя",
                quest_items=quest_items,
                quest_index=0,
                quest_answers=[],
            )
            await state.set_state(QuestStates.waiting_for_answer)

            await status_msg.delete()
            await answer_plain(
                message,
                f"👨‍👩‍👦 Персональное задание от Учителя!\n"
                f"📘 {quest.get('title') or 'Задание'}\n\n"
                f"{active_question}"
                f"{parent_comment_block}"
                f"{history_feedback}\n\n"
                "Отправь ответы одним сообщением. После отправки задание перейдёт Учителю "
                "на ручную проверку.\n\n"
                "Напиши ответ в чат (или введи /cancel для отмены)."
            )
            return
        except Exception as e:
            logger.error(f"Ошибка парсинга задания Учителя: {e}")
    await status_msg.delete()
    from bot.handlers.quests import quest_entry_keyboard

    await message.answer(
        "🧩 Создай квест-тест под свою тему.\n\n"
        "Можно выбрать учебник, страницу или тему из базы EduAI, "
        "либо сразу описать запрос текстом — минимум класс, предмет и тема.",
        reply_markup=quest_entry_keyboard(),
    )


@router.message(QuestStates.waiting_for_answer, F.text)
async def check_quest_answer(message: Message, state: FSMContext):
    user_answer = (message.text or "").strip()
    user_id = message.from_user.id
    data = await state.get_data()
    task_id = data.get("active_task_id")
    question_text = data.get("question_text") or ""
    correct_answer = data.get("correct_answer") or ""
    quest_items = data.get("quest_items") or []
    quest_index = int(data.get("quest_index") or 0)
    quest_answers = list(data.get("quest_answers") or [])

    status_msg = await message.answer("🔍 ИИ проверяет твой ответ…")
    try:
        from api.schemas.tasks import OpenAITaskVerification

        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT parent_id, assignment_source, subject, topic, topic_context
                FROM tasks_history WHERE task_id=$1 AND student_id=$2
                """,
                task_id, user_id,
            )
            if not row:
                await status_msg.edit_text("⚠️ Активное задание не найдено.")
                await state.clear()
                return
            source = normalize_assignment_source(row.get("assignment_source"), row.get("parent_id"))
            parent_id = row.get("parent_id") if source == TEACHER else None
            raw_topic_context = row.get("topic_context") if hasattr(row, "get") else row["topic_context"]
            topic_context = (
                json.loads(raw_topic_context)
                if isinstance(raw_topic_context, str)
                else (raw_topic_context or {})
            )

            if source == TEACHER:
                answer_data = {
                    "provided_answer": user_answer,
                    "review_status": "pending_review",
                }
                async with conn.transaction():
                    attempt_number = int(await conn.fetchval(
                        "SELECT COALESCE(MAX(attempt_number),0)+1 FROM task_submissions WHERE task_id=$1 AND student_id=$2",
                        task_id, user_id,
                    ) or 1)
                    await conn.execute(
                        """
                        INSERT INTO task_submissions (task_id, student_id, answer_text, attempt_number, status)
                        VALUES ($1,$2,$3,$4,'pending_review')
                        """,
                        task_id, user_id, user_answer, attempt_number,
                    )
                    updated = await conn.fetchval(
                        """
                        UPDATE tasks_history
                        SET student_answers_json=$1::jsonb, status='pending_review'::task_status,
                            updated_at=CURRENT_TIMESTAMP
                        WHERE task_id=$2 AND student_id=$3 AND status IN ('created','in_progress')
                        RETURNING task_id
                        """,
                        json.dumps(answer_data, ensure_ascii=False), task_id, user_id,
                    )
                    if not updated:
                        await status_msg.edit_text("⚠️ Задание уже было отправлено на проверку.")
                        await state.clear()
                        return

                await status_msg.delete()
                await answer_plain(message, "✅ Ответ отправлен Учителю и ожидает ручной проверки.")
                if parent_id:
                    try:
                        await send_plain_to_chat(
                            message.bot,
                            parent_id,
                            "📝 Ученик отправил ответ на назначенное задание. "
                            "Откройте историю заданий в EduAI для ручной проверки.",
                        )
                    except Exception:
                        logger.warning("Не удалось уведомить Учителя о новом ответе", exc_info=True)
                await state.clear()
                return

            grading_context = await build_context_from_metadata(
                conn,
                str(topic_context.get("topic") or row.get("topic") or question_text or "answer checking"),
                topic_context,
            )

        response = await parse_chat_completion(openai_client,
            messages=[
                {"role": "system", "content": task_grading_prompt()},
                {
                    "role": "user",
                    "content": (
                        f"Assignment source: {source}.\n"
                        f"Task Question: {question_text}\n"
                        f"Reference Answer: {correct_answer}\n"
                        f"Student's Answer: {user_answer}\n\n"
                        f"PRIMARY EDUCATIONAL CONTEXT:\n"
                        f"{grading_context.primary.content if grading_context.primary else 'none'}\n\n"
                        f"RANKED EDUAI SUPPLEMENTS:\n{grading_context.database_context or 'none'}"
                    ),
                },
            ],
            response_format=OpenAITaskVerification,
        )
        verification = response.choices[0].message.parsed
        await status_msg.delete()

        attempt = {
            "item_id": (
                quest_items[quest_index].get("id")
                if quest_items and quest_index < len(quest_items)
                else f"q{quest_index + 1}"
            ),
            "question_text": question_text,
            "provided_answer": user_answer,
            "verification_feedback": verification.explanation,
            "is_correct": verification.is_correct,
        }
        quest_answers.append(attempt)
        student_answers_json = {
            "provided_answer": user_answer,
            "verification_feedback": verification.explanation,
            "is_correct": verification.is_correct,
            "current_index": quest_index,
            "answers": quest_answers,
        }

        if verification.is_correct:
            next_index = quest_index + 1
            if quest_items and next_index < len(quest_items):
                next_item = quest_items[next_index]
                student_answers_json["current_index"] = next_index
                async with db.pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE tasks_history SET student_answers_json=$1::jsonb, updated_at=CURRENT_TIMESTAMP WHERE task_id=$2",
                        json.dumps(student_answers_json, ensure_ascii=False), task_id,
                    )
                await state.update_data(
                    quest_index=next_index,
                    quest_answers=quest_answers,
                    question_text=next_item.get("question_text") or "",
                    correct_answer=next_item.get("reference_answer") or "",
                )
                await answer_plain(
                    message,
                    f"✅ Верно! {verification.explanation}\n\n"
                    f"❓ Вопрос {next_index + 1} из {len(quest_items)}\n\n"
                    f"{next_item.get('question_text', '')}\n\n"
                    "Напиши следующий ответ (или /cancel для отмены).",
                )
                return

            question_count = max(1, len(quest_items) or 1)
            total_attempts = max(question_count, len(quest_answers))
            quality = min(1.0, question_count / total_attempts)
            final_status = "evaluated" if source == TEACHER else "completed"
            student_answers_json["completed_items"] = question_count
            student_answers_json["quality_score"] = quality

            async with db.pool.acquire() as conn:
                async with conn.transaction():
                    attempt_number = int(await conn.fetchval(
                        "SELECT COALESCE(MAX(attempt_number),0)+1 FROM task_submissions WHERE task_id=$1 AND student_id=$2",
                        task_id, user_id,
                    ) or 1)
                    update_result = await conn.execute(
                        """
                        UPDATE tasks_history
                        SET student_answers_json=$1::jsonb, score=$2, status=$3::task_status,
                            completed_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
                        WHERE task_id=$4 AND student_id=$5 AND status IN ('created','in_progress')
                        """,
                        json.dumps(student_answers_json, ensure_ascii=False),
                        round(quality * 100), final_status, task_id, user_id,
                    )
                    if str(update_result).strip().upper() == "UPDATE 0":
                        await answer_plain(message, "Этот квест уже был завершён.")
                        await state.clear()
                        return
                    await conn.execute(
                        """
                        INSERT INTO task_submissions (
                            task_id, student_id, answer_text, attempt_number, ai_feedback, score, status, reviewed_at
                        ) VALUES ($1,$2,$3,$4,$5,$6,$7,CURRENT_TIMESTAMP)
                        """,
                        task_id, user_id, user_answer, attempt_number, verification.explanation,
                        100, "completed",
                    )

            completion = f"\n🏁 Квест-тест завершён: {question_count} из {question_count} вопросов."
            await answer_plain(
                message,
                f"🎉 Верно! {verification.explanation}{completion}",
            )
            # Only explicit Teacher assignments are reported to the Teacher.
            if source == TEACHER and parent_id:
                try:
                    await send_plain_to_chat(
                        message.bot,
                        parent_id,
                        "📈 Ваш Ученик завершил назначенное вами задание.\n"
                        f"Результат: {round(quality * 100)}%\n"
                        f"Последний ответ: {user_answer}\n"
                        f"Разбор ИИ: {verification.explanation}",
                    )
                except Exception:
                    pass
            await state.clear()
            return

        await state.update_data(quest_answers=quest_answers)
        async with db.pool.acquire() as conn:
            attempt_number = int(await conn.fetchval(
                "SELECT COALESCE(MAX(attempt_number),0)+1 FROM task_submissions WHERE task_id=$1 AND student_id=$2",
                task_id, user_id,
            ) or 1)
            await conn.execute(
                """
                INSERT INTO task_submissions (
                    task_id, student_id, answer_text, attempt_number, ai_feedback, score, status, reviewed_at
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,CURRENT_TIMESTAMP)
                """,
                task_id, user_id, user_answer, attempt_number, verification.explanation,
                0, "needs_revision",
            )
            await conn.execute(
                "UPDATE tasks_history SET student_answers_json=$1::jsonb, updated_at=CURRENT_TIMESTAMP WHERE task_id=$2",
                json.dumps(student_answers_json, ensure_ascii=False), task_id,
            )
        progress = f"\nВопрос {quest_index + 1} из {len(quest_items)} остаётся активным." if quest_items else ""
        await answer_plain(
            message,
            f"❌ Не совсем так…\n{verification.explanation}{progress}\n\n"
            "Попробуй ещё раз.",
        )

    except Exception as exc:
        logger.exception("Ошибка верификации ответа в боте: %s", exc)
        try:
            await status_msg.edit_text("⚠️ Ошибка проверки. Попробуй отправить ответ ещё раз.")
        except Exception:
            pass
