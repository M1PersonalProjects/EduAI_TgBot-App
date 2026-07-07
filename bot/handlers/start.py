import json
from config import settings

from aiogram import Router, F
from aiogram.filters import CommandStart, CommandObject, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from database import db
from bot.keyboards import get_role_keyboard
from bot.handlers.webapp import get_student_menu, get_parent_menu
from logger_config import logger

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject):
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
            await message.answer("Вы не можете привязать свой собственный аккаунт в качестве ребенка.")
            return
            
        async with db.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO users (tg_id, username, role, parent_id)
                    VALUES ($1, $2, 'student'::user_role, $3)
                    ON CONFLICT (tg_id) DO UPDATE SET parent_id = $3, role = 'student'::user_role
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
            "🎉 Успех! Вы успешно связали аккаунт с Родителем.\nВам доступен интерактивный ИИ-тьютор, квесты и магазин наград!",
            reply_markup=get_student_menu()
        )

        student_label = f"@{username}" if username else f"ID: {user_id}"
        try:
            await message.bot.send_message(
                chat_id=parent_id,
                text=f"🔔 Ребенок ({student_label}) успешно привязал свой аккаунт к вашему профилю!"
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить уведомление родителю {parent_id}: {e}")
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
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="👨‍👩‍👦 Переключиться на Родителя", callback_data="admin_toggle_role")]
            ])
            await message.answer(
                "👑 *Добро пожаловать, Главный Администратор EduAI!*\n\n"
                "Система распознала ваш Telegram ID. Вам доступно управление базой знаний.\n"
                "Вы можете переключаться между режимом администрирования и интерфейсом родителя с помощью кнопки ниже или команды /toggle.",
                reply_markup=kb,
                parse_mode="Markdown"
            )
        else:
            await message.answer(
                "Добро пожаловать в EduAI! Вы вошли в режиме *Родитель*.\nИспользуйте команду /toggle, чтобы вернуться в режим Администратора.",
                reply_markup=get_parent_menu(),
                parse_mode="Markdown"
            )
        return

    # --- СЦЕНАРИЙ 3: Обычный авторизованный пользователь (Родитель / Ученик) ---
    async with db.pool.acquire() as conn:
        user = await conn.fetchrow("SELECT role FROM users WHERE tg_id = $1", user_id)

    if user:
        role = user['role']
        if role == 'parent':
            await message.answer("Добро пожаловать в EduAI! Вы вошли как Родитель.", reply_markup=get_parent_menu())
        elif role == 'student':
            await message.answer("Привет! Рад снова видеть тебя в EduAI. Готов к новым знаниям?", reply_markup=get_student_menu())
        return
        
    # --- СЦЕНАРИЙ 4: Новый пользователь (Выбор роли) ---
    await message.answer(
        f"Привет, {message.from_user.first_name}! 👋 \nЯ **EduAI** — твой интеллектуальный помощник по школьной программе.\n\nДля начала работы, пожалуйста, выбери свою роль:",
        reply_markup=get_role_keyboard(),
        parse_mode="Markdown"
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
        inline_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👨‍👩‍👦 Переключиться на Родителя", callback_data="admin_toggle_role")]
        ])
    else:
        text_msg = (
            "👨‍👩‍👦 *Режим Родителя активирован!*\n\n"
            "Теперь бот отображает для вас меню родительского контроля. "
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
async def cmd_toggle_role(message: Message):
    if message.from_user.id in settings.admin_ids:
        await toggle_admin_role_logic(message.from_user.id, message)


# Переключатель по инлайн-кнопке для админа
@router.callback_query(F.data == "admin_toggle_role")
async def callback_toggle_role(callback: CallbackQuery):
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
            await callback.message.edit_text("✅ Роль успешно сохранена!\n\nТы зарегистрирован как **Ученик**.", parse_mode="Markdown")
            await callback.message.answer(
                "Тебе доступен интерактивный ИИ-тьютор, квесты и магазин наград!",
                reply_markup=get_student_menu()
            )
        elif selected_role == 'parent':
            await callback.message.edit_text("✅ Роль успешно сохранена!\n\nВы зарегистрированы как **Родитель**.", parse_mode="Markdown")
            await callback.message.answer(
                "Используйте нижнее меню для взаимодействия с платформой:",
                reply_markup=get_parent_menu()
            )
            
    await callback.answer()