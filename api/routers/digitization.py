from __future__ import annotations

import hashlib
import re
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from api.security import require_roles
from database import db
from services.digitization.digitization_queue import ensure_queue_storage

router = APIRouter(
    prefix="/api/v1/admin/digitization",
    tags=["Digitization queue"],
)

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
    value = Path(str(name or "")).stem
    value = value.strip().casefold().replace("ё", "е")
    return re.sub(r"\s+", " ", value)


async def _write_upload(upload: UploadFile, destination: Path, limit: int) -> int:
    total = 0
    with destination.open("wb") as out:
        while True:
            chunk = await upload.read(CHUNK_SIZE)
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                destination.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail="Файл превышает допустимый размер",
                )
            out.write(chunk)

    if total == 0:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="Получен пустой файл")
    return total


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


async def _empty_books(conn) -> List[dict]:
    rows = await conn.fetch(
        """
        SELECT
            b.book_id,
            b.book_title,
            b.book_program,
            b.book_class,
            b.book_author,
            0::bigint AS pages_count
        FROM book b
        WHERE NOT EXISTS (
            SELECT 1 FROM page p WHERE p.book_id = b.book_id
        )
        ORDER BY b.book_class, b.book_program, b.book_title, b.book_id
        """
    )
    return [dict(row) for row in rows]


async def _automatic_match(
    conn,
    filename: str,
) -> Tuple[Optional[int], Optional[str], str]:
    normalized = _normalized_title(filename)
    candidates = [
        book
        for book in await _empty_books(conn)
        if _normalized_title(book["book_title"]) == normalized
    ]
    if len(candidates) == 1:
        return int(candidates[0]["book_id"]), "automatic", "matched_automatic"
    if len(candidates) > 1:
        return None, None, "ambiguous_match"
    return None, None, "unmatched"


