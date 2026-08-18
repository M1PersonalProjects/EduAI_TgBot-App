from typing import List, Optional

from aiogram.types import BufferedInputFile

from services.response_formatter import (
    contains_raw_latex,
    is_complex_formula,
    render_formula_png,
    telegram_formula_fallback,
    telegram_parts,
    telegram_safe_text,
)

TELEGRAM_TEXT_LIMIT = 4000


def split_telegram_text(
    text: str,
    limit: int = TELEGRAM_TEXT_LIMIT,
) -> List[str]:
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


async def answer_plain(
    message,
    text: str,
    reply_markup: Optional[object] = None,
):
    """
    Send Telegram content safely.

    Telegram never receives:
    - an empty string;
    - whitespace-only text;
    - raw LaTeX when math formatting is required.
    """

    raw_text = str(text or "")

    if not raw_text.strip():
        raw_text = (
            "Не удалось сформировать текстовый ответ. "
            "Попробуйте повторить или немного переформулировать вопрос."
        )

    # Ordinary text

    if not contains_raw_latex(raw_text):
        chunks = [
            chunk
            for chunk in split_telegram_text(raw_text)
            if str(chunk or "").strip()
        ]

        if not chunks:
            chunks = [
                "Не удалось сформировать текстовый ответ. "
                "Попробуйте повторить вопрос."
            ]

        sent = None

        for index, chunk in enumerate(chunks):
            safe_chunk = telegram_safe_text(chunk).strip()

            if not safe_chunk:
                continue

            markup = (
                reply_markup
                if index == len(chunks) - 1
                else None
            )

            sent = await message.answer(
                safe_chunk,
                reply_markup=markup,
                parse_mode=None,
            )

        return sent

    # Markdown / LaTeX-aware response

    parts = telegram_parts(raw_text)

    sendable = []

    for part in parts:
        content = str(part.content or "")

        if part.kind == "formula":
            if not content.strip():
                continue

            if is_complex_formula(content):
                png = render_formula_png(content)

                if png:
                    sendable.append(
                        ("photo", png, content)
                    )
                else:
                    fallback = telegram_formula_fallback(
                        content
                    )

                    if str(fallback or "").strip():
                        sendable.append(
                            ("text", fallback, "")
                        )

            else:
                fallback = telegram_formula_fallback(
                    content
                )

                if str(fallback or "").strip():
                    sendable.append(
                        ("text", fallback, "")
                    )

        else:
            if content.strip():
                sendable.append(
                    ("text", content, "")
                )

    # Split large text parts

    expanded = []

    for kind, payload, extra in sendable:

        if kind == "text":
            for chunk in split_telegram_text(payload):
                safe_chunk = telegram_safe_text(chunk).strip()

                if safe_chunk:
                    expanded.append(
                        ("text", safe_chunk, "")
                    )

        else:
            expanded.append(
                (kind, payload, extra)
            )

    # Absolute last-resort fallback

    if not expanded:
        expanded = [
            (
                "text",
                (
                    "Не удалось отобразить ответ. "
                    "Попробуйте повторить вопрос."
                ),
                "",
            )
        ]

    sent = None

    for index, (kind, payload, extra) in enumerate(
        expanded
    ):
        markup = (
            reply_markup
            if index == len(expanded) - 1
            else None
        )

        if kind == "photo":
            sent = await message.answer_photo(
                BufferedInputFile(
                    payload,
                    filename="formula.png",
                ),
                caption=None,
                reply_markup=markup,
            )

        else:
            safe_payload = telegram_safe_text(payload).strip()

            if not safe_payload:
                continue

            sent = await message.answer(
                safe_payload,
                reply_markup=markup,
                parse_mode=None,
            )

    return sent


async def send_plain_to_chat(
    bot,
    chat_id: int,
    text: str,
    reply_markup: Optional[object] = None,
):
    """Send generated/user-derived content to an arbitrary Telegram chat safely.

    Use this instead of ``bot.send_message`` whenever the payload may contain
    AI-generated mathematics. Unlike ``answer_plain`` there is no source
    ``Message`` object, so formulas use the human-readable Telegram fallback
    rather than image rendering. The important invariant is the same: raw TeX
    commands never reach Telegram.
    """
    raw_text = str(text or "").strip() or (
        "Не удалось сформировать текстовый ответ. Попробуйте повторить запрос."
    )
    safe_text = telegram_safe_text(raw_text).strip() or (
        "Не удалось отобразить ответ. Попробуйте повторить запрос."
    )
    chunks = split_telegram_text(safe_text) or [safe_text]
    sent = None
    for index, chunk in enumerate(chunks):
        payload = telegram_safe_text(chunk).strip()
        if not payload:
            continue
        kwargs = {
            "chat_id": chat_id,
            "text": payload,
            "parse_mode": None,
        }
        if index == len(chunks) - 1 and reply_markup is not None:
            kwargs["reply_markup"] = reply_markup
        sent = await bot.send_message(**kwargs)
    return sent
