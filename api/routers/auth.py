from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status

from api.schemas.accounts import WebAppAuthRequest, WebAuthRequest
from api.security import create_session_token, get_current_user, verify_telegram_webapp_data
from database import db


router = APIRouter(prefix="/api/v1/auth", tags=["Authentication v1"])


def _auth_response(user, telegram_photo_url: Optional[str] = None) -> dict:
    """
    Формирует ответ сессии для пользователя.
    """
    return {
        "status": "success",
        "tg_id": user["tg_id"],
        "username": user["username"],
        "role": user["role"],
        "mentor_kind": user.get("mentor_kind") if hasattr(user, "get") else user["mentor_kind"],
        "session_token": create_session_token(user["tg_id"]),
        "telegram_photo_url": telegram_photo_url or None,
    }


async def _find_user(tg_id: int):
    """
    Находит пользователя по tg_id в базе данных для проверки существует он или нет.
    """
    async with db.pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT tg_id, username, role, parent_id, mentor_kind FROM users WHERE tg_id = $1",
            tg_id,
        )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Вы ещё не зарегистрированы. Пожалуйста, посетите нашего Telegram-бота.",
        )
    return user


@router.post("/telegram-webapp")
async def telegram_webapp_login(payload: WebAppAuthRequest):
    """
    Точка входа для Telegram Web App.
    Проверяет сессию и возвращает роль пользователя из СУБД.
    """
    telegram_user = verify_telegram_webapp_data(payload.init_data_raw)
    tg_id = telegram_user.get("id")
    if not isinstance(tg_id, int):
        raise HTTPException(status_code=400, detail="Telegram не передал идентификатор пользователя")
    return _auth_response(await _find_user(tg_id), telegram_user.get("photo_url"))


@router.post("/browser-login")
async def browser_login(payload: WebAuthRequest):
    """
    Точка входа для браузерного входа.
    Проверяет сессию и возвращает роль пользователя из СУБД.
    """
    return _auth_response(await _find_user(payload.tg_id))


@router.get("/session")
async def validate_session(user=Depends(get_current_user)):
    """
    Проверка действительности сессии и получение информации о пользователе.
    """
    return {
        "tg_id": user["tg_id"],
        "username": user["username"],
        "role": user["role"],
        "mentor_kind": user.get("mentor_kind") if hasattr(user, "get") else user["mentor_kind"],
        "parent_id": user["parent_id"],
        "is_admin": user["is_admin"],
    }
