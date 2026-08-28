from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services import chat_memory


class FetchRecorder:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.calls = []

    async def fetch(self, query, *args):
        self.calls.append((query, args))
        return self.rows


@pytest.mark.asyncio
async def test_short_term_memory_is_exactly_last_ten_messages():
    rows = [
        {
            "message_id": number,
            "sender": "user" if number % 2 else "ai",
            "message_text": f"m{number}",
            "created_at": number,
        }
        for number in range(20, 10, -1)
    ]
    conn = FetchRecorder(rows)
    history = await chat_memory.load_context_messages(conn, 42, "session-a", "current")

    assert chat_memory.SHORT_TERM_MESSAGES == 10
    assert len(history) == 10
    assert [item["message_id"] for item in history] == list(range(11, 21))
    _, args = conn.calls[-1]
    assert args == (42, "session-a", 10)


@pytest.mark.asyncio
async def test_attachment_query_is_scoped_to_owner_and_session():
    conn = FetchRecorder([])
    await chat_memory.session_attachments(conn, 42, "chat-a")
    query, args = conn.calls[-1]
    normalized = " ".join(query.split())
    assert "cm.user_id=$1" in normalized
    assert "cm.session_id=$2" in normalized
    assert "a.owner_id=$1" in normalized
    assert args == (42, "chat-a")
    assert "LIMIT" not in normalized.upper()


@pytest.mark.asyncio
async def test_old_pdf_remains_resolvable_after_long_chat(monkeypatch):
    rows = [
        {
            "attachment_id": 200,
            "original_name": "new-notes.pdf",
            "mime_type": "application/pdf",
            "extension": "pdf",
            "extracted_text": "Новые заметки",
        },
        {
            "attachment_id": 100,
            "original_name": "first-homework.pdf",
            "mime_type": "application/pdf",
            "extension": "pdf",
            "extracted_text": "Старое домашнее задание по дробям",
        },
    ]
    monkeypatch.setattr(
        chat_memory,
        "load_session_state",
        AsyncMock(return_value=({}, "")),
    )
    selected = await chat_memory.select_relevant_attachments(
        object(),
        42,
        "chat-a",
        "Вернёмся к PDF, который я присылал в самом начале",
        available_rows=rows,
    )
    assert selected
    assert selected[0]["attachment_id"] == 100


def test_tutor_uses_shared_session_memory_and_channel_prompt_contract():
    source = open("services/tutor.py", encoding="utf-8").read()
    assert "await session_attachments" in source
    assert "available_rows=all_session_attachments" in source
    assert "attachments_inventory=attachments_inventory_text" in source
    assert "output_channel=message_source" in source
    assert 'message_source="telegram"' not in source  # TutorService is channel-agnostic at call sites.


def test_telegram_prompt_targets_one_message():
    from services.tutor_policy import build_tutor_prompt

    prompt = build_tutor_prompt("student", None, output_channel="telegram")
    lowered = prompt.lower()
    assert "one telegram text message" in lowered
    assert "do not split the answer" in lowered
    assert "raw latex" in lowered


@pytest.mark.asyncio
async def test_long_telegram_tutor_answer_is_one_document_object():
    from bot.messages import TELEGRAM_TEXT_LIMIT, answer_plain

    message = AsyncMock()
    message.answer = AsyncMock()
    message.answer_document = AsyncMock(return_value=SimpleNamespace(message_id=1))

    await answer_plain(message, "д" * (TELEGRAM_TEXT_LIMIT + 250))

    message.answer.assert_not_awaited()
    message.answer_document.assert_awaited_once()
    kwargs = message.answer_document.await_args.kwargs
    assert kwargs["document"].filename == "umnix-answer.txt"


@pytest.mark.asyncio
async def test_short_telegram_tutor_answer_is_one_safe_message():
    from bot.messages import answer_plain
    from services.response_formatter import contains_raw_latex

    message = AsyncMock()
    message.answer = AsyncMock(return_value=SimpleNamespace(message_id=1))
    message.answer_document = AsyncMock()

    await answer_plain(message, r"Ответ: \\frac{1}{3} и \\sqrt{9}")

    message.answer.assert_awaited_once()
    message.answer_document.assert_not_awaited()
    outgoing = message.answer.await_args.args[0]
    assert not contains_raw_latex(outgoing)
    assert r"\\frac" not in outgoing
    assert r"\\sqrt" not in outgoing


@pytest.mark.asyncio
async def test_ai_helper_state_persists_for_five_messages(
    make_message, mock_db, mock_fsm_context, monkeypatch
):
    from bot.handlers import ai_chat

    user_id = 777
    state = mock_fsm_context(user_id, user_id)
    enter_message = make_message("🤖 ИИ-помощник", user_id=user_id)
    monkeypatch.setattr(
        ai_chat,
        "ensure_telegram_session",
        AsyncMock(return_value={"session_id": "00000000-0000-0000-0000-000000000777"}),
    )
    monkeypatch.setattr(ai_chat, "exit_book_mode", AsyncMock())

    await ai_chat.enter_general_ai_helper(enter_message, state)
    assert await state.get_state() == ai_chat.AIChatStates.active.state

    mock_db.mock_conn.fetchrow.return_value = {"role": "student"}
    responder = AsyncMock(
        return_value={"message_text": "Ответ", "book_mode": False}
    )
    monkeypatch.setattr(ai_chat, "respond", responder)
    monkeypatch.setattr(ai_chat, "parse_telegram_attachment", AsyncMock(return_value=None))

    for index in range(5):
        message = make_message(f"Сообщение {index + 1}", user_id=user_id)
        await ai_chat.quick_ai_chat_fallback(message)
        assert await state.get_state() == ai_chat.AIChatStates.active.state

    assert responder.await_count == 5
    assert all(
        call.kwargs["message_source"] == "telegram"
        for call in responder.await_args_list
    )


@pytest.mark.asyncio
async def test_books_replace_free_ai_state(
    make_message, mock_db, mock_fsm_context
):
    from bot.handlers.ai_chat import AIChatStates
    from bot.handlers.quests import BookFilterStates, start_book_filter

    user_id = 778
    state = mock_fsm_context(user_id, user_id)
    await state.set_state(AIChatStates.active)
    mock_db.mock_conn.fetchrow.return_value = {"role": "student"}
    message = make_message("📚 Учебники", user_id=user_id)

    await start_book_filter(message, state)

    assert await state.get_state() == BookFilterStates.choosing_grade.state


@pytest.mark.asyncio
async def test_pressing_ai_helper_again_returns_to_free_ai(
    make_message, mock_fsm_context, monkeypatch
):
    from bot.handlers import ai_chat
    from bot.handlers.quests import BookFilterStates

    user_id = 779
    state = mock_fsm_context(user_id, user_id)
    await state.set_state(BookFilterStates.choosing_book)
    message = make_message("🤖 ИИ-помощник", user_id=user_id)
    monkeypatch.setattr(
        ai_chat,
        "ensure_telegram_session",
        AsyncMock(return_value={"session_id": "00000000-0000-0000-0000-000000000779"}),
    )
    monkeypatch.setattr(ai_chat, "exit_book_mode", AsyncMock())

    await ai_chat.enter_general_ai_helper(message, state)

    assert await state.get_state() == ai_chat.AIChatStates.active.state
