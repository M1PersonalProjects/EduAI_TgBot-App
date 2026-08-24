import pytest
from unittest.mock import ANY

from bot.handlers.parent import (
    ask_ai_parent_start,
    process_parent_analytics_query,
    parent_create_test_start,
    ParentStates,
)


@pytest.mark.asyncio
async def test_ask_ai_parent_no_child(make_message, mock_db, mock_fsm_context):
    user_id = 111
    message = make_message(text="📊 Аналитика Ученика (ИИ)", user_id=user_id)
    state = mock_fsm_context(user_id, user_id)
    mock_db.mock_conn.fetchrow.side_effect = [{"role": "parent"}, None]

    await ask_ai_parent_start(message, state)

    message.answer.assert_called_once_with(
        "❌ У вас еще нет привязанных аккаунтов Учеников. Аналитика недоступна."
    )


@pytest.mark.asyncio
async def test_process_parent_analytics_success(make_message, mock_db, mock_openai, mock_fsm_context):
    parent_id = 111
    message = make_message(text="В каких темах ошибки?", user_id=parent_id)
    state = mock_fsm_context(parent_id, parent_id)
    await state.set_state(ParentStates.waiting_for_analytics_question)

    status_msg = message.answer.return_value
    mock_db.mock_conn.fetchrow.return_value = {"tg_id": 222}
    mock_db.mock_conn.fetch.return_value = [
        {
            "topic_context": '{"subject": "Математика"}',
            "questions_json": '{"title": "Дроби"}',
            "student_answers_json": '{"verification_feedback": "Ошибся в знаменателе"}',
            "score": 10,
            "status": "completed",
        }
    ]

    await process_parent_analytics_query(message, state)

    mock_openai.chat.completions.create.assert_called_once()
    status_msg.delete.assert_called_once()
    message.answer.assert_any_call(
        "Аналитический отчет ИИ: Ребенок отлично справляется!",
        reply_markup=None,
        parse_mode=None,
    )
    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_legacy_telegram_task_button_redirects_to_webapp(make_message, mock_db, mock_fsm_context):
    parent_id = 111
    message = make_message(text="📝 Создать ИИ-тест для Ученика", user_id=parent_id)
    state = mock_fsm_context(parent_id, parent_id)
    mock_db.mock_conn.fetchrow.return_value = {"role": "parent"}

    await parent_create_test_start(message, state)

    assert await state.get_state() is None
    text = message.answer.call_args.args[0]
    assert "перенесено в WebApp" in text
    markup = message.answer.call_args.kwargs["reply_markup"]
    assert markup.inline_keyboard[0][0].text == "🌐 Открыть EduAI"
