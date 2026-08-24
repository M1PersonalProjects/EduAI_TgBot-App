from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_admin_reuses_current_reference_style_and_tutor_glow():
    html = _text("templates/admin.html")
    css = _text("static/css/app.css")
    admin_js = _text("static/js/admin.js")
    assert '<body class="admin-page">' in html
    assert "gradient-text" in html
    assert "text-emerald-200" not in html
    assert "bg-emerald-300" not in html
    assert "text-emerald-200" not in admin_js
    assert "body.admin-page .eduai-top-glow" in css
    assert "eduai-reference-glow-shift 5s linear infinite" in css
    assert ".admin-accent-text { color: var(--reference-accent)" in css


def test_top_settings_opens_theme_picker_without_duplicate_rail_button():
    app_js = _text("static/js/app.js")
    chat_js = _text("static/js/chat.js")
    assert "function openThemeSettings()" in app_js
    assert "EduAIUI = { applyTheme, setTheme, resetInterfaceLayout, openThemeSettings }" in app_js
    assert "data-rail-settings" not in chat_js
    assert 'data-theme-choice="light"' in app_js
    assert 'data-theme-choice="dark"' in app_js
    assert 'data-theme-choice="system"' in app_js
    assert "Светлая" in app_js
    assert "Тёмная" in app_js
    assert "Системная" in app_js


def test_theme_picker_is_bound_to_viewport_on_every_page():
    css = _text("static/css/app.css")
    assert '.ui-settings-popover,' in css
    assert "position: fixed !important" in css
    assert "right: max(.65rem, env(safe-area-inset-right))" in css
    assert "max-width: calc(100vw - 1.3rem)" in css
