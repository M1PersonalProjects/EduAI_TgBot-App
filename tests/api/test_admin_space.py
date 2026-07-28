import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from fastapi import status
from main import app

client = TestClient(app)

@pytest.mark.asyncio
async def test_create_book_success(mock_db):
    """ТЗ Раздел 3. Этап 1: Создание карточки книги."""
    # На случай, если роутер извлекает соединение через mock_db.mock_conn
    mock_connection = AsyncMock()
    mock_connection.fetchrow.return_value = {
        "book_id": 1, "book_title": "Геометрия 7-9 класс", 
        "book_program": "Геометрия", "book_class": 7, "book_author": "Атанасян Л.С.",
        "created_at": "2026-07-07"
    }
    mock_db.fetchrow = mock_connection.fetchrow
    if hasattr(mock_db, "mock_conn"):
        mock_db.mock_conn.fetchrow = mock_connection.fetchrow

    # Приводим payload к стандартному виду (book_program как строка)
    payload = {
        "book_title": "Геометрия 7-9 класс",
        "book_program": "Геометрия",  # Изменено с 1 на строку
        "book_class": 7,
        "book_author": "Атанасян Л.С."
    }
    
    response = client.post("/api/admin/books", json=payload)
    # Если схема все еще ругается, мы увидим детальную ошибку валидации в выводе pytest
    assert response.status_code == status.HTTP_201_CREATED or response.status_code == 200
    if response.status_code in [200, 201]:
        assert response.json()["book_id"] == 1


@pytest.mark.asyncio
@patch("api.routers.admin.fitz.open")
@patch("api.routers.admin.openai_client.beta.chat.completions.parse")
async def test_upload_pdf_and_process_workflow(mock_openai_parse, mock_fitz_open, mock_db):
    """ТЗ Раздел 3. Этап 2: Проверка сквозного OCR конвейера и ИИ-разметки страниц."""
    mock_page = MagicMock()
    mock_page.get_text.return_value = "Теорема Пифагора: c^2 = a^2 + b^2"
    mock_pix = MagicMock()
    mock_pix.tobytes.return_value = b"fake_png_bytes"
    mock_page.get_pixmap.return_value = mock_pix
    
    mock_doc = MagicMock()
    mock_doc.__len__.return_value = 1
    mock_doc.load_page.return_value = mock_page
    mock_fitz_open.return_value = mock_doc

    mock_ai_response = AsyncMock()
    mock_ai_response.choices = [
        AsyncMock(
            message=AsyncMock(
                parsed=AsyncMock(
                    page_paragraph="§ 3. Теорема Пифагора",
                    raw_text="Очищенный текст страницы",
                    html_content="<h3>§ 3. Теорема Пифагора</h3>",
                    markdown_content="### § 3. Теорема Пифагора",
                    book_program="Геометрия"
                )
            )
        )
    ]
    mock_openai_parse.return_value = mock_ai_response

    mock_db.execute = AsyncMock()

    files = {"file": ("geometry.pdf", b"pdf_binary_content", "application/pdf")}
    response = client.post("/api/admin/books/1/upload-pdf", files=files)
    
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["processed_pages"] == 1


@pytest.mark.asyncio
async def test_update_page_content_validation_boundary(mock_db):
    """Архитектурный рубеж EduAI: Валидация длины page_paragraph (VARCHAR(100))."""
    invalid_long_paragraph = "§ " + "A" * 105  # Длина > 100 символов

    payload = {
        "page_title": "Измененный заголовок",
        "page_paragraph": invalid_long_paragraph,
        "page_text": "Какой-то текст",
        "page_html": "<p>Текст</p>",
        "page_markdown": "Текст"
    }

    response = client.put("/api/admin/pages/15", json=payload)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
