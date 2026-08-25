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
from services.tutor import exit_book_mode, openai_client, respond, ensure_telegram_session, search_web_for_education
from services.educational_context import build_educational_context
from services.task_generation import generate_exact_task_set, task_set_payload
from services.tutor_policy import student_task_prompt
from services.quest_generation import canonicalize_subject, parse_quest_request
from services.assignment_source import infer_difficulty

router = Router()

class BookFilterStates(StatesGroup):
    choosing_grade = State()
    choosing_subject = State()
    choosing_book = State()
    choosing_topic = State()
    context_ready = State()
    waiting_for_ai_question = State()
    waiting_for_quest_request = State()


def quest_test_button():
    return [InlineKeyboardButton(text="🧩 Создать квест-тест", callback_data="create_quest_test")]


def quest_entry_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📚 Выбрать учебник / тему", callback_data="quest_choose_context")],
        [InlineKeyboardButton(text="✍️ Создать по запросу", callback_data="create_quest_test")],
    ])


@router.message(F.text.in_({"📚 Учебники", "📚 Каталог учебников"}))
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
            
    keyboard_buttons.append(quest_test_button())
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
        await call.answer("Для этого класса пока нет учебников. Квест можно создать по вашему запросу.")
        await enter_quest_request_mode(call.message, state)
        return

    keyboard_buttons = []
    await state.update_data(available_subjects=subjects)
    for index, sub in enumerate(subjects):
        keyboard_buttons.append([
            InlineKeyboardButton(text=f"📐 {sub}"[:64], callback_data=f"subject_{index}")
        ])
        
    keyboard_buttons.append(quest_test_button())
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
        await call.answer("Учебники пока не загружены. Квест можно создать по классу, предмету и теме.")
        await enter_quest_request_mode(call.message, state)
        return

    keyboard_buttons = []
    for b in books:
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"📘 {b['book_author']} — {b['book_title']}"[:64],
                callback_data=f"book_{b['book_id']}"
            )
        ])
    keyboard_buttons.append(quest_test_button())
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
    keyboard_buttons.append(quest_test_button())
    keyboard_buttons.append([
        InlineKeyboardButton(text="🤖 Задать вопрос по учебнику", callback_data="ask_ai_with_context")
    ])
    inline_kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await state.set_state(BookFilterStates.choosing_topic)
    await call.message.edit_text(
        "📋 Выбранный контекст:\n"
        f"🏫 Класс: {data.get('chosen_grade')}\n"
        f"📐 Предмет: {data.get('chosen_subject')}\n"
        f"📖 Учебник: {book_label}\n\n"
        "Шаг 4: Выберите страницу ниже либо напишите номер параграфа или тему.\n"
        "После выбора можно создать квест-тест или задать вопрос ИИ.\n\n"
        "Этот контекст будет закреплён до команды /exit_book.",
        reply_markup=inline_kb,
    )

@router.message(BookFilterStates.choosing_topic, F.text)
async def handle_topic_text(message: Message, state: FSMContext):
    await state.update_data(chosen_topic=message.text.strip())
    await show_context_actions(message, state)


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
    await show_context_actions(call.message, state)


async def show_context_actions(target_message: Message, state: FSMContext):
    data = await state.get_data()
    await state.set_state(BookFilterStates.context_ready)
    topic_label = data.get("chosen_topic") or (
        f"страница ID {data.get('chosen_page_id')}" if data.get("chosen_page_id") else "весь учебник"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        quest_test_button(),
        [InlineKeyboardButton(text="🤖 Задать вопрос ИИ", callback_data="ask_ai_with_context")],
    ])
    await target_message.answer(
        "✅ Учебный контекст выбран.\n"
        f"Тема/раздел: {topic_label}\n\n"
        "Что сделать с этим контекстом?",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.in_({"skip_to_question", "ask_ai_with_context"}))
