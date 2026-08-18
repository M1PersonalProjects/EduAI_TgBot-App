import json
from typing import Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from openai import AsyncOpenAI

from database import db
from config import settings
from api.schemas.tasks import TaskGenerationResponse, SubmitAnswerRequest, SubmitAnswerResponse
from logger_config import logger
from services.response_formatter import MATH_FORMATTING_RULES
from services.context_resolver import resolve_book_context
from services.tutor_policy import student_task_prompt, task_grading_prompt

router = APIRouter(prefix="/api/tasks", tags=["Tasks"])

openai_client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())


class OpenAITaskGeneration(BaseModel):
    title: str = Field(..., description="Название задания/квеста (например: Практика по теме Градусная мера угла)")
    description: str = Field(..., description="Текст задачи/вопроса для ученика. Красивый Юникод (², •, °), без знаков $.")
    correct_answer: str = Field(..., description="Краткий эталонный ответ (число или слово) для сохранения и автопроверки бэкендом")

class OpenAITaskVerification(BaseModel):
    is_correct: bool = Field(..., description="True если ответ верен, иначе False")
    explanation: str = Field(..., description="Доброжелательное объяснение для Ученика на русском языке")

class GenerateTaskRequest(BaseModel):
    student_id: int
    book_id: int
    page_id: Optional[int] = None
    topic: Optional[str] = Field(default=None, max_length=300)
    instructions: Optional[str] = Field(default=None, max_length=4000)


