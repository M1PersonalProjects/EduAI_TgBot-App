import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


STOP_WORDS = {
    "как", "что", "это", "для", "или", "мне", "мой", "моя", "при", "про",
    "the", "from", "with", "this", "explain", "book", "класс", "страница",
    "учебник", "задача", "упражнение", "пожалуйста",
}

TRANSLIT = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
})


@dataclass
class ResolvedContext:
    book_id: int
    book_title: str
    book_author: str
    book_program: str
    book_class: int
    page_id: Optional[int] = None
    page_number: Optional[int] = None
    page_paragraph: Optional[str] = None
    page_title: Optional[str] = None
    content: str = ""
    source: str = "natural_language"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def label(self) -> str:
        page = f", стр. {self.page_number}" if self.page_number else ""
        return f"{self.book_title}{page}"


def _tokens(value: str) -> List[str]:
    values = re.findall(r"[a-zа-яё0-9]+", (value or "").lower())
    return [item for item in values if len(item) >= 3 and item not in STOP_WORDS]


def _transliterate(value: str) -> str:
    return (value or "").lower().translate(TRANSLIT)


def _extract_number(pattern: str, prompt: str) -> Optional[int]:
    match = re.search(pattern, prompt or "", flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def extract_hints(prompt: str) -> Dict[str, Any]:
    return {
        "book_class": _extract_number(
            r"(?:^|\s)(\d{1,2})(?:\s*[-–]?(?:й|ый|ой|го|ого|th|st|nd|rd))?\s*[-–]?\s*(?:класс(?:а|е)?|grade)", prompt
        ),
        "page_number": _extract_number(
            r"(?:стр(?:аниц[аеуы])?\.?|page)\s*№?\s*(\d{1,4})", prompt
        ),
        "paragraph": _extract_number(r"(?:§|параграф)\s*№?\s*(\d{1,4})", prompt),
        "exercise": _extract_number(
            r"(?:упражнени[ея]|задач[аи]|номер|exercise|problem)\s*№?\s*(\d{1,4})",
            prompt,
        ),
        "tokens": _tokens(prompt),
    }


def _book_score(book: Any, hints: Dict[str, Any], manual: Dict[str, Any]) -> int:
    score = 0
    if manual.get("book_id") == book["book_id"]:
        score += 100
    expected_class = manual.get("book_class") or hints.get("book_class")
    if expected_class:
        score += 24 if int(book["book_class"]) == int(expected_class) else -30
    expected_program = (manual.get("book_program") or "").lower()
    if expected_program and expected_program in (book["book_program"] or "").lower():
        score += 35
    searchable = " ".join([
        book["book_title"] or "", book["book_author"] or "", book["book_program"] or ""
    ]).lower()
    searchable_latin = _transliterate(searchable)
    author = (book["book_author"] or "").lower()
    for token in hints.get("tokens", []):
        if token in searchable or token in searchable_latin:
            score += 6
        if token in author or token in _transliterate(author):
            score += 6
    return score


async def _fetch_exact(conn, book_id: int, page_id: Optional[int], page_number: Optional[int]):
    if not page_id and not page_number:
        return await conn.fetchrow(
            """
            SELECT b.book_id, b.book_title, b.book_author, b.book_program, b.book_class,
                   NULL::INTEGER AS page_id, NULL::INTEGER AS page_number,
                   NULL::VARCHAR AS page_paragraph, NULL::VARCHAR AS page_title,
                   NULL::TEXT AS page_markdown, NULL::TEXT AS page_text
            FROM book b WHERE b.book_id = $1
            """,
            book_id,
        )
    query = """
        SELECT b.book_id, b.book_title, b.book_author, b.book_program, b.book_class,
               p.page_id, p.page_number, p.page_paragraph, p.page_title,
               p.page_markdown, p.page_text
        FROM book b LEFT JOIN page p ON p.book_id = b.book_id
        WHERE b.book_id = $1
    """
    params: List[Any] = [book_id]
    if page_id:
        params.append(page_id)
        query += f" AND p.page_id = ${len(params)}"
    elif page_number:
        params.append(page_number)
        query += f" AND p.page_number = ${len(params)}"
    query += " ORDER BY p.page_number NULLS LAST LIMIT 1"
    return await conn.fetchrow(query, *params)


def _to_context(row: Any, source: str) -> Optional[ResolvedContext]:
    if not row:
        return None
    return ResolvedContext(
        book_id=row["book_id"],
        book_title=row["book_title"],
        book_author=row["book_author"],
        book_program=row["book_program"],
        book_class=row["book_class"],
        page_id=row["page_id"],
        page_number=row["page_number"],
        page_paragraph=row["page_paragraph"],
        page_title=row["page_title"],
        content=(row["page_markdown"] or row["page_text"] or "")[:14000],
        source=source,
    )


async def resolve_context(
    conn,
    prompt: str,
    manual: Optional[Dict[str, Any]] = None,
) -> Optional[ResolvedContext]:
    """Resolve an optional textbook context from filters and natural language."""
    manual = {key: value for key, value in (manual or {}).items() if value not in (None, "")}
    hints = extract_hints(prompt)
    explicit_book_id = manual.get("book_id")
    explicit_page_id = manual.get("page_id")
    page_number = manual.get("page_number") or hints.get("page_number")

    if explicit_book_id and (explicit_page_id or page_number):
        row = await _fetch_exact(conn, int(explicit_book_id), explicit_page_id, page_number)
        return _to_context(row, "manual")

    params: List[Any] = []
    query = "SELECT book_id, book_title, book_author, book_program, book_class FROM book WHERE TRUE"
    if explicit_book_id:
        params.append(int(explicit_book_id))
        query += f" AND book_id = ${len(params)}"
    selected_class = manual.get("book_class") or hints.get("book_class")
    if selected_class:
        params.append(int(selected_class))
        query += f" AND book_class = ${len(params)}"
    if manual.get("book_program"):
        params.append(manual["book_program"])
        query += f" AND book_program ILIKE ${len(params)}"
    query += " ORDER BY created_at DESC LIMIT 200"
    books = await conn.fetch(query, *params)

    scored = sorted(
        ((_book_score(book, hints, manual), book) for book in books),
        key=lambda item: item[0], reverse=True,
    )
    selected_book = scored[0][1] if scored and (scored[0][0] > 0 or manual or selected_class) else None

    if selected_book:
        selected_searchable = " ".join([
            selected_book["book_title"] or "", selected_book["book_author"] or "",
            selected_book["book_program"] or "",
        ]).lower()
        selected_latin = _transliterate(selected_searchable)
        has_named_book_hint = any(
            token in selected_searchable or token in selected_latin
            for token in hints.get("tokens", [])
        )
        natural_source = (
            "natural_language_explicit"
            if page_number or hints.get("paragraph") or has_named_book_hint
            else "natural_language"
        )
        exact = await _fetch_exact(conn, selected_book["book_id"], explicit_page_id, page_number)
        if exact and (page_number or explicit_page_id):
            return _to_context(exact, "manual" if manual else natural_source)

        terms = hints.get("tokens", [])[:5]
        if hints.get("paragraph"):
            terms.insert(0, f"параграф {hints['paragraph']}")
        if hints.get("exercise"):
            terms.insert(0, f"упражнение {hints['exercise']}")
        if manual.get("page_paragraph"):
            terms.insert(0, str(manual["page_paragraph"]))
        if not terms:
            return _to_context(
                await _fetch_exact(conn, selected_book["book_id"], None, None),
                "manual" if manual else natural_source,
            )
        page_query = """
            SELECT b.book_id, b.book_title, b.book_author, b.book_program, b.book_class,
                   p.page_id, p.page_number, p.page_paragraph, p.page_title,
                   p.page_markdown, p.page_text
            FROM page p JOIN book b ON b.book_id = p.book_id WHERE b.book_id = $1
        """
        page_params: List[Any] = [selected_book["book_id"]]
        if terms:
            conditions = []
            for term in terms:
                page_params.append(f"%{term}%")
                position = len(page_params)
                conditions.append(
                    f"(p.page_paragraph ILIKE ${position} OR p.page_title ILIKE ${position} "
                    f"OR p.page_text ILIKE ${position})"
                )
            page_query += " AND (" + " OR ".join(conditions) + ")"
        page_query += " ORDER BY p.page_number LIMIT 1"
        page = await conn.fetchrow(page_query, *page_params)
        if not page:
            page = await _fetch_exact(conn, selected_book["book_id"], None, None)
        return _to_context(page, "manual" if manual else natural_source)

    # No identifiable book: search page topics across the knowledge base.
    terms = hints.get("tokens", [])[:4]
    if not terms:
        return None
    page_params = []
    conditions = []
    for term in terms:
        page_params.append(f"%{term}%")
        position = len(page_params)
        conditions.append(
            f"(p.page_paragraph ILIKE ${position} OR p.page_title ILIKE ${position} "
            f"OR p.page_text ILIKE ${position})"
        )
    page = await conn.fetchrow(
        """
        SELECT b.book_id, b.book_title, b.book_author, b.book_program, b.book_class,
               p.page_id, p.page_number, p.page_paragraph, p.page_title,
               p.page_markdown, p.page_text
        FROM page p JOIN book b ON b.book_id = p.book_id
        WHERE """ + " OR ".join(conditions) + " ORDER BY p.page_id DESC LIMIT 1",
        *page_params,
    )
    return _to_context(page, "natural_language")


async def load_locked_context(conn, session: Any) -> Optional[ResolvedContext]:
    if not session or session["context_locked"] is not True or not session["book_id"]:
        return None
    row = await _fetch_exact(conn, session["book_id"], session["page_id"], None)
    return _to_context(row, "locked")
