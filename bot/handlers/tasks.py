import json
import asyncio
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from database import db
from openai import AsyncOpenAI
from config import settings
from logger_config import logger
from bot.messages import answer_plain

router = Router()

openai_client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())


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
                   parent_id, parent_comment
            FROM tasks_history
            WHERE student_id = $1 AND parent_id IS NOT NULL AND status = 'created'::task_status
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
                f"\n\n💬 Комментарий от родителя:\n{parent_comment}"
                if parent_comment else ""
            )
            async with db.pool.acquire() as conn:
                await conn.execute("UPDATE tasks_history SET status = 'in_progress'::task_status WHERE task_id = $1", parent_task["task_id"])
            await state.update_data(
                active_task_id=parent_task["task_id"],
                question_text=quest.get("question_text"),
                correct_answer=quest.get("reference_answer"),
                parent_id=parent_task["parent_id"]
            )
            await state.set_state(QuestStates.waiting_for_answer)

            await status_msg.delete()
            await answer_plain(
                message,
                f"👨‍👩‍👦 Персональное задание от родителя!\n"
                f"🏆 Квест: {quest.get('title')}\n\n"
                f"{quest.get('question_text')}"
                f"{parent_comment_block}"
                f"{history_feedback}\n\n"
                "💰 Награда: 15 монет | ✨ 50 XP\n\n"
                "Напиши ответ в чат (или введи /cancel для отмены)."
            )
            return
        except Exception as e:
            logger.error(f"Ошибка парсинга родительского теста: {e}")
    async with db.pool.acquire() as conn:
        page = await conn.fetchrow(
            """
            SELECT p.page_id, p.page_markdown, p.page_title, b.book_title, b.book_program
            FROM page p
            JOIN book b ON p.book_id = b.book_id
            ORDER BY RANDOM()
            LIMIT 1
            """
        )

    if not page:
        await status_msg.edit_text("❌ База знаний пуста. Попроси администратора загрузить учебники!")
        return
    try:
        from api.routers.tasks import OpenAITaskGeneration

        response = await openai_client.beta.chat.completions.parse(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert school mathematics tutor on the EduAI platform. "
                        "Based on the provided textbook page context, generate exactly ONE engaging exercise or practical question to test the student's understanding.\n\n"
                        "CRITICAL FORMATTING RULES:\n"
                        "1. NEVER use LaTeX service symbols such as '$', '$$', '\\(', or '\\)'.\n"
                        "2. Format all mathematical notations using beautiful, human-readable Unicode characters: "
                        "use superscripts for powers (e.g., x², y³), '•' or 'x' for multiplication, '°' for degrees (e.g., 90°, 180°).\n"
                        "3. Ensure the 'correct_answer' field contains a concise, unambiguous baseline answer for automated verification.\n"
                        "4. Write the final 'title' and 'description' in Russian, as they will be displayed directly to the child."
                    )
                },
                {
                    "role": "user",
                    "content": f"Textbook: {page['book_title']} ({page['book_program']})\nPage Content Context:\n{page['page_markdown']}"
                }
            ],
            response_format=OpenAITaskGeneration
        )

        ai_task = response.choices[0].message.parsed

        topic_context = {
            "page_id": page["page_id"],
            "book_title": page["book_title"],
            "page_title": page["page_title"],
            "subject": page["book_program"]
        }

        questions_json = {
            "title": ai_task.title,
            "question_text": ai_task.description,
            "reference_answer": ai_task.correct_answer
        }
        async with db.pool.acquire() as conn:
            task_id = await conn.fetchval(
                """
                INSERT INTO tasks_history (student_id, parent_id, topic_context, questions_json, score, status)
                VALUES ($1, $2, $3, $4, $5, 'in_progress'::task_status)
                RETURNING task_id
                """,
                user_id, student["parent_id"], json.dumps(topic_context), json.dumps(questions_json), 0
            )
        await state.update_data(
            active_task_id=task_id,
            question_text=ai_task.description,
            correct_answer=ai_task.correct_answer,
            parent_id=None
        )
        await state.set_state(QuestStates.waiting_for_answer)

        await status_msg.delete()
        await answer_plain(
            message,
            f"🏆 Квест: {ai_task.title}\n\n"
            f"{ai_task.description}\n\n"
            "💰 Награда: 10 монет | ✨ 30 XP\n\n"
            "Напиши ответ в чат (или введи /cancel для отмены)."
        )
    except Exception as e:
        logger.error(f"Ошибка генерации квеста в боте: {e}")
        await status_msg.edit_text("❌ Произошла ошибка при создании задания ИИ. Попробуй еще раз: /quest")


