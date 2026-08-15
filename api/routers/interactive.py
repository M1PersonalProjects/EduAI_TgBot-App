from __future__ import annotations

import json
import uuid
from urllib.parse import quote
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from api.security import get_current_user
from database import db
from services.interactive_apps import serialize_app


router = APIRouter(prefix="/api/v1/interactive", tags=["Interactive assignments"])


class AssignmentRequest(BaseModel):
    student_ids: List[int] = Field(..., min_length=1, max_length=100)


class ResultRequest(BaseModel):
    score: float = 0
    max_score: float = 0
    completed: bool = False
    answers: dict[str, Any] = Field(default_factory=dict)


def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(status_code=404, detail="Интерактивное задание не найдено") from exc


async def _accessible_app(conn, app_id: uuid.UUID, user: Any):
    row = await conn.fetchrow(
        """
        SELECT a.app_id, a.owner_id, a.session_id, a.source_message_id, a.title,
               a.app_type, a.question_count, a.current_version, a.created_at,
               a.updated_at, v.html_document,
               EXISTS(
                   SELECT 1 FROM interactive_assignments ia
                   WHERE ia.app_id=a.app_id AND ia.student_id=$2
               ) AS assigned_to_user
        FROM interactive_apps a
        JOIN interactive_app_versions v
          ON v.app_id=a.app_id AND v.version_no=a.current_version
        WHERE a.app_id=$1
          AND (a.owner_id=$2 OR EXISTS(
              SELECT 1 FROM interactive_assignments ia
              WHERE ia.app_id=a.app_id AND ia.student_id=$2
          ))
        """,
        app_id,
        user["tg_id"],
    )
    if not row:
        raise HTTPException(status_code=404, detail="Интерактивное задание не найдено")
    return row


