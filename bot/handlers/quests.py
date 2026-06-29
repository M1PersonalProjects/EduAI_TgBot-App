from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
import json
from database import db

router = Router()

class QuestStates(StatesGroup):
    waiting_for_answer = State()

class BookFilterStates(StatesGroup):
    choosing_grade = State()
    choosing_subject = State()
    choosing_book = State()
    choosing_topic = State()
    waiting_for_ai_question = State()


def get_quest_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Запустить квест", callback_data="start_random_quest")]
    ])

@router.message(F.text == "🏆 Мой профиль")
async def show_real_student_profile(message: Message):
    user_id = message.from_user.id
    async with db.pool.acquire() as conn:
        user = await conn.fetchrow("SELECT role FROM users WHERE tg_id = $1", user_id)
        if not user or user["role"] != "student":
            return 
        stats = await conn.fetchrow("SELECT balance_coins, xp_total FROM gamification WHERE user_id = $1", user_id)
    
    coins = stats["balance_coins"] if stats else 0
    xp = stats["xp_total"] if stats else 0

    await message.answer(
        f"🏆 *Твой личный профиль EduAI*:\n\n"
        f"💰 Баланс: `{coins}` монет\n"
        f"✨ Опыт: `{xp}` XP\n\n"
        f"Чтобы получить новое задание и заработать награды, введи команду /quest",
        parse_mode="Markdown"
    )

def skip_to_ai_button():
    return [InlineKeyboardButton(text="🤖 Пропустить и спросить ИИ", callback_data="skip_to_question")]

# 1. Нажатие на кнопку "Каталог учебников" -> Выбор Класса
@router.message(F.text == "📚 Каталог учебников")
async def start_book_filter(message: Message, state: FSMContext):
    await state.clear()
    
    # Генерируем сетку кнопок для классов 1-11
    keyboard_buttons = []
    row = []
    for grade in range(1, 12):
        row.append(InlineKeyboardButton(text=f"🏫 {grade} класс", callback_data=f"grade_{grade}"))
        if len(row) == 3 or grade == 11:
            keyboard_buttons.append(row)
            row = []
            
    keyboard_buttons.append(skip_to_ai_button())
    inline_kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await state.set_state(BookFilterStates.choosing_grade)
    await message.answer(
        "Выбор контекста обучения 📚\n\n"
        "Шаг 1: Выберите **класс**, по программе которого у вас вопрос:",
        reply_markup=inline_kb,
        parse_mode="Markdown"
    )

# 2. Выбрали класс -> Выбор Предмета
@router.callback_query(BookFilterStates.choosing_grade, F.data.startswith("grade_"))
async def handle_grade_choice(call: CallbackQuery, state: FSMContext):
    grade = call.data.split("_")[1]
    await state.update_data(chosen_grade=grade)
    
    subjects = ["Математика", "Алгебра", "Геометрия"]
    keyboard_buttons = []
    
    for sub in subjects:
        keyboard_buttons.append([InlineKeyboardButton(text=f"📐 {sub}", callback_data=f"subject_{sub}")])
        
    keyboard_buttons.append(skip_to_ai_button())
    inline_kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await state.set_state(BookFilterStates.choosing_subject)
    await call.message.edit_text(
        f"Выбран класс: *{grade}*\n\n"
        "Шаг 2: Выберите **предмет** обучения:",
        reply_markup=inline_kb,
        parse_mode="Markdown"
    )

