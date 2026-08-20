import fitz
import base64
import asyncio
from fastapi import APIRouter, HTTPException, status, UploadFile, File
from database import db
from config import settings
from openai import AsyncOpenAI
from logger_config import logger
from api.schemas.admin import BookCreateRequest, BookAdminResponse, PageUpdateRequest, OpenAIPageResponse
from services.tutor import clean_ai_text
from services.prompts import TEXTBOOK_DIGITIZATION_RULES

router = APIRouter(prefix="/api/admin", tags=["Admin Space"])

# Клиент OpenAI
openai_client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())

@router.post("/books", response_model=BookAdminResponse, status_code=status.HTTP_201_CREATED)
async def create_book(payload: BookCreateRequest):
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
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Файл должен быть в формате PDF")

    doc = None
    try:
        pdf_bytes = await file.read()
        if not pdf_bytes or len(pdf_bytes) > 100 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="PDF должен быть не больше 100 МБ")
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages_processed = 0

        async with db.pool.acquire() as conn:
            for page_idx in range(len(doc)):
                pdf_page = doc.load_page(page_idx)
                page_num = page_idx + 1

                extracted_text = pdf_page.get_text()

                pix = pdf_page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
                img_bytes = pix.tobytes("png")
                base64_image = base64.b64encode(img_bytes).decode('utf-8')

                try:
                    response = await openai_client.beta.chat.completions.parse(
                        model="gpt-4o",
                        messages=[
                            {
                                "role": "system",
                                "content": TEXTBOOK_DIGITIZATION_RULES,
                            },
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": f"OCR text:\n{extracted_text}"},
                                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
                                ]
                            }
                        ],
                        response_format=OpenAIPageResponse,
                    )

                    ai_data = response.choices[0].message.parsed

                    await asyncio.sleep(0.5)

                    await conn.execute(
                        """
                        INSERT INTO page (book_id, page_title, page_number, page_paragraph, page_html, page_image, page_text, page_markdown)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                        """,
                        book_id, f"Страница {page_num}", page_num, ai_data.page_paragraph,
                        clean_ai_text(ai_data.html_content), f"data:image/png;base64,{base64_image}",
                        clean_ai_text(ai_data.raw_text), clean_ai_text(ai_data.markdown_content)
                    )

                    pages_processed += 1
                    logger.info(f"✅ Успешно обработана страница {page_num} книги {book_id}")

                except Exception as e:
                    logger.error(f"❌ Ошибка обработки страницы {page_num} книги {book_id}: {str(e)}")
                    continue

        return {"status": "success", "processed_pages": pages_processed, "message": "Учебник успешно обработан"}

    except HTTPException:
        raise
    except Exception as exc:
        logger.critical(f"Критическая ошибка обработки PDF: {str(exc)}")
        raise HTTPException(status_code=500, detail="Ошибка обработки PDF-файла")
    finally:
        if doc is not None:
            doc.close()

@router.get("/books/{book_id}/pages/{page_number}")
async def get_page_for_moderation(book_id: int, page_number: int):
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
    async with db.pool.acquire() as conn:
        # Проверяем, существует ли страница
        existing_page = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM page WHERE page_id = $1)",
            page_id
        )
        if not existing_page:
            raise HTTPException(status_code=404, detail="Страница не найдена")

        # Обновляем страницу
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