async def _validate_empty_book(conn, book_id: int) -> dict:
    book = await conn.fetchrow(
        """
        SELECT
            b.book_id,
            b.book_title,
            b.book_program,
            b.book_class,
            b.book_author,
            (SELECT COUNT(*) FROM page p WHERE p.book_id = b.book_id) AS pages_count
        FROM book b
        WHERE b.book_id = $1
        """,
        book_id,
    )
    if not book:
        raise HTTPException(status_code=404, detail="Учебник не найден")
    if int(book["pages_count"] or 0) != 0:
        raise HTTPException(
            status_code=409,
            detail=(
                "В выбранном учебнике уже есть оцифрованные страницы. "
                "Выберите другой пустой учебник или используйте явную "
                "функцию повторной оцифровки."
            ),
        )
    return dict(book)


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
    match_type: Optional[str],
    stage: str,
) -> dict:
    duplicate = await conn.fetchrow(
        """
        SELECT job_id, status, book_id, batch_id
        FROM textbook_digitization_jobs
        WHERE checksum_sha256 = $1
          AND status IN (
              'matching', 'pending', 'processing',
              'completed', 'waiting_for_book'
          )
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
            "batch_id": duplicate["batch_id"],
            "status": duplicate["status"],
            "book_id": duplicate["book_id"],
            "original_name": original_name,
        }

    row = await conn.fetchrow(
        """
        INSERT INTO textbook_digitization_jobs (
            batch_id, requested_by, book_id, original_name, stored_path,
            size_bytes, checksum_sha256, status, stage, match_type, matched_at
        )
        VALUES (
            $1, $2, $3, $4, $5, $6, $7,
            'matching', $8, $9,
            CASE WHEN $3::integer IS NULL THEN NULL ELSE CURRENT_TIMESTAMP END
        )
        RETURNING
            job_id, batch_id, book_id, original_name, size_bytes,
            checksum_sha256, status, stage, match_type, matched_at, created_at
        """,
        batch_id,
        owner_id,
        book_id,
        original_name,
        str(stored_path),
        size_bytes,
        checksum,
        stage,
        match_type,
    )
    return dict(row)


async def _jobs_from_pdf_uploads(
    uploads: List[UploadFile],
    *,
    batch_id: uuid.UUID,
    owner_id: int,
) -> List[dict]:
    storage = ensure_queue_storage()
    results: List[dict] = []

    async with db.pool.acquire() as conn:
        for upload in uploads:
            name = _safe_name(upload.filename or "")
            if not name.lower().endswith(".pdf"):
                raise HTTPException(
                    status_code=422,
                    detail=f"{name}: поддерживаются только PDF",
                )

            destination = storage / f"{uuid.uuid4().hex}.pdf"
            size = await _write_upload(upload, destination, MAX_PDF_BYTES)
            checksum = _sha256(destination)
            book_id, match_type, stage = await _automatic_match(conn, name)

            results.append(
                await _insert_job(
                    conn,
                    batch_id=batch_id,
                    owner_id=owner_id,
                    original_name=name,
                    stored_path=destination,
                    size_bytes=size,
                    checksum=checksum,
                    book_id=book_id,
                    match_type=match_type,
                    stage=stage,
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
            raise HTTPException(
                status_code=422,
                detail="Файл не является корректным ZIP-архивом",
            )

        with zipfile.ZipFile(archive_path) as archive:
            infos = []
            uncompressed = 0

            for info in archive.infolist():
                raw = info.filename.replace("\\", "/")
                posix = PurePosixPath(raw)

                if info.is_dir() or "__MACOSX" in posix.parts:
                    continue
                if posix.is_absolute() or ".." in posix.parts:
                    raise HTTPException(
                        status_code=422,
                        detail="ZIP содержит небезопасный путь",
                    )
                if not raw.lower().endswith(".pdf"):
                    continue
                if info.file_size > MAX_PDF_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"{raw}: PDF больше 100 МБ",
                    )

                uncompressed += info.file_size
                if uncompressed > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail="Распакованный ZIP слишком большой",
                    )
                infos.append(info)

            if not infos:
                raise HTTPException(
                    status_code=422,
                    detail="ZIP-архив не содержит PDF-файлов",
                )
            if len(infos) > MAX_FILES_PER_BATCH:
                raise HTTPException(
                    status_code=413,
                    detail=f"В ZIP разрешено не более {MAX_FILES_PER_BATCH} PDF",
                )

            async with db.pool.acquire() as conn:
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
                                raise HTTPException(
                                    status_code=413,
                                    detail=f"{name}: PDF больше 100 МБ",
                                )
                            out.write(chunk)

                    checksum = _sha256(destination)
                    book_id, match_type, stage = await _automatic_match(conn, name)
                    results.append(
                        await _insert_job(
                            conn,
                            batch_id=batch_id,
                            owner_id=owner_id,
                            original_name=name,
                            stored_path=destination,
                            size_bytes=written,
                            checksum=checksum,
                            book_id=book_id,
                            match_type=match_type,
                            stage=stage,
                        )
                    )
        return results
    finally:
        archive_path.unlink(missing_ok=True)


@router.get("/empty-books")
async def list_empty_digitization_books(user=Depends(require_roles("admin"))):
    async with db.pool.acquire() as conn:
        return await _empty_books(conn)


@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_digitization_batch(
    files: List[UploadFile] = File(...),
    default_book_id: Optional[int] = Form(default=None),
    book_map_json: str = Form(default="{}"),
    user=Depends(require_roles("admin")),
):
    # Compatibility only. TZ25 deliberately performs matching after upload.
    del default_book_id, book_map_json

    if not files:
        raise HTTPException(status_code=422, detail="Выберите хотя бы один PDF или ZIP")
    if len(files) > MAX_FILES_PER_BATCH:
        raise HTTPException(
            status_code=413,
            detail=f"За раз можно загрузить не более {MAX_FILES_PER_BATCH} файлов",
        )

    batch_id = uuid.uuid4()
    names = [_safe_name(file.filename or "") for file in files]
    zip_files = [f for f, name in zip(files, names) if name.lower().endswith(".zip")]
    pdf_files = [f for f, name in zip(files, names) if name.lower().endswith(".pdf")]

    if zip_files and (len(zip_files) != 1 or pdf_files or len(files) != 1):
        raise HTTPException(
            status_code=422,
            detail="ZIP загружается отдельно от PDF-файлов",
        )
    if not zip_files and len(pdf_files) != len(files):
        raise HTTPException(
            status_code=422,
            detail="Поддерживаются только .pdf и один .zip",
        )

    if zip_files:
        jobs = await _jobs_from_zip(
            zip_files[0],
            batch_id=batch_id,
            owner_id=user["tg_id"],
        )
    else:
        jobs = await _jobs_from_pdf_uploads(
            pdf_files,
            batch_id=batch_id,
            owner_id=user["tg_id"],
        )

    return {
        "batch_id": str(batch_id),
        "status": "matching",
        "jobs": jobs,
    }


@router.get("/jobs")
async def list_digitization_jobs(
    limit: int = 200,
    user=Depends(require_roles("admin")),
):
    limit = min(max(limit, 1), 500)
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                j.job_id, j.batch_id, j.book_id,
                b.book_title, b.book_program, b.book_class, b.book_author,
                j.original_name, j.size_bytes, j.checksum_sha256,
                j.match_type, j.matched_at,
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


@router.post("/jobs/{job_id}/assign/{book_id}")
async def assign_digitization_book(
    job_id: int,
    book_id: int,
    user=Depends(require_roles("admin")),
):
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            job = await conn.fetchrow(
                """
                SELECT job_id, batch_id, status
                FROM textbook_digitization_jobs
                WHERE job_id = $1
                FOR UPDATE
                """,
                job_id,
            )
            if not job:
                raise HTTPException(status_code=404, detail="Задача не найдена")
            if job["status"] != "matching":
                raise HTTPException(
                    status_code=409,
                    detail="Сопоставление можно менять только до запуска пакета.",
                )

            await _validate_empty_book(conn, book_id)

            already_used = await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM textbook_digitization_jobs
                    WHERE batch_id = $1
                      AND job_id <> $2
                      AND book_id = $3
                )
                """,
                job["batch_id"],
                job_id,
                book_id,
            )
            if already_used:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Этот учебник уже сопоставлен с другим файлом "
                        "в текущей очереди."
                    ),
                )

            row = await conn.fetchrow(
                """
                UPDATE textbook_digitization_jobs
                SET book_id = $1,
                    match_type = 'manual',
                    matched_at = CURRENT_TIMESTAMP,
                    stage = 'matched_manual',
                    error_text = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_id = $2
                RETURNING job_id, batch_id, book_id, match_type, status, stage
                """,
                book_id,
                job_id,
            )
    return dict(row)


