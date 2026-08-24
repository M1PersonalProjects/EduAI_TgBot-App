import json
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from database import db
from logger_config import logger
from services.ai import create_chat_completion, openai_client
from config import settings
from bot.messages import answer_plain
from services.tutor_policy import teacher_analytics_prompt

router = Router()

class ParentStates(StatesGroup):
    waiting_for_analytics_question = State()


# 1. ИИ-АНАЛИТИКА УСПЕВАЕМОСТИ ДЛЯ УЧИТЕЛЯ

@router.message(F.text == "📊 Аналитика Ученика (ИИ)")
async def ask_ai_parent_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    async with db.pool.acquire() as conn:
        user = await conn.fetchrow("SELECT role FROM users WHERE tg_id = $1", user_id)
        child = await conn.fetchrow("SELECT tg_id FROM users WHERE parent_id = $1 AND role = 'student' LIMIT 1", user_id)
    
    if not user or user["role"] not in ["parent", "admin"]:
        await message.answer("Эта функция доступна только для пользователей с ролью Учитель.")
        return

    if not child:
        await message.answer("❌ У вас еще нет привязанных аккаунтов Учеников. Аналитика недоступна.")
        return

    await state.set_state(ParentStates.waiting_for_analytics_question)
    await message.answer(
        "🤖 *ИИ-консультант для Учителя*\n\n"
        "Я проанализирую все квесты, которые решал ваш Ученик, его ответы и ошибки.\n"
        "Задайте любой интересующий вас вопрос (например: _«В каких темах мой Ученик чаще всего ошибается?»_).\n"
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
    status_msg = await message.answer("🔍 *ИИ изучает историю выполненных заданий и строит отчет...* ⏳", parse_mode="Markdown")

    try:
        async with db.pool.acquire() as conn:
            child = await conn.fetchrow("SELECT tg_id FROM users WHERE parent_id = $1 AND role = 'student' LIMIT 1", parent_id)
            if not child:
                await status_msg.edit_text("Ошибка: Ученик не найден.")
                await state.clear()
                return
            
            history = await conn.fetch(
                """
                SELECT topic_context, questions_json, student_answers_json, score, status 
                FROM tasks_history
                WHERE student_id = $1 AND assignment_source = 'teacher'
                ORDER BY created_at DESC LIMIT 20
                """,
                child["tg_id"]
            )

        history_summary = []
        for row in history:
            topic = json.loads(row["topic_context"]) if isinstance(row["topic_context"], str) else row["topic_context"]
            quest = json.loads(row["questions_json"]) if isinstance(row["questions_json"], str) else row["questions_json"]
            ans = json.loads(row["student_answers_json"]) if row["student_answers_json"] and isinstance(row["student_answers_json"], str) else row["student_answers_json"]
            
            status_str = "Выполнено успешно" if row["status"] in {"completed", "evaluated"} else "В процессе / Ошибка"
            ans_feedback = ans.get("verification_feedback", "Нет ответа") if ans else "Нет ответа"
            
            history_summary.append(
                f"- Предмет: {topic.get('subject')}, Тема: {quest.get('title')}\n"
                f"  Статус: {status_str}, Оценка: {row['score']}\n"
                f"  Фидбек ИИ: {ans_feedback}"
            )

        context_str = "\n".join(history_summary) if history_summary else "История заданий пока пуста."

        response = await create_chat_completion(openai_client,
            messages=[
                {
                    "role": "system",
                    "content": (
                        teacher_analytics_prompt()                    )
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
        logger.error(f"Ошибка ИИ-аналитики для Учителя: {e}")
        await status_msg.edit_text("❌ Не удалось построить отчет аналитики. Попробуйте позже.")
    
    await state.clear()


# 2. ИИ-ГЕНЕРАЦИЯ ТЕСТОВ РОДИТЕЛЕМ ДЛЯ УЧЕНИКОВ
# 2. УСТАРЕВШАЯ ТОЧКА СОЗДАНИЯ ЗАДАНИЯ В TELEGRAM

@router.message(F.text == "📝 Создать ИИ-тест для Ученика")
async def parent_create_test_start(message: Message, state: FSMContext):
    """Перенаправляет старую кнопку в WebApp, не создавая параллельный workflow."""
    await state.clear()
    async with db.pool.acquire() as conn:
        user = await conn.fetchrow("SELECT role FROM users WHERE tg_id = $1", message.from_user.id)
    if not user or user["role"] not in ["parent", "admin"]:
        await message.answer("Эта функция доступна только Учителям.")
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="🌐 Открыть EduAI",
            web_app=WebAppInfo(url=settings.webapp_base_url),
        )
    ]])
    await message.answer(
        "Создание обычных заданий перенесено в WebApp. "
        "Создайте черновик на странице «Ученики» или прямо из ответа ИИ-тьютора, "
        "проверьте его и только затем отправьте Ученику.",
        reply_markup=keyboard,
    )
