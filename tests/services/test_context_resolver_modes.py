import pytest

from services.education.context_resolver import resolve_book_context


BOOK = {
    "book_id": 1,
    "book_title": "Математика 5",
    "book_author": "Автор",
    "book_program": "Математика",
    "book_class": 5,
    "page_id": None,
    "page_number": None,
    "page_paragraph": None,
    "page_title": None,
    "page_markdown": None,
    "page_text": None,
}


class ContextConn:
    def __init__(self, rows):
        self.rows = rows

    async def fetchrow(self, query, *args):
        return BOOK

    async def fetch(self, query, *args):
        return self.rows


def page(number, paragraph, title=None):
    return {
        "book_id": 1,
        "book_title": "Математика 5",
        "book_author": "Автор",
        "book_program": "Математика",
        "book_class": 5,
        "page_id": number,
        "page_number": number,
        "page_paragraph": paragraph,
        "page_title": title or paragraph,
        "page_markdown": f"Материал страницы {number}. Тема {paragraph}.",
        "page_text": "",
    }


@pytest.mark.asyncio
async def test_manual_whole_book_keeps_all_pages_in_order():
    rows = [page(number, f"§ {number}. Тема {number}") for number in range(1, 9)]
    context = await resolve_book_context(ContextConn(rows), 1, "объясни тему", source="manual")

    assert context is not None
    assert context.context_mode == "whole_book"
    assert [item["page_number"] for item in context.used_pages] == list(range(1, 9))
    assert context.content.index("Страница 1") < context.content.index("Страница 8")


@pytest.mark.asyncio
async def test_paragraph_selection_uses_every_page_of_that_paragraph_only():
    rows = [
        page(10, "§ 3. Дроби"),
        page(11, "§ 3. Дроби — продолжение"),
        page(12, "§ 4. Проценты"),
    ]
    context = await resolve_book_context(
        ContextConn(rows),
        1,
        "объясни параграф 3",
        paragraph="3",
        source="manual",
    )

    assert context is not None
    assert context.context_mode == "paragraph"
    assert [item["page_number"] for item in context.used_pages] == [10, 11]
    assert "Страница 12" not in context.content
