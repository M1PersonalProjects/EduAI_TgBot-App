from typing import List, Optional

from aiogram.types import BufferedInputFile

from services.response_formatter import (
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
    """Compatibility wrapper; now understands canonical Markdown+LaTeX safely."""
    parts = telegram_parts(text)
    sent = None
    sendable = []
    for part in parts:
        if part.kind == "formula" and is_complex_formula(part.content):
            png = render_formula_png(part.content)
            if png:
                sendable.append(("photo", png, part.content))
            else:
                sendable.append(("text", telegram_formula_fallback(part.content), ""))
        else:
            sendable.append(("text", part.content, ""))

    expanded = []
    for kind, payload, extra in sendable:
        if kind == "text":
            expanded.extend(("text", chunk, "") for chunk in split_telegram_text(payload) if chunk)
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
            sent = await message.answer(payload, reply_markup=markup, parse_mode=None)
    return sent
