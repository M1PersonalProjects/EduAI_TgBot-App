from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.media import parse_telegram_attachment
from bot.messages import answer_plain
from database import db
from logger_config import logger
from services.file_parser import AttachmentError
from services.thinking import TelegramThinkingIndicator
from services.tutor import create_session, exit_book_mode, respond


router = Router()


def exit_book_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Выйти из Book Mode", callback_data="exit_book_mode")
    ]])


@router.message(Command("exit_book"))
async def exit_book_command(message: Message, state: FSMContext):
    try:
        await exit_book_mode(message.from_user.id)
    except LookupError:
        pass
    await state.clear()
    await message.answer("✅ Book Mode выключен. Теперь можно задавать общие вопросы.")


@router.callback_query(F.data == "exit_book_mode")
async def exit_book_callback(callback: CallbackQuery, state: FSMContext):
    try:
        await exit_book_mode(callback.from_user.id)
    except LookupError:
        pass
    await state.clear()
    await callback.answer("Book Mode выключен")
    await callback.message.answer("✅ Контекст учебника очищен. Задавайте любой вопрос.")


@router.message(Command("new_chat"))
async def new_bot_chat(message: Message):
    await create_session(message.from_user.id)
    await message.answer("✨ Создан новый чат с ИИ-тьютором.")


@router.message(StateFilter(None), F.text | F.photo | F.document)
async def quick_ai_chat_fallback(message: Message):
    user_text = (message.text or message.caption or "").strip()
    if user_text.startswith("/"):
        return

    async with db.pool.acquire() as conn:
        user = await conn.fetchrow("SELECT role FROM users WHERE tg_id = $1", message.from_user.id)
    if not user:
        await message.answer(
            "Сначала зарегистрируйтесь: отправьте /start и выберите свою роль."
        )
        return
    if user["role"] not in ("student", "parent", "admin"):
        await message.answer("Для вашей роли ИИ-тьютор пока недоступен.")
        return

    logger.info(
        "Telegram tutor request: user=%s type=%s",
        message.from_user.id,
        "photo" if message.photo else "document" if message.document else "text",
    )
    indicator = await TelegramThinkingIndicator(message, "ИИ-тьютор думает").start()
    try:
        attachment = await parse_telegram_attachment(message)
        result = await respond(
            user_id=message.from_user.id,
            role=user["role"],
            message_text=user_text,
            attachment=attachment,
        )
        await indicator.stop()
        await answer_plain(
            message,
            result["message_text"],
            reply_markup=exit_book_keyboard() if result["book_mode"] else None,
        )
    except AttachmentError as exc:
        await indicator.stop(delete=False)
        await indicator.status_message.edit_text(f"❌ {exc}")
    except Exception as exc:
        logger.exception("Telegram tutor failed for %s: %s", message.from_user.id, exc)
        await indicator.stop(delete=False)
        await indicator.status_message.edit_text(
            "❌ Не удалось связаться с ИИ-тьютором. Попробуйте позже."
        )
