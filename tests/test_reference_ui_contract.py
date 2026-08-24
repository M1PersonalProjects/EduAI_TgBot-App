from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_reference_background_is_shared_and_performance_aware():
    app = text("static/js/app.js")
    css = text("static/css/app.css")
    assert "setupMatrixBackground" in app
    assert "eduai-matrix-canvas" in app
    assert "requestAnimationFrame(draw)" in app
    assert "prefers-reduced-motion: reduce" in css
    assert "--matrix-rgb" in css
    assert "mask-image: linear-gradient" in css


def test_tutor_top_glow_is_permanent_and_ai_thinking_only_intensifies_it():
    app = text("static/js/app.js")
    css = text("static/css/app.css")
    assert "document.body.classList.add('ai-thinking')" in app
    assert "document.body.classList.remove('ai-thinking')" in app
    assert ".eduai-top-glow" in css
    assert "body.ai-thinking .eduai-top-glow" in css
    assert 'body[data-active-section="tutor"] .eduai-top-glow' in css
    assert 'body[data-active-section="assistant"] .eduai-top-glow' in css
    assert 'opacity:.58 !important' in css
    assert 'body[data-active-section="assistant"].ai-thinking .eduai-top-glow' in css


def test_tutor_desktop_sidebar_cannot_collapse_text_into_one_letter_column():
    chat = text("static/js/chat.js")
    css = text("static/css/app.css")
    assert "installTutorRail" in chat
    assert "chat-rail-actions" in chat
    assert ".tutor-chat-layout.threads-collapsed .chat-thread-sidebar > *:not(.chat-rail-actions)" in css
    assert "width: 72px !important" in css
    assert ".tutor-chat-layout:not(.threads-collapsed) .chat-thread-sidebar" in css


def test_chat_matches_reference_message_and_composer_geometry():
    css = text("static/css/app.css")
    chat = text("static/js/chat.js")
    assert "max-width: 75% !important" in css
    assert "width: 100% !important" in css
    assert "#parent-chat-form" in css
    assert "border-radius: 999px !important" in css
    assert "ИИ-тьютор" in chat


def test_templates_bust_old_frontend_cache():
    for name in ("auth.html", "student.html", "parent.html", "admin.html", "interactive.html"):
        source = text(f"templates/{name}")
        assert "app.css?v=20260824-ux-polish-2" in source
        assert "app.js?v=20260824-ux-polish-2" in source
        assert "20260823-tz-2" not in source
