from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from bot.messages import answer_plain
from database import db
from services.quest_generation import check_quest_choice_answer, format_quest_question

router = Router()


class QuestStates(StatesGroup):
    """Состояние временного Telegram Quest-test."""

    waiting_for_answer = State()


@router.message(Command(commands=["cancel"]))
@router.message(F.text.lower() == "отмена")
async def cancel_quest(message: Message, state: FSMContext):
    """Останавливает Quest-test и полностью очищает временное состояние."""
    current_state = await state.get_state()
    if current_state is None:
        await answer_plain(message, "Сейчас нет активного Quest-test.")
        return
    await state.clear()
    await answer_plain(message, "Quest-test остановлен. Новый можно запустить в любое время.")


@router.message(Command(commands=["quest"]))
@router.message(F.text.in_({"🧩 Квест-тест", "🚀 Запустить квест"}))
async def start_quest(message: Message, state: FSMContext):
    """Открывает отдельный Telegram-only режим Quest-test для Ученика."""
    await state.clear()
    user_id = message.from_user.id

    async with db.pool.acquire() as conn:
        role = await conn.fetchval("SELECT role FROM users WHERE tg_id = $1", user_id)

    if role != "student":
        await answer_plain(message, "Quest-test доступен только пользователям с ролью Ученик.")
        return

    from bot.handlers.quests import quest_entry_keyboard

    await message.answer(
        "🧩 Quest-test\n\n"
        "Выберите учебник/тему из Umnix или опишите своими словами, какой тест хотите пройти. "
        "Состояние теста хранится только временно в Telegram и очищается после завершения или отмены.",
        reply_markup=quest_entry_keyboard(),
    )


@router.message(QuestStates.waiting_for_answer, F.text)
async def check_quest_answer(message: Message, state: FSMContext):
    """Проверяет текущий вопрос Quest-test без записи результата в БД."""
    data = await state.get_data()
    items = list(data.get("quest_items") or [])
    index = int(data.get("quest_index") or 0)
    answers = list(data.get("quest_answers") or [])

    if not items or index < 0 or index >= len(items):
        await state.clear()
        await answer_plain(message, "Активный Quest-test не найден. Запустите новый через кнопку «Квест-тест».")
        return

    item = items[index]
    is_correct, selected = check_quest_choice_answer(item, message.text or "")
    if is_correct is None:
        await answer_plain(
            message,
            "Ответьте только номером варианта. Если правильных вариантов несколько — перечислите их через пробел, например: 1 3.",
        )
        return

    answers.append(
        {
            "question_id": item.get("id") or index + 1,
            "selected_option_numbers": list(selected),
            "is_correct": bool(is_correct),
        }
    )

    if not is_correct:
        await state.update_data(quest_answers=answers)
        await answer_plain(
            message,
            "Пока неверно. Попробуйте ещё раз — текущий вопрос остаётся активным.\n\n"
            + format_quest_question(item, index + 1, len(items)),
        )
        return

    next_index = index + 1
    if next_index < len(items):
        next_item = items[next_index]
        await state.update_data(
            quest_index=next_index,
            quest_answers=answers,
            question_text=next_item.get("question_text") or "",
            correct_answer=next_item.get("reference_answer") or "",
        )
        await answer_plain(
            message,
            "✅ Верно!\n\n" + format_quest_question(next_item, next_index + 1, len(items)),
        )
        return

    correct_count = sum(1 for answer in answers if answer.get("is_correct"))
    total = len(items)
    title = str(data.get("quest_title") or "Quest-test").strip()
    await state.clear()
    await answer_plain(
        message,
        f"🏁 {title} завершён!\n\n"
        f"Правильных ответов: {correct_count} из {total}.\n"
        "Результат не сохраняется в БД. Можно сразу запустить новый Quest-test.",
    )
