import pytest
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
    assert "correct_answer" not in fsm_data
    assert fsm_data["assignment_source"] == "teacher"

@pytest.mark.asyncio
async def test_teacher_task_answer_goes_to_manual_review(make_message, mock_db, mock_fsm_context, monkeypatch):
    user_id = 555
    message = make_message(text="4", user_id=user_id)
    state = mock_fsm_context(user_id, user_id)
    await state.set_data({
        "active_task_id": 100, "question_text": "2+2=?", "parent_id": 999,
        "assignment_source": "teacher",
    })
    await state.set_state(QuestStates.waiting_for_answer)

    mock_db.mock_conn.fetchrow.return_value = {
        "parent_id": 999,
        "assignment_source": "teacher",
        "subject": "Математика",
        "topic": "Сложение",
        "topic_context": '{"topic":"Сложение"}',
    }
    mock_db.mock_conn.fetchval.side_effect = [1, 100]
    grading = AsyncMock()
    monkeypatch.setattr("bot.handlers.tasks.parse_chat_completion", grading)

    await check_quest_answer(message, state)

    grading.assert_not_awaited()
    assert await state.get_state() is None
    final_text = message.answer.call_args[0][0]
    assert "ожидает ручной проверки" in final_text
    assert any("pending_review" in str(call.args[0]) for call in mock_db.mock_conn.execute.await_args_list)
    message.bot.send_message.assert_called_once_with(chat_id=999, text=ANY, parse_mode=None)


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
    """Проверка обработки правильного ответа в ИИ-практике."""
    payload = {
        "tg_id": 12345,
        "task_id": 777,
        "student_answer": "25"
    }
    
    mock_db.mock_conn.fetchrow.return_value = {
        "task_id": 777,
        "parent_id": None,
        "assignment_source": "tutor_practice",
        "questions_json": '{"question_text": "Сторона 5. Площадь?", "reference_answer": "25"}',
        "topic_context": '{"subject": "Математика", "topic": "Площадь квадрата"}',
        "student_answers_json": None
    }
    
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
    mock_db.mock_conn.fetchval.return_value = 777

    response = await api_client.post("/api/tasks/submit", json=payload)

    assert response.status_code == 200
    json_data = response.json()
    assert json_data["success"] is True
    assert "Ты верно возвёл 5 в квадрат!" in json_data["message"]


@pytest.mark.asyncio
async def test_submit_task_answer_incorrect(api_client, mock_db, monkeypatch):
    """Проверка неверного ответа через API: сохранение попытки для повторной работы."""
    payload = {
        "tg_id": 12345,
        "task_id": 777,
        "student_answer": "30"
    }
    
    mock_db.mock_conn.fetchrow.return_value = {
        "task_id": 777,
        "parent_id": None,
        "assignment_source": "tutor_practice",
        "questions_json": '{"question_text": "Сторона 5. Площадь?", "reference_answer": "25"}',
        "topic_context": '{"subject": "Математика", "topic": "Площадь квадрата"}',
        "student_answers_json": None
    }
    
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
    assert "Ошибка в вычислениях" in json_data["message"]


@pytest.mark.asyncio
async def test_start_quest_without_teacher_task_opens_quest_builder(
    make_message, mock_db, mock_fsm_context
):
    user_id = 556
    message = make_message(text="/quest", user_id=user_id)
    state = mock_fsm_context(user_id, user_id)
    mock_db.mock_conn.fetchrow.side_effect = [
        {"parent_id": 999},
        None,
    ]

    await start_quest(message, state)

    texts = [call.args[0] for call in message.answer.await_args_list]
    assert any("Создай квест-тест" in text for text in texts)
    final_markup = message.answer.await_args_list[-1].kwargs["reply_markup"]
    labels = [button.text for row in final_markup.inline_keyboard for button in row]
    assert "📚 Выбрать учебник / тему" in labels
    assert "✍️ Создать по запросу" in labels


@pytest.mark.asyncio
async def test_multi_question_quest_advances_without_paying_early(
    make_message, mock_db, mock_fsm_context, monkeypatch
):
    user_id = 557
    message = make_message(text="4", user_id=user_id)
    state = mock_fsm_context(user_id, user_id)
    await state.set_data({
        "active_task_id": 101,
        "question_text": "2+2=?",
        "correct_answer": "4",
        "parent_id": None,
        "quest_items": [
            {"id": "q1", "question_text": "2+2=?", "reference_answer": "4"},
            {"id": "q2", "question_text": "3+3=?", "reference_answer": "6"},
        ],
        "quest_index": 0,
        "quest_answers": [],
    })
    await state.set_state(QuestStates.waiting_for_answer)

    mock_parse = AsyncMock()
    mock_parse.return_value.choices[0].message.parsed = MockTaskVer(
        is_correct=True, explanation="Верно"
    )
    monkeypatch.setattr(openai_client.beta.chat.completions, "parse", mock_parse)
    mock_db.mock_conn.fetchrow.return_value = {"topic_context": '{"topic":"арифметика"}'}

    await check_quest_answer(message, state)

    data = await state.get_data()
    assert data["quest_index"] == 1
    assert data["question_text"] == "3+3=?"
    assert data["correct_answer"] == "6"
    assert await state.get_state() == QuestStates.waiting_for_answer.state
    # Промежуточный ответ сохраняется без дополнительных побочных эффектов.
    assert mock_db.mock_conn.execute.call_count == 1
