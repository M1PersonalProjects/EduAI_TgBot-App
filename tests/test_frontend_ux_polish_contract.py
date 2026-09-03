from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_composer_is_compact_and_empty_placeholder_does_not_expand_it():
    chat = _text("static/js/chat.js")
    css = _text("static/css/app.css")
    student = _text("templates/student.html")
    parent = _text("templates/parent.html")
    assert "if (!String(input.value || '').trim())" in chat
    assert "baseHeight = mobile ? 34 : 32" in chat
    assert 'placeholder="Спросите Umnix…"' in student
    assert 'placeholder="Спросите Umnix…"' in parent
    assert "min-height: 42px !important" in css
    assert "width: min(100%, 960px)" in css


def test_mobile_tutor_navigation_contains_sections_and_role_switch():
    app = _text("static/js/app.js")
    css = _text("static/css/app.css")
    assert "function setupTutorMobileNavigation" in app
    assert "tutor-mobile-nav-toggle" in app
    assert "tutor-mobile-nav-sheet" in app
    assert "primaryNav.querySelectorAll('[data-section]').forEach(addSection)" in app
    assert "quick-role-switch" in app
    assert "rotate(360deg)" in css
    assert ".tutor-chat-layout.mobile-nav-open .tutor-mobile-nav-sheet" in css


def test_theme_popover_and_mobile_drawers_are_animated_not_blinking():
    app = _text("static/js/app.js")
    chat = _text("static/js/chat.js")
    css = _text("static/css/app.css")
    assert "popover.classList.add('is-open')" in app
    assert "popover.classList.remove('is-open')" in app
    assert ".ui-settings-popover.is-open" in css
    assert "thread-swipe-dragging" in chat
    assert "--thread-drag-x" in chat
    assert "visibility: hidden" in css


def test_light_theme_muted_text_is_contrast_safe():
    css = _text("static/css/app.css")
    assert "--reference-muted: #5f6672" in css
    assert 'html[data-theme="light"] .message-content' in css
    assert "color: #24282f !important" in css


def test_telegram_avatar_prefers_webapp_photo_and_retries_bot_api_quickly():
    chat = _text("static/js/chat.js")
    auth = _text("static/js/auth.js")
    profile = _text("services/bot/telegram_profile.py")
    auth_api = _text("api/routers/auth.py")
    assert "initDataUnsafe?.user?.photo_url" in chat
    assert "telegram_photo_url" in auth
    assert 'telegram_user.get("photo_url")' in auth_api
    assert "avatar_fallback_url" in chat
    assert "_AVATAR_NEGATIVE_TTL_SECONDS = 45" in profile


def test_admin_has_consistent_page_gutter():
    css = _text("static/css/app.css")
    assert "body.admin-page .admin-main-area" in css
    assert "padding-left: clamp(.9rem, 2vw, 1.5rem) !important" in css
    assert "padding-right: clamp(.9rem, 2vw, 1.5rem) !important" in css
