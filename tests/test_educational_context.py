import asyncio
from types import SimpleNamespace

from services.educational_context import search_eduai_materials


class FakeConnection:
    def __init__(self, rows):
        self.rows = rows

    async def fetch(self, _sql, *_params):
        return self.rows


def _row(book_id, title, program, level, page_id, content):
    return {
        "book_id": book_id,
        "book_title": title,
        "book_program": program,
        "book_class": level,
        "book_author": "Author",
        "page_id": page_id,
        "page_number": page_id,
        "page_title": "Обыкновенные дроби",
        "page_paragraph": "Дроби",
        "content": content,
    }


def test_context_source_priority_keeps_peer_textbook_before_collections():
    primary = SimpleNamespace(book_id=1, book_program="Математика", book_class=5)
    rows = [
        _row(4, "ГДЗ и ответы", "Математика", 5, 40, "дроби ответы примеры"),
        _row(3, "Сборник задач", "Математика", 5, 30, "дроби задачи практика"),
        _row(2, "Математика 5 класс", "Математика", 5, 20, "дроби теория упражнения"),
        _row(5, "Другая программа", "Физика", 7, 50, "дроби как часть измерения"),
    ]
    result = asyncio.run(search_eduai_materials(FakeConnection(rows), "обыкновенные дроби", primary=primary))
    kinds = [item.kind for item in result]
    assert kinds[:3] == ["peer_textbook", "problem_collection", "solution_book"]
    assert "eduai_material" in kinds
