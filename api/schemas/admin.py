from pydantic import BaseModel, Field, ConfigDict
from typing import Optional

class BookCreateRequest(BaseModel):
    book_title: str = Field(..., max_length=246, description="Название учебника")
    book_program: str = Field(..., max_length=100, description="Название предмета (например, 'Алгебра', 'Геометрия', 'ОГЭ Математика')")
    book_class: int = Field(..., ge=1, le=11, description="Класс")
    book_author: str = Field(..., max_length=256, description="Автор учебника")

class BookAdminResponse(BookCreateRequest):
    book_id: int
    
    model_config = ConfigDict(from_attributes=True)

class PageUpdateRequest(BaseModel):
    page_title: Optional[str] = Field(None, max_length=256)
    page_paragraph: Optional[str] = Field(None, max_length=100)
    page_text: str
    page_html: str
    page_markdown: str

# Схема Structured Outputs под ТЗ для разбора ответа OpenAI
class OpenAIPageResponse(BaseModel):
    page_paragraph: str = Field(..., description="Extracted main section title or paragraph name, max 100 chars.")
    raw_text: str = Field(..., description="Coherent cleaned page text, fixing OCR typos.")
    html_content: str = Field(..., description="Valid HTML formatting for layout, lists, and tables.")
    markdown_content: str = Field(..., description="Telegram markdown. Strictly NO mathematical syntax like $, $$, \\(, \\]. Rewrite formulas cleanly as natural text expressions.")