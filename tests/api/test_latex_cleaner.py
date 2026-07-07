import pytest
from unittest.mock import AsyncMock, patch, MagicMock

@pytest.mark.asyncio
@patch("api.routers.admin.fitz.open")
@patch("api.routers.admin.fitz.Matrix")
@patch("api.routers.admin.openai_client.beta.chat.completions.parse")
async def test_openai_vision_latex_filtering_enforcement(
    mock_openai_parse, mock_matrix, mock_fitz_open, mock_db
):
    """Проверка жесткого правила ТЗ: ИИ-разметка учебников (Раздел 4.1)."""
    
    # 1. Настраиваем заглушку для PyMuPDF (fitz)
    mock_page = MagicMock()
    mock_page.get_text.return_value = "Формула корней: x = b^2 - 4ac"
    
    # Эмулируем получение байт картинки
    mock_pixmap = MagicMock()
    mock_pixmap.tobytes.return_value = b"fake_png_bytes"
    mock_page.get_pixmap.return_value = mock_pixmap
    
    mock_doc = MagicMock()
    mock_doc.__len__.return_value = 1
    mock_doc.load_page.return_value = mock_page
    mock_fitz_open.return_value = mock_doc
    
    # Нам также нужно вернуть что-то из Matrix, чтобы pixmap не упал
    mock_matrix.return_value = MagicMock()

    # 2. Настраиваем ответ OpenAI, возвращающий структуру OpenAIPageResponse
    mock_ai_data = MagicMock()
    mock_ai_data.page_paragraph = "§ 5"
    mock_ai_data.raw_text = "Решаем уравнение"
    mock_ai_data.html_content = "<div>D = b^2 - 4ac</div>"
    mock_ai_data.markdown_content = "Формула: D = b^2 - 4ac или x = 0" # Без знаков $
    mock_ai_data.book_program = "Математика"

    mock_choice = MagicMock()
    mock_choice.message.parsed = mock_ai_data

    mock_ai_response = MagicMock()
    mock_ai_response.choices = [mock_choice]
    mock_openai_parse.return_value = mock_ai_response

    # Извлекаем замоканный объект соединения из фикстуры mock_db
    conn = mock_db.mock_conn
    conn.execute = AsyncMock(return_value="INSERT 0 1")

    # 3. Делаем АСИНХРОННЫЙ запрос через api_client из conftest.py
    # Обрати внимание: фикстуру api_client нужно запросить в аргументах теста!
    pass

@pytest.mark.asyncio
@patch("api.routers.admin.fitz.open")
@patch("api.routers.admin.fitz.Matrix")
@patch("api.routers.admin.openai_client.beta.chat.completions.parse")
async def test_openai_vision_latex_filtering_enforcement(
    mock_openai_parse, mock_matrix, mock_fitz_open, mock_db, api_client
):
    # Повторяем настройку моков внутри теста с асинхронным клиентом
    mock_page = MagicMock()
    mock_page.get_text.return_value = "Текст"
    mock_pixmap = MagicMock()
    mock_pixmap.tobytes.return_value = b"png"
    mock_page.get_pixmap.return_value = mock_pixmap
    
    mock_doc = MagicMock()
    mock_doc.__len__.return_value = 1
    mock_doc.load_page.return_value = mock_page
    mock_fitz_open.return_value = mock_doc

    mock_ai_data = MagicMock()
    mock_ai_data.page_paragraph = "§ 5"
    mock_ai_data.raw_text = "Решаем"
    mock_ai_data.html_content = "p"
    mock_ai_data.markdown_content = "Очищенный текст без LaTeX"
    mock_ai_data.book_program = "Математика"

    mock_choice = MagicMock()
    mock_choice.message.parsed = mock_ai_data
    mock_ai_response = MagicMock()
    mock_ai_response.choices = [mock_choice]
    mock_openai_parse.return_value = mock_ai_response

    conn = mock_db.mock_conn
    conn.execute = AsyncMock()

    files = {"file": ("math.pdf", b"%PDF-1.4 fake binary data", "application/pdf")}
    
    # Отправляем асинхронный POST-запрос
    response = await api_client.post("/api/admin/books/1/upload-pdf", files=files)
    
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert conn.execute.called