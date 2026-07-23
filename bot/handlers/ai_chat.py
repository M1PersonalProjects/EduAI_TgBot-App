from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from database import db
from openai import AsyncOpenAI
from config import settings
from logger_config import logger

router = Router()
openai_client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())

@router.message(F.text, F.state == None)
async def quick_ai_chat_fallback(message: Message):
    user_id = message.from_user.id
    user_text = message.text.strip()
    
    # Игнорируем системные команды, если они проскочили мимо других роутеров
    if user_text.startswith("/"):
        return

    async with db.pool.acquire() as conn:
        user = await conn.fetchrow("SELECT role FROM users WHERE tg_id = $1", user_id)
        if not user or user["role"] != "student":
            return  # Чат предназначен для учеников

    status_msg = await message.answer("🧠 *ИИ-Тьютор думает...* ⏳", parse_mode="Markdown")

    try:
        async with db.pool.acquire() as conn:
            # 1. Сохраняем сообщение пользователя в общую базу
            await conn.execute(
                "INSERT INTO chat_messages (user_id, sender, message_text) VALUES ($1, 'user', $2)",
                user_id, user_text
            )
            
            # 2. Достаем последние 6 сообщений для соблюдения контекста
            history_records = await conn.fetch(
                """
                SELECT sender, message_text FROM chat_messages 
                WHERE user_id = $1 
                ORDER BY created_at DESC LIMIT 6
                """,
                user_id
            )
        
        # Разворачиваем историю в хронологический порядок
        messages = [
            {
                "role": "system", 
                "content": (
                    "You are a friendly and encouraging AI math tutor on the EduAI platform. "
                    "Answer the student's brief questions accurately, briefly and politely in Russian.\n"
                    "STRICT RULES:\n"
                    "1. NEVER use LaTeX service symbols like '$', '$$', '\\(', '\\)'.\n"
                    "2. Use clean text and Unicode notation: powers as x², multiplication as •, degrees as °.\n"
                    "3. Keep the response text short and plain so it reads well in a chat bubble."
                )
            }
        ]
        
        for r in reversed(history_records):
            role = "user" if r["sender"] == "user" else "assistant"
            messages.append({"role": role, "content": r["message_text"]})

        # 3. Запрос в OpenAI
        response = await openai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.4
        )
        ai_reply = response.choices[0].message.content

        # 4. Сохраняем ответ ИИ в базу чата
        async with db.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO chat_messages (user_id, sender, message_text) VALUES ($1, 'ai', $2)",
                user_id, ai_reply
            )

        await status_msg.delete()
        await message.answer(ai_reply)

    except Exception as e:
        logger.error(f"Ошибка быстрого ИИ-чата в боте: {e}")
        await status_msg.edit_text("❌ Не удалось связаться с ИИ-тьютором. Попробуй позже.")