async def handle_skip_callback(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await enter_ai_question_mode(call.message, state)

@router.callback_query(F.data == "quest_choose_context")
async def handle_quest_choose_context(call: CallbackQuery, state: FSMContext):
    await state.clear()
    async with db.pool.acquire() as conn:
        user = await conn.fetchrow("SELECT role FROM users WHERE tg_id = $1", call.from_user.id)
    if not user or user["role"] != "student":
        await call.answer("Квест-тесты доступны Ученику.", show_alert=True)
        return
    await state.update_data(user_role="student")
    keyboard_buttons = []
    row = []
    for grade in range(1, 12):
        row.append(InlineKeyboardButton(text=f"🏫 {grade} класс", callback_data=f"grade_{grade}"))
        if len(row) == 3 or grade == 11:
            keyboard_buttons.append(row)
            row = []
    keyboard_buttons.append(quest_test_button())
    await state.set_state(BookFilterStates.choosing_grade)
    await call.answer()
    await call.message.edit_text(
        "🧩 Создание квест-теста\n\n"
        "Выберите класс и при желании учебник/страницу. "
        "Либо нажмите «Создать квест-тест» и опишите класс, предмет и тему текстом.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons),
    )


@router.callback_query(F.data == "create_quest_test")
async def handle_create_quest_test(call: CallbackQuery, state: FSMContext):
    async with db.pool.acquire() as conn:
        user = await conn.fetchrow("SELECT role FROM users WHERE tg_id = $1", call.from_user.id)
    if not user or user["role"] != "student":
        await call.answer("Квест-тесты доступны Ученику.", show_alert=True)
        return
    await state.update_data(user_role="student")
    await call.answer()
    await enter_quest_request_mode(call.message, state)


async def enter_quest_request_mode(target_message: Message, state: FSMContext):
    data = await state.get_data()
    selected = []
    if data.get("chosen_grade"):
        selected.append(f"{data['chosen_grade']} класс")
    if data.get("chosen_subject"):
        selected.append(str(data["chosen_subject"]))
    if data.get("chosen_book_label"):
        selected.append(str(data["chosen_book_label"]))
    if data.get("chosen_topic"):
        selected.append(f"тема: {data['chosen_topic']}")
    elif data.get("chosen_page_id"):
        selected.append("выбранная страница учебника")

    await state.set_state(BookFilterStates.waiting_for_quest_request)
    context_text = ", ".join(selected) if selected else "учебник не выбран"
    await target_message.answer(
        "🧩 Создание квест-теста\n\n"
        f"Текущий контекст: {context_text}.\n\n"
        "Напишите параметры квеста. Минимально нужны класс, предмет и тема; "
        "уже выбранные параметры повторять не нужно. Количество вопросов необязательно — по умолчанию 5.\n\n"
        "Примеры:\n"
        "• 7 класс, математика, обыкновенные дроби, 5 вопросов\n"
        "• Предмет: физика; тема: давление; 8 вопросов\n"
        "• 10 вопросов повышенной сложности\n\n"
        "Для отмены: /cancel"
    )


@router.message(BookFilterStates.waiting_for_quest_request, F.text | F.photo | F.document)
async def generate_quest_test_from_request(message: Message, state: FSMContext):
    request_text = (message.text or message.caption or "").strip()
    attachment = None
    attachment_text = ""
    if not request_text and (message.photo or message.document):
        request_text = "Создай квест-тест по прикреплённому учебному материалу"
    if not request_text:
        await message.answer("Опишите квест свободным сообщением или приложите учебный материал.")
        return

    data = await state.get_data()
    draft = parse_quest_request(
        request_text,
        grade=data.get("chosen_grade"),
        subject=data.get("chosen_subject") or "",
        topic=data.get("chosen_topic") or "",
        default_count=5,
    )

    indicator = await TelegramThinkingIndicator(
        message, "ИИ создаёт квест-тест и подбирает учебный контекст"
    ).start()
    try:
        try:
            attachment = await parse_telegram_attachment(message)
            attachment_text = (getattr(attachment, "text", "") or getattr(attachment, "content", "") or "")[:24000]
        except AttachmentError as exc:
            await indicator.stop(delete=False)
            await indicator.status_message.edit_text(f"❌ {exc}")
            return

        async with db.pool.acquire() as conn:
            student = await conn.fetchrow(
                "SELECT role, parent_id FROM users WHERE tg_id = $1",
                message.from_user.id,
            )
            if not student or student["role"] != "student":
                await indicator.stop(delete=False)
                await indicator.status_message.edit_text("Квест-тесты доступны только Ученику.")
                return

            canonical_subject = draft.subject
            if draft.subject and draft.grade and not data.get("chosen_subject"):
                subject_rows = await conn.fetch(
                    "SELECT DISTINCT book_program FROM book WHERE book_class = $1 ORDER BY book_program",
                    draft.grade,
                )
                canonical_subject = canonicalize_subject(
                    draft.subject,
                    [row["book_program"] for row in subject_rows if row["book_program"]],
                )
                draft = parse_quest_request(
                    request_text,
                    grade=draft.grade,
                    subject=canonical_subject,
                    topic=draft.topic,
                    default_count=draft.requested_count,
                )

            manual = {
                "book_class": draft.grade,
                "book_program": draft.subject or None,
                "book_id": data.get("chosen_book_id"),
                "page_id": data.get("chosen_page_id"),
                "page_paragraph": data.get("chosen_topic"),
            }
            bundle = await build_educational_context(
                conn,
                request_text + ("\n" + attachment_text[:4000] if attachment_text else ""),
                manual=manual,
                allow_context_resolution=True,
                allow_web=True,
                web_search=search_web_for_education,
                requested_items=draft.requested_count,
            )

        primary = bundle.primary
        inferred_grade = draft.grade or (primary.book_class if primary else None) or data.get("chosen_grade")
        inferred_subject = draft.subject or (primary.book_program if primary else "") or data.get("chosen_subject") or ""
        inferred_topic = (
            draft.topic
            or data.get("chosen_topic")
            or ((primary.page_title or primary.page_paragraph or "") if primary else "")
            or ("по прикреплённому материалу" if attachment_text else "")
        )
        spec = parse_quest_request(
            request_text,
            grade=inferred_grade,
            subject=inferred_subject,
            topic=inferred_topic,
            default_count=draft.requested_count,
        )
        if spec.missing_fields:
            await indicator.stop(delete=False)
            missing = ", ".join(spec.missing_fields)
            hint = ""
            if spec.missing_fields == ("класс",):
                hint = "\nНапишите только класс, например: «1 класс» или «7 класс»."
            elif spec.missing_fields == ("предмет",):
                hint = "\nНапишите только предмет, например: «математика» или «биология»."
            elif spec.missing_fields == ("тема",):
                hint = "\nНапишите только тему квеста."
            await indicator.status_message.edit_text(
                "Не хватает данных для квеста: " + missing + "." + hint
            )
            return

        primary_text = primary.content if primary else "none"
        ai_task = await generate_exact_task_set(
            openai_client,
            system_prompt=student_task_prompt(),
            user_content=(
                "Create a Telegram quest-test for a Student. Infer wording, level and examples from the request, attachment and sources.\n"
                f"Grade: {spec.grade}\n"
                f"Subject: {spec.subject}\n"
                f"Topic: {spec.topic}\n"
                f"Student request: {spec.raw_request}\n\n"
                f"ATTACHED MATERIAL:\n{attachment_text or 'none'}\n\n"
                f"PRIMARY TEXTBOOK CONTEXT:\n{primary_text}\n\n"
                f"RANKED EDUAI SUPPLEMENTS:\n{bundle.database_context or 'none'}\n\n"
                f"WEB FALLBACK:\n{bundle.web_context or 'none'}"
            ),
            requested_count=spec.requested_count,
        )
        questions_json = task_set_payload(ai_task)
        items = questions_json.get("items") or []
        if not items:
            raise ValueError("Quest generator returned no task items")

        topic_context = {
            "source": "telegram_quest_test",
            "request": spec.raw_request,
            "attachment_used": bool(attachment_text),
            "book_id": primary.book_id if primary else data.get("chosen_book_id"),
            "page_id": primary.page_id if primary else data.get("chosen_page_id"),
            "book_title": primary.book_title if primary else data.get("chosen_book_label"),
            "book_class": spec.grade,
            "book_program": spec.subject,
            "page_title": primary.page_title if primary else None,
            "topic": spec.topic,
            "subject": spec.subject,
            "requested_count": spec.requested_count,
            "generated_count": len(items),
            "source_trace": bundle.source_trace,
            "difficulty": infer_difficulty(spec.raw_request, spec.topic),
        }
        async with db.pool.acquire() as conn:
            task_id = await conn.fetchval(
                """
                INSERT INTO tasks_history (
                    student_id, parent_id, assignment_source, title, subject, topic,
                    topic_context, questions_json, score, status, sent_at, updated_at
                )
                VALUES (
                    $1, NULL, 'tutor_practice', $2, $3, $4, $5::jsonb, $6::jsonb,
                    0, 'in_progress'::task_status, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                RETURNING task_id
                """,
                message.from_user.id,
                ai_task.title,
                spec.subject,
                spec.topic,
                json.dumps(topic_context, ensure_ascii=False),
                json.dumps(questions_json, ensure_ascii=False),
            )

        first = items[0]
        from bot.handlers.tasks import QuestStates
        await state.update_data(
            active_task_id=task_id,
            question_text=first.get("question_text") or "",
            correct_answer=first.get("reference_answer") or "",
            parent_id=None,
            assignment_source="tutor_practice",
            quest_title=ai_task.title,
            quest_items=items,
            quest_index=0,
            quest_answers=[],
            quest_subject=spec.subject,
            quest_topic=spec.topic,
        )
        await state.set_state(QuestStates.waiting_for_answer)
        await indicator.stop()
        await answer_plain(
            message,
            f"🏆 Квест-тест: {ai_task.title}\n"
            f"📚 {spec.grade} класс · {spec.subject}\n"
            f"🎯 Тема: {spec.topic}\n"
            f"❓ Вопрос 1 из {len(items)}\n\n"
            f"{first.get('question_text', '')}\n\n"
            "Напиши ответ в чат (или /cancel для отмены)."
        )
    except Exception as exc:
        logger.exception("Ошибка генерации квест-теста в Telegram: %s", exc)
        await indicator.stop(delete=False)
        await indicator.status_message.edit_text(
            "❌ Не удалось создать квест-тест. Попробуйте уточнить запрос или приложенный материал."
        )


async def enter_ai_question_mode(target_message: Message, state: FSMContext):
    data = await state.get_data()
    summary = "📚 Book Mode EduAI\n\n"
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
    await message.answer("✅ Book Mode выключен. Для свободного чата нажмите «🤖 ИИ-помощник».")


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
