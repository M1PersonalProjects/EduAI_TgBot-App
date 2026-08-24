from pathlib import Path
from config import settings
from fastapi import APIRouter, HTTPException, status, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from database import db
from api.security import verify_telegram_webapp_data
from api.schemas.accounts import (
    LinkAccountsRequest, MonitoringResponse, StudentProgressResponse,
    WebAppAuthRequest, RoleSwitchRequest, AuthResponse, WebAuthRequest
)

router = APIRouter(prefix="/api/accounts", tags=["Accounts"])

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[2] / "templates"))

@router.get("/login", response_class=HTMLResponse)
async def get_login_page(request: Request):
    return templates.TemplateResponse(request, "auth.html")

@router.post("/verify-webapp", response_model=AuthResponse)
async def verify_webapp_session(payload: WebAppAuthRequest):
    """
    Безопасная точка входа для Telegram Web App.
    Проверяет сессию и возвращает роль пользователя из СУБД.
    """
    tg_user = verify_telegram_webapp_data(payload.init_data_raw)
    tg_id = tg_user.get("id")

    async with db.pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT tg_id, username, role FROM users WHERE tg_id = $1",
            tg_id
        )
        if not user:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Вы ещё не зарегистрированы. Пожалуйста, посетите нашего Telegram-бота."
            )

    return {
        "status": "success",
        "tg_id": user["tg_id"],
        "username": user["username"],
        "role": user["role"]
    }


@router.post("/switch-role")
async def switch_user_role(payload: RoleSwitchRequest):
    """
    Смена роли Учитель <-> Админ с проверкой безопасности через Telegram Web App.
    В самом сайте Telegram WebApp.
    """
    tg_user = verify_telegram_webapp_data(payload.init_data_raw)
    if tg_user.get("id") != payload.tg_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Действие запрещено: попытка входа в чужой аккаунта."
        )

    if payload.target_role not in ["admin", "parent"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Недопустимая роль пользователя. Возможны только 'admin' или 'teacher'"
        )

    if payload.target_role == "admin" and payload.tg_id not in settings.admin_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Критическая ошибка доступа: вашего ID нет в списке администраторов системы."
        )

    async with db.pool.acquire() as conn:
        async with conn.transaction():
            current_user = await conn.fetchrow(
                "SELECT role FROM users WHERE tg_id = $1",
                payload.tg_id
            )
            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Пользователь не найден в базе данных"
                )

            if current_user["role"] not in ["admin", "parent"]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="У вас нет прав для изменения роли аккаунта."
                )

            await conn.execute(
                "UPDATE users SET role = $1 WHERE tg_id = $2",
                payload.target_role, payload.tg_id
            )

    return {
        "status": "success",
        "message": f"Роль успешно изменена на {payload.target_role}. Проверка безопасности пройдена."
    }


@router.get("/monitoring/{parent_tg_id}", response_model=MonitoringResponse)
async def get_parent_monitoring(parent_tg_id: int):
    """
    Получение мониторинга активности учеников для Учителя/Админа на их странице сайта.
    """
    async with db.pool.acquire() as conn:
        parent = await conn.fetchrow(
            "SELECT tg_id FROM users WHERE tg_id = $1 AND role IN ('parent', 'admin')",
            parent_tg_id
        )
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Учитель/Администратор с таким Telegram ID не найден"
            )

        rows = await conn.fetch(
            """
            SELECT u.tg_id, u.username, u.role
            FROM users u
            WHERE u.parent_id = $1 AND u.role = 'student'
            """,
            parent_tg_id
        )

    students_list = [
        StudentProgressResponse(
            tg_id=row["tg_id"],
            username=row["username"] or f"ID: {row['tg_id']}",
            role="student"
        ) for row in rows
    ]

    return MonitoringResponse(
        parent_tg_id=parent_tg_id,
        students=students_list
    )


@router.post("/link", status_code=status.HTTP_200_OK)
async def link_parent_and_student(payload: LinkAccountsRequest):
    """
    Логика привязки аккаунта ученика к Учителю/Админу (без создания самой ссылки).
    Результатом является привязка аккаунта ученика к Учителю/Админу в БД.
    """
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            parent = await conn.fetchrow(
                "SELECT tg_id, role FROM users WHERE tg_id = $1",
                payload.parent_tg_id
            )
            if not parent:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Учитель с таким Telegram ID не найден"
                )

            student = await conn.fetchrow(
                "SELECT tg_id FROM users WHERE tg_id = $1",
                payload.student_tg_id
            )
            if not student:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Ученик с таким Telegram ID не найден"
                )

            await conn.execute(
                """
                UPDATE users
                SET parent_id = $1, role = 'student'
                WHERE tg_id = $2
                """,
                payload.parent_tg_id, payload.student_tg_id
            )

            if parent["role"] != "admin":
                await conn.execute(
                    "UPDATE users SET role = 'parent' WHERE tg_id = $1",
                    payload.parent_tg_id
                )


    return {
        "status": "success",
        "message": f"Аккаунт ученика {payload.student_tg_id} успешно привязан к Учителю {payload.parent_tg_id}"
    }


@router.get("/profile/{tg_id}", response_model=StudentProgressResponse)
async def get_user_profile(tg_id: int):
    """
    Получение профиля Ученика по tg_id.
    """
    async with db.pool.acquire() as conn:
        profile = await conn.fetchrow(
            """
            SELECT u.tg_id, u.username, u.role
            FROM users u
            WHERE u.tg_id = $1
            """,
            tg_id
        )

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Профиль не найден"
        )

    return StudentProgressResponse(
        tg_id=profile["tg_id"],
        username=profile["username"] or f"ID: {profile['tg_id']}",
        role=profile["role"]
    )


@router.post("/auth", response_model=AuthResponse)
async def web_auth(payload: WebAuthRequest):
    """
    Авторизация через браузер по tg_id.
    Если пользователь есть в БД, возвращаем статус успеха.
    Если нет — отдаем 404.
    """
    async with db.pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT tg_id, username, role FROM users WHERE tg_id = $1",
            payload.tg_id
        )

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Пользователь не зарегистрирован в системе. Пожалуйста, зайдите в Telegram-бота."
            )

    return {
        "status": "success",
        "tg_id": user["tg_id"],
        "username": user["username"],
        "role": user["role"]
    }
