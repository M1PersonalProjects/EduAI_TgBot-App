import json
from typing import Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from database import db
from api.schemas.tasks import OpenAITaskVerification, TaskGenerationResponse, SubmitAnswerRequest, SubmitAnswerResponse
from logger_config import logger
from services.ai import openai_client, parse_chat_completion
from services.context_resolver import resolve_book_context
from services.educational_context import build_context_from_metadata, build_educational_context, selected_context_from_page
from services.task_generation import (
    GeneratedTaskSet,
    extract_requested_task_count,
    generate_exact_task_set,
    task_set_payload,
)
from services.tutor_policy import student_task_prompt, task_grading_prompt
from services.assignment_source import TEACHER, infer_difficulty, normalize_assignment_source

router = APIRouter(prefix="/api/tasks", tags=["Tasks"])



class OpenAITaskGeneration(GeneratedTaskSet):
    """Backward-compatible name for the structured multi-task response model."""


class GenerateTaskRequest(BaseModel):
    student_id: int
    book_id: int
    page_id: Optional[int] = None
    topic: Optional[str] = Field(default=None, max_length=300)
    instructions: Optional[str] = Field(default=None, max_length=4000)
    task_count: int = Field(default=1, ge=1, le=100)


@router.get("/generate/{tg_id}", response_model=TaskGenerationResponse)
async def generate_task_legacy(tg_id: int):
    """
    Генерация случайного задания для ученика с указанным tg_id.
    Использует случайную страницу из базы знаний для создания задания.
    """
    async with db.pool.acquire() as conn:
        student = await conn.fetchrow(
            "SELECT parent_id FROM users WHERE tg_id = $1 AND role = 'student'",
            tg_id,
        )
        if not student:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ученик с таким Telegram ID не найден",
            )

        page = await conn.fetchrow(
            """
            SELECT
                p.page_id,
                p.page_markdown,
                p.page_text,
                p.page_title,
                p.page_number,
                b.book_id,
                b.book_title,
                b.book_program,
                b.book_class,
                b.book_author
            FROM page p
            JOIN book b ON b.book_id = p.book_id
            WHERE COALESCE(NULLIF(BTRIM(p.page_markdown), ''), NULLIF(BTRIM(p.page_text), '')) IS NOT NULL
            ORDER BY random()
            LIMIT 1
            """
        )
        if not page:
            raise HTTPException(status_code=404, detail="База знаний пуста.")

    page_content = page.get("page_markdown") or page.get("page_text") or ""
    try:
        primary = selected_context_from_page(page, source="legacy_random_page_generation")
        async with db.pool.acquire() as conn:
            from services.tutor import search_web_for_education
            bundle = await build_educational_context(
                conn,
                page.get("page_title") or page.get("book_program") or "practice",
                selected_context=primary,
                allow_context_resolution=False,
                allow_web=True,
                web_search=search_web_for_education,
            )
        source_text = (
            f"PRIMARY TEXTBOOK:\n{page_content}\n\n"
            f"RANKED UMNIX.AI SUPPLEMENTS:\n{bundle.database_context or 'none'}\n\n"
            f"WEB FALLBACK:\n{bundle.web_context or 'none'}"
        )
        ai_task = await generate_exact_task_set(
            openai_client,
            system_prompt=student_task_prompt(),
            user_content=(
                f"Textbook: {page.get('book_title', '')} ({page.get('book_program', '')})\n"
                f"{source_text}"
            ),
            requested_count=1,
        )

        topic_context = {
            "source": "legacy_random_page_generation",
            "book_id": page.get("book_id"),
            "book_title": page.get("book_title"),
            "book_class": page.get("book_class"),
            "book_program": page.get("book_program"),
            "context_mode": "single_page",
            "page_id": page.get("page_id"),
            "page_title": page.get("page_title"),
            "subject": page.get("book_program"),
            "source_trace": bundle.source_trace,
            "difficulty": infer_difficulty(page.get("page_title"), page_content),
        }
        questions_json = task_set_payload(ai_task)

        async with db.pool.acquire() as conn:
            task_id = await conn.fetchval(
                """
                INSERT INTO tasks_history
                    (student_id, parent_id, assignment_source, title, subject, topic, topic_context, questions_json, score, status)
                VALUES ($1, NULL, 'tutor_practice', $2, $3, $4, $5, $6, $7, 'created'::task_status)
                RETURNING task_id
                """,
                tg_id,
                ai_task.title,
                page.get("book_program"),
                page.get("page_title") or page.get("book_program") or ai_task.title,
                json.dumps(topic_context, ensure_ascii=False),
                json.dumps(questions_json, ensure_ascii=False),
                0,
            )

        return TaskGenerationResponse(
            task_id=task_id,
            title=ai_task.title,
            description=ai_task.description,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Ошибка ИИ при legacy-генерации задачи: %s", exc)
        raise HTTPException(status_code=500, detail="Ошибка при создании квеста")


@router.post("/generate/{tg_id}", response_model=TaskGenerationResponse)
async def generate_task(tg_id: int, payload: GenerateTaskRequest):
    """
    Генерация задания для ученика с указанным tg_id.
    """
    query_text = f"{payload.topic or ''}\n{payload.instructions or ''}".strip()
    requested_count = (
        payload.task_count
        if payload.task_count != 1
        else extract_requested_task_count(payload.topic, payload.instructions, default=1)
    )
    async with db.pool.acquire() as conn:
        student = await conn.fetchrow(
            "SELECT parent_id FROM users WHERE tg_id = $1 AND role = 'student'", tg_id
        )
        if not student:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ученик с таким Telegram ID не найден",
            )
        context = await resolve_book_context(
            conn,
            book_id=payload.book_id,
            page_id=payload.page_id,
            query=query_text,
            source="legacy_task_generation",
        )
        if not context:
            raise HTTPException(status_code=404, detail="База знаний пуста.")
        if payload.page_id is not None and context.page_id is None:
            raise HTTPException(status_code=404, detail="Страница не относится к выбранному учебнику")
        from services.tutor import search_web_for_education
        bundle = await build_educational_context(
            conn,
            query_text or context.book_program,
            selected_context=context,
            allow_context_resolution=False,
            allow_web=True,
            web_search=search_web_for_education,
            requested_items=requested_count,
        )

    try:
        ai_task = await generate_exact_task_set(
            openai_client,
            system_prompt=student_task_prompt(),
            user_content=(
                f"Textbook: {context.book_title} ({context.book_program})\n"
                f"Context mode: {context.context_mode}\n"
                f"Topic: {payload.topic or ''}\n"
                f"Teacher instructions: {payload.instructions or ''}\n"
                f"PRIMARY TEXTBOOK CONTEXT:\n{context.content}\n\n"
                f"RANKED UMNIX.AI SUPPLEMENTS:\n{bundle.database_context or 'none'}\n\n"
                f"WEB FALLBACK:\n{bundle.web_context or 'none'}"
            ),
            requested_count=requested_count,
        )

        topic_context = {
            "source": "legacy_task_generation",
            "topic": payload.topic,
            "book_id": context.book_id,
            "book_title": context.book_title,
            "book_class": context.book_class,
            "book_program": context.book_program,
            "context_mode": context.context_mode,
            "page_id": context.page_id,
            "page_title": context.page_title,
            "used_pages": context.used_pages,
            "subject": context.book_program,
            "requested_count": requested_count,
            "generated_count": len(ai_task.items),
            "source_trace": bundle.source_trace,
            "difficulty": infer_difficulty(payload.topic, payload.instructions),
        }
        questions_json = task_set_payload(ai_task)

        async with db.pool.acquire() as conn:
            task_id = await conn.fetchval(
                """
                INSERT INTO tasks_history (
                    student_id, parent_id, assignment_source, title, subject, topic, topic_context, questions_json, score, status
                )
                VALUES ($1, NULL, 'tutor_practice', $2, $3, $4, $5, $6, $7, 'created'::task_status)
                RETURNING task_id
                """,
                tg_id,
                ai_task.title,
                context.book_program,
                payload.topic or context.page_title or context.book_program or ai_task.title,
                json.dumps(topic_context, ensure_ascii=False),
                json.dumps(questions_json, ensure_ascii=False),
                0,
            )
        return TaskGenerationResponse(
            task_id=task_id,
            title=ai_task.title,
            description=ai_task.description,
        )
    except Exception as exc:
        logger.error("Ошибка ИИ при генерации задачи: %s", exc)
        raise HTTPException(status_code=500, detail="Ошибка при создании квеста")


