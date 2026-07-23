import json
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from openai import AsyncOpenAI

from database import db
from config import settings
from api.schemas.tasks import TaskGenerationResponse, SubmitAnswerRequest, SubmitAnswerResponse
from logger_config import logger

router = APIRouter(prefix="/api/tasks", tags=["Tasks"])

openai_client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())


class OpenAITaskGeneration(BaseModel):
    title: str = Field(..., description="Название задания/квеста (например: Практика по теме Градусная мера угла)")
    description: str = Field(..., description="Текст задачи/вопроса для ученика. Красивый Юникод (², •, °), без знаков $.")
    correct_answer: str = Field(..., description="Краткий эталонный ответ (число или слово) для сохранения и автопроверки бэкендом")

class OpenAITaskVerification(BaseModel):
    is_correct: bool = Field(..., description="True если ответ верен, иначе False")
    explanation: str = Field(..., description="Доброжелательное объяснение для ребенка на русском языке")


@router.get("/generate/{tg_id}", response_model=TaskGenerationResponse)
async def generate_task(tg_id: int):
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
        
        page = await conn.fetchrow(
            """
            SELECT p.page_id, p.page_markdown, p.page_title, b.book_title, b.book_program
            FROM page p
            JOIN book b ON p.book_id = b.book_id
            ORDER BY RANDOM() 
            LIMIT 1
            """
        )
        if not page:
            raise HTTPException(status_code=404, detail="База знаний пуста.")

    try:
        response = await openai_client.beta.chat.completions.parse(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert school mathematics tutor on the EduAI platform. "
                        "Based on the provided textbook page context, generate exactly ONE engaging exercise or practical question to test the student's understanding.\n\n"
                        "CRITICAL FORMATTING RULES:\n"
                        "1. NEVER use LaTeX service symbols such as '$', '$$', '\\(', or '\\)'.\n"
                        "2. Format all mathematical notations using beautiful, human-readable Unicode characters: "
                        "use superscripts for powers (e.g., x², y³), '•' or 'x' for multiplication, '°' for degrees (e.g., 90°, 180°), and clear fractions (e.g., 1/2 or ½).\n"
                        "3. Ensure the 'correct_answer' field contains a concise, unambiguous baseline answer (a single number or word) for automated verification.\n"
                        "4. Write the final 'title' and 'description' in Russian, as they will be displayed directly to the child."
                    )
                },
                {
                    "role": "user",
                    "content": f"Textbook: {page['book_title']} ({page['book_program']})\nPage Content Context:\n{page['page_markdown']}"
                }
            ],
            response_format=OpenAITaskGeneration
        )
        
        ai_task = response.choices[0].message.parsed
        
        topic_context = {
            "page_id": page["page_id"],
            "book_title": page["book_title"],
            "page_title": page["page_title"],
            "subject": page["book_program"]
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
                    "content": (
                        "You are a supportive and encouraging school mathematics teacher grading a student's answer. "
                        "Compare the student's answer with the provided reference answer.\n\n"
                        "GRADING RULES:\n"
                        "1. If the student's answer matches the reference answer in meaning or is mathematically equivalent "
                        "(e.g., '0.5' and '1/2', '5' and '5 cm', 'x=3' and '3'), set 'is_correct' to True. Otherwise, set it to False.\n"
                        "2. Provide a friendly, polite, and constructive explanation ('explanation') in Russian tailored for a child.\n"
                        "3. Do not use any LaTeX symbols ('$') in your explanation. Use clean text and Unicode characters if necessary."
                    )
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
