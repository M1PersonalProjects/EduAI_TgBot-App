import inspect
import json
import re
from dataclasses import asdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from services.attachment_storage import get_attachment, load_attachment_for_ai

SHORT_TERM_MESSAGES = 24
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
    """Возвращает JSON-безопасное представление для сохраняемой памяти сеанса.

    Значения базы данных уже являются примитивными, но тесты на основе AsyncMock могут отображать
    ожидаемые или фиктивные объекты с помощью незаполненных вызовов. Эти значения не
    являются фактическим состоянием сеанса и никогда не должны сохраняться.
    """
    if inspect.isawaitable(value):
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
    recent_rows = await conn.fetch(
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
    recent = [dict(row) for row in reversed(recent_rows)]
    recent_ids = {row["message_id"] for row in recent}

    state, _ = await load_session_state(conn, user_id, session_id)
    pinned_ids = []
    active = state.get("active_task_set_message_id")
    candidates = list(state.get("pinned_message_ids") or [])
    if active:
        candidates.append(active)
    for candidate in candidates:
        try:
            candidate_id = int(candidate)
        except (TypeError, ValueError):
            continue
        if candidate_id not in recent_ids and candidate_id not in pinned_ids:
            pinned_ids.append(candidate_id)

    old: List[Dict[str, Any]] = []
    if pinned_ids:
        rows = await conn.fetch(
            """
            SELECT message_id, sender, message_text, created_at
            FROM chat_messages
            WHERE user_id=$1 AND session_id=$2 AND message_id=ANY($3::int[])
            ORDER BY created_at ASC, message_id ASC
            """,
            user_id,
            session_id,
            pinned_ids,
        )
        old.extend(dict(row) for row in rows)

    tokens = query_tokens(current_query)
    if (has_context_reference(current_query) or tokens) and recent:
        patterns = [f"%{token}%" for token in tokens[:8]]
        if patterns:
            rows = await conn.fetch(
                """
                SELECT message_id, sender, message_text, created_at
                FROM chat_messages
                WHERE user_id=$1 AND session_id=$2
                  AND message_id <> ALL($3::int[])
                  AND lower(replace(message_text, 'ё', 'е')) ILIKE ANY($4::text[])
                ORDER BY created_at DESC, message_id DESC
                LIMIT 6
                """,
                user_id,
                session_id,
                list(recent_ids) or [0],
                patterns,
            )
            old.extend(dict(row) for row in reversed(rows))

    dedup: Dict[int, Dict[str, Any]] = {}
    for item in old + recent:
        dedup[item["message_id"]] = item
    ordered = sorted(dedup.values(), key=lambda item: (item.get("created_at"), item["message_id"]))

    budget = MAX_HISTORY_CHARS
    result: List[Dict[str, Any]] = []
    for item in reversed(ordered):
        text = str(item.get("message_text") or "")
        limit = MAX_OLD_MESSAGE_CHARS if item["message_id"] not in recent_ids else 9000
        text = text[:limit]
        if not text:
            continue
        if len(text) > budget and result:
            continue
        copied = dict(item)
        copied["message_text"] = text[:budget]
        result.append(copied)
        budget -= len(copied["message_text"])
        if budget <= 0:
            break
    return list(reversed(result))


async def session_attachments(conn, user_id: int, session_id, limit: int = 50) -> List[Dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT a.attachment_id, a.owner_id, a.original_name, a.storage_path,
               a.mime_type, a.extension, a.size_bytes, a.extracted_text,
               a.processing_status, a.created_at, cma.message_id, cm.created_at AS message_created_at
        FROM chat_message_attachments cma
        JOIN chat_messages cm ON cm.message_id=cma.message_id
        JOIN attachments a ON a.attachment_id=cma.attachment_id
        WHERE cm.user_id=$1 AND cm.session_id=$2 AND a.owner_id=$1
        ORDER BY cm.created_at DESC, cma.sort_order ASC
        LIMIT $3
        """,
        user_id,
        session_id,
        limit,
    )
    return [dict(row) for row in rows]


async def select_relevant_attachments(conn, user_id: int, session_id, query: str) -> List[Dict[str, Any]]:
    rows = await session_attachments(conn, user_id, session_id)
    if not rows:
        return []
    state, _ = await load_session_state(conn, user_id, session_id)
    active_ids = set(int(x) for x in state.get("referenced_attachment_ids") or [])
    scored = []
    for rank, row in enumerate(rows):
        score = attachment_score(row, query, newest_rank=rank)
        if row["attachment_id"] in active_ids:
            score += 15
        scored.append((score, rank, row))
    scored.sort(key=lambda item: (-item[0], item[1]))

    reference = has_context_reference(query)
    selected = [row for score, _, row in scored if score >= (6 if reference else 10)][:MAX_RELEVANT_ATTACHMENTS]
    if not selected and reference:
        selected = [rows[0]]
    return selected


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
