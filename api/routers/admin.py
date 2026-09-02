import fitz
from fastapi import APIRouter, HTTPException, status, UploadFile, File
from database import db
from logger_config import logger
from services.ai import openai_client
from api.schemas.admin import BookCreateRequest, BookAdminResponse, PageUpdateRequest
from services.digitization.textbook_digitizer import digitize_pdf_bytes

router = APIRouter(prefix="/api/admin", tags=["Admin Space"])


@router.post("/books", response_model=BookAdminResponse, status_code=status.HTTP_201_CREATED)
async def create_book(payload: BookCreateRequest):
    """
    Создание новой книги в БД."""
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO book (book_title, book_program, book_class, book_author)
            VALUES ($1, $2, $3, $4)
            RETURNING book_id, book_title, book_program, book_class, book_author, created_at
            """,
            payload.book_title, payload.book_program, payload.book_class, payload.book_author
        )
        return dict(row)

@router.post("/books/{book_id}/upload-pdf")
async def upload_pdf_and_process(book_id: int, file: UploadFile = File(...)):
    """Принимает PDF и передаёт оцифровку в общий сервис учебников (ограничение 100Мб)."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Файл должен быть в формате PDF")

    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="PDF пуст")
    if len(pdf_bytes) > 100 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="PDF должен быть не больше 100 Мб")

    try:
        return await digitize_pdf_bytes(book_id, pdf_bytes, client=openai_client)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Критическая ошибка обработки PDF книги %s", book_id)
        raise HTTPException(status_code=500, detail="Ошибка обработки PDF-файла") from exc

@router.get("/books/{book_id}/pages/{page_number}")
async def get_page_for_moderation(book_id: int, page_number: int):
    """
    Получение страницы книги для модерации по book_id и page_number.
    """
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT page_id, book_id, page_title, page_number, page_paragraph,
                   page_html, page_image, page_text, page_markdown
            FROM page
            WHERE book_id = $1 AND page_number = $2
            """,
            book_id, page_number
        )
        if not row:
            raise HTTPException(status_code=404, detail="Страница не найдена.")
        return dict(row)

@router.put("/pages/{page_id}")
async def update_page_content(page_id: int, payload: PageUpdateRequest):
    """
    Обновление содержимого страницы книги по page_id.
    """
    async with db.pool.acquire() as conn:
        existing_page = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM page WHERE page_id = $1)",
            page_id
        )
        if not existing_page:
            raise HTTPException(status_code=404, detail="Страница не найдена")

        await conn.execute(
            """
            UPDATE page
            SET page_title = COALESCE($1, page_title),
                page_paragraph = COALESCE($2, page_paragraph),
                page_text = COALESCE($3, page_text),
                page_html = COALESCE($4, page_html),
                page_markdown = COALESCE($5, page_markdown)
            WHERE page_id = $6
            """,
            payload.page_title, payload.page_paragraph, payload.page_text,
            payload.page_html, payload.page_markdown, page_id
        )
        return {"status": "success", "message": "Изменения сохранены"}
