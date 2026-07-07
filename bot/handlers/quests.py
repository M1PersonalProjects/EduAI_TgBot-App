import json
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from database import db
from openai import AsyncOpenAI
from config import settings
from logger_config import logger

router = Router()

openai_client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())

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


@router.message(F.text == "📚 Каталог учебников")
async def start_book_filter(message: Message, state: FSMContext):
    await state.clear()
    
    user_id = message.from_user.id
    async with db.pool.acquire() as conn:
        user = await conn.fetchrow("SELECT role FROM users WHERE tg_id = $1", user_id)
        if not user:
            await message.answer("Пожалуйста, сначала зарегистрируйтесь в системе.")
            return

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
    for sub in subjects:
        keyboard_buttons.append([InlineKeyboardButton(text=f"📐 {sub}", callback_data=f"subject_{sub}")])
        
    keyboard_buttons.append(skip_to_ai_button())
    inline_kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await state.set_state(BookFilterStates.choosing_subject)
    await call.message.edit_text(
        f"Выбран класс: *{grade}*\n\n"
        "Шаг 2: Выберите **предмет** обучения (сформировано автоматически):",
        reply_markup=inline_kb,
        parse_mode="Markdown"
    )


@router.callback_query(BookFilterStates.choosing_subject, F.data.startswith("subject_"))
async def handle_subject_choice(call: CallbackQuery, state: FSMContext):
    subject = call.data.split("_")[1]
    await state.update_data(chosen_subject=subject)
    data = await state.get_data()
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
                text=f"📘 {b['book_author']} — {b['book_title'][:18]}...", 
                callback_data=f"book_{b['book_id']}"
            )
        ])
    keyboard_buttons.append(skip_to_ai_button())
    inline_kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await state.set_state(BookFilterStates.choosing_book)
    await call.message.edit_text(
        f"Выбран класс: *{grade}*, Предмет: *{subject}*\n\nШаг 3: Выберите **учебник** из базы:",
        reply_markup=inline_kb,
        parse_mode="Markdown"
    )


@router.callback_query(BookFilterStates.choosing_book, F.data.startswith("book_"))
async def handle_book_choice(call: CallbackQuery, state: FSMContext):
    book_id = int(call.data.split("_")[1])
    
    async with db.pool.acquire() as conn:
        book_info = await conn.fetchrow("SELECT book_title, book_author FROM book WHERE book_id = $1", book_id)
    
    book_label = f"{book_info['book_author']} {book_info['book_title']}" if book_info else "Выбранный учебник"
    await state.update_data(chosen_book_id=book_id, chosen_book_label=book_label)
    
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
        f"📖 Учебник: {book_label}\n\n"
        "Шаг 4: Напишите в чат **номер параграфа, тему или страницу** (например: *Параграф 12* или *стр. 45*).\n\n"
        "Если это не важно, просто нажмите на кнопку ниже:",
        reply_markup=inline_kb,
        parse_mode="Markdown"
    )

@router.message(BookFilterStates.choosing_topic)
async def handle_topic_text(message: Message, state: FSMContext):
    await state.update_data(chosen_topic=message.text.strip())
    await enter_ai_question_mode(message, state)