@router.post("/batches/{batch_id}/confirm")
async def confirm_digitization_batch(
    batch_id: uuid.UUID,
    user=Depends(require_roles("admin")),
):
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            rows = await conn.fetch(
                """
                SELECT job_id, book_id, original_name, status, match_type
                FROM textbook_digitization_jobs
                WHERE batch_id = $1
                ORDER BY job_id
                FOR UPDATE
                """,
                batch_id,
            )
            if not rows:
                raise HTTPException(status_code=404, detail="Пакет не найден")

            statuses = {row["status"] for row in rows}
            if "matching" not in statuses:
                if statuses.issubset({"pending", "processing", "completed", "failed"}):
                    return {
                        "batch_id": str(batch_id),
                        "status": "already_started",
                        "jobs_count": len(rows),
                    }
                raise HTTPException(status_code=409, detail="Пакет сейчас нельзя запустить")

            if statuses != {"matching"}:
                raise HTTPException(
                    status_code=409,
                    detail="В пакете есть задачи с несовместимыми статусами.",
                )

            missing = [row["original_name"] for row in rows if row["book_id"] is None]
            if missing:
                raise HTTPException(
                    status_code=422,
                    detail="Не завершено сопоставление всех файлов: " + ", ".join(missing[:5]),
                )

            book_ids = [int(row["book_id"]) for row in rows]
            if len(book_ids) != len(set(book_ids)):
                raise HTTPException(
                    status_code=409,
                    detail="Один учебник нельзя назначить двум PDF в одном пакете.",
                )

            for book_id in book_ids:
                await _validate_empty_book(conn, book_id)

            await conn.execute(
                """
                UPDATE textbook_digitization_jobs
                SET status = 'pending',
                    stage = 'queued',
                    error_text = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE batch_id = $1
                  AND status = 'matching'
                """,
                batch_id,
            )

    return {
        "batch_id": str(batch_id),
        "status": "queued",
        "jobs_count": len(rows),
    }


@router.post("/jobs/{job_id}/retry")
async def retry_digitization_job(
    job_id: int,
    user=Depends(require_roles("admin")),
):
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE textbook_digitization_jobs
            SET status = 'pending',
                stage = 'queued_retry',
                error_text = NULL,
                started_at = NULL,
                finished_at = NULL,
                processed_pages = 0,
                total_pages = 0,
                retry_count = retry_count + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE job_id = $1
              AND status = 'failed'
              AND book_id IS NOT NULL
            RETURNING job_id, batch_id, book_id, match_type, status, retry_count
            """,
            job_id,
        )

    if not row:
        raise HTTPException(
            status_code=409,
            detail=(
                "Повторить можно только неудачную задачу "
                "с сохранённым сопоставлением."
            ),
        )
    return dict(row)
