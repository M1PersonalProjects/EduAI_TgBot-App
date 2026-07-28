import asyncio
import re
import uuid
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

from config import settings
from database import db
from services.context_resolver import ResolvedContext, load_locked_context, resolve_context
from services.file_parser import ParsedAttachment


openai_client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())


def _session_uuid(session_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(session_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise LookupError("Некорректный идентификатор чата") from exc


def clean_ai_text(value: Optional[str]) -> str:
    text = str(value or "").replace("$", "")
    text = text.replace("\\(", "").replace("\\)", "")
    text = text.replace("\\[", "").replace("\\]", "")
    text = re.sub(r"\\frac\{([^{}]+)\}\{([^{}]+)\}", r"(\1)/(\2)", text)
    text = re.sub(r"\\sqrt\{([^{}]+)\}", r"√(\1)", text)
    text = re.sub(r"\\(?:begin|end)\{[^}]+\}", "", text)
    return re.sub(r"\\[A-Za-z]+\*?", "", text).strip()


def book_mode_footer(context: ResolvedContext) -> str:
    return (
        f"\n\n---\n💡 Вы сейчас задаёте вопросы по «{context.label}». "
        "Чтобы выйти из режима учебника и задавать общие вопросы, отправьте /exit_book "
        "или нажмите кнопку «Выйти из Book Mode»."
    )


async def ensure_session(conn, user_id: int, session_id: Optional[str] = None):
    if session_id:
        parsed_id = _session_uuid(session_id)
        session = await conn.fetchrow(
            """
            SELECT session_id, user_id, title, book_id, page_id, context_locked,
                   created_at, updated_at
            FROM chat_sessions WHERE session_id = $1 AND user_id = $2
            """,
            parsed_id,
            user_id,
        )
        if not session:
            raise LookupError("Чат не найден")
        return session

    session = await conn.fetchrow(
        """
        SELECT session_id, user_id, title, book_id, page_id, context_locked,
               created_at, updated_at
        FROM chat_sessions WHERE user_id = $1 ORDER BY updated_at DESC LIMIT 1
        """,
        user_id,
    )
    if not session:
        new_id = uuid.uuid4()
        session = await conn.fetchrow(
            """
            INSERT INTO chat_sessions (session_id, user_id, title)
            VALUES ($1, $2, 'Новый чат')
            RETURNING session_id, user_id, title, book_id, page_id, context_locked,
                      created_at, updated_at
            """,
            new_id,
            user_id,
        )
        await conn.execute(
            "UPDATE chat_messages SET session_id = $1 WHERE user_id = $2 AND session_id IS NULL",
            new_id,
            user_id,
        )
    return session


async def create_session(user_id: int, title: str = "Новый чат") -> Dict[str, Any]:
    session_id = uuid.uuid4()
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO chat_sessions (session_id, user_id, title)
            VALUES ($1, $2, $3)
            RETURNING session_id, user_id, title, book_id, page_id, context_locked,
                      created_at, updated_at
            """,
            session_id,
            user_id,
            (title.strip() or "Новый чат")[:35],
        )
    return dict(row)


async def list_sessions(user_id: int) -> List[Dict[str, Any]]:
    async with db.pool.acquire() as conn:
        await ensure_session(conn, user_id)
        rows = await conn.fetch(
            """
            SELECT s.session_id, s.title, s.book_id, s.page_id, s.context_locked,
                   s.created_at, s.updated_at, COUNT(m.message_id) AS message_count,
                   b.book_title, p.page_number
            FROM chat_sessions s
            LEFT JOIN chat_messages m ON m.session_id = s.session_id
            LEFT JOIN book b ON b.book_id = s.book_id
            LEFT JOIN page p ON p.page_id = s.page_id
            WHERE s.user_id = $1
            GROUP BY s.session_id, b.book_title, p.page_number
            ORDER BY s.updated_at DESC
            """,
            user_id,
        )
    return [dict(row) for row in rows]


async def rename_session(user_id: int, session_id: str, title: str) -> Dict[str, Any]:
    clean_title = title.strip()
    if not clean_title or len(clean_title) > 35:
        raise ValueError("Название должно содержать от 1 до 35 символов")
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE chat_sessions SET title = $1, updated_at = CURRENT_TIMESTAMP
            WHERE session_id = $2 AND user_id = $3
            RETURNING session_id, title, book_id, page_id, context_locked, updated_at
            """,
            clean_title,
            _session_uuid(session_id),
            user_id,
        )
    if not row:
        raise LookupError("Чат не найден")
    return dict(row)


async def delete_session(user_id: int, session_id: str) -> None:
    async with db.pool.acquire() as conn:
        deleted = await conn.fetchval(
            "DELETE FROM chat_sessions WHERE session_id = $1 AND user_id = $2 RETURNING session_id",
            _session_uuid(session_id),
            user_id,
        )
    if not deleted:
        raise LookupError("Чат не найден")


async def get_messages(user_id: int, session_id: str) -> List[Dict[str, Any]]:
    async with db.pool.acquire() as conn:
        session = await ensure_session(conn, user_id, session_id)
        rows = await conn.fetch(
            """
            SELECT message_id, sender, message_text, attachment_name, attachment_type, created_at
            FROM chat_messages WHERE user_id = $1 AND session_id = $2
            ORDER BY created_at ASC LIMIT 500
            """,
            user_id,
            session["session_id"],
        )
    return [dict(row) for row in rows]


async def lock_context(
    user_id: int,
    session_id: str,
    manual_context: Dict[str, Any],
) -> ResolvedContext:
    async with db.pool.acquire() as conn:
        session = await ensure_session(conn, user_id, session_id)
        context = await resolve_context(conn, "", manual_context)
        if not context:
            raise LookupError("Не удалось найти выбранный учебный контекст")
        await conn.execute(
            """
            UPDATE chat_sessions SET book_id = $1, page_id = $2, context_locked = TRUE,
                   updated_at = CURRENT_TIMESTAMP
            WHERE session_id = $3
            """,
            context.book_id,
            context.page_id,
            session["session_id"],
        )
    context.source = "locked"
    return context


async def exit_book_mode(user_id: int, session_id: Optional[str] = None) -> Dict[str, Any]:
    async with db.pool.acquire() as conn:
        session = await ensure_session(conn, user_id, session_id)
        row = await conn.fetchrow(
            """
            UPDATE chat_sessions SET book_id = NULL, page_id = NULL, context_locked = FALSE,
                   updated_at = CURRENT_TIMESTAMP
            WHERE session_id = $1
            RETURNING session_id, title, context_locked
            """,
            session["session_id"],
        )
    return dict(row)


def _system_prompt(role: str, context: Optional[ResolvedContext]) -> str:
    if role == "student":
        prompt = (
            "Ты — терпеливый школьный ИИ-тьютор и сократовский наставник. "
            "Объясняй по шагам, сначала задавай наводящие вопросы и не выдавай готовый ответ сразу."
        )
    else:
        prompt = (
            "Ты — универсальный образовательный ИИ-тьютор для родителя. "
            "Объясняй темы по шагам, а по просьбе помогай создавать задания и тесты для детей."
        )
    prompt += (
        " Отвечай по-русски. Используй только обычный текст и Markdown. "
        "LaTeX, символы $ и служебная математическая разметка запрещены."
    )
    if context:
        prompt += (
            f"\n\nКонтекст учебника: {context.book_title}, автор {context.book_author}, "
            f"{context.book_class} класс, {context.book_program}"
        )
        if context.page_number:
            prompt += f", страница {context.page_number}"
        if context.page_paragraph:
            prompt += f", параграф {context.page_paragraph}"
        prompt += f".\nМатериал страницы:\n{clean_ai_text(context.content)}"
    return prompt


async def respond(
    user_id: int,
    role: str,
    message_text: str,
    session_id: Optional[str] = None,
    attachment: Optional[ParsedAttachment] = None,
    manual_context: Optional[Dict[str, Any]] = None,
    lock_selected_context: bool = False,
) -> Dict[str, Any]:
    clean_text = clean_ai_text(message_text) or "Проанализируй вложение и помоги разобраться."
    async with db.pool.acquire() as conn:
        session = await ensure_session(conn, user_id, session_id)
        locked_context = await load_locked_context(conn, session)
        if locked_context and not locked_context.page_id:
            context = await resolve_context(
                conn, clean_text, {"book_id": locked_context.book_id}
            ) or locked_context
            locked_context = context
        else:
            context = locked_context or await resolve_context(conn, clean_text, manual_context)
        should_lock_context = lock_selected_context or (
            context is not None and context.source == "natural_language_explicit"
        )
        if should_lock_context and context and not locked_context:
            await conn.execute(
                """
                UPDATE chat_sessions SET book_id=$1, page_id=$2, context_locked=TRUE,
                       updated_at=CURRENT_TIMESTAMP WHERE session_id=$3
                """,
                context.book_id,
                context.page_id,
                session["session_id"],
            )
            context.source = "locked"
            locked_context = context

        message_id = await conn.fetchval(
            """
            INSERT INTO chat_messages
                (user_id, session_id, sender, message_text, attachment_name, attachment_type)
            VALUES ($1, $2, 'user', $3, $4, $5) RETURNING message_id
            """,
            user_id,
            session["session_id"],
            clean_text,
            attachment.filename if attachment else None,
            attachment.mime_type if attachment else None,
        )
        history = await conn.fetch(
            """
            SELECT message_id, sender, message_text FROM chat_messages
            WHERE user_id=$1 AND session_id=$2 ORDER BY created_at DESC LIMIT 16
            """,
            user_id,
            session["session_id"],
        )

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": _system_prompt(role, context)}
    ]
    for item in reversed(history):
        content: Any = item["message_text"]
        if item["message_id"] == message_id and attachment:
            attachment_note = ""
            if attachment.extracted_text:
                attachment_note = (
                    f"\n\nИзвлечённый текст из файла «{attachment.filename}»:\n"
                    f"{attachment.extracted_text}"
                )
            content = [{"type": "text", "text": item["message_text"] + attachment_note}]
            for image_url in attachment.image_data_urls[:3]:
                content.append({"type": "image_url", "image_url": {"url": image_url}})
        messages.append({
            "role": "user" if item["sender"] == "user" else "assistant",
            "content": content,
        })

    response = await asyncio.wait_for(
        openai_client.chat.completions.create(
            model="gpt-4o", messages=messages, temperature=0.35, max_tokens=2000
        ),
        timeout=120,
    )
    reply = clean_ai_text(response.choices[0].message.content)
    if locked_context:
        reply += book_mode_footer(locked_context)

    async with db.pool.acquire() as conn:
        ai_message_id = await conn.fetchval(
            """
            INSERT INTO chat_messages (user_id, session_id, sender, message_text)
            VALUES ($1, $2, 'ai', $3) RETURNING message_id
            """,
            user_id,
            session["session_id"],
            reply,
        )
        await conn.execute(
            "UPDATE chat_sessions SET updated_at=CURRENT_TIMESTAMP WHERE session_id=$1",
            session["session_id"],
        )
        if session["title"] == "Новый чат":
            generated_title = clean_text.replace("\n", " ")[:35].strip() or "Вложение"
            await conn.execute(
                "UPDATE chat_sessions SET title=$1 WHERE session_id=$2",
                generated_title,
                session["session_id"],
            )

    return {
        "message_id": ai_message_id,
        "session_id": str(session["session_id"]),
        "sender": "ai",
        "message_text": reply,
        "context": context.to_dict() if context else None,
        "book_mode": bool(locked_context),
    }
