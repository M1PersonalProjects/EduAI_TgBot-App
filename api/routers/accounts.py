from fastapi import APIRouter, HTTPException, status
from database import db
from api.schemas.accounts import LinkAccountsRequest, MonitoringResponse, StudentProgressResponse

router = APIRouter(prefix="/api/accounts", tags=["Accounts"])

@router.post("/link", status_code=status.HTTP_200_OK)
async def link_parent_and_student(payload: LinkAccountsRequest):
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            # 1. Проверяем существование родителя и его роль
            parent = await conn.fetchrow(
                "SELECT tg_id, role FROM users WHERE tg_id = $1", 
                payload.parent_tg_id
            )
            if not parent:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Родитель с таким Telegram ID не найден"
                )
            
            # 2. Проверяем существование ученика
            student = await conn.fetchrow(
                "SELECT tg_id FROM users WHERE tg_id = $1", 
                payload.student_tg_id
            )
            if not student:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Ученик с таким Telegram ID не найден"
                )

            # 3. Связываем их в таблице и явно проставляем роли
            await conn.execute(
                """
                UPDATE users 
                SET parent_id = $1, role = 'student' 
                WHERE tg_id = $2
                """,
                payload.parent_tg_id, payload.student_tg_id
            )
            
            # На всякий случай убедимся, что у родителя стоит правильная роль
            await conn.execute(
                "UPDATE users SET role = 'parent' WHERE tg_id = $1",
                payload.parent_tg_id
            )

            # Инициализируем запись в gamification для ученика, если её ещё нет
            await conn.execute(
                """
                INSERT INTO gamification (user_id, balance_coins, xp_total, streak_days)
                VALUES ($1, 0, 0, 0)
                ON CONFLICT (user_id) DO NOTHING
                """,
                payload.student_tg_id
            )

    return {
        "status": "success",
        "message": f"Аккаунт ученика {payload.student_tg_id} успешно привязан к родителю {payload.parent_tg_id}"
    }


@router.get("/monitoring/{parent_tg_id}", response_model=MonitoringResponse)
async def get_parent_monitoring(parent_tg_id: int):
    async with db.pool.acquire() as conn:
        parent = await conn.fetchrow(
            "SELECT tg_id FROM users WHERE tg_id = $1 AND role = 'parent'", 
            parent_tg_id
        )
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Родитель с таким Telegram ID не найден"
            )

        rows = await conn.fetch(
            """
            SELECT u.tg_id, u.username, 
                   COALESCE(g.balance_coins, 0) as balance_coins, 
                   COALESCE(g.xp_total, 0) as xp_total, 
                   COALESCE(g.streak_days, 0) as streak_days
            FROM users u
            LEFT JOIN gamification g ON u.tg_id = g.user_id
            WHERE u.parent_id = $1 AND u.role = 'student'
            """,
            parent_tg_id
        )

    students_list = []
    for row in rows:
        students_list.append(
            StudentProgressResponse(
                tg_id=row["tg_id"],
                username=row["username"] or f"ID: {row['tg_id']}",
                role="student",
                balance_coins=row["balance_coins"] or 0,
                xp_total=row["xp_total"] or 0,
                streak_days=row["streak_days"] or 0
            )
        )

    return MonitoringResponse(
        parent_tg_id=parent_tg_id,
        students=students_list
    )


@router.get("/profile/{tg_id}", response_model=StudentProgressResponse)
async def get_user_profile(tg_id: int):
    async with db.pool.acquire() as conn:
        profile = await conn.fetchrow(
            """
            SELECT 
                u.tg_id, 
                u.username, 
                u.role,
                COALESCE(g.balance_coins, 0) as balance_coins, 
                COALESCE(g.xp_total, 0) as xp_total, 
                COALESCE(g.streak_days, 0) as streak_days
            FROM users u
            LEFT JOIN gamification g ON u.tg_id = g.user_id
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
        role=profile["role"] or "user",
        balance_coins=profile["balance_coins"],
        xp_total=profile["xp_total"],
        streak_days=profile["streak_days"]
    )