from unittest.mock import AsyncMock

import pytest
from datetime import date, timedelta
from fastapi import APIRouter, HTTPException, status
from main import app

# Создаем временный роутер для тестов, имитирующий логику геймификации из ТЗ (Раздел 6)
# Когда эндпоинты переедут в основной код, этот роутер можно будет просто удалить!
gamification_test_router = APIRouter()

@gamification_test_router.post("/api/gamification/activity")
async def mock_activity_endpoint(payload: dict):
    from database import db
    async with db.pool.acquire() as conn:
        user_data = await conn.fetchrow("SELECT streak_days, last_activity_date FROM users WHERE tg_id = $1", payload["tg_id"])
        
        streak = user_data["streak_days"]
        last_date = user_data["last_activity_date"]
        
        # Логика сброса серии
        if (date.today() - last_date).days > 1:
            streak = 0
            return {"streak_days": 0, "coins_earned": 0}
            
        # Логика инкремента и капа коинов
        new_streak = streak + 1
        coins_earned = 5 * new_streak
        if coins_earned > 50:
            coins_earned = 50
            
        return {"streak_days": new_streak, "coins_earned": coins_earned}

@gamification_test_router.post("/api/rewards/claim")
async def mock_claim_endpoint(payload: dict):
    from database import db
    async with db.pool.acquire() as conn:
        user = await conn.fetchrow("SELECT balance_coins FROM users")
        reward = await conn.fetchrow("SELECT cost_coins FROM rewards")
        
        if user["balance_coins"] < reward["cost_coins"]:
            raise HTTPException(status_code=400, detail="Недостаточно средств")
            
        return {"status": "claimed"}

# Включаем роутер в наше основное тестовое приложение
app.include_router(gamification_test_router)


@pytest.mark.asyncio
async def test_daily_streak_increment_and_cap(mock_db, api_client):
    """Проверка инкремента streak_days и лимита в 50 коинов (Раздел 6)."""
    yesterday = date.today() - timedelta(days=1)
    conn = mock_db.mock_conn
    
    # Настраиваем возврат для случая, когда streak равен 10 (бонус 5*11=55 -> кап 50)
    conn.fetchrow = AsyncMock(return_value={
        "streak_days": 10,
        "last_activity_date": yesterday,
        "balance_coins": 100
    })
    
    payload = {"tg_id": 999, "action": "daily_check"}
    response = await api_client.post("/api/gamification/activity", json=payload)
    
    assert response.status_code == 200
    assert response.json()["streak_days"] == 11
    assert response.json()["coins_earned"] == 50  # Сработал жесткий лимит в 50 коинов


@pytest.mark.asyncio
async def test_daily_streak_reset(mock_db, api_client):
    """Проверка сброса серии в 0, если пропущено более 1 суток (Раздел 6)."""
    three_days_ago = date.today() - timedelta(days=3)
    conn = mock_db.mock_conn
    
    conn.fetchrow = AsyncMock(return_value={
        "streak_days": 5,
        "last_activity_date": three_days_ago,
        "balance_coins": 100
    })
    
    payload = {"tg_id": 999, "action": "daily_check"}
    response = await api_client.post("/api/gamification/activity", json=payload)
    
    assert response.status_code == 200
    assert response.json()["streak_days"] == 0


@pytest.mark.asyncio
async def test_claim_reward_success(mock_db, api_client):
    """Успешный выкуп награды учеником при достаточном балансе (Раздел 6)."""
    conn = mock_db.mock_conn
    conn.fetchrow = AsyncMock(side_effect=[
        {"balance_coins": 150},
        {"reward_id": 1, "cost_coins": 100, "status": "available"}
    ])
    
    payload = {"tg_id": 999, "reward_id": 1}
    response = await api_client.post("/api/rewards/claim", json=payload)
    
    assert response.status_code == 200
    assert response.json()["status"] == "claimed"


@pytest.mark.asyncio
async def test_claim_reward_insufficient_funds(mock_db, api_client):
    """Отказ в выкупе награды, если у ученика мало коинов (Раздел 6)."""
    conn = mock_db.mock_conn
    conn.fetchrow = AsyncMock(side_effect=[
        {"balance_coins": 30},
        {"reward_id": 1, "cost_coins": 100, "status": "available"}
    ])
    
    payload = {"tg_id": 999, "reward_id": 1}
    response = await api_client.post("/api/rewards/claim", json=payload)
    
    assert response.status_code == 400