# 3. Выбрали предмет -> Выбор Учебника (Автора)
@router.callback_query(BookFilterStates.choosing_subject, F.data.startswith("subject_"))
async def handle_subject_choice(call: CallbackQuery, state: FSMContext):
    subject = call.data.split("_")[1]
    await state.update_data(chosen_subject=subject)
    
    data = await state.get_data()
    grade = data.get("chosen_grade")
    
    mock_books = {
        "Алгебра": [{"id": "makarychev", "text": "Макарычев Ю.Н."}, {"id": "mordkovich", "text": "Мордкович А.Г."}],
        "Геометрия": [{"id": "atanasyan", "text": "Атанасян Л.С."}, {"id": "pogorelov", "text": "Погорелов А.В."}],
        "Математика": [{"id": "vilenkin", "text": "Виленкин Н.Я."}, {"id": "peterson", "text": "Петерсон Л.Г."}]
    }
    
    available_books = mock_books.get(subject, [{"id": "generic", "text": "Стандартный учебник Просвещение"}])
    keyboard_buttons = []
    
    for book in available_books:
        keyboard_buttons.append([InlineKeyboardButton(text=f"📖 {book['text']}", callback_data=f"book_{book['id']}_{book['text']}")])
        
    keyboard_buttons.append(skip_to_ai_button())
    inline_kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await state.set_state(BookFilterStates.choosing_book)
    await call.message.edit_text(
        f"Класс: *{grade}* | Предмет: *{subject}*\n\n"
        "Шаг 3: Выберите конкретного **автора учебника**:",
        reply_markup=inline_kb,
        parse_mode="Markdown"
    )

# 4. Выбрали учебник -> Опциональный выбор параграфа/страницы
@router.callback_query(BookFilterStates.choosing_book, F.data.startswith("book_"))
async def handle_book_choice(call: CallbackQuery, state: FSMContext):
    parts = call.data.split("_")
    book_title = parts[2]
    await state.update_data(chosen_book=book_title)
    
    data = await state.get_data()
    
    keyboard_buttons = [
        [InlineKeyboardButton(text="📝 Задать вопрос по этому учебнику", callback_data="skip_to_question")]
    ]
    inline_kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await state.set_state(BookFilterStates.choosing_topic)
    await call.message.edit_text(
        f"📋 *Выбранный контекст*:\n"
        f"🏫 Класс: {data.get('chosen_grade')}\n"
        f"📐 Предмет: {data.get('chosen_subject')}\n"
        f"📖 Учебник: {book_title}\n\n"
        "Шаг 4: Напишите в чат **номер параграфа, тему или страницу** (например: *Параграф 12* или *стр. 45*).\n\n"
        "Если это не важно, просто нажмите на кнопку ниже:",
        reply_markup=inline_kb,
        parse_mode="Markdown"
    )

@router.message(BookFilterStates.choosing_topic)
async def handle_topic_text(message: Message, state: FSMContext):
    await state.update_data(chosen_topic=message.text.strip())
    await enter_ai_question_mode(message, state)

