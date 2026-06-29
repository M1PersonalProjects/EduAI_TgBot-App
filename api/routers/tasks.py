from fastapi import APIRouter, HTTPException, status
from database import db
from api.schemas.tasks import TaskGenerationResponse, SubmitAnswerRequest, SubmitAnswerResponse

from logger_config import logger

router = APIRouter(prefix="/api/tasks", tags=["Tasks"])

FAKE_ANSWERS_DB = {
    1: "4",
    2: "х=5",
    3: "причастие"
}

@router.get("/generate/{tg_id}", response_model=TaskGenerationResponse)
async def generate_task(tg_id: int):
    async with db.pool.acquire() as conn:
        student = await conn.fetchrow(
            "SELECT role FROM users WHERE tg_id = $1 AND role = 'student'", 
            tg_id
        )
        if not student:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ученик с таким Telegram ID не найден"
            )
        
        book = await conn.fetchrow("SELECT book_id, subject, class_level FROM books_db LIMIT 1")
    
    subject = book["subject"] if book else "Математика"
    class_level = book["class_level"] if book else 5

    task_id = 1
    title = f"Квест по предмету {subject} ({class_level} класс)"
    description = "Реши уравнение: 2x + 4 = 12. В ответ запиши только число."
    
    return TaskGenerationResponse(
        task_id=task_id,
        title=title,
        description=description,
        reward_coins=15,
        reward_xp=50
    )

@router.post("/submit", response_model=SubmitAnswerResponse)
async def submit_task_answer(payload: SubmitAnswerRequest):
    logger.info(f"Юзер TG_ID {payload.tg_id} отправил ответ на task_id: {payload.task_id}")
    correct_answer = FAKE_ANSWERS_DB.get(payload.task_id)
    logger.info(f"Результат поиска в DB: {correct_answer}")
    if not correct_answer:
        logger.warning(f"Ошибка 404! Задача task_id: {payload.task_id} не существует в базе")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Задание с таким ID не найдено"
        )
    logger.info(f"Результат поиска ответа в DB для task_id {payload.task_id}: {correct_answer}")

    is_correct = payload.student_answer.strip().lower() == correct_answer.strip().lower()

    async with db.pool.acquire() as conn:
        current_gamification = await conn.fetchrow(
            """
            SELECT balance_coins, xp_total 
            FROM gamification 
            WHERE user_id = $1
            """, 
            payload.tg_id
        )
        
        if not current_gamification:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Данные геймификации для этого пользователя не найдены"
            )

        coins = current_gamification["balance_coins"]
        xp = current_gamification["xp_total"]

        if is_correct:
            logger.info(f"Ученик {payload.tg_id} правильно решил задачу №{payload.task_id} и получил монеты")
            new_coins = coins + 15
            new_xp = xp + 50

            await conn.execute(
                """
                UPDATE gamification 
                SET balance_coins = $1, xp_total = $2 
                WHERE user_id = $3
                """,
                new_coins, new_xp, payload.tg_id
            )

            return SubmitAnswerResponse(
                success=True,
                message="🎉 Отлично! Ответ верный. Тебе начислено 15 монет и 50 XP!",
                new_balance_coins=new_coins,
                new_xp_total=new_xp
            )
        else:
            logger.info(f"Ученик {payload.tg_id} ошибся в задаче №{payload.task_id}")
            return SubmitAnswerResponse(
                success=False,
                message="❌ Ответ неверный. Попробуй ещё раз, у тебя обязательно получится!",
                new_balance_coins=coins,
                new_xp_total=xp
            )