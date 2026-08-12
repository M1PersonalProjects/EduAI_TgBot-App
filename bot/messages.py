from typing import List, Optional

from aiogram.types import BufferedInputFile

from services.response_formatter import (
    contains_raw_latex,
    is_complex_formula,
    render_formula_png,
    telegram_formula_fallback,
    telegram_parts,
)

TELEGRAM_TEXT_LIMIT = 4000


def split_telegram_text(text: str, limit: int = TELEGRAM_TEXT_LIMIT) -> List[str]:
    remaining = str(text or "")
    chunks: List[str] = []

    while len(remaining) > limit:
        position = remaining.rfind("\n", 0, limit)
        if position < limit // 2:
            position = remaining.rfind(" ", 0, limit)
        if position < limit // 2:
            position = limit

        chunks.append(remaining[:position].rstrip())
        remaining = remaining[position:].lstrip()

    if remaining or not chunks:
        chunks.append(remaining)

    return chunks


async def answer_plain(message, text: str, reply_markup: Optional[object] = None):
    """Send Telegram text safely, rendering LaTeX only when it is actually present.

    Compatibility is important here: ordinary non-mathematical messages must remain
    a single ``message.answer`` call whenever they fit into Telegram's text limit.
    Existing handlers and tests rely on that behaviour, and there is no reason to
    split plain text into artificial parts.

    Canonical Markdown+LaTeX is processed only when raw LaTeX is detected.
    """
    raw_text = str(text or "")

    # Fast path for ordinary Telegram messages.
    # Do not run them through telegram_parts(), because that formatter may split a
    # perfectly normal message into several answer() calls.
    if not contains_raw_latex(raw_text):
        chunks = split_telegram_text(raw_text)
        sent = None
        for index, chunk in enumerate(chunks):
            markup = reply_markup if index == len(chunks) - 1 else None
            sent = await message.answer(
                chunk,
                reply_markup=markup,
                parse_mode=None,
            )
        return sent

    # Math-aware path: never expose raw LaTeX to Telegram.
    parts = telegram_parts(raw_text)
    sent = None
    sendable = []

    for part in parts:
        if part.kind == "formula" and is_complex_formula(part.content):
            png = render_formula_png(part.content)
            if png:
                sendable.append(("photo", png, part.content))
            else:
                sendable.append(
                    ("text", telegram_formula_fallback(part.content), "")
                )
        elif part.kind == "formula":
            sendable.append(
                ("text", telegram_formula_fallback(part.content), "")
            )
        else:
            sendable.append(("text", part.content, ""))

    expanded = []
    for kind, payload, extra in sendable:
        if kind == "text":
            expanded.extend(
                ("text", chunk, "")
                for chunk in split_telegram_text(payload)
                if chunk
            )
        else:
            expanded.append((kind, payload, extra))

    if not expanded:
        expanded = [("text", "", "")]

    for index, (kind, payload, extra) in enumerate(expanded):
        markup = reply_markup if index == len(expanded) - 1 else None

        if kind == "photo":
            sent = await message.answer_photo(
                BufferedInputFile(payload, filename="formula.png"),
                caption=None,
                reply_markup=markup,
            )
        else:
            sent = await message.answer(
                payload,
                reply_markup=markup,
                parse_mode=None,
            )

    return sent
