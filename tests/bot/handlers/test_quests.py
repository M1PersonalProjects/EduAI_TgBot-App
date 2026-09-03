import pytest
from unittest.mock import AsyncMock

from services.core.file_parser import ParsedAttachment
from bot.handlers.quests import (
    start_book_filter,
    handle_grade_choice,
    handle_subject_choice,
    handle_book_choice,
    handle_topic_text,
    accept_final_ai_question,
    BookFilterStates,
)


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
    assert data["available_subjects"] == ["Математика"]
    assert await state.get_state() == BookFilterStates.choosing_subject.state

    callback_subject = make_callback_query(data="subject_0", user_id=user_id)
    mock_db.mock_conn.fetch.return_value = [
        {
            "book_id": 10,
            "book_author": "Виленкин",
            "book_title": "Математика 5 класс",
        }
    ]
    await handle_subject_choice(callback_subject, state)

    data = await state.get_data()
    assert data["chosen_subject"] == "Математика"
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
    mock_db.mock_conn.fetch.return_value = [
        {
            "page_id": 1,
            "page_number": 5,
            "page_paragraph": "Topic_with_underscores",
        }
    ]

    await handle_book_choice(callback, state)

    text = callback.message.edit_text.await_args.args[0]
    assert "/exit_book" in text
    assert callback.message.edit_text.await_args.kwargs.get("parse_mode") is None


@pytest.mark.asyncio
async def test_ai_tutor_multimodal_photo_uses_orchestrator(
    make_message, mock_db, mock_fsm_context, monkeypatch
):
    """Проверяет передачу Telegram-фото в единый AI-orchestrator."""
    user_id = 777
    session_id = "00000000-0000-0000-0000-000000000777"
    message = make_message(text="Реши уравнение", user_id=user_id, has_photo=True)
    state = mock_fsm_context(user_id, user_id)
    await state.set_state(BookFilterStates.waiting_for_ai_question)

    attachment = ParsedAttachment(
        filename="telegram-photo.jpg",
        mime_type="image/jpeg",
        image_data_urls=["data:image/jpeg;base64,dGVzdA=="],
    )
    parse_attachment = AsyncMock(return_value=attachment)
    ensure_session = AsyncMock(return_value={"session_id": session_id})
    generate = AsyncMock(
        return_value={
            "message_id": 123,
            "session_id": session_id,
            "sender": "ai",
            "message_text": "Ответ: x = 5",
            "context": None,
            "book_mode": False,
            "used_attachment_ids": [],
            "knowledge_source": "model",
        }
    )

    monkeypatch.setattr("bot.handlers.quests.parse_telegram_attachment", parse_attachment)
    monkeypatch.setattr("bot.handlers.quests.ensure_telegram_session", ensure_session)
    monkeypatch.setattr("bot.handlers.quests.generate_response", generate)

    await accept_final_ai_question(message, state)

    parse_attachment.assert_awaited_once_with(message)
    ensure_session.assert_awaited_once_with(user_id)
    generate.assert_awaited_once_with(
        user_id=user_id,
        role="student",
        session_id=session_id,
        message="Реши уравнение",
        mode="chat",
        attachment=attachment,
        manual_context={
            "book_class": None,
            "book_program": None,
            "book_id": None,
            "page_id": None,
            "page_paragraph": None,
        },
        lock_selected_context=False,
        message_source="telegram",
    )
    assert await state.get_state() is None
    message.answer.assert_any_call(
        "🎓 Ответ ИИ-Тьютора:\n\nОтвет: x = 5",
        reply_markup=None,
        parse_mode=None,
    )


@pytest.mark.asyncio
async def test_book_filter_replaces_skip_ai_with_quest_test_button(
    make_message, mock_db, mock_fsm_context
):
    user_id = 780
    state = mock_fsm_context(user_id, user_id)
    message = make_message(text="📚 Учебники", user_id=user_id)
    mock_db.mock_conn.fetchrow.return_value = {"role": "student"}

    await start_book_filter(message, state)

    markup = message.answer.await_args.kwargs["reply_markup"]
    labels = [button.text for row in markup.inline_keyboard for button in row]
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert "🧩 Создать квест-тест" in labels
    assert "🤖 Пропустить и спросить ИИ" not in labels
    assert "create_quest_test" in callbacks


@pytest.mark.asyncio
async def test_selected_topic_stops_before_ai_and_offers_quest_action(
    make_message, mock_fsm_context
):
    user_id = 781
    state = mock_fsm_context(user_id, user_id)
    await state.set_data(
        {
            "chosen_grade": 7,
            "chosen_subject": "Математика",
            "chosen_book_id": 10,
            "chosen_book_label": "Учебник 7 класса",
        }
    )
    await state.set_state(BookFilterStates.choosing_topic)
    message = make_message(text="Обыкновенные дроби", user_id=user_id)

    await handle_topic_text(message, state)

    assert await state.get_state() == BookFilterStates.context_ready.state
    data = await state.get_data()
    assert data["chosen_topic"] == "Обыкновенные дроби"
    markup = message.answer.await_args.kwargs["reply_markup"]
    labels = [button.text for row in markup.inline_keyboard for button in row]
    assert "🧩 Создать квест-тест" in labels
    assert "🤖 Задать вопрос ИИ" in labels
