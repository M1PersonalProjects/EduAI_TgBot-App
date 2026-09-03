from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import Optional

from database import db
from logger_config import logger
from services.digitization.textbook_digitizer import digitize_pdf_path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
QUEUE_STORAGE = PROJECT_ROOT / "storage" / "digitization_queue"
POLL_INTERVAL_SECONDS = 2.0

_worker_task: Optional[asyncio.Task] = None
_stop_event: Optional[asyncio.Event] = None


def ensure_queue_storage() -> Path:
    QUEUE_STORAGE.mkdir(parents=True, exist_ok=True)
    return QUEUE_STORAGE


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


async def _recover_interrupted_jobs() -> None:
    async with db.pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE textbook_digitization_jobs
            SET status = 'pending',
                stage = 'recovered_after_restart',
                started_at = NULL,
                error_text = CASE
                    WHEN error_text IS NULL OR error_text = ''
                    THEN 'Предыдущая обработка была прервана перезапуском сервера и поставлена в очередь повторно.'
                    ELSE error_text
                END,
                updated_at = CURRENT_TIMESTAMP
            WHERE status = 'processing'
            """
        )


async def _claim_next_job():
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(220025)")
            row = await conn.fetchrow(
                """
                SELECT
                    job_id, batch_id, book_id, original_name, stored_path,
                    checksum_sha256, retry_count, match_type
                FROM textbook_digitization_jobs
                WHERE status = 'pending'
                  AND book_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM textbook_digitization_jobs running
                      WHERE running.status = 'processing'
                  )
                ORDER BY created_at, job_id
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """
            )
            if not row:
                return None

            pages_count = await conn.fetchval(
                "SELECT COUNT(*) FROM page WHERE book_id = $1",
                row["book_id"],
            )
            if int(pages_count or 0) > 0 and int(row["retry_count"] or 0) == 0:
                await conn.execute(
                    """
                    UPDATE textbook_digitization_jobs
                    SET status = 'failed',
                        stage = 'book_not_empty',
                        error_text = 'В выбранном учебнике уже есть страницы. Автоматическая перезапись запрещена.',
                        finished_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE job_id = $1
                    """,
                    row["job_id"],
                )
                return None

            await conn.execute(
                """
                UPDATE textbook_digitization_jobs
                SET status = 'processing',
                    stage = 'starting',
                    started_at = CURRENT_TIMESTAMP,
                    finished_at = NULL,
                    error_text = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_id = $1
                """,
                row["job_id"],
            )
            return dict(row)


async def _update_progress(job_id: int, stage: str, processed: int, total: int) -> None:
    async with db.pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE textbook_digitization_jobs
            SET stage = $1,
                processed_pages = $2,
                total_pages = $3,
                updated_at = CURRENT_TIMESTAMP
            WHERE job_id = $4
            """,
            stage,
            processed,
            total,
            job_id,
        )


async def _process_job(job: dict) -> None:
    job_id = int(job["job_id"])
    path = Path(job["stored_path"])

    try:
        async def progress(stage: str, processed: int, total: int) -> None:
            await _update_progress(job_id, stage, processed, total)

        reset_pages = int(job.get("retry_count") or 0) > 0

        result = await digitize_pdf_path(
            int(job["book_id"]),
            path,
            progress_callback=progress,
            reset_pages=reset_pages,
        )

        async with db.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE textbook_digitization_jobs
                SET status = 'completed',
                    stage = 'completed',
                    processed_pages = $1,
                    total_pages = $2,
                    finished_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_id = $3
                """,
                result["processed_pages"],
                result["total_pages"],
                job_id,
            )
        path.unlink(missing_ok=True)

    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception("Digitization job %s failed: %s", job_id, exc)
        async with db.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE textbook_digitization_jobs
                SET status = 'failed',
                    stage = 'failed',
                    error_text = $1,
                    finished_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_id = $2
                """,
                str(exc)[:4000],
                job_id,
            )


async def _worker_loop() -> None:
    await _recover_interrupted_jobs()
    logger.info("Textbook digitization worker started")

    while _stop_event and not _stop_event.is_set():
        try:
            job = await _claim_next_job()
            if job:
                await _process_job(job)
                continue
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Digitization worker iteration failed: %s", exc)

        try:
            await asyncio.wait_for(
                _stop_event.wait(),
                timeout=POLL_INTERVAL_SECONDS,
            )
        except asyncio.TimeoutError:
            pass

    logger.info("Textbook digitization worker stopped")


async def start_digitization_worker() -> None:
    global _worker_task, _stop_event

    if _worker_task and not _worker_task.done():
        return

    ensure_queue_storage()
    _stop_event = asyncio.Event()
    _worker_task = asyncio.create_task(
        _worker_loop(),
        name="textbook-digitization-worker",
    )


async def stop_digitization_worker() -> None:
    global _worker_task, _stop_event

    if not _worker_task:
        return

    if _stop_event:
        _stop_event.set()

    try:
        await asyncio.wait_for(_worker_task, timeout=10)
    except asyncio.TimeoutError:
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
    finally:
        _worker_task = None
        _stop_event = None
