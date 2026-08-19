import json
from config import settings

from aiogram import Router, F
from aiogram.filters import CommandStart, CommandObject, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from database import db
from bot.keyboards import (
    get_admin_menu,
    get_parent_menu,
    get_role_keyboard,
    get_student_menu,
)
from logger_config import logger

router = Router()

STUDENT_START_TEXT = (
    "👋 *Добро пожаловать в EduAI!*\n\n"
    "🤖 *В Telegram можно:*\n"
    "• общаться с ИИ-тьютором и разбирать учебные темы;\n"
    "• отправлять фотографии и учебные файлы;\n"
    "• выбирать учебник в разделе «📚 Учебники» или спрашивать свободно через «🤖 ИИ-помощник»;\n"
    "• получать задания и отправлять решения;\n"
    "• следить за своим учебным прогрессом.\n\n"
    "🌐 *В EduAI WebApp доступно больше:*\n"
    "• полноценный чат и история диалогов;\n"
    "• удобная работа с заданиями и результатами;\n"
    "• учебники, награды и подробный прогресс.\n\n"
    "Для полного интерфейса нажмите *«🌐 Открыть EduAI»*."
)

PARENT_START_TEXT = (
    "👋 *Добро пожаловать в EduAI!*\n\n"
    "🤖 *В Telegram можно:*\n"
    "• привязать Ученика;\n"
    "• быстро посмотреть учебную активность;\n"
    "• выбирать учебник для вопроса или использовать свободный «🤖 ИИ-помощник»;\n"
    "• получать важные уведомления о заданиях и результатах.\n\n"
    "🌐 *В EduAI WebApp доступно больше:*\n"
    "• создавать задания вручную или с помощью ИИ;\n"
    "• прикреплять учебные материалы;\n"
    "• просматривать историю заданий, попытки и результаты;\n"
    "• управлять Учениками и учебным процессом.\n\n"
    "Для полного интерфейса нажмите *«🌐 Открыть EduAI»*."
)

ADMIN_START_TEXT = (
    "👑 *EduAI · режим Администратора*\n\n"
    "🤖 В Telegram доступны быстрые действия и переключение роли.\n\n"
    "🌐 *В EduAI WebApp:*\n"
    "• управление учебниками и страницами;\n"
    "• пакетная оцифровка;\n"
    "• пользователи и активности;\n"
    "• административные инструменты.\n\n"
    "Откройте полный интерфейс кнопкой *«🌐 Открыть EduAI»*."
)

NEW_USER_START_TEXT = (
    "👋 *Добро пожаловать в EduAI!*\n\n"
    "EduAI — образовательный помощник для Учеников и Учителей.\n\n"
    "🤖 Telegram подходит для быстрых действий, общения, уведомлений "
    "и работы с учебными заданиями.\n"
    "🌐 WebApp открывает полный интерфейс и расширенные возможности.\n\n"
    "Для начала выберите свою роль:"
)