@router.get("/generate/{tg_id}", response_model=TaskGenerationResponse)
async def generate_task_legacy(tg_id: int):
    """Генерация квестов с обратной совместимостью, используемая клиентом/тестами Telegram. 

    Эта конечная точка намеренно оставлена с методом GET, поскольку её используют существующие клиенты. Новое
    при родительском управлении с явным указанием книги/темы используется конечная точка POST,
    описанная ниже, и контекстный преобразователь для всей книги.
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
        response = await openai_client.beta.chat.completions.parse(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        student_task_prompt()
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Textbook: {page.get('book_title', '')} ({page.get('book_program', '')})\n"
                        f"Page content:\n{page_content}"
                    ),
                },
            ],
            response_format=OpenAITaskGeneration,
        )
        ai_task = response.choices[0].message.parsed

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
        }
        questions_json = {
            "title": ai_task.title,
            "question_text": ai_task.description,
            "reference_answer": ai_task.correct_answer,
        }

        async with db.pool.acquire() as conn:
            task_id = await conn.fetchval(
                """
                INSERT INTO tasks_history
                    (student_id, parent_id, topic_context, questions_json, score, status)
                VALUES ($1, $2, $3, $4, $5, 'created'::task_status)
                RETURNING task_id
                """,
                tg_id,
                student["parent_id"],
                json.dumps(topic_context),
                json.dumps(questions_json),
                0,
            )

        return TaskGenerationResponse(
            task_id=task_id,
            title=ai_task.title,
            description=ai_task.description,
            reward_coins=15,
            reward_xp=50,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Ошибка ИИ при legacy-генерации задачи: %s", exc)
        raise HTTPException(status_code=500, detail="Ошибка при создании квеста")


@router.post("/generate/{tg_id}", response_model=TaskGenerationResponse)
async def generate_task(tg_id: int, payload: GenerateTaskRequest):
    async with db.pool.acquire() as conn:
        student = await conn.fetchrow(
            "SELECT parent_id FROM users WHERE tg_id = $1 AND role = 'student'", 
            tg_id
        )
        if not student:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ученик с таким Telegram ID не найден"
            )
        
        context = await resolve_book_context(
            conn, book_id=payload.book_id, page_id=payload.page_id,
            query=f"{payload.topic or ''}\n{payload.instructions or ''}",
            source="legacy_task_generation",
        )
        if not context:
            raise HTTPException(status_code=404, detail="База знаний пуста.")
        if payload.page_id is not None and context.page_id is None:
            raise HTTPException(status_code=404, detail="Страница не относится к выбранному учебнику")
    try:
        response = await openai_client.beta.chat.completions.parse(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        student_task_prompt()
                    )
                },
                {
                    "role": "user",
                    "content": (f"Textbook: {context.book_title} ({context.book_program})\n" f"Context mode: {context.context_mode}\n" f"Topic: {payload.topic or ''}\n" f"Teacher instructions: {payload.instructions or ''}\n" f"Textbook context:\n{context.content}")
                }
            ],
            response_format=OpenAITaskGeneration
        )
        
        ai_task = response.choices[0].message.parsed
        
        topic_context = {
            "source": "legacy_task_generation", "topic": payload.topic,
            "book_id": context.book_id, "book_title": context.book_title,
            "book_class": context.book_class, "book_program": context.book_program,
            "context_mode": context.context_mode, "page_id": context.page_id,
            "page_title": context.page_title, "used_pages": context.used_pages,
            "subject": context.book_program,
        }
        
        questions_json = {
            "title": ai_task.title,
            "question_text": ai_task.description,
            "reference_answer": ai_task.correct_answer
        }

        async with db.pool.acquire() as conn:
            task_id = await conn.fetchval(
                """
                INSERT INTO tasks_history (student_id, parent_id, topic_context, questions_json, score, status)
                VALUES ($1, $2, $3, $4, $5, 'created'::task_status)
                RETURNING task_id
                """,
                tg_id, student["parent_id"], json.dumps(topic_context), json.dumps(questions_json), 0
            )

        return TaskGenerationResponse(
            task_id=task_id,
            title=ai_task.title,
            description=ai_task.description,
            reward_coins=15,
            reward_xp=50
        )

    except Exception as e:
        logger.error(f"Ошибка ИИ при генерации задачи: {str(e)}")
        raise HTTPException(status_code=500, detail="Ошибка при создании квеста")


@router.post("/submit", response_model=SubmitAnswerResponse)
async def submit_task_answer(payload: SubmitAnswerRequest):
    async with db.pool.acquire() as conn:
        task = await conn.fetchrow(
            """
            SELECT task_id, questions_json, topic_context
            FROM tasks_history
            WHERE task_id = $1 AND student_id = $2
            """,
            payload.task_id, payload.tg_id
        )
        if not task:
            raise HTTPException(status_code=404, detail="Задание не найдено")

        questions = task["questions_json"]
        if isinstance(questions, str):
            questions = json.loads(questions)
        correct_answer = questions.get("reference_answer", "")
        question_text = questions.get("question_text", "")

    try:
        response = await openai_client.beta.chat.completions.parse(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": task_grading_prompt()
                },
                {
                    "role": "user",
                    "content": (
                        f"Task Question: {question_text}\n"
                        f"Reference Answer: {correct_answer}\n"
                        f"Student's Answer: {payload.student_answer}"
                    )
                }
            ],
            response_format=OpenAITaskVerification
        )
        
        verification = response.choices[0].message.parsed
        
        student_answers_json = {
            "provided_answer": payload.student_answer,
            "verification_feedback": verification.explanation,
            "is_correct": verification.is_correct
        }

    except Exception as e:
        logger.error(f"Ошибка ИИ при верификации ответа: {str(e)}")
        raise HTTPException(status_code=500, detail="Ошибка нейросети при проверке ответа")

    async with db.pool.acquire() as conn:
        async with conn.transaction():
            current_gamification = await conn.fetchrow(
                "SELECT balance_coins, xp_total FROM gamification WHERE user_id = $1", 
                payload.tg_id
            )
            
            if not current_gamification:
                await conn.execute(
                    "INSERT INTO gamification (user_id, balance_coins, xp_total, streak_days) VALUES ($1, 0, 0, 0)",
                    payload.tg_id
                )
                coins, xp = 0, 0
            else:
                coins = current_gamification["balance_coins"] or 0
                xp = current_gamification["xp_total"] or 0

            if verification.is_correct:
                new_coins = coins + 15
                new_xp = xp + 50
                earned_score = 50

                updated_task = await conn.fetchval(
                    """
                    UPDATE tasks_history 
                    SET student_answers_json = $1, score = $2, status = 'evaluated'::task_status
                    WHERE task_id = $3 AND status IN ('created', 'in_progress')
                    RETURNING task_id
                    """, 
                    json.dumps(student_answers_json), earned_score, payload.task_id
                )
                if not updated_task:
                    raise HTTPException(status_code=409, detail="Задание уже было оценено")
                await conn.execute("UPDATE gamification SET balance_coins = $1, xp_total = $2 WHERE user_id = $3", new_coins, new_xp, payload.tg_id)

                return SubmitAnswerResponse(
                    success=True,
                    message=f"🎉 {verification.explanation}. Тебе начислено 15 монет и 50 XP!",
                    new_balance_coins=new_coins,
                    new_xp_total=new_xp
                )
            else:
                # Если ответ неверный, сохраняем попытку, очки остаются 0
                await conn.execute(
                    "UPDATE tasks_history SET student_answers_json = $1, score = 0, status = 'in_progress'::task_status WHERE task_id = $2 AND status IN ('created', 'in_progress')",
                    json.dumps(student_answers_json), payload.task_id
                )
                return SubmitAnswerResponse(
                    success=False,
                    message=f"❌ {verification.explanation}",
                    new_balance_coins=coins,
                    new_xp_total=xp
                )
