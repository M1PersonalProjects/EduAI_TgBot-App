from unittest.mock import AsyncMock

import pytest

from services.interactive.interactive_apps import (
    contains_embedded_solution_data,
    maybe_handle_chat_request,
    sanitize_interactive_html,
    serialize_app,
)


def test_interactive_page_uses_strict_sandbox_without_same_origin():
    from pathlib import Path
    template = Path("templates/interactive.html").read_text(encoding="utf-8")
    assert 'sandbox="allow-scripts"' in template
    assert "allow-same-origin" not in template
    assert 'referrerpolicy="no-referrer"' in template


def test_generated_html_is_self_contained_and_network_is_blocked():
    html = sanitize_interactive_html(
        """
        <!doctype html><html><head><meta name="viewport" content="width=device-width">
        <script src="https://evil.example/a.js"></script></head><body>
        <iframe src="https://evil.example"></iframe>
        <a href="https://evil.example">go</a><a href="/api/private">relative</a>
        <script>document.cookie; fetch("https://evil.example/x"); window.parent.postMessage({secret:true}, "*");</script>
        </body></html>
        """
    )
    assert "Content-Security-Policy" in html
    assert "connect-src 'none'" in html
    assert "https://evil.example" not in html
    assert 'href="/api/private"' not in html
    assert "<iframe" not in html.lower()
    assert "document.cookie" not in html
    assert html.count("window.parent.postMessage") == 1
    assert "EduAIInteractive" in html


def test_student_answer_keys_are_detected():
    assert contains_embedded_solution_data("<script>const correctAnswers={q1: 2}</script>")
    assert contains_embedded_solution_data("<script>answerKey = ['a']</script>")
    assert not contains_embedded_solution_data("<script>const answers = collectAnswers()</script>")


@pytest.mark.asyncio
async def test_normal_text_never_auto_starts_interactive_app(monkeypatch):
    create = AsyncMock()
    edit = AsyncMock()
    monkeypatch.setattr("services.interactive.interactive_apps.create_app", create)
    monkeypatch.setattr("services.interactive.interactive_apps.edit_app", edit)
    result = await maybe_handle_chat_request(
        user_id=1,
        session_id=__import__('uuid').uuid4(),
        role="parent",
        message_text="Создай интерактивное приложение по геометрии",
        context=None,
    )
    assert result is None
    create.assert_not_awaited()
    edit.assert_not_awaited()


@pytest.mark.asyncio
async def test_explicit_create_mode_starts_generator(monkeypatch):
    expected = {"app_id": "x"}
    create = AsyncMock(return_value=expected)
    monkeypatch.setattr("services.interactive.interactive_apps.create_app", create)
    result = await maybe_handle_chat_request(
        user_id=1,
        session_id=__import__('uuid').uuid4(),
        role="parent",
        message_text="Геометрия, 10 заданий",
        context=None,
        interactive_action="create",
    )
    assert result == expected
    create.assert_awaited_once()


def test_serialized_card_is_pinned_to_saved_version():
    import uuid
    app_id = uuid.uuid4()
    session_id = uuid.uuid4()
    data = serialize_app({
        "app_id": app_id,
        "session_id": session_id,
        "question_count": 10,
        "current_version": 5,
        "version_no": 2,
    })
    assert data["version_no"] == 2
    assert data["open_url"].endswith("?version=2")
    assert data["download_url"].endswith("?version=2")


def test_service_has_no_legacy_structured_shell_or_intent_detector():
    from pathlib import Path
    source = Path("services/interactive/interactive_apps.py").read_text(encoding="utf-8")
    assert "render_interactive_shell" not in source
    assert "InteractiveAppSpec" not in source
    assert "detect_create_request" not in source
    assert "detect_edit_request" not in source
