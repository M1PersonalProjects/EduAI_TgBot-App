from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_role_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="👨‍👩‍👦 Я Родитель", callback_data="set_role_parent"),
            InlineKeyboardButton(text="👨‍💻 Я Ученик", callback_data="set_role_student")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)