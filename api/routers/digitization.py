from __future__ import annotations

import hashlib
import json
import re
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from api.security import require_roles
from database import db
from services.digitization_queue import ensure_queue_storage

router = APIRouter(prefix="/api/v1/admin/digitization", tags=["Digitization queue"])

MAX_PDF_BYTES = 100 * 1024 * 1024
MAX_ARCHIVE_BYTES = 500 * 1024 * 1024
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
MAX_FILES_PER_BATCH = 50
CHUNK_SIZE = 1024 * 1024


def _safe_name(name: str) -> str:
    clean = Path(name.replace("\\", "/")).name.strip()
    clean = re.sub(r"[\x00-\x1f]", "", clean)
    return clean or "textbook.pdf"


def _normalized_title(name: str) -> str:
    stem = Path(name).stem.casefold()
    return re.sub(r"[^0-9a-zа-яё]+", " ", stem, flags=re.IGNORECASE).strip()


async def _write_upload(upload: UploadFile, destination: Path, limit: int) -> int:
    total = 0
    with destination.open("wb") as out:
        while True:
            chunk = await upload.read(CHUNK_SIZE)
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                out.close()
                destination.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Файл превышает допустимый размер")
            out.write(chunk)
    if total == 0:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="Получен пустой файл")
    return total


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as src:
        for chunk in iter(lambda: src.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


async def _books_by_normalized_title(conn) -> Dict[str, int]:
    rows = await conn.fetch("SELECT book_id, book_title FROM book")
    result: Dict[str, int] = {}
    duplicates = set()
    for row in rows:
        key = _normalized_title(row["book_title"])
        if key in result:
            duplicates.add(key)
        else:
            result[key] = int(row["book_id"])
    for key in duplicates:
        result.pop(key, None)
    return result


async def _insert_job(
    conn,
    *,
    batch_id: uuid.UUID,
    owner_id: int,
    original_name: str,
    stored_path: Path,
    size_bytes: int,
    checksum: str,
    book_id: Optional[int],
) -> dict:
    duplicate = await conn.fetchrow(
        """
        SELECT job_id, status, book_id
        FROM textbook_digitization_jobs
        WHERE checksum_sha256 = $1
          AND status IN ('pending', 'processing', 'completed', 'waiting_for_book')
        ORDER BY created_at DESC
        LIMIT 1
        """,
        checksum,
    )
    if duplicate:
        stored_path.unlink(missing_ok=True)
        return {
            "duplicate": True,
            "job_id": duplicate["job_id"],
            "status": duplicate["status"],
            "original_name": original_name,
        }

    job_status = "pending" if book_id is not None else "waiting_for_book"
    row = await conn.fetchrow(
        """
        INSERT INTO textbook_digitization_jobs (
            batch_id, requested_by, book_id, original_name, stored_path,
            size_bytes, checksum_sha256, status, stage
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        RETURNING job_id, batch_id, book_id, original_name, size_bytes,
                  checksum_sha256, status, stage, created_at
        """,
        batch_id,
        owner_id,
        book_id,
        original_name,
        str(stored_path),
        size_bytes,
        checksum,
        job_status,
        "queued" if book_id is not None else "waiting_for_book",
    )
    return dict(row)


async def _jobs_from_pdf_uploads(
    uploads: List[UploadFile],
    *,
    batch_id: uuid.UUID,
    owner_id: int,
    book_map: Dict[str, int],
    default_book_id: Optional[int],
) -> List[dict]:
    storage = ensure_queue_storage()
    results = []
    async with db.pool.acquire() as conn:
        title_map = await _books_by_normalized_title(conn)
        for upload in uploads:
            name = _safe_name(upload.filename or "")
            if not name.lower().endswith(".pdf"):
                raise HTTPException(status_code=422, detail=f"{name}: поддерживаются только PDF")
            destination = storage / f"{uuid.uuid4().hex}.pdf"
            size = await _write_upload(upload, destination, MAX_PDF_BYTES)
            checksum = _sha256(destination)
            mapped = book_map.get(name)
            if mapped is None:
                mapped = title_map.get(_normalized_title(name))
            if mapped is None and len(uploads) == 1:
                mapped = default_book_id
            results.append(
                await _insert_job(
                    conn,
                    batch_id=batch_id,
                    owner_id=owner_id,
                    original_name=name,
                    stored_path=destination,
                    size_bytes=size,
                    checksum=checksum,
                    book_id=mapped,
                )
            )
    return results


async def _jobs_from_zip(
    upload: UploadFile,
    *,
    batch_id: uuid.UUID,
    owner_id: int,
) -> List[dict]:
    storage = ensure_queue_storage()
    archive_path = storage / f"archive-{uuid.uuid4().hex}.zip"
    await _write_upload(upload, archive_path, MAX_ARCHIVE_BYTES)
    results: List[dict] = []
    try:
        if not zipfile.is_zipfile(archive_path):
            raise HTTPException(status_code=422, detail="Файл не является корректным ZIP-архивом")
        with zipfile.ZipFile(archive_path) as archive:
            infos = []
            uncompressed = 0
            for info in archive.infolist():
                raw = info.filename.replace("\\", "/")
                posix = PurePosixPath(raw)
                if info.is_dir() or "__MACOSX" in posix.parts:
                    continue
                if posix.is_absolute() or ".." in posix.parts:
                    raise HTTPException(status_code=422, detail="ZIP содержит небезопасный путь")
                if not raw.lower().endswith(".pdf"):
                    continue
                if info.file_size > MAX_PDF_BYTES:
                    raise HTTPException(status_code=413, detail=f"{raw}: PDF больше 100 МБ")
                uncompressed += info.file_size
                if uncompressed > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                    raise HTTPException(status_code=413, detail="Распакованный ZIP слишком большой")
                infos.append(info)
            if not infos:
                raise HTTPException(status_code=422, detail="ZIP-архив не содержит PDF-файлов")
            if len(infos) > MAX_FILES_PER_BATCH:
                raise HTTPException(status_code=413, detail=f"В ZIP разрешено не более {MAX_FILES_PER_BATCH} PDF")

            async with db.pool.acquire() as conn:
                title_map = await _books_by_normalized_title(conn)
                for info in infos:
                    name = _safe_name(info.filename)
                    destination = storage / f"{uuid.uuid4().hex}.pdf"
                    written = 0
                    with archive.open(info, "r") as source, destination.open("wb") as out:
                        while True:
                            chunk = source.read(CHUNK_SIZE)
                            if not chunk:
                                break
                            written += len(chunk)
                            if written > MAX_PDF_BYTES:
                                destination.unlink(missing_ok=True)
                                raise HTTPException(status_code=413, detail=f"{name}: PDF больше 100 МБ")
                            out.write(chunk)
                    checksum = _sha256(destination)
                    mapped = title_map.get(_normalized_title(name))
                    results.append(
                        await _insert_job(
                            conn,
                            batch_id=batch_id,
                            owner_id=owner_id,
                            original_name=name,
                            stored_path=destination,
                            size_bytes=written,
                            checksum=checksum,
                            book_id=mapped,
                        )
                    )
        return results
    finally:
        archive_path.unlink(missing_ok=True)


@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_digitization_batch(
    files: List[UploadFile] = File(...),
    default_book_id: Optional[int] = Form(default=None),
    book_map_json: str = Form(default="{}"),
    user=Depends(require_roles("admin")),
):
    if not files:
        raise HTTPException(status_code=422, detail="Выберите хотя бы один PDF или ZIP")
    if len(files) > MAX_FILES_PER_BATCH:
        raise HTTPException(status_code=413, detail=f"За раз можно загрузить не более {MAX_FILES_PER_BATCH} файлов")
    try:
        raw_map = json.loads(book_map_json or "{}")
        book_map = {str(k): int(v) for k, v in raw_map.items() if v is not None}
    except (ValueError, TypeError, json.JSONDecodeError):
        raise HTTPException(status_code=422, detail="Некорректная карта учебников")

    batch_id = uuid.uuid4()
    names = [_safe_name(file.filename or "") for file in files]
    zip_files = [f for f, name in zip(files, names) if name.lower().endswith(".zip")]
    pdf_files = [f for f, name in zip(files, names) if name.lower().endswith(".pdf")]
    if zip_files and (len(zip_files) != 1 or pdf_files or len(files) != 1):
        raise HTTPException(status_code=422, detail="ZIP загружается отдельно от PDF-файлов")
    if not zip_files and len(pdf_files) != len(files):
        raise HTTPException(status_code=422, detail="Поддерживаются только .pdf и один .zip")

    if zip_files:
        jobs = await _jobs_from_zip(zip_files[0], batch_id=batch_id, owner_id=user["tg_id"])
    else:
        jobs = await _jobs_from_pdf_uploads(
            pdf_files,
            batch_id=batch_id,
            owner_id=user["tg_id"],
            book_map=book_map,
            default_book_id=default_book_id,
        )
    return {"batch_id": str(batch_id), "jobs": jobs}


@router.get("/jobs")
async def list_digitization_jobs(
    limit: int = 200,
    user=Depends(require_roles("admin")),
):
    limit = min(max(limit, 1), 500)
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT j.job_id, j.batch_id, j.book_id, b.book_title,
                   j.original_name, j.size_bytes, j.checksum_sha256,
                   j.status, j.stage, j.processed_pages, j.total_pages,
                   j.error_text, j.retry_count, j.created_at, j.started_at,
                   j.finished_at, j.updated_at
            FROM textbook_digitization_jobs j
            LEFT JOIN book b ON b.book_id = j.book_id
            ORDER BY j.created_at DESC, j.job_id DESC
            LIMIT $1
            """,
            limit,
        )
    return [dict(row) for row in rows]


@router.post("/jobs/{job_id}/retry")
async def retry_digitization_job(job_id: int, user=Depends(require_roles("admin"))):
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE textbook_digitization_jobs
            SET status = CASE WHEN book_id IS NULL THEN 'waiting_for_book' ELSE 'pending' END,
                stage = CASE WHEN book_id IS NULL THEN 'waiting_for_book' ELSE 'queued' END,
                error_text = NULL,
                started_at = NULL,
                finished_at = NULL,
                processed_pages = 0,
                total_pages = 0,
                retry_count = retry_count + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE job_id = $1 AND status = 'failed'
            RETURNING job_id, status, retry_count
            """,
            job_id,
        )
    if not row:
        raise HTTPException(status_code=409, detail="Повторить можно только неудачную задачу")
    return dict(row)


@router.post("/jobs/{job_id}/assign/{book_id}")
async def assign_digitization_book(
    job_id: int,
    book_id: int,
    user=Depends(require_roles("admin")),
):
    async with db.pool.acquire() as conn:
        exists = await conn.fetchval("SELECT EXISTS(SELECT 1 FROM book WHERE book_id=$1)", book_id)
        if not exists:
            raise HTTPException(status_code=404, detail="Учебник не найден")
        row = await conn.fetchrow(
            """
            UPDATE textbook_digitization_jobs
            SET book_id = $1,
                status = 'pending',
                stage = 'queued',
                error_text = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE job_id = $2
              AND status IN ('waiting_for_book', 'failed')
            RETURNING job_id, book_id, status
            """,
            book_id,
            job_id,
        )
    if not row:
        raise HTTPException(status_code=409, detail="Эту задачу сейчас нельзя переназначить")
    return dict(row)
