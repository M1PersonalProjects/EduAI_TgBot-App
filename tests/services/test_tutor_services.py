import io
import zipfile

import pytest

from services.education.context_resolver import ResolvedContext, _book_score, extract_hints
from services.core.file_parser import (
    MAX_ATTACHMENT_BYTES,
    MAX_PDF_BYTES,
    AttachmentError,
    attachment_size_limit,
    parse_attachment,
)
from services.bot.thinking import format_elapsed
from services.ai.orchestrator import book_mode_footer, clean_ai_text


def test_context_hints_support_russian_and_english_requests():
    english = extract_hints(
        "Explain exercise 3 from the 6th-grade Math book by Vilenkin"
    )
    russian = extract_hints(
        "Объясни параграф 7 на странице 42 учебника за 6 класс"
    )

    assert english["book_class"] == 6
    assert english["exercise"] == 3
    assert russian["book_class"] == 6
    assert russian["page_number"] == 42
    assert russian["paragraph"] == 7


def test_transliterated_author_is_ranked_as_a_book_hint():
    book = {
        "book_id": 1,
        "book_title": "Математика",
        "book_author": "Виленкин",
        "book_program": "Математика",
        "book_class": 6,
    }
    hints = extract_hints("6th-grade book by Vilenkin")

    assert _book_score(book, hints, {}) >= 36


def test_file_parser_accepts_image_text_and_docx():
    image = parse_attachment(b"not-empty-image", "photo.webp", "image/webp")
    text = parse_attachment("Пример текста".encode(), "notes.txt", "text/plain")

    docx_buffer = io.BytesIO()
    with zipfile.ZipFile(docx_buffer, "w") as archive:
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="urn:test"><w:p><w:t>Текст DOCX</w:t></w:p></w:document>',
        )
    docx = parse_attachment(
        docx_buffer.getvalue(),
        "lesson.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    assert image.image_data_urls[0].startswith("data:image/webp;base64,")
    assert text.extracted_text == "Пример текста"
    assert "Текст DOCX" in docx.extracted_text


def test_file_parser_accepts_presentation_open_document_and_html():
    pptx_buffer = io.BytesIO()
    with zipfile.ZipFile(pptx_buffer, "w") as archive:
        archive.writestr(
            "ppt/slides/slide1.xml",
            '<p:sld xmlns:p="urn:p" xmlns:a="urn:a"><a:t>Слайд PPTX</a:t></p:sld>',
        )
    odt_buffer = io.BytesIO()
    with zipfile.ZipFile(odt_buffer, "w") as archive:
        archive.writestr(
            "content.xml",
            '<office:document xmlns:office="urn:o"><office:text>Текст ODT</office:text></office:document>',
        )

    pptx = parse_attachment(
        pptx_buffer.getvalue(),
        "lesson.pptx",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )
    odt = parse_attachment(
        odt_buffer.getvalue(), "lesson.odt", "application/vnd.oasis.opendocument.text"
    )
    html = parse_attachment(
        b"<html><body><h1>Topic</h1><p>Explanation</p></body></html>",
        "lesson.html",
        "text/html",
    )
    no_extension = parse_attachment(
        b"plain text", "telegram-document", "text/plain"
    )

    assert "Слайд PPTX" in pptx.extracted_text
    assert "Текст ODT" in odt.extracted_text
    assert html.extracted_text == "Topic Explanation"
    assert no_extension.extracted_text == "plain text"


def test_file_parser_rejects_empty_and_unsupported_files():
    with pytest.raises(AttachmentError):
        parse_attachment(b"", "empty.pdf")
    with pytest.raises(AttachmentError):
        parse_attachment(b"data", "archive.exe")


def test_pdf_has_a_separate_100_mb_upload_limit():
    assert MAX_PDF_BYTES == 100 * 1024 * 1024
    assert attachment_size_limit("book.pdf") == MAX_PDF_BYTES
    assert attachment_size_limit("upload", "application/pdf") == MAX_PDF_BYTES
    assert attachment_size_limit("photo.png", "image/png") == MAX_ATTACHMENT_BYTES


def test_thinking_timer_and_book_footer_are_stable():
    context = ResolvedContext(
        book_id=1,
        book_title="Математика 6",
        book_author="Виленкин",
        book_program="Математика",
        book_class=6,
        page_id=2,
        page_number=42,
    )

    assert format_elapsed(75) == "01:15"
    assert "/exit_book" in book_mode_footer(context)
    assert "Математика 6, стр. 42" in book_mode_footer(context)
    cleaned = clean_ai_text(r"Ответ: $x^2$, \(y\), \frac{1}{2} и \sqrt{9}")
    assert "$" not in cleaned
    assert "\\frac" not in cleaned
    assert "(1)/(2)" in cleaned
    assert "√(9)" in cleaned
