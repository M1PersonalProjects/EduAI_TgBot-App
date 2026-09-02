from datetime import datetime, timedelta, timezone
from pathlib import Path

from services.education.conversation_context import (
    ATTACHMENT_MODE,
    BOOK_MODE,
    GENERAL_MODE,
    explicit_attachment_reference,
    explicit_mixed_source_request,
    filter_history_since_activation,
    normalize_mode,
)


def test_context_modes_are_explicit():
    assert normalize_mode("book") == BOOK_MODE
    assert normalize_mode("attachment") == ATTACHMENT_MODE
    assert normalize_mode("general") == GENERAL_MODE
    assert normalize_mode("unknown") == GENERAL_MODE


def test_reference_detection_prefers_explicit_file_language():
    assert explicit_attachment_reference("Вернёмся к моему PDF с задачами")
    assert explicit_attachment_reference("Проверь второй пример в файле")
    assert not explicit_attachment_reference("Объясни это задание")


def test_explicit_comparison_allows_mixed_sources():
    assert explicit_mixed_source_request(
        "Сравни эту тему из учебника с задачами в моём PDF"
    )
    assert not explicit_mixed_source_request("Вернёмся к моему PDF")


def test_history_is_scoped_after_context_switch():
    now = datetime.now(timezone.utc)
    history = [
        {"message_id": 1, "created_at": now - timedelta(minutes=5)},
        {"message_id": 2, "created_at": now + timedelta(seconds=1)},
    ]
    filtered = filter_history_since_activation(history, now)
    assert [item["message_id"] for item in filtered] == [2]


def test_tutor_book_mode_excludes_old_attachments_by_default():
    source = Path("services/ai/orchestrator.py").read_text(encoding="utf-8")
    assert "elif active_mode == BOOK_MODE:" in source
    assert "if attachment_reference:" in source
    assert "selected_attachments = []" in source


def test_telegram_always_uses_special_session():
    source = Path("bot/handlers/ai_chat.py").read_text(encoding="utf-8")
    assert "ensure_telegram_session" in source
    assert 'message_source="telegram"' in source
    assert "create_session" not in source


def test_webapp_keeps_telegram_chat_visible_and_non_deletable():
    source = Path("static/js/chat.js").read_text(encoding="utf-8")
    assert "telegram_default" in source
    assert "telegramDefault" in source
    assert "message_source" in source



def test_explicit_book_reference_detects_natural_language_textbook_pointer():
    from services.education.conversation_context import explicit_book_reference
    assert explicit_book_reference("В учебнике Математика 5 класс на странице 42 объясни пример")
    assert explicit_book_reference("Возьми параграф 7 и объясни правило")
    assert not explicit_book_reference("Как у тебя дела?")
