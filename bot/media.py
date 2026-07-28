import asyncio
import io
from typing import Optional

from aiogram.types import Message

from services.file_parser import (
    attachment_size_limit,
    AttachmentError,
    ParsedAttachment,
    parse_attachment,
)


async def _parse_safely(
    data: bytes, filename: str, mime_type: str
) -> ParsedAttachment:
    try:
        return await asyncio.to_thread(parse_attachment, data, filename, mime_type)
    except AttachmentError:
        raise
    except Exception as exc:
        raise AttachmentError(
            f"Не удалось прочитать файл «{filename}». Проверьте, что он не повреждён."
        ) from exc


async def parse_telegram_attachment(message: Message) -> Optional[ParsedAttachment]:
    if not message.photo and not message.document:
        return None

    buffer = io.BytesIO()
    if message.photo:
        file_info = await message.bot.get_file(message.photo[-1].file_id)
        await message.bot.download_file(file_info.file_path, destination=buffer)
        data = buffer.getvalue() or b"telegram-photo"
        return await _parse_safely(data, "telegram-photo.jpg", "image/jpeg")

    document = message.document
    size_limit = attachment_size_limit(
        document.file_name or "telegram-document",
        document.mime_type or "application/octet-stream",
    )
    if document.file_size and document.file_size > size_limit:
        limit_mb = size_limit // (1024 * 1024)
        raise AttachmentError(f"Максимальный размер этого вложения — {limit_mb} МБ")
    file_info = await message.bot.get_file(document.file_id)
    await message.bot.download_file(file_info.file_path, destination=buffer)
    return await _parse_safely(
        buffer.getvalue(),
        document.file_name or "telegram-document",
        document.mime_type or "application/octet-stream",
    )