@router.callback_query(F.data == "skip_to_question")
async def handle_skip_callback(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await enter_ai_question_mode(call.message, state)

async def enter_ai_question_mode(target_message: Message, state: FSMContext):
    data = await state.get_data()
    summary = "🤖 *Режим ИИ-Помощника EduAI*\n\n"
    if data.get("chosen_grade"):
        summary += f"📍 Контекст: {data.get('chosen_grade')} класс, {data.get('chosen_subject')}"
        if data.get('chosen_book_label'):
            summary += f" ({data.get('chosen_book_label')})"
        summary += "\n\n"
    else:
        summary += "📍 Контекст: *Глобальный поиск по всей базе знаний*\n\n"
        
    await state.set_state(BookFilterStates.waiting_for_ai_question)
    await target_message.answer(
        summary + "Напишите свой вопрос ИИ-тьютору или пришлите фото/документ с задачей:",
        parse_mode="Markdown"
    )


@router.message(BookFilterStates.waiting_for_ai_question)
async def accept_final_ai_question(message: Message, state: FSMContext):
    question_text = message.text or message.caption or ""
    question_text = question_text.strip()
    data = await state.get_data()
    
    status_msg = await message.answer("🧠 *ИИ-Тьютор изучает учебники и медиафайлы...* ⏳", parse_mode="Markdown")
    
    grade = data.get("chosen_grade")
    book_id = data.get("chosen_book_id")
    topic = data.get("chosen_topic")
    
    context_str = ""
    async with db.pool.acquire() as conn:
        query = """
            SELECT p.page_markdown, b.book_title, p.page_number
            FROM page p
            JOIN book b ON p.book_id = b.book_id
            WHERE 1=1
        """
        params = []
        
        if book_id:
            params.append(int(book_id))
            query += f" AND b.book_id = ${len(params)}"
        elif grade:
            params.append(int(grade))
            query += f" AND b.book_class = ${len(params)}"
            
        search_term = topic if topic else question_text
        if search_term and len(search_term) > 2:
            params.append(f"%{search_term[:25]}%")
            query += f" AND (p.page_markdown ILIKE ${len(params)} OR p.page_text ILIKE ${len(params)})"
        
        query += " LIMIT 3"
        records = await conn.fetch(query, *params)
        
        if not records:
            fallback_query = """
                SELECT p.page_markdown, b.book_title, p.page_number
                FROM page p
                JOIN book b ON p.book_id = b.book_id
                WHERE 1=1
            """
            fb_params = []
            if book_id:
                fb_params.append(int(book_id))
                fallback_query += " AND b.book_id = $1"
            elif grade:
                fb_params.append(int(grade))
                fallback_query += " AND b.book_class = $1"
            fallback_query += " LIMIT 3"
            records = await conn.fetch(fallback_query, *fb_params)
        
        if records:
            context_str = "\n\n".join([f"From textbook '{r['book_title']}' (page {r['page_number']}):\n{r['page_markdown']}" for r in records])

    try:
        system_instruction = (
            "You are an experienced and encouraging school mathematics tutor on the EduAI platform. "
            "Your task is to explain mathematical concepts step-by-step or solve problems for a child in a clear, polite manner.\n\n"
            "STRICT RULES:\n"
            "1. Use the provided textbook contexts if they are relevant to the user's question.\n"
            "2. Absolutely NEVER use LaTeX markdown expressions like '$', '$$', '\\(', '\\)'.\n"
            "3. Format all formulas cleanly using clear human-readable Unicode symbols: superscripts for powers (e.g., x², a³), '•' for multiplication, '°' for degrees.\n"
            "4. Respond entirely in Russian, maintaining a supportive and friendly tone tailored for a student."
        )
        
        user_text = f"Student's Question: {question_text}"
        if context_str:
            user_text += f"\n\nTextbook Knowledge Base Context:\n{context_str}"

        # Конструируем мультимодальный контент для OpenAI
        user_contents = [{"type": "text", "text": user_text}]

        if message.photo:
            photo = message.photo[-1]
            file_info = await message.bot.get_file(photo.file_id)
            photo_url = f"https://api.telegram.org/file/bot{settings.bot_token.get_secret_value()}/{file_info.file_path}"
            user_contents.append({
                "type": "image_url",
                "image_url": {"url": photo_url}
            })
        elif message.document:
            doc = message.document
            user_contents[0]["text"] += f"\n[Attached document: '{doc.file_name}', Mime-type: {doc.mime_type}]"

        response = await openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_contents}
            ],
            temperature=0.3
        )
        
        ai_reply = response.choices[0].message.content

        await status_msg.delete()
        await message.answer(
            f"🎓 *Ответ ИИ-Тьютора*:\n\n{ai_reply}",
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logger.error(f"OpenAI MultiModal Error: {e}")
        await status_msg.edit_text("❌ Произошла ошибка при обращении к нейросети. Попробуйте позже.")
        
    await state.clear()