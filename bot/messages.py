from typing import List, Optional

from aiogram.types import BufferedInputFile

from services.response_formatter import telegram_safe_text

# Telegram text messages are physically limited by the platform. Keep a little
# headroom below the documented 4096-character ceiling so entity/counting edge
# cases cannot turn a valid tutor reply into BadRequest: message is too long.
TELEGRAM_TEXT_LIMIT = 4000
LONG_ANSWER_FILENAME = "eduai-answer.txt"
LONG_ANSWER_CAPTION = (
    "📄 Ответ ИИ-тьютора не помещается в одно текстовое сообщение Telegram. "
    "Полный ответ — в этом файле."
)
EMPTY_ANSWER_FALLBACK = (
    "Не удалось сформировать текстовый ответ. "
    "Попробуйте повторить или немного переформулировать вопрос."
)


def split_telegram_text(text: str, limit: int = TELEGRAM_TEXT_LIMIT) -> List[str]:
    """Legacy utility kept for compatibility.

    AI-tutor delivery no longer uses this function: one user request must map to
    one Telegram object. Callers that explicitly need chunks for non-tutor UI
    may still use it.
    """
    remaining = str(text or "")
    chunks: List[str] = []
    while len(remaining) > limit:
        position = remaining.rfind("\n", 0, limit)
        if position < limit // 2:
            position = remaining.rfind(" ", 0, limit)
        if position < limit // 2:
            position = limit
        chunk = remaining[:position].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[position:].lstrip()
    tail = remaining.strip()
    if tail:
        chunks.append(tail)
    return chunks


def _safe_telegram_payload(text: str) -> str:
    raw = str(text or "").strip() or EMPTY_ANSWER_FALLBACK
    return telegram_safe_text(raw).strip() or EMPTY_ANSWER_FALLBACK


def _text_document(text: str) -> BufferedInputFile:
    return BufferedInputFile(text.encode("utf-8"), filename=LONG_ANSWER_FILENAME)


async def answer_plain(message, text: str, reply_markup: Optional[object] = None):
    """Send one logical tutor response as exactly one Telegram object.

    Short answers are one text message. If the safe Telegram representation is
    too long, the full answer is sent once as a UTF-8 text document instead of
    being fragmented into multiple sequential messages. Raw LaTeX is removed at
    this final boundary by ``telegram_safe_text``.
    """
    safe_text = _safe_telegram_payload(text)
    if len(safe_text) <= TELEGRAM_TEXT_LIMIT:
        return await message.answer(
            safe_text,
            reply_markup=reply_markup,
            parse_mode=None,
        )

    kwargs = {
        "document": _text_document(safe_text),
        "caption": LONG_ANSWER_CAPTION,
        "parse_mode": None,
    }
    if reply_markup is not None:
        kwargs["reply_markup"] = reply_markup
    return await message.answer_document(**kwargs)


async def send_plain_to_chat(
    bot,
    chat_id: int,
    text: str,
    reply_markup: Optional[object] = None,
):
    """Safe one-object delivery to an arbitrary Telegram chat."""
    safe_text = _safe_telegram_payload(text)
    if len(safe_text) <= TELEGRAM_TEXT_LIMIT:
        kwargs = {
            "chat_id": chat_id,
            "text": safe_text,
            "parse_mode": None,
        }
        if reply_markup is not None:
            kwargs["reply_markup"] = reply_markup
        return await bot.send_message(**kwargs)

    kwargs = {
        "chat_id": chat_id,
        "document": _text_document(safe_text),
        "caption": LONG_ANSWER_CAPTION,
        "parse_mode": None,
    }
    if reply_markup is not None:
        kwargs["reply_markup"] = reply_markup
    return await bot.send_document(**kwargs)
