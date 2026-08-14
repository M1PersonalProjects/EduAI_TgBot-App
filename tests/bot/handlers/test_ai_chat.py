import io
import zipfile
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers import ai_chat
from bot.media import parse_telegram_attachment
from services.file_parser import ParsedAttachment


@pytest.mark.asyncio
async def test_quick_tutor_handles_plain_text(make_message, mock_db, monkeypatch):
    message = make_message("Объясни дроби", user_id=501)
    mock_db.mock_conn.fetchrow.return_value = {"role": "student"}
    responder = AsyncMock(return_value={
        "message_text": "Начнём с определения дроби.",
        "book_mode": False,
    })
    monkeypatch.setattr(ai_chat, "respond", responder)
    monkeypatch.setattr(
        ai_chat,
        "ensure_telegram_session",
        AsyncMock(return_value={"session_id": "00000000-0000-0000-0000-000000000501"}),
    )

    await ai_chat.quick_ai_chat_fallback(message)

    responder.assert_awaited_once()
    assert responder.await_args.kwargs["message_text"] == "Объясни дроби"
    assert any(
        call.args and call.args[0] == "Начнём с определения дроби."
        for call in message.answer.await_args_list
    )


@pytest.mark.asyncio
async def test_quick_tutor_passes_telegram_document_to_ai(
    make_message, mock_db, monkeypatch
):
    message = make_message("", user_id=502)
    message.document = AsyncMock()
    message.document.file_name = "lesson.pptx"
    mock_db.mock_conn.fetchrow.return_value = {"role": "parent"}
    attachment = ParsedAttachment(
        filename="lesson.pptx",
        mime_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        extracted_text="Текст презентации",
    )
    monkeypatch.setattr(
        ai_chat, "parse_telegram_attachment", AsyncMock(return_value=attachment)
    )
    responder = AsyncMock(return_value={
        "message_text": "Презентация разобрана.",
        "book_mode": False,
    })
    monkeypatch.setattr(ai_chat, "respond", responder)
    monkeypatch.setattr(
        ai_chat,
        "ensure_telegram_session",
        AsyncMock(return_value={"session_id": "00000000-0000-0000-0000-000000000502"}),
    )

    await ai_chat.quick_ai_chat_fallback(message)

    responder.assert_awaited_once()
    assert responder.await_args.kwargs["attachment"] is attachment


@pytest.mark.asyncio
async def test_telegram_document_is_downloaded_and_parsed():
    pptx = io.BytesIO()
    with zipfile.ZipFile(pptx, "w") as archive:
        archive.writestr(
            "ppt/slides/slide1.xml",
            '<p:sld xmlns:p="urn:p" xmlns:a="urn:a"><a:t>Telegram PPTX</a:t></p:sld>',
        )
    payload = pptx.getvalue()
    message = AsyncMock()
    message.photo = None
    message.document = SimpleNamespace(
        file_id="file-1",
        file_name="lesson.pptx",
        mime_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        file_size=len(payload),
    )
    message.bot.get_file = AsyncMock(
        return_value=SimpleNamespace(file_path="documents/lesson.pptx")
    )

    async def download_file(_path, destination):
        destination.write(payload)

    message.bot.download_file = AsyncMock(side_effect=download_file)

    attachment = await parse_telegram_attachment(message)

    assert attachment.filename == "lesson.pptx"
    assert "Telegram PPTX" in attachment.extracted_text
