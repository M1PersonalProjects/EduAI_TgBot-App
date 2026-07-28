from typing import List, Optional


TELEGRAM_TEXT_LIMIT = 4000


def split_telegram_text(text: str, limit: int = TELEGRAM_TEXT_LIMIT) -> List[str]:
    """Split plain text without cutting words where possible."""
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
    """Send untrusted/AI text safely, attaching the keyboard to the last chunk."""
    chunks = split_telegram_text(text)
    sent = None
    for index, chunk in enumerate(chunks):
        sent = await message.answer(
            chunk,
            reply_markup=reply_markup if index == len(chunks) - 1 else None,
            parse_mode=None,
        )
    return sent
