import pytest
import json
from unittest.mock import AsyncMock, MagicMock, ANY
from bot.handlers.parent import (
    ask_ai_parent_start, 
    process_parent_analytics_query,
    parent_create_test_start,
    process_custom_test_generation,
    callback_parent_edit_request,
    process_parent_edited_text,
    callback_approve_and_save,
    ParentStates,
    ParentTestGeneration
)


@pytest.mark.asyncio
async def test_ask_ai_parent_no_child(make_message, mock_db, mock_fsm_context):
    """Тест: Родитель пытается открыть аналитику, но у него нет детей."""
    user_id = 111
    message = make_message(text="📊 Аналитика ребенка (ИИ)", user_id=user_id)
    state = mock_fsm_context(user_id, user_id)
    
    # База говорит: роль родитель, но ребенка (child) нет (None)
    mock_db.mock_conn.fetchrow.side_effect = [
        {"role": "parent"},
        None
    ]
    
    await ask_ai_parent_start(message, state)
    
    message.answer.assert_called_once_with("❌ У вас еще нет привязанных аккаунтов детей. Аналитика недоступна.")


@pytest.mark.asyncio
async def test_process_parent_analytics_success(make_message, mock_db, mock_openai, mock_fsm_context):
    """Тест: Успешный сбор истории из БД и формирование ответа ИИ-консультанта."""
    parent_id = 111
    message = make_message(text="В каких темах ошибки?", user_id=parent_id)
    state = mock_fsm_context(parent_id, parent_id)
    await state.set_state(ParentStates.waiting_for_analytics_question)
    
    # Мокаем статусное сообщение
    status_msg = AsyncMock()
    message.answer.return_value = status_msg
    
    # База возвращает ребенка и фейковую историю заданий
    mock_db.mock_conn.fetchrow.return_value = {"tg_id": 222}
    mock_db.mock_conn.fetch.return_value = [
        {
            "topic_context": '{"subject": "Математика"}',
            "questions_json": '{"title": "Дроби"}',
            "student_answers_json": '{"verification_feedback": "Ошибся в знаменателе"}',
            "score": 10,
            "status": "completed"
        }
    ]
    
    await process_parent_analytics_query(message, state)
    
    # Проверяем, что OpenAI был вызван
    mock_openai.chat.completions.create.assert_called_once()
    # Проверяем, что статусное сообщение удалилось, а родителю ушел ответ ИИ
    status_msg.delete.assert_called_once()
    message.answer.assert_any_call(
        "Аналитический отчет ИИ: Ребенок отлично справляется!",
        reply_markup=None,
        parse_mode=None,
    )
    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_parent_create_test_generation(make_message, mock_db, mock_openai, mock_fsm_context):
    """Тест: Запрос темы и генерация структурированного теста через OpenAI."""
    parent_id = 111
    message = make_message(text="Теорема Пифагора", user_id=parent_id)
    state = mock_fsm_context(parent_id, parent_id)
    await state.set_state(ParentStates.waiting_for_test_topic)
    
    # 1. Настраиваем фейковую страницу учебника
    mock_db.mock_conn.fetchrow.return_value = {
        "page_id": 12, "page_markdown": "Формула: a2 + b2 = c2", "page_title": "Пифагор",
        "book_title": "Геометрия 8 класс", "book_program": "Геометрия", "student_id": 222
    }
    
    # 2. Настраиваем структурированный ответ от OpenAI (Pydantic модель)
    fake_ai_test = ParentTestGeneration(
        title="Тест на гипотенузу",
        description="Найди c, если a=3, b=4",
        correct_answer="5"
    )
    mock_openai.beta.chat.completions.parse.return_value.choices[0].message.parsed = fake_ai_test
    
    await process_custom_test_generation(message, state)
    
    # Проверяем переход в режим модерации
    assert await state.get_state() == ParentStates.moderating_test.state
    # Проверяем, что родителю вывелся предпросмотр
    response_text = message.answer.call_args[0][0]
    assert "Тест на гипотенузу" in response_text
    assert "Найди c, если a=3, b=4" in response_text


@pytest.mark.asyncio
async def test_process_parent_editing(make_message, mock_fsm_context):
    """Тест: Родителю не понравился текст и он его успешно отредактировал."""
    parent_id = 111
    message = make_message(text="Новый измененный текст задачи", user_id=parent_id)
    state = mock_fsm_context(parent_id, parent_id)
    
    # Загоняем во FSM фейковые данные первичной генерации
    await state.set_data({"generated_title": "Заголовок", "generated_answer": "42"})
    await state.set_state(ParentStates.editing_test)
    
    await process_parent_edited_text(message, state)
    
    # Проверяем, что состояние вернулось на модерацию, а текст обновился
    assert await state.get_state() == ParentStates.moderating_test.state
    data = await state.get_data()
    assert data["generated_description"] == "Новый измененный текст задачи"
    assert "Новый измененный текст задачи" in message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_callback_approve_and_save_test(make_callback_query, mock_db, mock_fsm_context):
    """Тест: Родитель нажал кнопку Аппрува. Данные пишутся в базу, ребенку идет отправка."""
    parent_id = 111
    callback = make_callback_query(data="parent_approve_test", user_id=parent_id)
    state = mock_fsm_context(parent_id, parent_id)
    
    # Наполняем FSM данными, готовыми к сохранению
    await state.set_data({
        "student_id": 222, "page_id": 12, "book_title": "Геометрия", 
        "book_program": "Математика", "topic_query": "Дроби",
        "generated_title": "Итоговый тест", "generated_description": "Реши уравнение", 
        "generated_answer": "x=3"
    })
    await state.set_state(ParentStates.moderating_test)
    
    # Эмулируем INSERT ... RETURNING task_id = 77
    mock_db.mock_conn.fetchval = AsyncMock(return_value=77)
    
    await callback_approve_and_save(callback, state)
    
    # 1. Проверяем, что вызвалась запись в базу данных
    mock_db.mock_conn.fetchval.assert_called_once()
    # 2. Проверяем отправку личного сообщения ребенку (student_id = 222)
    callback.bot.send_message.assert_called_once_with(
        chat_id=222,
        text=ANY,
            parse_mode=None
    )
    # 3. Проверяем очистку стейта
    assert await state.get_state() is None