@router.message(QuestStates.waiting_for_answer)
async def check_quest_answer(message: Message, state: FSMContext):
    user_answer = message.text.strip()
    user_id = message.from_user.id

    data = await state.get_data()
    task_id = data.get("active_task_id")
    question_text = data.get("question_text")
    correct_answer = data.get("correct_answer")
    parent_id = data.get("parent_id")

    status_msg = await message.answer("🔍 *Учитель проверяет твой ответ...* ⏳", parse_mode="Markdown")
    try:
        from api.routers.tasks import OpenAITaskVerification

        response = await openai_client.beta.chat.completions.parse(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a supportive and encouraging school mathematics teacher grading a student's answer. "
                        "Compare the student's answer with the provided reference answer.\n\n"
                        "GRADING RULES:\n"
                        "1. If the student's answer matches the reference answer in meaning or is mathematically equivalent "
                        "(e.g., '0.5' and '1/2', '5' and '5 cm'), set 'is_correct' to True. Otherwise, set it to False.\n"
                        "2. Provide a friendly, polite, and constructive explanation ('explanation') in Russian tailored for a child.\n"
                        "3. Do not use any LaTeX symbols ('$') in your explanation. Use clean text and Unicode characters if necessary."
                    )
                },
                {
                    "role": "user",
                    "content": f"Task Question: {question_text}\nReference Answer: {correct_answer}\nStudent's Answer: {user_answer}"
                }
            ],
            response_format=OpenAITaskVerification
        )
        verification = response.choices[0].message.parsed
        await status_msg.delete()
        student_answers_json = {
            "provided_answer": user_answer,
            "verification_feedback": verification.explanation,
            "is_correct": verification.is_correct
        }

        coins_reward = 15 if parent_id else 10
        xp_reward = 50 if parent_id else 30
        if verification.is_correct:
            async with db.pool.acquire() as conn:
                async with conn.transaction():
                    current_stats = await conn.fetchrow(
                        "SELECT balance_coins, xp_total FROM gamification WHERE user_id = $1",
                        user_id
                    )

                    coins = current_stats["balance_coins"] if current_stats else 0
                    xp = current_stats["xp_total"] if current_stats else 0

                    new_coins = coins + coins_reward
                    new_xp = xp + xp_reward
                    await conn.execute(
                        """
                        UPDATE tasks_history
                        SET student_answers_json = $1, score = $2, status = 'completed'::task_status
                        WHERE task_id = $3
                        """,
                        json.dumps(student_answers_json), xp_reward, task_id
                    )

                    await conn.execute(
                        """
                        INSERT INTO gamification (user_id, balance_coins, xp_total, streak_days)
                        VALUES ($1, $2, $3, 1)
                        ON CONFLICT (user_id) DO UPDATE SET balance_coins = $2, xp_total = $3
                        """,
                        user_id, new_coins, new_xp
                    )
            await answer_plain(
                message,
                f"🎉 Верно! {verification.explanation}\n\n"
                f"💰 Начислено: +{coins_reward} монет и +{xp_reward} XP.\n"
                "Проверить баланс можно в меню «🏆 Мой профиль»."
            )
            if parent_id:
                try:
                    await message.bot.send_message(
                        chat_id=parent_id,
                        text=f"📈 *Ваш ребенок успешно выполнил домашнее задание!*\nОтвет ребенка: _'{user_answer}'_\nРазбор ИИ: {verification.explanation}"
                    )
                except Exception:
                    pass

            await state.clear()
        else:
            async with db.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE tasks_history SET student_answers_json = $1 WHERE task_id = $2",
                    json.dumps(student_answers_json), task_id
                )
            await answer_plain(
                message,
                f"❌ Не совсем так...\n{verification.explanation}\n\n"
                "Попробуй ещё раз! Или введи /cancel, чтобы прервать квест."
            )

    except Exception as e:
        logger.error(f"Ошибка верификации ответа в боте: {e}")
        await status_msg.edit_text("⚠️ Ошибка проверки. Попробуй отправить ответ еще раз.")
