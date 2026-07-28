import json
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from database import db
from openai import AsyncOpenAI
from config import settings
from logger_config import logger
from pydantic import BaseModel
from bot.messages import answer_plain

router = Router()
openai_client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())

class ParentStates(StatesGroup):
    waiting_for_analytics_question = State()
    waiting_for_test_topic = State()
    moderating_test = State()
    editing_test = State()

# Схема для Structured Outputs от OpenAI при генерации родительского теста
class ParentTestGeneration(BaseModel):
    title: str
    description: str
    correct_answer: str


# 1. ИИ-АНАЛИТИКА УСПЕВАЕМОСТИ ДЛЯ РОДИТЕЛЯ

@router.message(F.text == "📊 Аналитика ребенка (ИИ)")
async def ask_ai_parent_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    async with db.pool.acquire() as conn:
        user = await conn.fetchrow("SELECT role FROM users WHERE tg_id = $1", user_id)
        child = await conn.fetchrow("SELECT tg_id FROM users WHERE parent_id = $1 AND role = 'student' LIMIT 1", user_id)
    
    if not user or user["role"] not in ["parent", "admin"]:
        await message.answer("Эта функция доступна только для пользователей с ролью Родитель.")
        return

    if not child:
        await message.answer("❌ У вас еще нет привязанных аккаунтов детей. Аналитика недоступна.")
        return

    await state.set_state(ParentStates.waiting_for_analytics_question)
    await message.answer(
        "🤖 *ИИ-Консультант для родителей*\n\n"
        "Я проанализирую все квесты, которые решал ваш ребенок, его ответы и ошибки.\n"
        "Задайте любой интересующий вас вопрос (например: _«В каких темах мой ребенок чаще всего ошибается?»_).\n"
        "Напишите **Отмена** в чате для выхода.",
        parse_mode="Markdown"
    )


@router.message(ParentStates.waiting_for_analytics_question)
async def process_parent_analytics_query(message: Message, state: FSMContext):
    if message.text.lower() == "отмена":
        await state.clear()
        await message.answer("Выход из режима аналитики.")
        return

    parent_id = message.from_user.id
    parent_query = message.text.strip()
    status_msg = await message.answer("🔍 *ИИ изучает историю выполненных квестов и строит отчет...* ⏳", parse_mode="Markdown")

    try:
        async with db.pool.acquire() as conn:
            child = await conn.fetchrow("SELECT tg_id FROM users WHERE parent_id = $1 AND role = 'student' LIMIT 1", parent_id)
            if not child:
                await status_msg.edit_text("Ошибка: Ребенок не найден.")
                await state.clear()
                return
            
            history = await conn.fetch(
                """
                SELECT topic_context, questions_json, student_answers_json, score, status 
                FROM tasks_history 
                WHERE student_id = $1
                ORDER BY created_at DESC LIMIT 20
                """,
                child["tg_id"]
            )

        history_summary = []
        for row in history:
            topic = json.loads(row["topic_context"]) if isinstance(row["topic_context"], str) else row["topic_context"]
            quest = json.loads(row["questions_json"]) if isinstance(row["questions_json"], str) else row["questions_json"]
            ans = json.loads(row["student_answers_json"]) if row["student_answers_json"] and isinstance(row["student_answers_json"], str) else row["student_answers_json"]
            
            status_str = "Выполнено успешно" if row["status"] == "completed" else "В процессе / Ошибка"
            ans_feedback = ans.get("verification_feedback", "Нет ответа") if ans else "Нет ответа"
            
            history_summary.append(
                f"- Предмет: {topic.get('subject')}, Тема: {quest.get('title')}\n"
                f"  Статус: {status_str}, Оценка/XP: {row['score']}\n"
                f"  Фидбек ИИ: {ans_feedback}"
            )

        context_str = "\n".join(history_summary) if history_summary else "История заданий пока пуста."

        response = await openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert educational data analyst and psychologist helper for parents. "
                        "Based on the provided student's task history, answer the parent's question politely and constructively in Russian.\n"
                        "Focus on highlighting strengths and providing advice on topics that need improvement. Do not use LaTeX."
                    )
                },
                {
                    "role": "user",
                    "content": f"Parent's Question: {parent_query}\n\nStudent's Progress History:\n{context_str}"
                }
            ]
        )

        await status_msg.delete()
        await answer_plain(message, response.choices[0].message.content)
    
    except Exception as e:
        logger.error(f"Ошибка ИИ-аналитики для родителя: {e}")
        await status_msg.edit_text("❌ Не удалось построить отчет аналитики. Попробуйте позже.")
    
    await state.clear()


