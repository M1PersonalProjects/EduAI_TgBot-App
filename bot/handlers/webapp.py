from aiogram import Router, F
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.fsm.context import FSMContext
from database import db
from bot.keyboards import get_parent_menu, get_student_menu
from bot.messages import answer_plain
from urllib.parse import quote
from services.mentor_identity import mentor_label, normalize_mentor_kind

router = Router()


@router.message(F.text == "➕ Привязать Ученика")
async def generate_child_link(message: Message, state: FSMContext = None):
    if state is not None:
        await state.clear()
    user_id = message.from_user.id

    async with db.pool.acquire() as conn:
        user = await conn.fetchrow("SELECT role, mentor_kind FROM users WHERE tg_id = $1", user_id)
        
    if not user or user['role'] not in ['parent', 'admin']:
        await message.answer("Эта команда доступна Учителю, Родителю или Администратору.")
        return
        
    mentor_kind = normalize_mentor_kind(user.get('mentor_kind'))
    role_label = mentor_label(mentor_kind)
    bot_user = await message.bot.get_me()
    link = f"https://t.me/{bot_user.username}?start=reg_{user_id}"

    share_url = (
        "https://t.me/share/url?url="
        + quote(link, safe="")
        + "&text="
        + quote(f"{role_label} приглашает тебя присоединиться к Umnix как Ученик", safe="")
    )
    await message.answer(
        f"👤 *Приглашение от роли «{role_label}»*\n\n"
        f"Отправьте эту ссылку Ученику. После перехода и нажатия *Старт* бот покажет, "
        f"что приглашение отправил именно {role_label}, и свяжет аккаунт с вашим профилем Umnix.\n\n"
        f"`{link}`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="Поделиться ссылкой", url=share_url),
            ]]
        ),
    )


@router.message(F.text == "📊 Мониторинг в чате")
async def show_parent_monitoring(message: Message, state: FSMContext = None):
    if state is not None:
        await state.clear()
    user_id = message.from_user.id

    async with db.pool.acquire() as conn:
        user = await conn.fetchrow("SELECT role, mentor_kind FROM users WHERE tg_id = $1", user_id)
        if not user or user['role'] not in ['parent', 'admin']:
            await message.answer("Эта статистика доступна Учителям, Родителям и Администраторам.")
            return

        children = await conn.fetch(
            """
            SELECT u.tg_id, u.username,
                   COUNT(t.task_id) AS tasks_total,
                   COUNT(t.task_id) FILTER (WHERE t.status IN ('completed', 'evaluated')) AS tasks_done,
                   COALESCE(ROUND(AVG(t.score))::int, 0) AS average_score
            FROM users u
            LEFT JOIN tasks_history t
              ON t.student_id = u.tg_id AND t.assignment_source = 'teacher'
            WHERE u.parent_id = $1 AND u.role = 'student'
            GROUP BY u.tg_id, u.username
            ORDER BY u.username NULLS LAST
            """,
            user_id
        )

    if not children:
        await message.answer(
            "У вас пока нет привязанных Учеников.\n\n"
            "Нажмите кнопку **➕ Привязать Ученика**, чтобы отправить ему инвайт-ссылку.",
            parse_mode="Markdown"
        )
        return

    report = "📊 Мониторинг успеваемости Учеников:\n\n"
    for idx, child in enumerate(children, start=1):
        name = f"@{child['username']}" if child['username'] else f"Ученик ID: {child['tg_id']}"
        tasks_total = int(child['tasks_total'] or 0)
        tasks_done = int(child['tasks_done'] or 0)
        average_score = int(child['average_score'] or 0)

        report += (
            f"{idx}. 👤 {name}\n"
            f"   📝 Заданий: {tasks_done}/{tasks_total} выполнено\n"
            f"   📊 Средняя оценка: {average_score}\n\n"
        )

    await answer_plain(message, report)