@router.post("/submit", response_model=SubmitAnswerResponse)
async def submit_task_answer(payload: SubmitAnswerRequest):
    """
    Отправка ответа ученика на задание.
    """
    async with db.pool.acquire() as conn:
        task = await conn.fetchrow(
            """
            SELECT task_id, parent_id, assignment_source, questions_json, topic_context, student_answers_json
            FROM tasks_history
            WHERE task_id = $1 AND student_id = $2
              AND status IN ('created', 'in_progress')
            """,
            payload.task_id, payload.tg_id,
        )
        if not task:
            raise HTTPException(status_code=404, detail="Задание не найдено")

        questions = task["questions_json"]
        if isinstance(questions, str):
            questions = json.loads(questions)
        topic_context = task["topic_context"]
        if isinstance(topic_context, str):
            topic_context = json.loads(topic_context)
        previous_answers = task["student_answers_json"]
        if isinstance(previous_answers, str):
            try:
                previous_answers = json.loads(previous_answers)
            except json.JSONDecodeError:
                previous_answers = {}
        previous_answers = previous_answers or {}
        attempt_number = int(previous_answers.get("attempt_count") or 0) + 1
        source = normalize_assignment_source(
            task.get("assignment_source") if hasattr(task, "get") else task["assignment_source"],
            task.get("parent_id") if hasattr(task, "get") else task["parent_id"],
        )

        if source == TEACHER:
            answer_data = {
                "provided_answer": payload.student_answer,
                "review_status": "pending_review",
                "attempt_count": attempt_number,
            }
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO task_submissions (task_id, student_id, answer_text, attempt_number, status)
                    VALUES ($1,$2,$3,$4,'pending_review')
                    """,
                    payload.task_id, payload.tg_id, payload.student_answer, attempt_number,
                )
                updated = await conn.fetchval(
                    """
                    UPDATE tasks_history
                    SET student_answers_json=$1::jsonb, status='pending_review'::task_status,
                        updated_at=CURRENT_TIMESTAMP
                    WHERE task_id=$2 AND student_id=$3 AND status IN ('created','in_progress')
                    RETURNING task_id
                    """,
                    json.dumps(answer_data, ensure_ascii=False), payload.task_id, payload.tg_id,
                )
                if not updated:
                    raise HTTPException(status_code=409, detail="Задание уже отправлено на проверку")
            return SubmitAnswerResponse(
                success=True,
                status="pending_review",
                message="Ответ отправлен Учителю и ожидает ручной проверки.",
            )

        question_text = questions.get("question_text", "")
        correct_answer = questions.get("reference_answer", "")
        grading_context = await build_context_from_metadata(
            conn,
            str((topic_context or {}).get("topic") or question_text),
            topic_context or {},
        )

    try:
        response = await parse_chat_completion(
            openai_client,
            messages=[
                {"role": "system", "content": task_grading_prompt()},
                {
                    "role": "user",
                    "content": (
                        f"Task Question: {question_text}\n"
                        f"Reference Answer: {correct_answer}\n"
                        f"Student's Answer: {payload.student_answer}\n\n"
                        f"PRIMARY EDUCATIONAL CONTEXT:\n{grading_context.primary.content if grading_context.primary else 'none'}\n\n"
                        f"RANKED UMNIX.AI SUPPLEMENTS:\n{grading_context.database_context or 'none'}"
                    ),
                },
            ],
            response_format=OpenAITaskVerification,
        )
        verification = response.choices[0].message.parsed
    except Exception as exc:
        logger.error("Ошибка ИИ при верификации ответа: %s", exc)
        raise HTTPException(status_code=500, detail="Ошибка нейросети при проверке ответа")

    student_answers_json = {
        "provided_answer": payload.student_answer,
        "verification_feedback": verification.explanation,
        "is_correct": verification.is_correct,
        "attempt_count": attempt_number,
    }

    async with db.pool.acquire() as conn:
        async with conn.transaction():
            if verification.is_correct:
                updated_task = await conn.fetchval(
                    """
                    UPDATE tasks_history
                    SET student_answers_json=$1::jsonb, score=100, status='completed'::task_status,
                        completed_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
                    WHERE task_id=$2 AND student_id=$3
                      AND status IN ('created', 'in_progress')
                    RETURNING task_id
                    """,
                    json.dumps(student_answers_json, ensure_ascii=False),
                    payload.task_id,
                    payload.tg_id,
                )
                if not updated_task:
                    raise HTTPException(status_code=409, detail="Задание уже было завершено")
                return SubmitAnswerResponse(
                    success=True,
                    status="completed",
                    message=f"🎉 {verification.explanation}",
                )

            await conn.execute(
                """
                UPDATE tasks_history
                SET student_answers_json=$1::jsonb, score=0, status='in_progress'::task_status,
                    updated_at=CURRENT_TIMESTAMP
                WHERE task_id=$2 AND student_id=$3 AND status IN ('created', 'in_progress')
                """,
                json.dumps(student_answers_json, ensure_ascii=False),
                payload.task_id,
                payload.tg_id,
            )
            return SubmitAnswerResponse(
                success=False,
                status="in_progress",
                message=f"❌ {verification.explanation}",
            )
