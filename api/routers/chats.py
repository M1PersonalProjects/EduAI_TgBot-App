import os
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
    """
    Схема сообщения в чате.
    """
    sender: str = Field(..., description="'user' или 'ai'")
    message_text: str


class SendMessageRequest(BaseModel):
    """
    Схема запроса на отправку сообщения в чат.
    """
    tg_id: int
    message_text: str = Field(..., min_length=1, max_length=12000)


def _assert_owner(tg_id: int, user: dict) -> None:
    """
    Проверяет, что пользователь имеет право доступа к чату с указанным tg_id.
    """
    if int(tg_id) != int(user["tg_id"]):
        raise HTTPException(status_code=403, detail="Нельзя обращаться к чужому чату")


async def _history(tg_id: int) -> List[MessageSchema]:
    """
    Получение истории сообщений для пользователя с указанным tg_id.
    """
    async with db.pool.acquire() as conn:
        session = await ensure_session(conn, tg_id)
    records = await get_messages(tg_id, str(session["session_id"]))
    return [MessageSchema(sender=row["sender"], message_text=row["message_text"]) for row in records]


@router.get("/history/{tg_id}", response_model=List[MessageSchema])
async def get_chat_history(tg_id: int, user=Depends(get_current_user)):
    """
    Получение истории сообщений для пользователя с указанным tg_id.
    """
    _assert_owner(tg_id, user)
    return await _history(tg_id)


@router.post("/send", response_model=MessageSchema)
async def send_message_from_webapp(payload: SendMessageRequest, user=Depends(get_current_user)):
    """
    Отправка сообщения в чат от имени пользователя с указанным tg_id.
    """
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
    """
    Каскадное удаление контекста чата для пользователя.
    """
    _assert_owner(tg_id, user)
    file_paths_to_delete = []

    async with db.pool.acquire() as conn:
        async with conn.transaction():
            # Получаем текущую сессию пользователя
            session = await ensure_session(conn, tg_id)
            session_id = session["session_id"]

            # Находим все файлы, связанные с сообщениями этой сессии
            attachment_rows = await conn.fetch(
                """
                SELECT DISTINCT a.attachment_id, a.storage_path, preview_path
                FROM attachment a
                JOIN chat_message_attachment cma ON a.attachment_id = cma.attachment_id
                JOIN chat_messages cm ON cma.message_id = cm.message_id
                WHERE cm.user_id = $1 AND cm.session_id = $2
                """,
                tg_id,
                session_id
            )

            # Формируем список ID файлов через обычный цикл
            attachment_ids = []
            for row in attachment_rows:
                attachment_ids.append(row["attachment_id"])

            # Формируем список путей к файлам на диске через обычные циклы и условия
            for row in attachment_rows:
                storage_path = row["storage_path"]
                preview_path = row["preview_path"]
                
                if storage_path:
                    file_paths_to_delete.append(storage_path)
                if preview_path:
                    file_paths_to_delete.append(preview_path)

            # Удаляем сообщения чата
            await conn.execute(
                "DELETE FROM chat_messages WHERE user_id=$1 AND session_id=$2",
                tg_id,
                session_id,
            )

            # Удаляем записи самих файлов из БД, если они не привязаны к домашним заданиям
            if attachment_ids:
                await conn.execute(
                    """
                    DELETE FROM attachments 
                    WHERE attachment_id = ANY($1::bigint[])
                      AND attachment_id NOT IN (SELECT attachment_id FROM task_attachments)
                      AND attachment_id NOT IN (SELECT attachment_id FROM task_submission_attachments)
                    """,
                    attachment_ids
                )

    # Очищаем физические файлы с сервера (выполняется после успешного завершения транзакции в БД)
    for file_path in file_paths_to_delete:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as exc:
            logger.error("Ошибка при удалении файла чата с диска %s: %s", file_path, exc)


@tutor_router.get("/{tg_id}", response_model=List[MessageSchema])
async def get_tutor_chat_history(tg_id: int, user=Depends(get_current_user)):
    """
    Получение истории сообщений для пользователя с указанным tg_id через API ИИ-тьютора.
    """
    _assert_owner(tg_id, user)
    return await _history(tg_id)


@tutor_router.post("/send", response_model=MessageSchema)
async def send_tutor_message(payload: SendMessageRequest, user=Depends(get_current_user)):
    """
    Отправка сообщения в чат от имени пользователя с указанным tg_id через API ИИ-тьютора.
    """
    return await send_message_from_webapp(payload, user)


@tutor_router.delete("/{tg_id}", status_code=status.HTTP_204_NO_CONTENT)
async def clear_tutor_chat(tg_id: int, user=Depends(get_current_user)):
    """
    Каскадное удаление контекста чата для пользователя через API ИИ-тьютора.
    """
    return await clear_chat_context(tg_id, user)
