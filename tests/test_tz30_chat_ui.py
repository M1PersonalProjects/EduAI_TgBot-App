from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_chat_keeps_jump_to_bottom_without_forced_ai_scroll():
    js = read("static/js/chat.js")
    student = read("templates/student.html")
    parent = read("templates/parent.html")
    css = read("static/css/app.css")

    assert "data-chat-jump-bottom" in student
    assert "data-chat-jump-bottom" in parent
    assert "isNearBottom" in js
    assert "updateJumpButton" in js
    assert "scrollToBottom" in js
    assert "loadSessions(result.session_id, { loadMessages: false })" in js
    assert ".chat-jump-bottom" in css
    assert "position: absolute" in css


def test_chat_thread_sidebar_is_collapsible_and_mobile_drawer():
    js = read("static/js/chat.js")
    css = read("static/css/app.css")
    for template in (read("templates/student.html"), read("templates/parent.html")):
        assert "data-chat-layout" in template
        assert "data-chat-sidebar-toggle" in template
        assert "data-chat-sidebar-backdrop" in template
    assert "threads-collapsed" in js
    assert "threads-drawer-open" in js
    assert "@media (max-width: 1279px)" in css


def test_interactive_card_actions_do_not_use_square_thread_action_buttons():
    js = read("static/js/chat.js")
    css = read("static/css/app.css")
    assert "interactive-card-action" in js
    assert "interactive-card-actions" in css
    assert "min-width: max-content" in css
    assert "grid-template-columns: 1fr" in css


def test_chat_composer_autosizes_and_has_mobile_send_button():
    js = read("static/js/chat.js")
    css = read("static/css/app.css")
    assert "resizeComposer" in js
    assert "chat-composer-input" in css
    assert "chat-send-label" in css
    assert "max-height: 8rem" in css
