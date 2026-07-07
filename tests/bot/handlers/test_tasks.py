import pytest
import sys
import json
from unittest.mock import AsyncMock, MagicMock, ANY
from pydantic import BaseModel
from api.routers.tasks import openai_client, OpenAITaskGeneration, OpenAITaskVerification

class MockTaskGen(BaseModel):
    title: str
    description: str
    correct_answer: str

class MockTaskVer(BaseModel):
    is_correct: bool
    explanation: str

mock_api_module = MagicMock()
mock_api_module.OpenAITaskGeneration = MockTaskGen
mock_api_module.OpenAITaskVerification = MockTaskVer
sys.modules["api.routers.tasks"] = mock_api_module

from bot.handlers.tasks import start_quest, check_quest_answer, QuestStates, openai_client

@pytest.mark.asyncio
async def test_start_quest_priority_parent(make_message, mock_db, mock_fsm_context):
    user_id = 555
    message = make_message(text="🚀 Запустить квест", user_id=user_id)
    state = mock_fsm_context(user_id, user_id)
    
    mock_db.mock_conn.fetchrow.side_effect = [
        {"parent_id": 999},
        {
            "task_id": 42,
            "topic_context": '{"subject": "Геометрия"}',
            "questions_json": '{"title": "Тест от мамы", "question_text": "2+2=?", "reference_answer": "4"}',
            "student_answers_json": None,
            "parent_id": 999
        }
    ]
    
    await start_quest(message, state)
    mock_db.mock_conn.execute.assert_called_once_with(
        "UPDATE tasks_history SET status = 'in_progress'::task_status WHERE task_id = $1", 42
    )
    fsm_data = await state.get_data()
    assert fsm_data["active_task_id"] == 42
    assert fsm_data["correct_answer"] == "4"

@pytest.mark.asyncio
async def test_check_quest_answer_correct(make_message, mock_db, mock_fsm_context, monkeypatch):
    user_id = 555
    message = make_message(text="4", user_id=user_id)
    state = mock_fsm_context(user_id, user_id)
    
    await state.set_data({
        "active_task_id": 100, "question_text": "2+2=?", "correct_answer": "4", "parent_id": 999
    })
    await state.set_state(QuestStates.waiting_for_answer)
    
    # Явно подменяем метод parse у конкретного openai_client внутри модуля tasks
    mock_parse = AsyncMock()
    fake_verification = MockTaskVer(is_correct=True, explanation="Отлично выполнено!")
    mock_parse.return_value.choices[0].message.parsed = fake_verification
    monkeypatch.setattr(openai_client.beta.chat.completions, "parse", mock_parse)
    
    mock_db.mock_conn.fetchrow.return_value = {"balance_coins": 10, "xp_total": 20}
    
    await check_quest_answer(message, state)
    
    assert mock_db.mock_conn.execute.call_count == 2
    assert await state.get_state() is None
    assert "Начислено: `+15` монет и `+50` XP." in message.answer.call_args[0][0]
    message.bot.send_message.assert_called_once_with(chat_id=999, text=ANY)


@pytest.mark.asyncio
async def test_generate_task_success(api_client, mock_db, monkeypatch):
    """Успешная генерация квеста по случайной странице учебника."""
    tg_id = 12345
    
    # 1. Настраиваем мок ответов от базы данных
    mock_db.mock_conn.fetchrow.side_effect = [
        {"parent_id": 999}, 
        {
            "page_id": 42, 
            "page_markdown": "Формула площади квадрата S = a²", 
            "page_title": "Площадь квадрата", 
            "book_title": "Геометрия 7 класс", 
            "book_program": "Геометрия"
        }
    ]
    mock_db.mock_conn.fetchval.return_value = 777 
    
    # 2. ПОЛНОСТЬЮ МОКАЕМ КЛИЕНТ OPENAI ДЛЯ РОУТЕРА
    from api.routers.tasks import openai_client
    mock_openai_client = AsyncMock()
    
    fake_ai_task = OpenAITaskGeneration(
        title="Практика по площади квадрата",
        description="Найди площадь квадрата со стороной 5 см.",
        correct_answer="25"
    )
    
    # Настраиваем цепочку вызовов: client.beta.chat.completions.parse()
    mock_parse_response = MagicMock()
    mock_parse_response.choices[0].message.parsed = fake_ai_task
    mock_openai_client.beta.chat.completions.parse = AsyncMock(return_value=mock_parse_response)
    
    # Патчим в модуле роутера задач
    monkeypatch.setattr("api.routers.tasks.openai_client", mock_openai_client)
    
    # 3. Выполняем запрос к API
    response = await api_client.get(f"/api/tasks/generate/{tg_id}")
    
    # 4. Проверяем утверждения (Assertions)
    assert response.status_code == 200
    json_data = response.json()
    assert json_data["task_id"] == 777
    assert json_data["title"] == "Практика по площади квадрата"


