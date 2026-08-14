import json
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from database import db
from logger_config import logger
from bot.media import parse_telegram_attachment
from bot.messages import answer_plain
from bot.handlers.ai_chat import exit_book_keyboard
from services.file_parser import AttachmentError
from services.thinking import TelegramThinkingIndicator
from services.tutor import exit_book_mode, openai_client, respond, ensure_telegram_session

router = Router()

class BookFilterStates(StatesGroup):
    choosing_grade = State()
    choosing_subject = State()
    choosing_book = State()
    choosing_topic = State()
    waiting_for_ai_question = State()


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
        f"🏆 Твой личный профиль EduAI:\n\n"
        f"💰 Баланс: {coins} монет\n"
        f"✨ Опыт: {xp} XP\n\n"
        "Чтобы получить новое задание и заработать награды, введи команду /quest"
    )

def skip_to_ai_button():
    return [InlineKeyboardButton(text="🤖 Пропустить и спросить ИИ", callback_data="skip_to_question")]


@router.message(F.text == "📚 Каталог учебников")
async def start_book_filter(message: Message, state: FSMContext):
    await state.clear()
    
    user_id = message.from_user.id
    async with db.pool.acquire() as conn:
        user = await conn.fetchrow("SELECT role FROM users WHERE tg_id = $1", user_id)
        if not user:
            await message.answer("Пожалуйста, сначала зарегистрируйтесь в системе.")
            return
    await state.update_data(user_role=user["role"])

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
        "Шаг 1: Выберите класс, по программе которого у вас вопрос:",
        reply_markup=inline_kb,
    )


@router.callback_query(BookFilterStates.choosing_grade, F.data.startswith("grade_"))
async def handle_grade_choice(call: CallbackQuery, state: FSMContext):
    grade = int(call.data.split("_")[1])
    await state.update_data(chosen_grade=grade)
    
    async with db.pool.acquire() as conn:
        records = await conn.fetch(
            "SELECT DISTINCT book_program FROM book WHERE book_class = $1 ORDER BY book_program",
            grade
        )
    
    subjects = [r["book_program"] for r in records if r["book_program"]]

    if not subjects:
        await call.answer("Для этого класса пока нет доступных предметов. Переходим к ИИ-помощнику.")
        await enter_ai_question_mode(call.message, state)
        return

    keyboard_buttons = []
    await state.update_data(available_subjects=subjects)
    for index, sub in enumerate(subjects):
        keyboard_buttons.append([
            InlineKeyboardButton(text=f"📐 {sub}"[:64], callback_data=f"subject_{index}")
        ])
        
    keyboard_buttons.append(skip_to_ai_button())
    inline_kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await state.set_state(BookFilterStates.choosing_subject)
    await call.message.edit_text(
        f"Выбран класс: {grade}\n\n"
        "Шаг 2: Выберите предмет обучения (сформировано автоматически):",
        reply_markup=inline_kb,
    )


@router.callback_query(BookFilterStates.choosing_subject, F.data.startswith("subject_"))
async def handle_subject_choice(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    subject_token = call.data.split("_", 1)[1]
    available_subjects = data.get("available_subjects", [])
    subject = (
        available_subjects[int(subject_token)]
        if subject_token.isdigit() and int(subject_token) < len(available_subjects)
        else subject_token
    )
    await state.update_data(chosen_subject=subject)
    grade = int(data.get("chosen_grade"))
    
    async with db.pool.acquire() as conn:
        books = await conn.fetch(
            "SELECT book_id, book_author, book_title FROM book WHERE book_class = $1 AND book_program ILIKE $2",
            grade, f"%{subject}%"
        )

    if not books:
        await call.answer("Учебники для этого класса еще не загружены. Переходим к ИИ-помощнику.")
        await enter_ai_question_mode(call.message, state)
        return

    keyboard_buttons = []
    for b in books:
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"📘 {b['book_author']} — {b['book_title']}"[:64],
                callback_data=f"book_{b['book_id']}"
            )
        ])
    keyboard_buttons.append(skip_to_ai_button())
    inline_kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await state.set_state(BookFilterStates.choosing_book)
    await call.message.edit_text(
        f"Выбран класс: {grade}, предмет: {subject}\n\n"
        "Шаг 3: Выберите учебник из базы:",
        reply_markup=inline_kb,
    )


