from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from database import db

router = Router()

def get_parent_menu() -> ReplyKeyboardMarkup:
    buttons = [
        [
            KeyboardButton(text="➕ Привязать ребенка"),
            KeyboardButton(text="📊 Мониторинг")
        ],
        [
            KeyboardButton(text="📊 Аналитика ребенка (ИИ)"),
            KeyboardButton(text="📝 Создать ИИ-тест для ребенка")
        ]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_student_menu() -> ReplyKeyboardMarkup:
    buttons = [
        [
            KeyboardButton(text="🚀 Запустить квест"),
            KeyboardButton(text="📚 Каталог учебников")
        ],
        [
            KeyboardButton(text="🏆 Мой профиль")
        ]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


@router.message(F.text == "➕ Привязать ребенка")
async def generate_child_link(message: Message):
    user_id = message.from_user.id

    async with db.pool.acquire() as conn:
        user = await conn.fetchrow("SELECT role FROM users WHERE tg_id = $1", user_id)
        
    if not user or user['role'] != 'parent':
        await message.answer("Эта команда доступна только для пользователей с ролью Родитель.")
        return
        
    bot_user = await message.bot.get_me()
    link = f"https://t.me/{bot_user.username}?start=reg_{user_id}"

    await message.answer(
        f"Чтобы привязать аккаунт ребенка, перешлите ему эту ссылку:\n\n`{link}`\n\n"
        f"После того как ребенок перейдет по ней и нажмет *Старт*, его профиль автоматически свяжется с твоим.",
        parse_mode="Markdown"
    )


@router.message(F.text == "📊 Мониторинг")
async def show_parent_monitoring(message: Message):
    user_id = message.from_user.id

    async with db.pool.acquire() as conn:
        user = await conn.fetchrow("SELECT role FROM users WHERE tg_id = $1", user_id)
        if not user or user['role'] != 'parent':
            await message.answer("Эта статистика доступна только для Родителей.")
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

    report = "📊 *Мониторинг успеваемости детей*:\n\n"
    for idx, child in enumerate(children, start=1):
        name = f"@{child['username']}" if child['username'] else f"Ученик ID: {child['tg_id']}"
        coins = child['balance_coins'] or 0
        xp = child['xp_total'] or 0
        streak = child['streak_days'] or 0
        
        report += (
            f"{idx}. 👤 *{name}*\n"
            f"   💰 Баланс: `{coins}` монет\n"
            f"   ✨ Опыт: `{xp}` XP\n"
            f"   🔥 Ударный режим: `{streak}` дн.\n\n"
        )

    await message.answer(report, parse_mode="Markdown")