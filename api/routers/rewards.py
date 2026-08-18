from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from database import db
from logger_config import logger

router = APIRouter(prefix="/api/rewards", tags=["Rewards"])


class RewardCreate(BaseModel):
    name: str = Field(..., max_length=256, description="Название награды")
    description: str = Field(..., max_length=500, description="Описание награды")
    cost_coins: int = Field(..., ge=1, description="Стоимость в монетах")
    category: str = Field(default="other", description="Категория награды")


class RewardResponse(BaseModel):
    reward_id: int
    name: str
    description: str
    cost_coins: int
    category: str
    created_at: Optional[datetime] = None


class StudentRewardPurchase(BaseModel):
    reward_id: int
    student_tg_id: int


@router.post("/parent/{parent_tg_id}", response_model=RewardResponse, status_code=status.HTTP_201_CREATED)
async def create_reward(parent_tg_id: int, payload: RewardCreate):
    """Создание новой награды родителем"""
    async with db.pool.acquire() as conn:
        # Проверяем, что пользователь - родитель или админ
        parent = await conn.fetchrow(
            "SELECT tg_id, role FROM users WHERE tg_id = $1",
            parent_tg_id
        )
        if not parent or parent["role"] not in ["parent", "admin"]:
            logger.warning(f"⚠️ Попытка создания награды неавторизованным пользователем {parent_tg_id}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Создавать награды может только Родитель или Администратор"
            )
        
        # Создаём награду
        reward = await conn.fetchrow(
            """
            INSERT INTO rewards (parent_id, name, description, cost_coins, category)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING reward_id, name, description, cost_coins, category, created_at
            """,
            parent_tg_id, payload.name, payload.description, payload.cost_coins, payload.category
        )
        logger.info(f"✅ Награда создана: {reward['reward_id']} родителем {parent_tg_id}")
    
    return dict(reward) if reward else None


@router.get("/parent/{parent_tg_id}", response_model=List[RewardResponse])
async def get_parent_rewards(parent_tg_id: int):
    """Получить все награды, созданные родителем"""
    async with db.pool.acquire() as conn:
        rewards = await conn.fetch(
            """
            SELECT reward_id, name, description, cost_coins, category, created_at
            FROM rewards
            WHERE parent_id = $1
            ORDER BY created_at DESC
            """,
            parent_tg_id
        )
    
    return [dict(r) for r in rewards]


@router.delete("/parent/{parent_tg_id}/{reward_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_reward(parent_tg_id: int, reward_id: int):
    """Удалить награду"""
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            # Проверяем собственность
            reward = await conn.fetchrow(
                "SELECT parent_id FROM rewards WHERE reward_id = $1",
                reward_id
            )
            if not reward or reward["parent_id"] != parent_tg_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Вы не можете удалить эту награду"
                )
            
            # Удаляем награду
            await conn.execute(
                "DELETE FROM rewards WHERE reward_id = $1",
                reward_id
            )
    
    return None


@router.post("/purchase", status_code=status.HTTP_200_OK)
async def purchase_reward(payload: StudentRewardPurchase):
    """Купить награду ученику (списать монеты и выдать награду)"""
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            # Проверяем, существует ли студент в системе
            student = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM users WHERE tg_id = $1 AND role = 'student')",
                payload.student_tg_id
            )
            if not student:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Ученик не найден или не зарегистрирован"
                )
            
            # Получаём информацию о награде
            reward = await conn.fetchrow(
                "SELECT reward_id, cost_coins FROM rewards WHERE reward_id = $1",
                payload.reward_id
            )
            if not reward:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Награда не найдена"
                )
            

            new_balance = await conn.fetchval(
                """
                UPDATE gamification
                SET balance_coins = balance_coins - $1
                WHERE user_id = $2 AND balance_coins >= $1
                RETURNING balance_coins
                """,
                reward["cost_coins"], payload.student_tg_id
            )
            if new_balance is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Недостаточно монет для покупки"
                )
            
            await conn.execute(
                """
                INSERT INTO reward_purchases (student_id, reward_id, cost_coins)
                VALUES ($1, $2, $3)
                """,
                payload.student_tg_id, payload.reward_id, reward["cost_coins"]
            )
    
    logger.info(f"✅ Студент {payload.student_tg_id} успешно купил награду {payload.reward_id} за {reward['cost_coins']} монет")
    return {"status": "success", "message": "Награда успешно выдана"}


@router.get("/student/{student_tg_id}")
async def get_student_rewards(student_tg_id: int):
    """Получить награды, полученные студентом"""
    async with db.pool.acquire() as conn:
        rewards = await conn.fetch(
            """
            SELECT r.reward_id, r.name, r.description, r.cost_coins, r.category, rp.purchased_at
            FROM reward_purchases rp
            JOIN rewards r ON rp.reward_id = r.reward_id
            WHERE rp.student_id = $1
            ORDER BY rp.purchased_at DESC
            """,
            student_tg_id
        )
    
    return [dict(r) for r in rewards]


@router.get("/store")
async def get_rewards_store():
    """Получить магазин доступных наград"""
    async with db.pool.acquire() as conn:
        rewards = await conn.fetch(
            """
            SELECT reward_id, name, description, cost_coins, category
            FROM rewards
            ORDER BY cost_coins ASC
            """
        )
    
    return [dict(r) for r in rewards]
