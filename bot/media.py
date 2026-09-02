import asyncio
import io
from typing import Optional

from aiogram.types import Message
from fastapi import UploadFile
from starlette.datastructures import Headers

from services.core.attachment_storage import get_attachment, load_attachment_for_ai, save_upload
from services.core.file_parser import (
    attachment_size_limit,
    AttachmentError,
    ParsedAttachment,
    parse_attachment,
)


async def _parse_safely(data: bytes, filename: str, mime_type: str) -> ParsedAttachment:
    """
    Безопасно парсит вложение, перехватывая ошибки и преобразуя их в AttachmentError.
    """
    try:
        return await asyncio.to_thread(parse_attachment, data, filename, mime_type)
    except AttachmentError:
        raise
    except Exception as exc:
        raise AttachmentError(
            f"Не удалось прочитать файл «{filename}». Проверьте, что он не повреждён."
        ) from exc


async def _store_for_chat(data: bytes, filename: str, mime_type: str, owner_id: int) -> Optional[ParsedAttachment]:
    """
    Сохраняет вложение в хранилище и возвращает объект ParsedAttachment.
    """
    try:
        upload = UploadFile(
            file=io.BytesIO(data),
            filename=filename,
            headers=Headers({"content-type": mime_type}),
            size=len(data),
        )
        stored = await save_upload(upload=upload, owner_id=owner_id)
        if not isinstance(stored.attachment_id, int):
            return None
        row = await get_attachment(stored.attachment_id)
        parsed = await load_attachment_for_ai(row)
        parsed.attachment_id = stored.attachment_id
        return parsed
    except AttachmentError:
        raise
    except Exception:
        return None


async def parse_telegram_attachment(message: Message) -> Optional[ParsedAttachment]:
    """
    Парсит вложение из Telegram-сообщения, сохраняя его в хранилище и возвращая объект ParsedAttachment.
    """
    if not message.photo and not message.document:
        return None

    buffer = io.BytesIO()
    if message.photo:
        file_info = await message.bot.get_file(message.photo[-1].file_id)
        await message.bot.download_file(file_info.file_path, destination=buffer)
        data = buffer.getvalue() or b"telegram-photo"
        stored = await _store_for_chat(
            data, "telegram-photo.jpg", "image/jpeg", message.from_user.id
        )
        return stored or await _parse_safely(data, "telegram-photo.jpg", "image/jpeg")

    document = message.document
    filename = document.file_name or "telegram-document"
    mime_type = document.mime_type or "application/octet-stream"
    size_limit = attachment_size_limit(filename, mime_type)
    if document.file_size and document.file_size > size_limit:
        limit_mb = size_limit // (1024 * 1024)
        raise AttachmentError(f"Максимальный размер этого вложения — {limit_mb} МБ")

    file_info = await message.bot.get_file(document.file_id)
    await message.bot.download_file(file_info.file_path, destination=buffer)
    data = buffer.getvalue()
    stored = await _store_for_chat(data, filename, mime_type, message.from_user.id)
    return stored or await _parse_safely(data, filename, mime_type)