@router.get("/students")
async def teacher_students(user=Depends(get_current_user)):
    if user["role"] not in {"parent", "admin"}:
        raise HTTPException(status_code=403, detail="Список Учеников доступен только Учителю")
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT tg_id, username
            FROM users
            WHERE parent_id=$1 AND role='student'
            ORDER BY username NULLS LAST, tg_id
            """,
            user["tg_id"],
        )
    return [dict(row) for row in rows]


@router.get("/{app_id}")
async def get_interactive(app_id: str, user=Depends(get_current_user)):
    async with db.pool.acquire() as conn:
        row = await _accessible_app(conn, _uuid(app_id), user)
    data = serialize_app(row)
    data["html_document"] = row["html_document"]
    data["can_assign"] = user["role"] in {"parent", "admin"} and row["owner_id"] == user["tg_id"]
    return data


@router.get("/{app_id}/versions")
async def versions(app_id: str, user=Depends(get_current_user)):
    parsed = _uuid(app_id)
    async with db.pool.acquire() as conn:
        await _accessible_app(conn, parsed, user)
        rows = await conn.fetch(
            """
            SELECT version_no, change_request, created_by, created_at
            FROM interactive_app_versions
            WHERE app_id=$1 ORDER BY version_no DESC
            """,
            parsed,
        )
    return [dict(row) for row in rows]


@router.get("/{app_id}/download")
async def download_interactive(app_id: str, user=Depends(get_current_user)):
    parsed = _uuid(app_id)
    async with db.pool.acquire() as conn:
        row = await _accessible_app(conn, parsed, user)
    display_name = re_safe_filename(row["title"]) + ".html"
    encoded_name = quote(display_name, safe="")
    return Response(
        content=row["html_document"],
        media_type="text/html; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="interactive.html"; filename*=UTF-8\'\'{encoded_name}'
            )
        },
    )


def re_safe_filename(value: str) -> str:
    import re
    clean = re.sub(r"[^A-Za-zА-Яа-яЁё0-9._-]+", "_", str(value or "interactive"))
    return clean.strip("._")[:80] or "interactive"


@router.post("/{app_id}/assign", status_code=status.HTTP_201_CREATED)
async def assign_interactive(
    app_id: str,
    payload: AssignmentRequest,
    user=Depends(get_current_user),
):
    if user["role"] not in {"parent", "admin"}:
        raise HTTPException(status_code=403, detail="Назначать задания может только Учитель")
    parsed = _uuid(app_id)
    created = []
    async with db.pool.acquire() as conn:
        owner = await conn.fetchrow(
            "SELECT app_id, title, current_version FROM interactive_apps WHERE app_id=$1 AND owner_id=$2",
            parsed,
            user["tg_id"],
        )
        if not owner:
            raise HTTPException(status_code=404, detail="Интерактивное задание не найдено")
        students = await conn.fetch(
            """
            SELECT tg_id FROM users
            WHERE tg_id = ANY($1::bigint[]) AND parent_id=$2 AND role='student'
            """,
            payload.student_ids,
            user["tg_id"],
        )
        valid_ids = {int(row["tg_id"]) for row in students}
        requested = {int(value) for value in payload.student_ids}
        if valid_ids != requested:
            raise HTTPException(status_code=404, detail="Один или несколько Учеников не привязаны к Учителю")
        async with conn.transaction():
            for student_id in payload.student_ids:
                assignment_batch = uuid.uuid4()
                topic_context = {
                    "source": "interactive_app",
                    "interactive_app_id": str(parsed),
                    "interactive_version": int(owner["current_version"]),
                }
                questions_json = {
                    "title": owner["title"],
                    "question_text": "Откройте интерактивное задание и выполните его на странице EduAI.",
                    "reference_answer": "Результат проверяется самим интерактивным заданием.",
                    "interactive_app_id": str(parsed),
                }
                task_id = await conn.fetchval(
                    """
                    INSERT INTO tasks_history (
                        student_id, parent_id, assignment_batch_id, title,
                        subject, topic, topic_context, questions_json,
                        score, status, sent_at, updated_at
                    ) VALUES (
                        $1,$2,$3,$4,'Интерактивное задание',$4,$5::jsonb,$6::jsonb,
                        0,'created'::task_status,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP
                    ) RETURNING task_id
                    """,
                    student_id,
                    user["tg_id"],
                    assignment_batch,
                    owner["title"],
                    json.dumps(topic_context, ensure_ascii=False),
                    json.dumps(questions_json, ensure_ascii=False),
                )
                assignment_id = await conn.fetchval(
                    """
                    INSERT INTO interactive_assignments (app_id, teacher_id, student_id, task_id)
                    VALUES ($1,$2,$3,$4)
                    ON CONFLICT (app_id, student_id) DO UPDATE
                    SET teacher_id=EXCLUDED.teacher_id, task_id=EXCLUDED.task_id,
                        assigned_at=CURRENT_TIMESTAMP
                    RETURNING assignment_id
                    """,
                    parsed,
                    user["tg_id"],
                    student_id,
                    task_id,
                )
                created.append({"student_id": student_id, "task_id": task_id, "assignment_id": assignment_id})
    return {"status": "assigned", "app_id": str(parsed), "assignments": created}


@router.post("/{app_id}/result")
async def save_result(
    app_id: str,
    payload: ResultRequest,
    user=Depends(get_current_user),
):
    if user["role"] != "student":
        raise HTTPException(status_code=403, detail="Результат сохраняется только для Ученика")
    parsed = _uuid(app_id)
    async with db.pool.acquire() as conn:
        assignment = await conn.fetchrow(
            """
            SELECT ia.assignment_id, ia.task_id, a.current_version
            FROM interactive_assignments ia
            JOIN interactive_apps a ON a.app_id=ia.app_id
            WHERE ia.app_id=$1 AND ia.student_id=$2
            """,
            parsed,
            user["tg_id"],
        )
        if not assignment:
            raise HTTPException(status_code=404, detail="Это интерактивное задание не назначено Ученику")
        maximum = max(float(payload.max_score or 0), 0.0)
        requested_score = max(float(payload.score or 0), 0.0)
        score = min(requested_score, maximum) if maximum > 0 else 0.0
        percent = min(100, round((score / maximum) * 100)) if maximum > 0 else (100 if payload.completed else 0)
        progress = {
            "score": score,
            "max_score": maximum,
            "percent": percent,
            "completed": bool(payload.completed),
            "answers": payload.answers,
        }
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO interactive_results (
                    app_id, version_no, student_id, assignment_id,
                    score, max_score, progress, completed
                ) VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8)
                """,
                parsed,
                assignment["current_version"],
                user["tg_id"],
                assignment["assignment_id"],
                score,
                maximum,
                json.dumps(progress, ensure_ascii=False),
                payload.completed,
            )
            if assignment["task_id"]:
                attempt = await conn.fetchval(
                    """
                    SELECT COALESCE(MAX(attempt_number),0)+1
                    FROM task_submissions WHERE task_id=$1 AND student_id=$2
                    """,
                    assignment["task_id"],
                    user["tg_id"],
                )
                await conn.execute(
                    """
                    INSERT INTO task_submissions (
                        task_id, student_id, answer_text, attempt_number,
                        ai_feedback, score, status, reviewed_at
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7,CURRENT_TIMESTAMP)
                    """,
                    assignment["task_id"],
                    user["tg_id"],
                    json.dumps(payload.answers, ensure_ascii=False),
                    attempt,
                    "Результат интерактивного задания сохранён.",
                    percent,
                    "completed" if payload.completed else "needs_revision",
                )
                await conn.execute(
                    """
                    UPDATE tasks_history
                    SET student_answers_json=$1::jsonb, score=$2,
                        status=$3::task_status,
                        completed_at=CASE WHEN $3='evaluated' THEN CURRENT_TIMESTAMP ELSE completed_at END,
                        updated_at=CURRENT_TIMESTAMP
                    WHERE task_id=$4 AND student_id=$5
                    """,
                    json.dumps(progress, ensure_ascii=False),
                    percent,
                    "evaluated" if payload.completed else "in_progress",
                    assignment["task_id"],
                    user["tg_id"],
                )
    return {"status": "saved", "score": score, "max_score": maximum, "percent": percent, "completed": payload.completed}
