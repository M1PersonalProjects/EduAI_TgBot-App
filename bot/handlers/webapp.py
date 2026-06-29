from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from database import db

router = Router()

def get_parent_menu() -> ReplyKeyboardMarkup:
    buttons = [
        [
            KeyboardButton(text="➕ Привязать ребенка"),
            KeyboardButton(text="📊 Мониторинг (Скоро на сервере)")
        ]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_student_menu() -> ReplyKeyboardMarkup:
    buttons = [
        [
            KeyboardButton(text="📚 Каталог учебников"),
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
        f"Чтобы привязать аккаунт ребенка, перешлите ему эту ссылку:\n\n`{link}`\n\nПосле перехода по ссылке его профиль автоматически свяжется с вашим.",
        parse_mode="Markdown"
    )
