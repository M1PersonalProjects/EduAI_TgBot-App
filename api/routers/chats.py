from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import List
from database import db
from openai import AsyncOpenAI
from config import settings
from logger_config import logger

router = APIRouter(prefix="/api/chats", tags=["Web App AI Chat"])
tutor_router = APIRouter(prefix="/api/tutor/chats", tags=["Web App AI Chat (Alias)"])
openai_client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())

class MessageSchema(BaseModel):
    sender: str = Field(..., description="'user' или 'ai'")
    message_text: str

class SendMessageRequest(BaseModel):
    tg_id: int
    message_text: str

@router.get("/history/{tg_id}", response_model=List[MessageSchema])
async def get_chat_history(tg_id: int):
    """Возвращает историю переписки для отображения в Web App"""
    async with db.pool.acquire() as conn:
        records = await conn.fetch(
            "SELECT sender, message_text FROM chat_messages WHERE user_id = $1 ORDER BY created_at ASC",
            tg_id
        )
    return [MessageSchema(sender=r["sender"], message_text=r["message_text"]) for r in records]


@router.post("/send", response_model=MessageSchema)
async def send_message_from_webapp(payload: SendMessageRequest):
    """Принимает сообщение из Web App, генерирует ответ ИИ с учетом контекста и возвращает его"""
    try:
        async with db.pool.acquire() as conn:
            # Сохраняем реплику пользователя
            await conn.execute(
                "INSERT INTO chat_messages (user_id, sender, message_text) VALUES ($1, 'user', $2)",
                payload.tg_id, payload.message_text
            )
            
            # Получаем контекст для OpenAI
            history_records = await conn.fetch(
                "SELECT sender, message_text FROM chat_messages WHERE user_id = $1 ORDER BY created_at DESC LIMIT 10",
                payload.tg_id
            )
            logger.info(f"📨 Получено сообщение от пользователя {payload.tg_id}")

        messages = [
            {
                "role": "system", 
                "content": (
                    "You are an encouraging AI math tutor on the EduAI web application. "
                    "Explain concepts beautifully using clear text or Markdown formatting.\n"
                    "STRICT RULES:\n"
                    "1. NEVER use LaTeX ('$', '$$').\n"
                    "2. Format equations using beautiful Unicode signs (e.g., a² + b² = c²).\n"
                    "3. Always answer in Russian language."
                )
            }
        ]
        
        for r in reversed(history_records):
            role = "user" if r["sender"] == "user" else "assistant"
            messages.append({"role": role, "content": r["message_text"]})

        response = await openai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.4
        )
        ai_reply = response.choices[0].message.content
        logger.info(f"✅ Ответ ИИ сгенерирован для пользователя {payload.tg_id}")

        # Сохраняем ответ ИИ в базу
        async with db.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO chat_messages (user_id, sender, message_text) VALUES ($1, 'ai', $2)",
                payload.tg_id, ai_reply
            )

        return MessageSchema(sender="ai", message_text=ai_reply)
    except Exception as e:
        logger.error(f"❌ Ошибка при обработке сообщения от {payload.tg_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Ошибка обработки запроса")


@router.delete("/clear/{tg_id}", status_code=status.HTTP_204_NO_CONTENT)
async def clear_chat_context(tg_id: int):
    """Позволяет ученику очистить историю (начать диалог заново с чистого листа)"""
    async with db.pool.acquire() as conn:
        await conn.execute("DELETE FROM chat_messages WHERE user_id = $1", tg_id)
    return None


# === Alias routes for /api/tutor/chats prefix ===

@tutor_router.get("/{tg_id}", response_model=List[MessageSchema])
async def get_tutor_chat_history(tg_id: int):
    """Alias: Get chat history via /api/tutor/chats"""
    return await get_chat_history(tg_id)


@tutor_router.post("/send", response_model=MessageSchema)
async def send_tutor_message(payload: SendMessageRequest):
    """Alias: Send message via /api/tutor/chats"""
    return await send_message_from_webapp(payload)


@tutor_router.delete("/{tg_id}", status_code=status.HTTP_204_NO_CONTENT)
async def clear_tutor_chat(tg_id: int):
    """Alias: Clear chat via /api/tutor/chats"""
    return await clear_chat_context(tg_id)