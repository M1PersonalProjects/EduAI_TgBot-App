from pathlib import Path
from typing import List

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse

from api.security import get_current_user
from database import db
from services.attachment_storage import (
    delete_attachment,
    ensure_attachment_access,
    save_upload,
)


router = APIRouter(
    prefix="/api/v1/attachments",
    tags=["Attachments v1"],
)


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_attachments(
    files: List[UploadFile] = File(...),
    user=Depends(get_current_user),
):
    if not files:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Выберите хотя бы один файл",
        )

    if len(files) > 10:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="За один раз можно загрузить не более 10 файлов",
        )

    uploaded = []

    for file in files:
        attachment = await save_upload(
            upload=file,
            owner_id=user["tg_id"],
        )
        uploaded.append(attachment.to_dict())

    return {"attachments": uploaded}


@router.get("")
async def list_my_attachments(
    limit: int = 50,
    user=Depends(get_current_user),
):
    limit = min(max(limit, 1), 100)

    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                attachment_id,
                original_name,
                mime_type,
                extension,
                size_bytes,
                processing_status,
                created_at
            FROM attachments
            WHERE owner_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            user["tg_id"],
            limit,
        )

    return [
        {
            **dict(row),
            "download_url":
                f"/api/v1/attachments/{row['attachment_id']}/download",
            "preview_url":
                f"/api/v1/attachments/{row['attachment_id']}/preview",
        }
        for row in rows
    ]


@router.get("/{attachment_id}/download")
async def download_attachment(
    attachment_id: int,
    user=Depends(get_current_user),
):
    attachment = await ensure_attachment_access(
        attachment_id,
        user,
    )

    path: Path = attachment["absolute_path"]

    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Файл отсутствует в хранилище",
        )

    return FileResponse(
        path=str(path),
        media_type=attachment["mime_type"],
        filename=attachment["original_name"],
    )


@router.get("/{attachment_id}/preview")
async def preview_attachment(
    attachment_id: int,
    user=Depends(get_current_user),
):
    attachment = await ensure_attachment_access(
        attachment_id,
        user,
    )

    path: Path = attachment["absolute_path"]

    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Файл отсутствует в хранилище",
        )

    previewable = (
        attachment["mime_type"].startswith("image/")
        or attachment["mime_type"] == "application/pdf"
        or attachment["mime_type"].startswith("text/")
    )

    if not previewable:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Предпросмотр этого формата не поддерживается",
        )

    headers = {
        "Content-Disposition":
            f'inline; filename="{attachment["storage_name"]}"'
    }

    return FileResponse(
        path=str(path),
        media_type=attachment["mime_type"],
        headers=headers,
    )


@router.delete(
    "/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_attachment(
    attachment_id: int,
    user=Depends(get_current_user),
):
    await delete_attachment(
        attachment_id=attachment_id,
        owner_id=user["tg_id"],
    )