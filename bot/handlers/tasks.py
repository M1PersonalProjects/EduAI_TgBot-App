from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from database import db

router = Router()

class QuestStates(StatesGroup):
    waiting_for_answer = State()

@router.message(F.text == "/quest")
async def start_quest(message: Message, state: FSMContext):
    user_id = message.from_user.id

    async with db.pool.acquire() as conn:
        student = await conn.fetchrow("SELECT role FROM users WHERE tg_id = $1 AND role = 'student'", user_id)
    
    if not student:
        await message.answer("Тренировочные квесты доступны только для пользователей с ролью Ученик.")
        return

    await state.set_state(QuestStates.waiting_for_answer)
    await message.answer(
        "📝 *Новое задание по Математике*:\n\n"
        "Реши уравнение: 2x + 4 = 12\n\n"
        "Отправь мне в ответ только получившееся число.",
        parse_mode="Markdown"
    )

@router.message(QuestStates.waiting_for_answer)
async def check_quest_answer(message: Message, state: FSMContext):
    user_answer = message.text.strip()
    user_id = message.from_user.id

    if user_answer == "4":
        async with db.pool.acquire() as conn:
            current_stats = await conn.fetchrow(
                "SELECT balance_coins, xp_total FROM gamification WHERE user_id = $1", 
                user_id
            )
            
            new_coins = (current_stats["balance_coins"] or 0) + 15
            new_xp = (current_stats["xp_total"] or 0) + 50

            await conn.execute(
                """
                UPDATE gamification 
                SET balance_coins = $1, xp_total = $2 
                WHERE user_id = $3
                """,
                new_coins, new_xp, user_id
            )

        await message.answer(
            f"🎉 *Ура! Ответ верный!*\n\n"
            f"Тебе начислено *15 монет* и *50 XP*.\n"
            f"Проверить баланс можно кнопкой «🏆 Мой профиль».",
            parse_mode="Markdown"
        )
        await state.clear()
    else:
        await message.answer(
            "❌ Ответ не совсем точный. Попробуй посчитать еще раз и пришли новый ответ!\n"
            "Если хочешь прервать квест, введи /cancel."
        )

@router.message(F.text == "/cancel")
async def cancel_quest(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Выполнение задания прервано. Ты можешь вернуться к нему в любое время.")