from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_tutor_uses_one_stable_rail_without_resizing_chat_center():
    css = read("static/css/app.css")
    assert 'grid-template-columns:72px minmax(0,1fr) !important' in css
    assert 'body[data-active-section="assistant"] > .app-shell > .sidebar' in css
    assert '.tutor-chat-layout:not(.threads-collapsed) .chat-thread-sidebar' in css
    assert 'position:absolute !important' in css
    assert 'grid-column:2 !important' in css


def test_file_library_has_page_api_and_tutor_navigation():
    main = read("main.py")
    router = read("api/routers/attachments.py")
    chat = read("static/js/chat.js")
    page = read("templates/files.html")
    client = read("static/js/files.js")
    assert '@app.get("/files"' in main
    assert '@router.get("/library")' in router
    assert 'list_chat_attachment_library' in router
    assert "location.href = '/files.html'" in chat
    assert 'Библиотека файлов' in page
    assert '/api/v1/attachments/library' in client


def test_forget_attachment_removes_chat_memory_link_and_keeps_task_safety():
    storage = read("services/core/attachment_storage.py")
    router = read("api/routers/attachments.py")
    chat = read("static/js/chat.js")
    client = read("static/js/files.js")
    assert 'forget_attachment_from_chat_memory' in storage
    assert 'DELETE FROM chat_message_attachments' in storage
    assert 'attachment_name = NULL, attachment_type = NULL' in storage
    assert "active_attachment_ids = array_remove" in storage
    assert 'task_attachments' in storage
    assert 'task_submission_attachments' in storage
    assert '@router.delete("/{attachment_id}/memory")' in router
    assert 'data-chat-attachment="forget"' in chat
    assert '/memory' in client


def test_file_library_groups_web_and_telegram_by_chat_session():
    storage = read("services/core/attachment_storage.py")
    assert 'JOIN chat_sessions s' in storage
    assert 's.title AS chat_title' in storage
    assert 'telegram_default' in storage
    assert 'message_source' in storage