# 5. Общая точка перехода к непосредственному вопросу к ИИ
@router.callback_query(F.data == "skip_to_question")
async def handle_skip_callback(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await enter_ai_question_mode(call.message, state)

async def enter_ai_question_mode(target_message: Message, state: FSMContext):
    data = await state.get_data()
    
    summary = "🤖 *Режим ИИ-Помощника*\n\n"
    if data.get("chosen_grade"):
        summary += f"📍 Фильтр: {data.get('chosen_grade')} класс, {data.get('chosen_subject')}"
        if data.get('chosen_book'):
            summary += f" ({data.get('chosen_book')})"
        if data.get('chosen_topic'):
            summary += f", {data.get('chosen_topic')}"
        summary += "\n\n"
    else:
        summary += "📍 Фильтр: *Автоопределение темы* (ИИ проанализирует все учебники программы)\n\n"
        
    await state.set_state(BookFilterStates.waiting_for_ai_question)
    
    await target_message.answer(
        summary + "Напишите свой вопрос ИИ-тьютору (например, условие сложной задачи или то, что непонятно в теории):",
        parse_mode="Markdown"
    )

# 6. Финальный прием вопроса ученика/родителя
@router.message(BookFilterStates.waiting_for_ai_question)
async def accept_final_ai_question(message: Message, state: FSMContext):
    question_text = message.text.strip()
    data = await state.get_data()
    
    response = (
        "🧠 *Запрос отправлен на обработку!*\n\n"
        f"❓ *Твой вопрос:* {question_text}\n\n"
        "🛠 *Собранные метаданные для ИИ*:\n"
        f"• Класс: {data.get('chosen_grade', 'Автоопределение')}\n"
        f"• Предмет: {data.get('chosen_subject', 'Автоопределение')}\n"
        f"• Учебник: {data.get('chosen_book', 'Автоопределение')}\n"
        f"• Локация: {data.get('chosen_topic', 'Автоопределение')}\n\n"
        "_(На следующем этапе здесь будет выполняться запрос к OpenAI, "
        "который вернет точный разбор со ссылкой на нужные правила!)_"
    )
    
    await message.answer(response, parse_mode="Markdown")
    await state.clear()

@router.callback_query(F.data.startswith("open_book_"))
async def handle_open_book(call: CallbackQuery):
    book_id = call.data.split("_")[2]
    await call.answer(f"Учебник №{book_id} успешно выбран! Интерактивные модули генерируются...", show_alert=True)

@router.message(F.text == "/quest")
async def send_quest_button(message: Message):
    await message.answer(
        "🎯 Хочешь заработать монеты и прокачать уровень?\n"
        "Нажми на кнопку ниже, чтобы запустить генерацию задания:",
        reply_markup=get_quest_keyboard()
    )

@router.callback_query(F.data == "start_random_quest")
async def start_quest_callback(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id

    async with db.pool.acquire() as conn:
        user = await conn.fetchrow("SELECT role, parent_id FROM users WHERE tg_id = $1", user_id)
        if not user or user["role"] != "student":
            await call.answer("Доступно только для учеников!", show_alert=True)
            return

        parent_id = user["parent_id"]
        
        task_data = {
            "question": "Реши уравнение: 3x - 5 = 10",
            "correct_answer": "5"
        }
        questions_json = json.dumps(task_data)
        
        topic_json = json.dumps({"theme": "Линейные уравнения"})

        await conn.execute(
            """
            INSERT INTO tasks_history (student_id, parent_id, topic_context, questions_json)
            VALUES ($1, $2, $3, $4)
            """,
            user_id, parent_id, topic_json, questions_json
        )

    await call.answer()
    await state.set_state(QuestStates.waiting_for_answer)
    await call.message.edit_text(
        f"📝 *Новое задание по теме «Линейные уравнения»*:\n\n"
        f"{task_data['question']}\n\n"
        "Пришли мне в ответ только получившееся число. Для отмены напиши `/cancel`.",
        parse_mode="Markdown"
    )

@router.message(QuestStates.waiting_for_answer)
async def check_quest_answer(message: Message, state: FSMContext):
    if message.text.strip() == "/cancel":
        await state.clear()
        await message.answer("Выполнение задания прервано.")
        return

    user_answer = message.text.strip()
    user_id = message.from_user.id

    async with db.pool.acquire() as conn:
        active_task = await conn.fetchrow(
            """
            SELECT task_id, questions_json 
            FROM tasks_history 
            WHERE student_id = $1 AND status = 'created'::task_status 
            ORDER BY task_id DESC LIMIT 1
            """,
            user_id
        )

        if not active_task:
            await message.answer("У тебя нет активных заданий.")
            await state.clear()
            return

        task_data = json.loads(active_task["questions_json"])
        correct_answer = task_data.get("correct_answer", "")

        if user_answer.lower() == correct_answer.lower():
            await conn.execute(
                """
                UPDATE tasks_history 
                SET status = 'completed'::task_status, score = 100, student_answers_json = $1 
                WHERE task_id = $2
                """,
                json.dumps({"student_answer": user_answer}), active_task["task_id"]
            )
            
            current_stats = await conn.fetchrow("SELECT balance_coins, xp_total FROM gamification WHERE user_id = $1", user_id)
            new_coins = (current_stats["balance_coins"] or 0) + 15
            new_xp = (current_stats["xp_total"] or 0) + 50

            await conn.execute(
                "UPDATE gamification SET balance_coins = $1, xp_total = $2 WHERE user_id = $3",
                new_coins, new_xp, user_id
            )

            await message.answer(
                "🎉 *Отлично! Ответ верный!*\n\n"
                "Задание успешно выполнено! Тебе начислено:\n"
                "💰 *+15 монет*\n"
                "✨ *+50 XP*",
                parse_mode="Markdown"
            )
            await state.clear()
        else:
            await message.answer("❌ Ответ неверный. Попробуй посчитать ещё раз или введи `/cancel`.")