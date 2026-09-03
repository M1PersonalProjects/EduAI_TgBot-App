from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.digitization import textbook_digitizer


@pytest.mark.asyncio
async def test_digitizer_saves_meaningful_title_and_sanitized_content(mock_db, monkeypatch):
    page = MagicMock()
    page.get_text.return_value = "Теорема Пифагора"
    pixmap = MagicMock()
    pixmap.tobytes.return_value = b"png"
    page.get_pixmap.return_value = pixmap

    document = MagicMock()
    document.__len__.return_value = 1
    document.load_page.return_value = page
    monkeypatch.setattr(textbook_digitizer.fitz, "open", MagicMock(return_value=document))

    ai_data = SimpleNamespace(
        page_title="Теорема Пифагора",
        page_paragraph="§ 3. Прямоугольный треугольник",
        raw_text=r"Формула: $c^2=a^2+b^2$",
        html_content=r"<p>\frac{a}{b}</p>",
        markdown_content=r"Результат: \sqrt{9}",
    )
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(parsed=ai_data))]
    )
    monkeypatch.setattr(
        textbook_digitizer,
        "parse_chat_completion",
        AsyncMock(return_value=response),
    )

    result = await textbook_digitizer.digitize_pdf_bytes(1, b"%PDF-test", client=object())

    assert result["processed_pages"] == 1
    call = mock_db.mock_conn.execute.await_args
    assert call.args[1] == 1
    assert call.args[2] == "Теорема Пифагора"
    assert call.args[4] == "§ 3. Прямоугольный треугольник"
    assert "$" not in call.args[7]
    assert "\\sqrt" not in call.args[8]


def test_page_payload_rejects_paragraph_longer_than_database_contract():
    from pydantic import ValidationError
    from api.routers.platform import PagePayload

    with pytest.raises(ValidationError):
        PagePayload(
            page_title="Тема",
            page_number=1,
            page_paragraph="§ " + "A" * 101,
            page_text="Текст",
            page_html="<p>Текст</p>",
            page_markdown="Текст",
        )
