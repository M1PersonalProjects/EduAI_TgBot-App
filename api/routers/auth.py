from fastapi import APIRouter, Depends, HTTPException, status

from api.routers.accounts import verify_telegram_webapp_data
from api.schemas.accounts import WebAppAuthRequest, WebAuthRequest
from api.security import create_session_token, get_current_user
from database import db


router = APIRouter(prefix="/api/v1/auth", tags=["Authentication v1"])


def _auth_response(user) -> dict:
    return {
        "status": "success",
        "tg_id": user["tg_id"],
        "username": user["username"],
        "role": user["role"],
        "session_token": create_session_token(user["tg_id"]),
    }


async def _find_user(tg_id: int):
    async with db.pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT tg_id, username, role, parent_id FROM users WHERE tg_id = $1",
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
    telegram_user = verify_telegram_webapp_data(payload.init_data_raw)
    tg_id = telegram_user.get("id")
    if not isinstance(tg_id, int):
        raise HTTPException(status_code=400, detail="Telegram не передал идентификатор пользователя")
    return _auth_response(await _find_user(tg_id))


@router.post("/browser-login")
async def browser_login(payload: WebAuthRequest):
    return _auth_response(await _find_user(payload.tg_id))


@router.get("/session")
async def validate_session(user=Depends(get_current_user)):
    return {
        "tg_id": user["tg_id"],
        "username": user["username"],
        "role": user["role"],
        "parent_id": user["parent_id"],
        "is_admin": user["is_admin"],
    }
