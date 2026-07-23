from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from config import settings

def get_role_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="👨‍👩‍👦 Я Родитель", callback_data="set_role_parent"),
            InlineKeyboardButton(text="👨‍💻 Я Ученик", callback_data="set_role_student")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_parent_menu() -> ReplyKeyboardMarkup:
    """Меню для родителей"""
    buttons = [
        [
            KeyboardButton(text="➕ Привязать ребенка"),
            KeyboardButton(
                text="📊 Панель Родителя (Web App)",
                web_app=WebAppInfo(url=f"{settings.webapp_base_url}/parent/dashboard")
            )
        ],
        [
            KeyboardButton(
                text="📝 Создать ИИ-тест (Web App)",
                web_app=WebAppInfo(url=f"{settings.webapp_base_url}/parent/create-test")
            ),
            KeyboardButton(text="📊 Мониторинг в чате")
        ]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def get_student_menu() -> ReplyKeyboardMarkup:
    """Меню для учеников"""
    buttons = [
        [
            KeyboardButton(
                text="🚀 Открыть EduAI (Web App)",
                web_app=WebAppInfo(url=settings.webapp_base_url)
            ),
            KeyboardButton(text="📚 Каталог учебников")
        ],
        [
            KeyboardButton(text="🏆 Мой профиль")
        ]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)