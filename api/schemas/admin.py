from pydantic import BaseModel, Field


class OpenAIPageResponse(BaseModel):
    page_title: str = Field(
        ...,
        max_length=256,
        description="Short descriptive title of the visible page topic in Russian.",
    )
    page_paragraph: str = Field(
        ...,
        max_length=100,
        description="Extracted main section title or paragraph name in Russian.",
    )
    raw_text: str = Field(..., description="Coherent cleaned page text, fixing OCR typos.")
    html_content: str = Field(..., description="Valid HTML formatting for layout, lists, and tables.")
    markdown_content: str = Field(
        ...,
        description=(
            "Telegram markdown. Strictly NO mathematical syntax like $, $$, \\(, or \\[. "
            "Rewrite formulas as readable natural-text expressions."
        ),
    )
