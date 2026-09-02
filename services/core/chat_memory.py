import inspect
import json
import re
from dataclasses import asdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from services.attachment_storage import get_attachment, load_attachment_for_ai

SHORT_TERM_MESSAGES = 10
MAX_HISTORY_CHARS = 36000
MAX_OLD_MESSAGE_CHARS = 12000
MAX_ATTACHMENT_TEXT_CHARS = 18000
MAX_RELEVANT_ATTACHMENTS = 3
MAX_IMAGE_ATTACHMENTS = 2

REFERENCE_MARKERS = (
    "это", "этот", "эта", "эту", "то задание", "тот пример", "следующ", "предыдущ",
    "перв", "втор", "трет", "четвер", "пят", "вернемся", "вернёмся", "из файла",
    "в файле", "в документе", "в нём", "в нем", "фото", "фотограф", "таблиц", "тот файл",
    "этот файл", "этот документ", "похож", "усложни его", "проверь мой ответ",
)

TASK_WORDS = {
    "первое": 1, "первый": 1, "первому": 1,
    "второе": 2, "второй": 2, "второму": 2,
    "третье": 3, "третий": 3, "третьему": 3,
    "четвертое": 4, "четвёртое": 4, "четвертый": 4, "четвёртый": 4,
    "пятое": 5, "пятый": 5,
}


def query_tokens(value: str, limit: int = 16) -> List[str]:
    tokens = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9]+", value or "")
    stop = {
        "который", "которая", "которое", "которые", "пожалуйста", "теперь", "давай",
        "сделай", "объясни", "проверь", "помоги", "можно", "нужно", "задание", "пример",
    }
    result: List[str] = []
    for token in tokens:
        normalized = token.lower().replace("ё", "е")
        if len(normalized) < 4 or normalized in stop or normalized in result:
            continue
        result.append(normalized)
        if len(result) >= limit:
            break
    return result


def has_context_reference(text: str) -> bool:
    lowered = (text or "").lower().replace("ё", "е")
    return any(marker.replace("ё", "е") in lowered for marker in REFERENCE_MARKERS)


def detect_task_number(text: str, previous: Optional[int] = None) -> Optional[int]:
    lowered = (text or "").lower().replace("ё", "е")
    explicit = re.search(r"(?:№|номер\s*)\s*(\d{1,3})", lowered)
    if explicit:
        return int(explicit.group(1))
    for word, number in TASK_WORDS.items():
        if word.replace("ё", "е") in lowered:
            return number
    if "следующ" in lowered and previous:
        return previous + 1
    if "предыдущ" in lowered and previous and previous > 1:
        return previous - 1
    return previous


def detect_topic(text: str) -> Optional[str]:
    value = (text or "").strip()
    patterns = [
        r"(?:тема|тему)\s*[«\"']([^»\"']{2,120})[»\"']",
        r"(?:разбер[её]м|изучаем|объясни тему)\s+([^.?!\n]{2,100})",
    ]
    for pattern in patterns:
        match = re.search(pattern, value, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip(" .,:;—-")[:120] or None
    return None


def looks_like_task_set(text: str) -> bool:
    value = text or ""
    numbered = re.findall(r"(?:^|\n)\s*(\d{1,2})[.)]\s+", value)
    return len(set(numbered)) >= 3


def attachment_score(row: Dict[str, Any], query: str, *, newest_rank: int = 0) -> int:
    score = max(0, 8 - newest_rank)
    lowered = (query or "").lower().replace("ё", "е")
    name = str(row.get("original_name") or "").lower().replace("ё", "е")
    mime = str(row.get("mime_type") or "").lower()
    extracted = str(row.get("extracted_text") or "").lower().replace("ё", "е")

    if name and name in lowered:
        score += 30
    stem = re.sub(r"\.[a-z0-9]{1,8}$", "", name)
    if len(stem) >= 4 and stem in lowered:
        score += 20
    if "pdf" in lowered and ("pdf" in mime or name.endswith(".pdf")):
        score += 8
    if any(word in lowered for word in ("фото", "фотограф", "картин", "изображ")) and mime.startswith("image/"):
        score += 12
    if any(word in lowered for word in ("файл", "документ", "вложен")):
        score += 5

    for token in query_tokens(query):
        if token in name:
            score += 8
        elif token in extracted:
            score += 2
    return score


def _json_safe_value(value: Any) -> Any:
    """Return a JSON-safe representation for persisted session memory.

    Database values are already primitive, but AsyncMock-based tests can expose
    awaitables or mock objects through unstubbed calls. Those values are not
    factual session state and must never be persisted.
    """
    if inspect.isawaitable(value):
        # A coroutine created by an unstubbed AsyncMock must not leak and cause
        # RuntimeWarning: coroutine was never awaited.
        close = getattr(value, "close", None)
        if callable(close):
            close()
        return None
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): safe for k, v in value.items() if (safe := _json_safe_value(v)) is not None}
    if isinstance(value, (list, tuple, set)):
        return [safe for item in value if (safe := _json_safe_value(item)) is not None]
    return None


