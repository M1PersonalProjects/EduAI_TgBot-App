from aiogram import Router, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message, CallbackQuery
from database import db
from bot.keyboards import get_role_keyboard
from bot.handlers.webapp import get_student_menu, get_parent_menu

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject):
    user_id = message.from_user.id
    username = message.from_user.username
    args = command.args
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
                    VALUES ($1, $2, 'student', $3)
                    ON CONFLICT (tg_id) DO UPDATE SET parent_id = $3, role = 'student'
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
            " 🎉  Успех! Вы успешно связали аккаунт с Родителем.\nВам доступен интерактивный ИИ-тьютор, квесты и магазин наград!",
            reply_markup=get_student_menu()
        )

        try:
            await message.bot.send_message(
                chat_id=parent_id,
                text=f" 🔔  Ребенок (@{username or user_id}) успешно привязал свой аккаунт к вашему профилю!"
            )
        except Exception:
            pass
        return
    async with db.pool.acquire() as conn:
        user = await conn.fetchrow("SELECT role FROM users WHERE tg_id = $1", user_id)

    if user:
        role = user['role']
        if role == 'parent':
            await message.answer(
                "Добро пожаловать в EduAI! Вы вошли как Родитель.",
                reply_markup=get_parent_menu()
            )
        else:
            await message.answer(
                "Привет! Рад снова видеть тебя в EduAI. Готов к новым знаниям?",
                reply_markup=get_student_menu()
            )
        return
    await message.answer(
        f"Привет, {message.from_user.first_name}!  👋 \nЯ **EduAI** — твой интеллектуальный помощник по школьной программе.\n\nДля начала работы, пожалуйста, выбери свою роль:",
        reply_markup=get_role_keyboard(),
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("set_role_"))
async def callbacks_num(callback: CallbackQuery):
    user_id = callback.from_user.id
    username = callback.from_user.username
    selected_role = callback.data.split("_")[2]
    async with db.pool.acquire() as conn:
        current_user = await conn.fetchrow("SELECT role FROM users WHERE tg_id = $1", user_id)
        if current_user and current_user["role"] in ["admin", "teacher"]:
            await callback.answer("У вас максимальный уровень прав. Изменение роли заблокировано!", show_alert=True)
            return
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO users (tg_id, username, role)
                VALUES ($1, $2, $3)
                ON CONFLICT (tg_id) DO UPDATE SET role = $3
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
        if selected_role == 'parent':
            await callback.message.edit_text(" ✅  Роль успешно сохранена!\n\nВы зарегистрированы как **Родитель**.")
            await callback.message.answer(
                "Используйте нижнее меню для взаимодействия с платформой:",
                reply_markup=get_parent_menu()
            )
        else:
            await callback.message.edit_text(" ✅  Роль успешно сохранена!\n\nТы зарегистрирован как **Ученик**.")
            await callback.message.answer(
                "Тебе доступен интерактивный ИИ-тьютор, квесты и магазин наград!",
                reply_markup=get_student_menu()
            )
    await callback.answer()
