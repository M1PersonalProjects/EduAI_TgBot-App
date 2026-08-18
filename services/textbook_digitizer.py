from __future__ import annotations

import asyncio
import base64
from pathlib import Path
from typing import Awaitable, Callable, Optional

import fitz
from openai import AsyncOpenAI

from api.schemas.admin import OpenAIPageResponse
from config import settings
from database import db
from logger_config import logger
from services.tutor import clean_ai_text

ProgressCallback = Callable[[str, int, int], Awaitable[None]]

openai_client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())


async def _noop_progress(stage: str, processed: int, total: int) -> None:
    return None


async def digitize_pdf_path(
    book_id: int,
    pdf_path: Path,
    *,
    progress_callback: Optional[ProgressCallback] = None,
    reset_pages: bool = True,
) -> dict:
    callback = progress_callback or _noop_progress
    doc = None
    try:
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        if pdf_path.stat().st_size <= 0:
            raise ValueError("PDF is empty")
        if pdf_path.stat().st_size > 100 * 1024 * 1024:
            raise ValueError("PDF должен быть не больше 100 МБ")

        doc = fitz.open(str(pdf_path))
        total_pages = len(doc)
        if total_pages <= 0:
            raise ValueError("PDF не содержит страниц")

        await callback("preparing", 0, total_pages)

        async with db.pool.acquire() as conn:
            if reset_pages:
                await conn.execute("DELETE FROM page WHERE book_id = $1", book_id)

            pages_processed = 0
            for page_idx in range(total_pages):
                pdf_page = doc.load_page(page_idx)
                page_num = page_idx + 1
                await callback("ocr", pages_processed, total_pages)

                extracted_text = pdf_page.get_text()
                pix = pdf_page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
                img_bytes = pix.tobytes("png")
                base64_image = base64.b64encode(img_bytes).decode("utf-8")

                response = await openai_client.beta.chat.completions.parse(
                    model="gpt-4o",
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are an expert textbook digitalizer and OCR post-processor. "
                                "Extract the textbook page and strictly format it into the requested JSON schema.\n\n"
                                "CRITICAL RULES FOR CONTENT PROCESSING:\n"
                                "1. page_paragraph: extract the main section title, paragraph number, or sub-topic; max 100 characters.\n"
                                "2. raw_text: clean plain-text extraction of the whole page.\n"
                                "3. html_content: valid semantic HTML; recreate tables with table/tr/td.\n"
                                "4. markdown_content: the page formatted in Markdown.\n\n"
                                "MATHEMATICS:\n"
                                "Do not expose malformed technical markup. Preserve readable school mathematics consistently."
                            ),
                        },
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": f"OCR text:\n{extracted_text}"},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{base64_image}"
                                    },
                                },
                            ],
                        },
                    ],
                    response_format=OpenAIPageResponse,
                )
                ai_data = response.choices[0].message.parsed
                if not ai_data:
                    raise RuntimeError(f"ИИ не вернул данные для страницы {page_num}")

                await conn.execute(
                    """
                    INSERT INTO page (
                        book_id, page_title, page_number, page_paragraph,
                        page_html, page_image, page_text, page_markdown
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    """,
                    book_id,
                    f"Страница {page_num}",
                    page_num,
                    ai_data.page_paragraph,
                    clean_ai_text(ai_data.html_content),
                    f"data:image/png;base64,{base64_image}",
                    clean_ai_text(ai_data.raw_text),
                    clean_ai_text(ai_data.markdown_content),
                )
                pages_processed += 1
                await callback("saving", pages_processed, total_pages)
                logger.info(
                    "Digitized page %s/%s for book %s",
                    page_num,
                    total_pages,
                    book_id,
                )
                await asyncio.sleep(0.5)

        await callback("completed", pages_processed, total_pages)
        return {
            "status": "success",
            "processed_pages": pages_processed,
            "total_pages": total_pages,
        }
    finally:
        if doc is not None:
            doc.close()