def _safe_int(value: Any) -> Optional[int]:
    if inspect.isawaitable(value):
        close = getattr(value, "close", None)
        if callable(close):
            close()
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def update_state_dict(
    state: Optional[Dict[str, Any]],
    *,
    message_text: str,
    message_id: int,
    book_id: Optional[int] = None,
    page_id: Optional[int] = None,
    referenced_attachment_ids: Optional[Sequence[int]] = None,
) -> Dict[str, Any]:
    safe_state = _json_safe_value(state or {})
    result = dict(safe_state) if isinstance(safe_state, dict) else {}
    safe_message_id = _safe_int(message_id)
    topic = detect_topic(message_text)
    if topic:
        result["current_topic"] = topic
    is_task_set = looks_like_task_set(message_text)
    lowered = (message_text or "").lower().replace("ё", "е")
    should_pin = (
        is_task_set
        or len(message_text or "") >= 1200
        or any(marker in lowered for marker in (
            "решаем задачу", "вот блок", "по очереди", "вернемся к этой задаче",
            "это исходное условие", "вот список заданий"
        ))
    )
    if should_pin and safe_message_id is not None:
        pinned = [int(x) for x in result.get("pinned_message_ids") or [] if str(x).isdigit()]
        if safe_message_id not in pinned:
            pinned.append(safe_message_id)
        result["pinned_message_ids"] = pinned[-6:]
    if is_task_set:
        if safe_message_id is not None:
            result["active_task_set_message_id"] = safe_message_id
        result["current_task_number"] = 1
    else:
        number = detect_task_number(message_text, result.get("current_task_number"))
        if number:
            result["current_task_number"] = number

    if any(marker in lowered for marker in (
        "по очереди", "не давай готов", "только подсказ", "сначала дай подсказ",
        "не показывай ответ", "помоги мне решить самостоятельно"
    )):
        notes = [str(x) for x in result.get("important_user_notes") or []]
        note = " ".join((message_text or "").split())[:500]
        if note and note not in notes:
            notes.append(note)
        result["important_user_notes"] = notes[-5:]
    safe_book_id = _safe_int(book_id)
    safe_page_id = _safe_int(page_id)
    if safe_book_id is not None:
        result["current_book_id"] = safe_book_id
    if safe_page_id is not None:
        result["current_page_id"] = safe_page_id
    if referenced_attachment_ids:
        safe_attachment_ids = []
        for value in referenced_attachment_ids:
            safe_value = _safe_int(value)
            if safe_value is not None and safe_value not in safe_attachment_ids:
                safe_attachment_ids.append(safe_value)
        if safe_attachment_ids:
            result["referenced_attachment_ids"] = safe_attachment_ids[:8]
    if safe_message_id is not None:
        result["last_user_message_id"] = safe_message_id
    return result


def build_memory_summary(state: Dict[str, Any], pinned_messages: Sequence[Dict[str, Any]]) -> str:
    lines = ["Conversation state (internal, factual only):"]
    mapping = [
        ("current_topic", "Current topic"),
        ("current_book_id", "Current book_id"),
        ("current_page_id", "Current page_id"),
        ("active_task_set_message_id", "Active task-set message_id"),
        ("current_task_number", "Current task number"),
        ("referenced_attachment_ids", "Referenced attachment_ids"),
        ("pinned_message_ids", "Pinned message_ids"),
        ("important_user_notes", "Important user notes"),
    ]
    for key, label in mapping:
        value = state.get(key)
        if value not in (None, "", []):
            lines.append(f"- {label}: {value}")
    for item in pinned_messages[:3]:
        snippet = " ".join(str(item.get("message_text") or "").split())[:700]
        if snippet:
            lines.append(f"- Important earlier message {item.get('message_id')}: {snippet}")
    lines.append("Do not invent missing history. If a reference remains ambiguous, ask a concise clarification question.")
    return "\n".join(lines)[:5000]


async def load_session_state(conn, user_id: int, session_id) -> Tuple[Dict[str, Any], str]:
    row = await conn.fetchrow(
        """
        SELECT memory_state, memory_summary
        FROM chat_sessions
        WHERE session_id=$1 AND user_id=$2
        """,
        session_id,
        user_id,
    )
    if not row:
        raise LookupError("Чат не найден")

    try:
        raw_state = row["memory_state"]
    except (KeyError, TypeError, AttributeError):
        raw_state = None
    state = _json_safe_value(raw_state)
    if isinstance(state, str):
        try:
            state = json.loads(state)
        except (TypeError, ValueError):
            state = {}
    if not isinstance(state, dict):
        state = {}

    try:
        raw_summary = row["memory_summary"]
    except (KeyError, TypeError, AttributeError):
        raw_summary = None
    safe_summary = _json_safe_value(raw_summary)
    summary = safe_summary if isinstance(safe_summary, str) else ""
    return dict(state), summary


