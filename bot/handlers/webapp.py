from aiogram import Router, F
from aiogram.types import Message
from database import db
from bot.keyboards import get_parent_menu, get_student_menu
from bot.messages import answer_plain

router = Router()


@router.message(F.text == "➕ Привязать ребенка")
async def generate_child_link(message: Message):
    user_id = message.from_user.id

    async with db.pool.acquire() as conn:
        user = await conn.fetchrow("SELECT role FROM users WHERE tg_id = $1", user_id)
        
    if not user or user['role'] not in ['parent', 'admin']:
        await message.answer("Эта команда доступна только для пользователей с ролью Родитель.")
        return
        
    bot_user = await message.bot.get_me()
    link = f"https://t.me/{bot_user.username}?start=reg_{user_id}"

    await message.answer(
        f"Чтобы привязать аккаунт ребенка, перешлите ему эту ссылку:\n\n`{link}`\n\n"
        f"После того как ребенок перейдет по ней и нажмет *Старт*, его профиль автоматически свяжется с твоим.",
        parse_mode="Markdown"
    )


@router.message(F.text == "📊 Мониторинг в чате")
async def show_parent_monitoring(message: Message):
    user_id = message.from_user.id

    async with db.pool.acquire() as conn:
        user = await conn.fetchrow("SELECT role FROM users WHERE tg_id = $1", user_id)
        if not user or user['role'] not in ['parent', 'admin']:
            await message.answer("Эта статистика доступна только для Родителей и Администраторов.")
            return

        children = await conn.fetch(
            """
            SELECT u.tg_id, u.username, g.balance_coins, g.xp_total, g.streak_days
            FROM users u
            LEFT JOIN gamification g ON u.tg_id = g.user_id
            WHERE u.parent_id = $1 AND u.role = 'student'
            """,
            user_id
        )

    if not children:
        await message.answer(
            "У вас пока нет привязанных детей.\n\n"
            "Нажмите кнопку **➕ Привязать ребенка**, чтобы отправить ему инвайт-ссылку.",
            parse_mode="Markdown"
        )
        return

    report = "📊 Мониторинг успеваемости детей:\n\n"
    for idx, child in enumerate(children, start=1):
        name = f"@{child['username']}" if child['username'] else f"Ученик ID: {child['tg_id']}"
        coins = child['balance_coins'] or 0
        xp = child['xp_total'] or 0
        streak = child['streak_days'] or 0
        
        report += (
            f"{idx}. 👤 {name}\n"
            f"   💰 Баланс: {coins} монет\n"
            f"   ✨ Опыт: {xp} XP\n"
            f"   🔥 Ударный режим: {streak} дн.\n\n"
        )

    await answer_plain(message, report)