@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, state: FSMContext = None):
    if state is not None:
        await state.clear()
    user_id = message.from_user.id
    username = message.from_user.username
    args = command.args

    # --- СЦЕНАРИЙ 1: Регистрация по реферальной ссылке от родителя ---
    if args and args.startswith("reg_"):
        try:
            parent_id = int(args.split("_")[1])
        except (IndexError, ValueError):
            await message.answer("Некорректная ссылка для регистрации.")
            return

        if user_id == parent_id:
            await message.answer("Вы не можете привязать свой собственный аккаунт в качестве Ученика.")
            return

        async with db.pool.acquire() as conn:
            inviter = await conn.fetchrow(
                "SELECT role FROM users WHERE tg_id = $1",
                parent_id,
            )
            if not inviter or inviter["role"] not in ("parent", "admin"):
                await message.answer("Эта ссылка привязки недействительна или её Учитель больше недоступен.")
                return

            existing = await conn.fetchrow(
                "SELECT role, parent_id FROM users WHERE tg_id = $1",
                user_id,
            )
            if existing and existing["role"] in ("parent", "admin"):
                await message.answer(
                    "Аккаунт Учителя или Администратора нельзя перепривязать как Ученика по реферальной ссылке."
                )
                return
            if existing and existing["role"] == "student":
                current_parent = existing.get("parent_id")
                if current_parent and int(current_parent) != parent_id:
                    await message.answer(
                        "Этот аккаунт Ученика уже привязан к другому Учителю. "
                        "Сначала отвяжите существующую связь в EduAI."
                    )
                    return
                if current_parent and int(current_parent) == parent_id:
                    await message.answer(
                        "✅ Ваш аккаунт уже привязан к этому Учителю.",
                        reply_markup=get_student_menu(),
                    )
                    return

            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO users (tg_id, username, role, parent_id)
                    VALUES ($1, $2, 'student'::user_role, $3)
                    ON CONFLICT (tg_id) DO UPDATE
                    SET parent_id = $3, role = 'student'::user_role, username = EXCLUDED.username
                    """,
                    user_id, username, parent_id
                )
                await conn.execute(
                    """
                    INSERT INTO gamification (user_id, balance_coins, xp_total, streak_days)
                    VALUES ($1, 0, 0, 0)
                    ON CONFLICT (user_id) DO NOTHING
                    """,
                    user_id
                )

        await message.answer(
            "🎉 Аккаунт успешно связан с Учителем!\n\n" + STUDENT_START_TEXT,
            reply_markup=get_student_menu()
        )

        student_label = f"@{username}" if username else f"ID: {user_id}"
        try:
            await message.bot.send_message(
                chat_id=parent_id,
                text=f"🔔 Ученик ({student_label}) успешно привязал свой аккаунт к вашему профилю!"
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить уведомление Учителю {parent_id}: {e}")
        return

    # --- СЦЕНАРИЙ 2: Вход или первичная инициализация Администратора ---
    if user_id in settings.admin_ids:
        async with db.pool.acquire() as conn:
            user = await conn.fetchrow("SELECT role FROM users WHERE tg_id = $1", user_id)
            if not user or user["role"] not in ["admin", "parent"]:
                await conn.execute(
                    """
                    INSERT INTO users (tg_id, username, role) VALUES ($1, $2, 'admin'::user_role)
                    ON CONFLICT (tg_id) DO UPDATE SET role = 'admin'::user_role
                    """,
                    user_id, username
                )
                role = "admin"
            else:
                role = user["role"]

        if role == "admin":
            await message.answer(
                ADMIN_START_TEXT,
                reply_markup=get_admin_menu(),
                parse_mode="Markdown",
            )
        else:
            await message.answer(
                PARENT_START_TEXT + "\n\nИспользуйте /toggle, чтобы вернуться в режим Администратора.",
                reply_markup=get_parent_menu(),
                parse_mode="Markdown"
            )
        return

    # --- СЦЕНАРИЙ 3: Обычный авторизованный пользователь (Учитель / Ученик) ---
    async with db.pool.acquire() as conn:
        user = await conn.fetchrow("SELECT role FROM users WHERE tg_id = $1", user_id)

    if user:
        role = user['role']
        if role == 'parent':
            await message.answer(
                PARENT_START_TEXT,
                reply_markup=get_parent_menu(),
                parse_mode="Markdown",
            )
        elif role == 'student':
            await message.answer(
                STUDENT_START_TEXT,
                reply_markup=get_student_menu(),
                parse_mode="Markdown",
            )
        return

    # --- СЦЕНАРИЙ 4: Новый пользователь (Выбор роли) ---
    await message.answer(
        NEW_USER_START_TEXT,
        reply_markup=get_role_keyboard(),
        parse_mode="Markdown",
    )


async def toggle_admin_role_logic(user_id: int, message_or_call) -> None:
    """Общая логика смены роли для админа"""
    if user_id not in settings.admin_ids:
        return

    async with db.pool.acquire() as conn:
        user = await conn.fetchrow("SELECT role FROM users WHERE tg_id = $1", user_id)
        if not user:
            return

        current_role = user["role"]
        new_role = "parent" if current_role == "admin" else "admin"

        await conn.execute("UPDATE users SET role = $1::user_role WHERE tg_id = $2", new_role, user_id)

    text_msg = ""
    reply_kb = None
    inline_kb = None

    if new_role == "admin":
        text_msg = (
            "👑 *Режим Администратора активирован!*\n\n"
            "Вы вернулись в панель управления. Все админские права и доступ к API восстановлены."
        )
        inline_kb = get_admin_menu()
    else:
        text_msg = (
            "👨‍👩‍👦 *Режим Учителя активирован!*\n\n"
            "Теперь бот отображает для вас меню Учителя. "
            "Чтобы вернуться в режим администрирования, используйте команду /toggle."
        )
        reply_kb = get_parent_menu()

    if isinstance(message_or_call, CallbackQuery):
        try:
            await message_or_call.message.delete()
        except Exception:
            pass
        await message_or_call.message.answer(text_msg, reply_markup=reply_kb or inline_kb, parse_mode="Markdown")
    else:
        await message_or_call.answer(text_msg, reply_markup=reply_kb or inline_kb, parse_mode="Markdown")


@router.message(Command("toggle"))
async def cmd_toggle_role(message: Message, state: FSMContext = None):
    if state is not None:
        await state.clear()
    if message.from_user.id in settings.admin_ids:
        await toggle_admin_role_logic(message.from_user.id, message)


# Переключатель по инлайн-кнопке для админа
@router.callback_query(F.data == "admin_toggle_role")
async def callback_toggle_role(callback: CallbackQuery, state: FSMContext = None):
    if state is not None:
        await state.clear()
    if callback.from_user.id in settings.admin_ids:
        await toggle_admin_role_logic(callback.from_user.id, callback)
    await callback.answer()


# Сохранение первичной роли для обычных пользователей
@router.callback_query(F.data.startswith("set_role_"))
async def callbacks_num(callback: CallbackQuery):
    user_id = callback.from_user.id
    username = callback.from_user.username
    selected_role = callback.data.split("_")[2]

    if user_id in settings.admin_ids:
        await callback.answer("У вас максимальный уровень прав. Используйте переключатель!", show_alert=True)
        return

    async with db.pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO users (tg_id, username, role)
                VALUES ($1, $2, $3::user_role)
                ON CONFLICT (tg_id) DO UPDATE SET role = $3::user_role
                """,
                user_id, username, selected_role
            )

            if selected_role == 'student':
                await conn.execute(
                    """
                    INSERT INTO gamification (user_id, balance_coins, xp_total, streak_days)
                    VALUES ($1, 0, 0, 0)
                    ON CONFLICT (user_id) DO NOTHING
                    """,
                    user_id
                )

    if selected_role == 'student':
        await callback.message.edit_text("✅ Роль успешно сохранена!\n\nТы зарегистрирован как **Ученик**.", parse_mode="Markdown")
        await callback.message.answer(
            STUDENT_START_TEXT,
            reply_markup=get_student_menu(),
            parse_mode="Markdown",
        )
    elif selected_role == 'parent':
        await callback.message.edit_text("✅ Роль успешно сохранена!\n\nВы зарегистрированы как **Учитель**.", parse_mode="Markdown")
        await callback.message.answer(
            PARENT_START_TEXT,
            reply_markup=get_parent_menu(),
            parse_mode="Markdown",
        )

    await callback.answer()