async def persist_session_state(conn, user_id: int, session_id, state: Dict[str, Any], summary: str = "") -> None:
    safe_state = _json_safe_value(state)
    if not isinstance(safe_state, dict):
        safe_state = {}
    await conn.execute(
        """
        UPDATE chat_sessions
        SET memory_state=$1::jsonb,
            memory_summary=CASE WHEN $2 <> '' THEN $2 ELSE memory_summary END,
            memory_updated_at=CURRENT_TIMESTAMP,
            updated_at=CURRENT_TIMESTAMP
        WHERE session_id=$3 AND user_id=$4
        """,
        json.dumps(safe_state, ensure_ascii=False),
        summary,
        session_id,
        user_id,
    )


async def load_context_messages(conn, user_id: int, session_id, current_query: str) -> List[Dict[str, Any]]:
    """Return exactly the short-term window for the current chat session.

    Long-lived attachment memory is handled independently through
    ``session_attachments``. Session state/summary may preserve factual pointers,
    but older chat rows are not silently re-injected into the LLM short-term
    history. The current user message is already stored before this function is
    called, so it is naturally part of the last 10 rows.
    """
    rows = await conn.fetch(
        """
        SELECT message_id, sender, message_text, created_at
        FROM chat_messages
        WHERE user_id=$1 AND session_id=$2
        ORDER BY created_at DESC, message_id DESC
        LIMIT $3
        """,
        user_id,
        session_id,
        SHORT_TERM_MESSAGES,
    )
    return [dict(row) for row in reversed(rows)]


