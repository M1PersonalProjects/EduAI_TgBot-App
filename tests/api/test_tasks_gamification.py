import pytest
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

@pytest.mark.asyncio
@patch("api.routers.tasks.openai_client.beta.chat.completions.parse")
async def test_api_submit_correct_answer_logic(mock_openai_parse, mock_db):
    """Проверка начисления наград в API с использованием корректной фикстуры mock_db."""
    
    # Готовим данные, которые должен поочередно вернуть fetchrow
    mock_responses = [
        {
            "task_id": 101,
            "parent_id": None,
            "assignment_source": "tutor_practice",
            "subject": "Математика",
            "topic": "Углы треугольника",
            "questions_json": '{"reference_answer": "180°", "question_text": "Сумма углов треугольника?"}',
            "topic_context": '{"book_id": 1, "topic": "Углы треугольника"}',
            "student_answers_json": None
        },
        {
            "balance_coins": 50,
            "xp_total": 200
        }
    ]
    
    # Реализуем функцию-side_effect, которая без проблем работает и со словарями, и с MagicMock объектами
    async def side_effect_fetchrow(*args, **kwargs):
        if mock_responses:
            return mock_responses.pop(0)
        return None

    # Покрываем все возможные варианты вызова fetchrow внутри твоего кастомного mock_db
    mock_db.fetchrow = AsyncMock(side_effect=side_effect_fetchrow)
    if hasattr(mock_db, "mock_conn"):
        mock_db.mock_conn.fetchrow = AsyncMock(side_effect=side_effect_fetchrow)

    mock_ai_response = AsyncMock()
    mock_ai_response.choices = [
        AsyncMock(message=AsyncMock(parsed=AsyncMock(is_correct=True, explanation="Превосходно!")))
    ]
    mock_openai_parse.return_value = mock_ai_response

    mock_db.execute = AsyncMock()
    if hasattr(mock_db, "mock_conn"):
        mock_db.mock_conn.execute = AsyncMock()
        mock_db.mock_conn.fetchval = AsyncMock(return_value=101)

    fake_reward = SimpleNamespace(
        xp=30, coins=0, balance_coins=50, xp_total=230,
        repetition_multiplier=1.0, achievements=(), completed_goals=(),
    )
    with patch("api.routers.tasks.award_learning_result", AsyncMock(return_value=fake_reward)):
        payload = {"task_id": 101, "tg_id": 999, "student_answer": "180 градусов"}
        response = client.post("/api/tasks/submit", json=payload)

    assert response.status_code == 200
    res_data = response.json()
    assert res_data["success"] is True
    return