@pytest.mark.asyncio
async def test_generate_task_student_not_found(api_client, mock_db):
    """Ошибка 404, если ученика нет в системе."""
    mock_db.mock_conn.fetchrow.return_value = None # Студент не найден
    
    response = await api_client.get("/api/tasks/generate/99999")
    
    assert response.status_code == 404
    assert response.json()["detail"] == "Ученик с таким Telegram ID не найден"


@pytest.mark.asyncio
async def test_submit_task_answer_correct(api_client, mock_db, monkeypatch):
    """Проверка ПРАВИЛЬНОГО ответа через API: обновление истории и начисление наград."""
    payload = {
        "tg_id": 12345,
        "task_id": 777,
        "student_answer": "25"
    }
    
    mock_db.mock_conn.fetchrow.side_effect = [
        {
            "task_id": 777,
            "questions_json": '{"question_text": "Сторона 5. Площадь?", "reference_answer": "25"}',
            "topic_context": '{"subject": "Математика"}'
        }, 
        {"balance_coins": 100, "xp_total": 500} 
    ]
    
    # ПОЛНОСТЬЮ МОКАЕМ КЛИЕНТ OPENAI ДЛЯ РОУТЕРА
    mock_openai_client = AsyncMock()
    fake_verification = OpenAITaskVerification(
        is_correct=True,
        explanation="Отлично! Ты верно возвёл 5 в квадрат!"
    )
    mock_parse_response = MagicMock()
    mock_parse_response.choices[0].message.parsed = fake_verification
    mock_openai_client.beta.chat.completions.parse = AsyncMock(return_value=mock_parse_response)
    
    monkeypatch.setattr("api.routers.tasks.openai_client", mock_openai_client)
    
    response = await api_client.post("/api/tasks/submit", json=payload)
    
    assert response.status_code == 200
    json_data = response.json()
    assert json_data["success"] is True
    assert json_data["new_balance_coins"] == 115
    assert "Ты верно возвёл 5 в квадрат!" in json_data["message"]


@pytest.mark.asyncio
async def test_submit_task_answer_incorrect(api_client, mock_db, monkeypatch):
    """Проверка НЕВЕРНОГО ответа через API: сохранение попытки без начисления наград."""
    payload = {
        "tg_id": 12345,
        "task_id": 777,
        "student_answer": "30"
    }
    
    mock_db.mock_conn.fetchrow.side_effect = [
        {
            "task_id": 777,
            "questions_json": '{"question_text": "Сторона 5. Площадь?", "reference_answer": "25"}',
            "topic_context": '{"subject": "Математика"}'
        },
        {"balance_coins": 100, "xp_total": 500}
    ]
    
    # ПОЛНОСТЬЮ МОКАЕМ КЛИЕНТ OPENAI ДЛЯ РОУТЕРА
    mock_openai_client = AsyncMock()
    fake_verification = OpenAITaskVerification(
        is_correct=False,
        explanation="Не совсем так. Ошибка в вычислениях."
    )
    mock_parse_response = MagicMock()
    mock_parse_response.choices[0].message.parsed = fake_verification
    mock_openai_client.beta.chat.completions.parse = AsyncMock(return_value=mock_parse_response)
    
    monkeypatch.setattr("api.routers.tasks.openai_client", mock_openai_client)
    
    response = await api_client.post("/api/tasks/submit", json=payload)
    
    assert response.status_code == 200
    json_data = response.json()
    assert json_data["success"] is False
    assert json_data["new_balance_coins"] == 100
    assert "Ошибка в вычислениях" in json_data["message"]