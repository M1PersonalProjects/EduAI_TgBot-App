import base64
import hashlib
import hmac
import json
import time
from typing import Callable, Dict, Iterable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import settings
from database import db


SESSION_TTL_SECONDS = 7 * 24 * 60 * 60
bearer_scheme = HTTPBearer(auto_error=False)


def _encode(value: bytes) -> str:
    """
    Кодирует байты в безопасную для URL строку Base64 без символов '=' в конце.
    """
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    """
    Декодирует безопасную для URL строку Base64 обратно в байты.
    """
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def create_session_token(tg_id: int) -> str:
    """
    Создаёт токен сессии для пользователя с указанным tg_id.
    """
    payload = {
        "tg_id": int(tg_id),
        "exp": int(time.time()) + SESSION_TTL_SECONDS,
    }
    body = _encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = hmac.new(
        settings.bot_token.get_secret_value().encode("utf-8"),
        body.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{body}.{_encode(signature)}"


def decode_session_token(token: str) -> Dict[str, int]:
    """
    Декодирует токен сессии и проверяет его подпись и срок действия.
    """
    try:
        body, supplied_signature = token.split(".", 1)
        expected_signature = hmac.new(
            settings.bot_token.get_secret_value().encode("utf-8"),
            body.encode("ascii"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(expected_signature, _decode(supplied_signature)):
            raise ValueError("invalid signature")
        payload = json.loads(_decode(body))
        if int(payload["exp"]) <= int(time.time()):
            raise ValueError("expired")
        return {"tg_id": int(payload["tg_id"]), "exp": int(payload["exp"])}
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Сессия недействительна или истекла",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> Dict[str, object]:
    """
    Получает текущего пользователя из токена сессии.
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется авторизация",
            headers={"WWW-Authenticate": "Bearer"},
        )

    session = decode_session_token(credentials.credentials)
    async with db.pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT tg_id, username, role, parent_id, mentor_kind FROM users WHERE tg_id = $1",
            session["tg_id"],
        )
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не найден")

    result = dict(user)
    result["is_admin"] = result["tg_id"] in settings.admin_ids or result["role"] == "admin"
    return result


def require_roles(*allowed_roles: str) -> Callable:
    """
    Декоратор для проверки роли пользователя.
    """
    allowed: Iterable[str] = set(allowed_roles)

    async def dependency(user: Dict[str, object] = Depends(get_current_user)) -> Dict[str, object]:
        if user["role"] not in allowed and not (user["is_admin"] and "admin" in allowed):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
        return user

    return dependency


def verify_telegram_webapp_data(init_data_raw: str) -> dict:
    """
    Проверяет подпись и срок действия Telegram WebApp initData.
    """
    import urllib.parse

    try:
        parsed_data = dict(urllib.parse.parse_qsl(init_data_raw))
        if "hash" not in parsed_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Некорректный формат данных: отсутствует hash",
            )
        telegram_hash = parsed_data.pop("hash")
        data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(parsed_data.items()))
        secret_key = hmac.new(
            b"WebAppData",
            settings.bot_token.get_secret_value().encode(),
            hashlib.sha256,
        ).digest()
        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(calculated_hash, telegram_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Ошибка валидации данных: хэш не совпадает",
            )

        try:
            auth_date = int(parsed_data.get("auth_date", "0"))
        except ValueError:
            auth_date = 0
        if auth_date <= 0 or abs(int(time.time()) - auth_date) > 24 * 60 * 60:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Данные Telegram устарели. Откройте Web App заново",
            )

        user_data = parsed_data.get("user")
        if not user_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Данные пользователя отсутствуют в initData",
            )
        return json.loads(user_data)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ошибка разбора initData: {exc}",
        ) from exc