async def session_attachments(
    conn,
    user_id: int,
    session_id,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Load every still-linked attachment for one chat session.

    The relationship is session-scoped through ``chat_message_attachments`` and
    ``chat_messages``. We intentionally do not impose a default LIMIT: old files
    must remain discoverable even after a long conversation. Duplicate links to
    the same attachment are collapsed in Python while preserving newest-first
    order.
    """
    query = """
        SELECT a.attachment_id, a.owner_id, a.original_name, a.storage_path,
               a.mime_type, a.extension, a.size_bytes, a.extracted_text,
               a.processing_status, a.created_at, cma.message_id, cm.created_at AS message_created_at
        FROM chat_message_attachments cma
        JOIN chat_messages cm ON cm.message_id=cma.message_id
        JOIN attachments a ON a.attachment_id=cma.attachment_id
        WHERE cm.user_id=$1 AND cm.session_id=$2 AND a.owner_id=$1
        ORDER BY cm.created_at DESC, cma.sort_order ASC, a.attachment_id DESC
    """
    rows = await conn.fetch(query, user_id, session_id)
    result: List[Dict[str, Any]] = []
    seen = set()
    for row in rows:
        item = dict(row)
        attachment_id = int(item["attachment_id"])
        if attachment_id in seen:
            continue
        seen.add(attachment_id)
        result.append(item)
        if limit is not None and len(result) >= max(0, int(limit)):
            break
    return result


def _attachment_type_matches(row: Dict[str, Any], query: str) -> bool:
    lowered = (query or "").casefold().replace("ё", "е")
    name = str(row.get("original_name") or "").casefold()
    mime = str(row.get("mime_type") or "").casefold()
    ext = str(row.get("extension") or "").casefold().lstrip(".")
    if "pdf" in lowered:
        return mime == "application/pdf" or name.endswith(".pdf") or ext == "pdf"
    if any(token in lowered for token in ("фото", "фотограф", "картин", "изображ", "скрин")):
        return mime.startswith("image/")
    if any(token in lowered for token in ("docx", "word")):
        return ext in {"doc", "docx"} or "word" in mime
    if any(token in lowered for token in ("таблиц", "xlsx", "excel")):
        return ext in {"xls", "xlsx", "csv"} or "spreadsheet" in mime or "excel" in mime
    return True


def _prefer_oldest_attachment(query: str) -> bool:
    lowered = (query or "").casefold().replace("ё", "е")
    return any(marker in lowered for marker in (
        "в начале", "самом начале", "первый файл", "первый pdf",
        "первый документ", "давно", "раньше присыл", "старый файл",
    ))


async def select_relevant_attachments(
    conn,
    user_id: int,
    session_id,
    query: str,
    *,
    available_rows: Optional[Sequence[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    rows = list(available_rows) if available_rows is not None else await session_attachments(
        conn, user_id, session_id
    )
    if not rows:
        return []

    state, _ = await load_session_state(conn, user_id, session_id)
    active_ids = set(int(x) for x in state.get("referenced_attachment_ids") or [] if str(x).isdigit())
    scored = []
    for rank, row in enumerate(rows):
        score = attachment_score(row, query, newest_rank=rank)
        if int(row["attachment_id"]) in active_ids:
            score += 15
        if not _attachment_type_matches(row, query):
            score -= 20
        scored.append((score, rank, row))
    scored.sort(key=lambda item: (-item[0], item[1]))

    reference = has_context_reference(query)
    selected = [row for score, _, row in scored if score >= (6 if reference else 10)][:MAX_RELEVANT_ATTACHMENTS]

    if reference and not selected:
        matching = [row for row in rows if _attachment_type_matches(row, query)]
        if matching:
            selected = [matching[-1] if _prefer_oldest_attachment(query) else matching[0]]

    # Natural references such as "Вернёмся к PDF, который я присылал в начале"
    # should honor the temporal clue even when recency scoring favored another file.
    if reference and _prefer_oldest_attachment(query):
        matching = [row for row in rows if _attachment_type_matches(row, query)]
        if matching:
            oldest = matching[-1]
            selected = [oldest] + [
                row for row in selected if int(row["attachment_id"]) != int(oldest["attachment_id"])
            ]
            selected = selected[:MAX_RELEVANT_ATTACHMENTS]
    return selected


def attachment_inventory(rows: Sequence[Dict[str, Any]]) -> str:
    """Metadata-only inventory for reference resolution; never sends file binaries."""
    items = []
    for row in rows:
        name = str(row.get("original_name") or f"attachment-{row.get('attachment_id')}").strip()
        mime = str(row.get("mime_type") or row.get("extension") or "file").strip()
        items.append(f"- attachment_id={row.get('attachment_id')}: {name} ({mime})")
    if not items:
        return ""
    return "Files attached to this chat (metadata only):\n" + "\n".join(items)


async def build_attachment_context(selected: Sequence[Dict[str, Any]], query: str = "") -> Tuple[str, List[str]]:
    text_blocks: List[str] = []
    image_urls: List[str] = []
    remaining = MAX_ATTACHMENT_TEXT_CHARS
    image_count = 0
    for row in selected:
        text = str(row.get("extracted_text") or "").strip()
        if text and remaining > 0:
            block = f"[Attachment {row['attachment_id']}: {row['original_name']}]\n{text[:remaining]}"
            text_blocks.append(block)
            remaining -= len(block)
        mime = str(row.get("mime_type") or "")
        lowered_query = (query or "").lower().replace("ё", "е")
        wants_visual_pdf = mime == "application/pdf" and (
            not text
            or any(token in lowered_query for token in ("таблиц", "рисунк", "схем", "изображ", "скан", "страниц"))
        )
        if (mime.startswith("image/") or wants_visual_pdf) and image_count < MAX_IMAGE_ATTACHMENTS:
            parsed = await load_attachment_for_ai(row)
            if parsed.image_data_urls:
                image_urls.extend(parsed.image_data_urls[:1])
                image_count += 1
    return "\n\n".join(text_blocks), image_urls[:MAX_IMAGE_ATTACHMENTS]


async def message_attachments_payload(conn, user_id: int, message_ids: Iterable[int]) -> Dict[int, List[Dict[str, Any]]]:
    ids = [int(x) for x in message_ids]
    if not ids:
        return {}
    rows = await conn.fetch(
        """
        SELECT cma.message_id, a.attachment_id, a.original_name, a.mime_type,
               a.extension, a.size_bytes, a.processing_status, a.created_at
        FROM chat_message_attachments cma
        JOIN chat_messages cm ON cm.message_id=cma.message_id
        JOIN attachments a ON a.attachment_id=cma.attachment_id
        WHERE cma.message_id=ANY($1::int[])
          AND cm.user_id=$2
          AND a.owner_id=$2
        ORDER BY cma.message_id, cma.sort_order, a.attachment_id
        """,
        ids,
        user_id,
    )
    result: Dict[int, List[Dict[str, Any]]] = {}
    for raw in rows:
        row = dict(raw)
        attachment_id = row["attachment_id"]
        payload = {
            "attachment_id": attachment_id,
            "original_name": row["original_name"],
            "mime_type": row["mime_type"],
            "extension": row["extension"],
            "size_bytes": row["size_bytes"],
            "processing_status": row["processing_status"],
            "created_at": row["created_at"],
            "download_url": f"/api/v1/attachments/{attachment_id}/download",
            "preview_url": f"/api/v1/attachments/{attachment_id}/preview",
        }
        result.setdefault(row["message_id"], []).append(payload)
    return result