# 2. ИИ-ГЕНЕРАЦИЯ ТЕСТОВ РОДИТЕЛЕМ ДЛЯ ДЕТЕЙ

@router.message(F.text == "📝 Создать ИИ-тест для ребенка")
async def parent_create_test_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    async with db.pool.acquire() as conn:
        user = await conn.fetchrow("SELECT role FROM users WHERE tg_id = $1", user_id)
        child = await conn.fetchrow("SELECT tg_id FROM users WHERE parent_id = $1 AND role = 'student' LIMIT 1", user_id)
        
    if not user or user["role"] not in ["parent", "admin"]:
        await message.answer("Эта функция доступна только Родителям.")
        return

    if not child:
        await message.answer("❌ У вас еще нет привязанных аккаунтов детей. Направьте ребенку ссылку для регистрации!")
        return

    await state.set_state(ParentStates.waiting_for_test_topic)
    await message.answer(
        "📝 *Конструктор домашних ИИ-заданий*\n\n"
        "Напишите тему, по которой вы хотите устроить проверку знаний своему ребенку (например: _«Умножение дробей»_ или _«Теорема Пифагора»_):\n"
        "Или напишите **Отмена** для выхода.",
        parse_mode="Markdown"
    )


@router.message(ParentStates.waiting_for_test_topic)
async def process_custom_test_generation(message: Message, state: FSMContext):
    if message.text.lower() == "отмена":
        await state.clear()
        await message.answer("Генерация отменена.")
        return

    parent_id = message.from_user.id
    topic_query = message.text.strip()
    status_msg = await message.answer("🎲 *ИИ сканирует библиотеку учебников и собирает проверочный тест...* ⏳", parse_mode="Markdown")

    async with db.pool.acquire() as conn:
        page = await conn.fetchrow(
            """
            SELECT p.page_id, p.page_markdown, p.page_title, b.book_title, b.book_program,
                   (SELECT tg_id FROM users WHERE parent_id = $1 AND role = 'student' LIMIT 1) as student_id
            FROM page p
            JOIN book b ON p.book_id = b.book_id
            WHERE p.page_markdown ILIKE $2 OR p.page_title ILIKE $2
            ORDER BY RANDOM()
            LIMIT 1
            """,
            parent_id, f"%{topic_query}%"
        )
        
        if not page:
            page = await conn.fetchrow(
                """
                SELECT p.page_id, p.page_markdown, p.page_title, b.book_title, b.book_program,
                       (SELECT tg_id FROM users WHERE parent_id = $1 AND role = 'student' LIMIT 1) as student_id
                FROM page p
                JOIN book b ON p.book_id = b.book_id
                ORDER BY RANDOM()
                LIMIT 1
                """,
                parent_id
            )

    if not page or not page["student_id"]:
        await status_msg.edit_text("❌ Не удалось найти учебные материалы или аккаунт ребенка.")
        await state.clear()
        return

    try:
        response = await openai_client.beta.chat.completions.parse(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert school textbook content developer for the EduAI application. "
                        "Create a deep-knowledge control mini-test or practical complex homework task tailored to the specific topic requested by the parent.\n\n"
                        "CRITICAL CRITERIA:\n"
                        "1. Strictly NO LaTeX elements or raw code signs ($ or $$).\n"
                        "2. Use pretty Unicode (e.g., √x, x², ½).\n"
                        "3. Make descriptions and text clearly understandable for a student. Write everything in Russian."
                    )
                },
                {
                    "role": "user",
                    "content": f"Requested Topic: {topic_query}\nTextbook Ref: {page['book_title']}\nContent context:\n{page['page_markdown']}"
                }
            ],
            response_format=ParentTestGeneration
        )

        ai_test = response.choices[0].message.parsed
        
        # Временно сохраняем параметры генерации в контекст FSM для модерации
        await state.update_data(
            generated_title=ai_test.title,
            generated_description=ai_test.description,
            generated_answer=ai_test.correct_answer,
            student_id=page["student_id"],
            page_id=page["page_id"],
            book_title=page["book_title"],
            book_program=page["book_program"],
            topic_query=topic_query
        )

        await status_msg.delete()
        await state.set_state(ParentStates.moderating_test)
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Отправить ребенку", callback_data="parent_approve_test"),
                InlineKeyboardButton(text="✏️ Редактировать текст", callback_data="parent_edit_test")
            ],
            [InlineKeyboardButton(text="❌ Отклонить и сбросить", callback_data="parent_reject_test")]
        ])

        await answer_plain(
            message,
            "🔍 Предпросмотр созданного ИИ-теста:\n\n"
            f"📋 Название: {ai_test.title}\n"
            f"📝 Задание: {ai_test.description}\n"
            f"🔑 Правильный ответ: {ai_test.correct_answer}\n\n"
            "Вы можете отредактировать текст задания или отправить его ребёнку:",
            reply_markup=kb,
        )

    except Exception as e:
        logger.error(f"Ошибка создания родительского теста: {e}")
        await status_msg.edit_text("❌ Не удалось сгенерировать тест. Попробуйте изменить формулировку темы.")
        await state.clear()


