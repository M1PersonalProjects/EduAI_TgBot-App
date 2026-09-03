from typing import Optional

from aiogram.types import BufferedInputFile

from services.core.response_formatter import format_for_telegram

TELEGRAM_TEXT_LIMIT = 4000
LONG_ANSWER_FILENAME = "umnix-answer.txt"
LONG_ANSWER_CAPTION = (
    "📄 Ответ ИИ-тьютора не помещается в одно текстовое сообщение Telegram. "
    "Полный ответ — в этом файле."
)
EMPTY_ANSWER_FALLBACK = (
    "Не удалось сформировать текстовый ответ. "
    "Попробуйте повторить или немного переформулировать вопрос."
)


def _safe_telegram_payload(text: str) -> str:
    """
    Формирует безопасный текст для отправки в Telegram, удаляя LaTeX и обрезая пустые строки.
    """
    raw = str(text or "").strip() or EMPTY_ANSWER_FALLBACK
    return format_for_telegram(raw).strip() or EMPTY_ANSWER_FALLBACK


def _text_document(text: str) -> BufferedInputFile:
    """
    Создаёт BufferedInputFile из текстового ответа для отправки в Telegram как документа.
    """
    return BufferedInputFile(text.encode("utf-8"), filename=LONG_ANSWER_FILENAME)


async def answer_plain(message, text: str, reply_markup: Optional[object] = None):
    """
    Отправляет один Telegram-объект: короткий текст или текстовый документ для длинного ответа.
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
    """
    Отправляет один Telegram-объект: короткий текст или текстовый документ для длинного ответа.
    """
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
