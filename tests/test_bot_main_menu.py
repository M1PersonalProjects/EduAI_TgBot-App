from pathlib import Path

from bot.keyboards import get_admin_menu, get_parent_menu, get_student_menu


OLD_WEBAPP_BUTTONS = (
    "📊 Панель Родителя (Web App)",
    "📝 Создать ИИ-тест (Web App)",
    "🚀 Открыть EduAI (Web App)",
)


def _button_texts(markup):
    rows = getattr(markup, "keyboard", None)
    if rows is None:
        rows = markup.inline_keyboard
    return [button.text for row in rows for button in row]


def _webapp_buttons(markup):
    rows = getattr(markup, "keyboard", None)
    if rows is None:
        rows = markup.inline_keyboard
    return [
        button
        for row in rows
        for button in row
        if getattr(button, "web_app", None) is not None
    ]


def test_parent_menu_has_one_universal_webapp_button():
    menu = get_parent_menu()
    texts = _button_texts(menu)
    assert "🌐 Открыть EduAI" in texts
    assert len(_webapp_buttons(menu)) == 1
    for old in OLD_WEBAPP_BUTTONS:
        assert old not in texts


def test_student_menu_uses_same_webapp_label():
    menu = get_student_menu()
    texts = _button_texts(menu)
    assert "🌐 Открыть EduAI" in texts
    assert len(_webapp_buttons(menu)) == 1
    for old in OLD_WEBAPP_BUTTONS:
        assert old not in texts


def test_admin_menu_has_webapp_and_role_toggle():
    menu = get_admin_menu()
    texts = _button_texts(menu)
    assert "🌐 Открыть EduAI" in texts
    assert "👩‍🏫 Переключиться на Учителя" in texts
    assert len(_webapp_buttons(menu)) == 1


def test_old_main_menu_webapp_buttons_do_not_exist_in_bot_source():
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("bot").rglob("*.py")
    )
    for old in OLD_WEBAPP_BUTTONS:
        assert old not in source


def test_start_has_role_specific_telegram_and_webapp_copy():
    source = Path("bot/handlers/start.py").read_text(encoding="utf-8")
    assert "STUDENT_START_TEXT" in source
    assert "PARENT_START_TEXT" in source
    assert "ADMIN_START_TEXT" in source
    assert "NEW_USER_START_TEXT" in source
    assert "В Telegram" in source
    assert "WebApp" in source
    assert "🌐 Открыть EduAI" in source