@router.callback_query(ParentStates.moderating_test, F.data == "parent_edit_test")
async def callback_parent_edit_request(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(ParentStates.editing_test)
    await call.message.answer("📝 Введите новый измененный текст задания. Название теста и эталонный ответ останутся прежними:")


@router.message(ParentStates.editing_test)
async def process_parent_edited_text(message: Message, state: FSMContext):
    new_desc = message.text.strip()
    await state.update_data(generated_description=new_desc)
    data = await state.get_data()
    
    await state.set_state(ParentStates.moderating_test)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Отправить ребенку", callback_data="parent_approve_test"),
            InlineKeyboardButton(text="✏️ Редактировать текст", callback_data="parent_edit_test")
        ],
        [InlineKeyboardButton(text="❌ Отклонить и сбросить", callback_data="parent_reject_test")]
    ])

    await answer_plain(
        message,
        "🔍 Обновлённый предпросмотр теста:\n\n"
        f"📋 Название: {data.get('generated_title')}\n"
        f"📝 Задание: {new_desc}\n"
        f"🔑 Правильный ответ: {data.get('generated_answer')}\n\n"
        "Всё верно? Отправляем?",
        reply_markup=kb,
    )


@router.callback_query(ParentStates.moderating_test, F.data == "parent_approve_test")
async def callback_approve_and_save(call: CallbackQuery, state: FSMContext):
    parent_id = call.from_user.id
    data = await state.get_data()
    
    student_id = data.get("student_id")
    
    topic_context = {
        "page_id": data.get("page_id"),
        "book_title": data.get("book_title"),
        "page_title": f"Домашнее задание: {data.get('topic_query')}",
        "subject": data.get("book_program")
    }
    
    questions_json = {
        "title": data.get("generated_title"),
        "question_text": data.get("generated_description"),
        "reference_answer": data.get("generated_answer")
    }

    try:
        async with db.pool.acquire() as conn:
            task_id = await conn.fetchval(
                """
                INSERT INTO tasks_history (student_id, parent_id, topic_context, questions_json, score, status)
                VALUES ($1, $2, $3, $4, 0, 'created'::task_status)
                RETURNING task_id
                """,
                student_id, parent_id, json.dumps(topic_context), json.dumps(questions_json)
            )

        await call.bot.send_message(
            chat_id=student_id,
            text="📬 Родитель прислал тебе персональное проверочное задание!\n\n"
                 f"🏆 Тест: {questions_json['title']}\n"
                 f"{questions_json['question_text']}\n\n"
                 "💰 Награда за выполнение: 15 монет | ✨ 50 XP\n"
                 "Просто начни выполнять квесты через меню — этот тест будет приоритетным!",
            parse_mode=None,
        )
        
        await call.message.edit_text("🚀 Тест успешно сохранен в базу и доставлен в Telegram-аккаунт вашего ребенка! Как только он даст ответ, система его проверит.", reply_markup=None)
        await call.answer("Успешно отправлено!")
    except Exception as e:
        logger.error(f"Не удалось доставить тест ученику {student_id}: {e}")
        await call.message.edit_text("⚠️ Тест сохранен в базу данных, но не удалось отправить личное уведомление ребенку (возможно, бот заблокирован).", reply_markup=None)
        await call.answer()
        
    await state.clear()


@router.callback_query(F.data == "parent_reject_test")
async def callback_reject_test(call: CallbackQuery, state: FSMContext):
    await call.answer("Тест отклонен")
    await call.message.edit_text("❌ Создание теста отменено. Вы можете начать заново в любой момент.", reply_markup=None)
    await state.clear()
