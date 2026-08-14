import pytest
from unittest.mock import AsyncMock, MagicMock, ANY
from bot.handlers.quests import (
    show_real_student_profile,
    start_book_filter,
    handle_grade_choice,
    handle_subject_choice,
    handle_book_choice,
    accept_final_ai_question,
    BookFilterStates,
    openai_client # Импортируем инстанс клиента для явного мока
)

@pytest.mark.asyncio
async def test_show_student_profile(make_message, mock_db):
    user_id = 777
    message = make_message(text="🏆 Мой профиль", user_id=user_id)
    mock_db.mock_conn.fetchrow.side_effect = [
        {"role": "student"},
        {"balance_coins": 120, "xp_total": 450}
    ]
    await show_real_student_profile(message)
    response = message.answer.call_args[0][0]
    assert "120 монет" in response
    assert "450 XP" in response

@pytest.mark.asyncio
async def test_book_filter_flow(make_message, make_callback_query, mock_db, mock_fsm_context):
    user_id = 777
    state = mock_fsm_context(user_id, user_id)
    message = make_message(text="📚 Каталог учебников", user_id=user_id)
    mock_db.mock_conn.fetchrow.return_value = {"role": "student"}
    await start_book_filter(message, state)
    assert await state.get_state() == BookFilterStates.choosing_grade.state

    callback_grade = make_callback_query(data="grade_5", user_id=user_id)
    mock_db.mock_conn.fetch.return_value = [{"book_program": "Математика"}]
    await handle_grade_choice(callback_grade, state)
    data = await state.get_data()
    assert data["chosen_grade"] == 5
    assert await state.get_state() == BookFilterStates.choosing_subject.state

    callback_sub = make_callback_query(data="subject_Математика", user_id=user_id)
    mock_db.mock_conn.fetch.return_value = [{"book_id": 10, "book_author": "Виленкин", "book_title": "Математика 5 класс"}]
    await handle_subject_choice(callback_sub, state)
    assert await state.get_state() == BookFilterStates.choosing_book.state


@pytest.mark.asyncio
async def test_book_choice_sends_exit_command_without_markdown_entities(
    make_callback_query, mock_db, mock_fsm_context
):
    user_id = 778
    state = mock_fsm_context(user_id, user_id)
    await state.set_data({"chosen_grade": 6, "chosen_subject": "math_program"})
    await state.set_state(BookFilterStates.choosing_book)
    callback = make_callback_query(data="book_10", user_id=user_id)
    mock_db.mock_conn.fetchrow.return_value = {
        "book_title": "Book_with_underscores",
        "book_author": "Author_name",
    }
    mock_db.mock_conn.fetch.return_value = [{
        "page_id": 1,
        "page_number": 5,
        "page_paragraph": "Topic_with_underscores",
    }]

    await handle_book_choice(callback, state)

    text = callback.message.edit_text.await_args.args[0]
    assert "/exit_book" in text
    assert callback.message.edit_text.await_args.kwargs.get("parse_mode") is None

@pytest.mark.asyncio
async def test_ai_tutor_multimodal_photo(make_message, mock_db, mock_fsm_context, monkeypatch):
    """Проверка отправки вопроса ИИ-тьютору вместе с фотографией."""
    user_id = 777
    message = make_message(text="Реши уравнение", user_id=user_id, has_photo=True)
    state = mock_fsm_context(user_id, user_id)
    await state.set_state(BookFilterStates.waiting_for_ai_question)
    
    mock_db.mock_conn.fetch.return_value = []
    
    # Явно подменяем метод create у конкретного openai_client внутри модуля quests
    mock_create = AsyncMock()
    mock_create.return_value.choices[0].message.content = "Ответ: x = 5"
    monkeypatch.setattr(openai_client.chat.completions, "create", mock_create)
    monkeypatch.setattr(
        "bot.handlers.quests.ensure_telegram_session",
        AsyncMock(return_value={"session_id": "00000000-0000-0000-0000-000000000777"}),
    )
    
    await accept_final_ai_question(message, state)
    
    message.bot.get_file.assert_called_once()
    mock_create.assert_called_once()
    assert await state.get_state() is None
    message.answer.assert_any_call(
        "🎓 Ответ ИИ-Тьютора:\n\nОтвет: x = 5",
        reply_markup=None,
        parse_mode=None,
    )
