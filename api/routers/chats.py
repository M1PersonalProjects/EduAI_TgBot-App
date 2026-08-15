"""Устаревшие псевдонимы чатов, сохраненные для старых клиентов WebApp.

 Новые клиенты используют ``/api/v1/tutor``. 
 Эти маршруты намеренно используют тот же сервис сессий и аутентификацию, 
 чтобы не обходить изоляцию потоков и не читать сообщения других пользователей Telegram.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.security import get_current_user
from database import db
from logger_config import logger
from services.tutor import ensure_session, get_messages, respond


router = APIRouter(prefix="/api/chats", tags=["Deprecated Web App AI Chat"])
tutor_router = APIRouter(prefix="/api/tutor/chats", tags=["Deprecated Web App AI Chat"])


class MessageSchema(BaseModel):
    sender: str = Field(..., description="'user' или 'ai'")
    message_text: str


class SendMessageRequest(BaseModel):
    tg_id: int
    message_text: str = Field(..., min_length=1, max_length=12000)


def _assert_owner(tg_id: int, user: dict) -> None:
    if int(tg_id) != int(user["tg_id"]):
        raise HTTPException(status_code=403, detail="Нельзя обращаться к чужому чату")


async def _history(tg_id: int) -> List[MessageSchema]:
    async with db.pool.acquire() as conn:
        session = await ensure_session(conn, tg_id)
    records = await get_messages(tg_id, str(session["session_id"]))
    return [MessageSchema(sender=row["sender"], message_text=row["message_text"]) for row in records]


@router.get("/history/{tg_id}", response_model=List[MessageSchema])
async def get_chat_history(tg_id: int, user=Depends(get_current_user)):
    _assert_owner(tg_id, user)
    return await _history(tg_id)


@router.post("/send", response_model=MessageSchema)
async def send_message_from_webapp(payload: SendMessageRequest, user=Depends(get_current_user)):
    _assert_owner(payload.tg_id, user)
    try:
        result = await respond(
            user_id=user["tg_id"], role=user["role"], message_text=payload.message_text
        )
        return MessageSchema(sender="ai", message_text=result["message_text"])
    except Exception as exc:
        logger.exception("Deprecated chat request failed: %s", exc)
        raise HTTPException(status_code=502, detail="ИИ-тьютор временно недоступен")


@router.delete("/clear/{tg_id}", status_code=status.HTTP_204_NO_CONTENT)
async def clear_chat_context(tg_id: int, user=Depends(get_current_user)):
    _assert_owner(tg_id, user)
    async with db.pool.acquire() as conn:
        session = await ensure_session(conn, tg_id)
        await conn.execute(
            "DELETE FROM chat_messages WHERE user_id=$1 AND session_id=$2",
            tg_id,
            session["session_id"],
        )


@tutor_router.get("/{tg_id}", response_model=List[MessageSchema])
async def get_tutor_chat_history(tg_id: int, user=Depends(get_current_user)):
    _assert_owner(tg_id, user)
    return await _history(tg_id)


@tutor_router.post("/send", response_model=MessageSchema)
async def send_tutor_message(payload: SendMessageRequest, user=Depends(get_current_user)):
    return await send_message_from_webapp(payload, user)


@tutor_router.delete("/{tg_id}", status_code=status.HTTP_204_NO_CONTENT)
async def clear_tutor_chat(tg_id: int, user=Depends(get_current_user)):
    return await clear_chat_context(tg_id, user)