@router.callback_query(BookFilterStates.choosing_book, F.data.startswith("book_"))
async def handle_book_choice(call: CallbackQuery, state: FSMContext):
    book_id = int(call.data.split("_")[1])
    
    async with db.pool.acquire() as conn:
        book_info = await conn.fetchrow("SELECT book_title, book_author FROM book WHERE book_id = $1", book_id)
        pages = await conn.fetch(
            """
            SELECT page_id, page_number, page_paragraph FROM page
            WHERE book_id = $1 ORDER BY page_number LIMIT 30
            """,
            book_id,
        )
    
    book_label = f"{book_info['book_author']} {book_info['book_title']}" if book_info else "Выбранный учебник"
    await state.update_data(chosen_book_id=book_id, chosen_book_label=book_label)
    
    data = await state.get_data()
    
    keyboard_buttons = []
    for page in pages:
        label = f"стр. {page['page_number']}"
        if page["page_paragraph"]:
            label += f" · {page['page_paragraph'][:28]}"
        keyboard_buttons.append([
            InlineKeyboardButton(text=label, callback_data=f"ctxpage_{page['page_id']}")
        ])
    keyboard_buttons.append([
        InlineKeyboardButton(text="📝 Весь учебник / указать тему", callback_data="skip_to_question")
    ])
    inline_kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await state.set_state(BookFilterStates.choosing_topic)
    await call.message.edit_text(
        "📋 Выбранный контекст:\n"
        f"🏫 Класс: {data.get('chosen_grade')}\n"
        f"📐 Предмет: {data.get('chosen_subject')}\n"
        f"📖 Учебник: {book_label}\n\n"
        "Шаг 4: Выберите страницу ниже либо напишите номер параграфа или тему.\n\n"
        "Этот контекст будет закреплён до команды /exit_book.",
        reply_markup=inline_kb,
    )

@router.message(BookFilterStates.choosing_topic, F.text)
async def handle_topic_text(message: Message, state: FSMContext):
    await state.update_data(chosen_topic=message.text.strip())
    await enter_ai_question_mode(message, state)


@router.message(BookFilterStates.choosing_topic, F.photo | F.document)
async def handle_topic_attachment(message: Message, state: FSMContext):
    """A file can be the first question immediately after book selection."""
    await state.set_state(BookFilterStates.waiting_for_ai_question)
    await accept_final_ai_question(message, state)


@router.callback_query(BookFilterStates.choosing_topic, F.data.startswith("ctxpage_"))
async def handle_page_choice(call: CallbackQuery, state: FSMContext):
    page_id = int(call.data.split("_")[1])
    await state.update_data(chosen_page_id=page_id)
    await call.answer("Страница выбрана")
    await enter_ai_question_mode(call.message, state)

@router.callback_query(F.data == "skip_to_question")
async def handle_skip_callback(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await enter_ai_question_mode(call.message, state)

async def enter_ai_question_mode(target_message: Message, state: FSMContext):
    data = await state.get_data()
    summary = "🤖 Режим ИИ-Помощника EduAI\n\n"
    if data.get("chosen_grade"):
        summary += f"📍 Контекст: {data.get('chosen_grade')} класс, {data.get('chosen_subject')}"
        if data.get('chosen_book_label'):
            summary += f" ({data.get('chosen_book_label')})"
        summary += "\n\n"
    else:
        summary += "📍 Контекст: автоматический поиск по запросу\n\n"
        
    await state.set_state(BookFilterStates.waiting_for_ai_question)
    await target_message.answer(
        summary + "Напишите вопрос или пришлите фото/документ. Выбор контекста необязателен:"
    )


@router.message(BookFilterStates.waiting_for_ai_question, Command("exit_book"))
async def exit_selected_book(message: Message, state: FSMContext):
    try:
        session = await ensure_telegram_session(message.from_user.id)
        await exit_book_mode(message.from_user.id, str(session["session_id"]))
    except LookupError:
        pass
    await state.clear()
    await message.answer("✅ Book Mode выключен. Теперь работает общий ИИ-тьютор.")


@router.message(BookFilterStates.waiting_for_ai_question)
async def accept_final_ai_question(message: Message, state: FSMContext):
    question_text = message.text or message.caption or ""
    question_text = question_text.strip()
    if not question_text and not message.photo and not message.document:
        await message.answer("Пришлите текст вопроса, фотографию или документ.")
        return
    data = await state.get_data()
    
    indicator = await TelegramThinkingIndicator(
        message, "ИИ-тьютор изучает контекст и вложение"
    ).start()
    try:
        attachment = await parse_telegram_attachment(message)
        manual_context = {
            "book_class": data.get("chosen_grade"),
            "book_program": data.get("chosen_subject"),
            "book_id": data.get("chosen_book_id"),
            "page_id": data.get("chosen_page_id"),
            "page_paragraph": data.get("chosen_topic"),
        }
        session = await ensure_telegram_session(message.from_user.id)
        result = await respond(
            user_id=message.from_user.id,
            role=data.get("user_role", "student"),
            session_id=str(session["session_id"]),
            message_text=question_text,
            attachment=attachment,
            manual_context=manual_context,
            lock_selected_context=bool(data.get("chosen_book_id")),
            message_source="telegram",
        )
        await indicator.stop()
        await answer_plain(
            message,
            f"🎓 Ответ ИИ-Тьютора:\n\n{result['message_text']}",
            reply_markup=exit_book_keyboard() if result["book_mode"] else None,
        )
    except AttachmentError as exc:
        await indicator.stop(delete=False)
        await indicator.status_message.edit_text(f"❌ {exc}")
    except Exception as exc:
        logger.exception("OpenAI MultiModal Error: %s", exc)
        await indicator.stop(delete=False)
        await indicator.status_message.edit_text(
            "❌ Произошла ошибка при обращении к нейросети. Попробуйте позже."
        )

    if not data.get("chosen_book_id"):
        await state.clear()
