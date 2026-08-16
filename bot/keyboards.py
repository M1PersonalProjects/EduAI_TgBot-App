from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from config import settings

def get_role_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="👩‍🏫 Я Учитель", callback_data="set_role_parent"),
            InlineKeyboardButton(text="👨‍💻 Я Ученик", callback_data="set_role_student")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_parent_menu() -> ReplyKeyboardMarkup:
    """Compact Telegram menu for Teachers (technical role: parent)."""
    buttons = [
        [
            KeyboardButton(text="➕ Привязать Ученика"),
            KeyboardButton(text="📊 Мониторинг в чате"),
        ],
        [
            KeyboardButton(text="📚 Учебники"),
            KeyboardButton(text="🤖 ИИ-помощник"),
        ],
        [
            KeyboardButton(
                text="🌐 Открыть EduAI",
                web_app=WebAppInfo(url=settings.webapp_base_url),
            ),
        ],
    ]
    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
    )


def get_student_menu() -> ReplyKeyboardMarkup:
    """Compact Telegram menu for students."""
    buttons = [
        [
            KeyboardButton(text="📚 Учебники"),
            KeyboardButton(text="🤖 ИИ-помощник"),
        ],
        [
            KeyboardButton(text="🏆 Мой профиль"),
        ],
        [
            KeyboardButton(
                text="🌐 Открыть EduAI",
                web_app=WebAppInfo(url=settings.webapp_base_url),
            ),
        ],
    ]
    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
    )


def get_admin_menu() -> InlineKeyboardMarkup:
    """Administrator quick actions without duplicating WebApp pages."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🌐 Открыть EduAI",
                    web_app=WebAppInfo(url=settings.webapp_base_url),
                )
            ],
            [
                InlineKeyboardButton(
                    text="👩‍🏫 Переключиться на Учителя",
                    callback_data="admin_toggle_role",
                )
            ],
        ]
    )
