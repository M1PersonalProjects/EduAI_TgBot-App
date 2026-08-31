from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_sender_identity_profile_and_new_chat_greeting_contract():
    tutor = read("services/tutor.py")
    api = read("api/routers/tutor.py")
    chat = read("static/js/chat.js")
    assert 'sender_name' in tutor
    assert '/profile' in api and 'display_name' in api
    assert "Добрый день, ${displayName}" in chat
    assert "item.sender_name" in chat
    assert "data-chat-profile" in chat
    assert "avatar_url" in chat


def test_teacher_ai_message_creates_editable_draft_before_send():
    platform = read("api/routers/platform.py")
    parent = read("static/js/parent.js")
    chat = read("static/js/chat.js")
    assert '/parent/task-drafts' in platform
    assert '/parent/task-drafts/{draft_id}/send' in platform
    assert 'status": "draft"' in platform
    assert "eduai:create-task-from-ai" in chat
    assert "eduai:create-task-from-ai" in parent
    assert "saveTaskDraft" in parent
    assert "send-task-draft" in parent
    # Обычное задание нельзя отправить в обход подтверждённого черновика.
    assert '@router.post(\n    "/parent/tasks",' not in platform
    # AI-черновик разрешено подготовить до выбора Ученика.
    assert 'if payload.student_ids:' in platform


def test_regular_teacher_tasks_require_manual_review_everywhere():
    platform = read("api/routers/platform.py")
    student = read("static/js/student.js")
    parent = read("static/js/parent.js")
    assert "pending_review" in platform
    assert "/review-suggestion" in platform
    assert "/review" in platform
    assert "Ручная проверка Учителя" in parent
    assert "Проверить" not in student
    assert not (ROOT / "api/routers/tasks.py").exists()


def test_student_transport_does_not_expose_teacher_answer_keys():
    platform = read("api/routers/platform.py")
    assert "SENSITIVE_STUDENT_TASK_KEYS" in platform
    assert '"reference_answer"' in platform
    assert '"correct_answer"' in platform
    assert '"ai_instructions"' in platform
    assert "student_safe_task_payload" in platform


def test_interactive_apps_use_existing_task_system_and_server_grading():
    interactive = read("api/routers/interactive.py")
    service = read("services/interactive_apps.py")
    chat = read("static/js/chat.js")
    assert "interactive_assignments" in interactive
    assert "tasks_history" in interactive
    assert "grade_interactive_submission" in interactive
    assert "contains_embedded_solution_data" in interactive
    assert "Отправить Ученикам" in chat
    assert "Проверить приложение" in chat
    assert "INTERACTIVE_GRADING_RULES" in service



def test_ios_chat_adaptation_profile_search_swipes_keyboard_and_book_sheet():
    chat = read("static/js/chat.js")
    app = read("static/js/app.js")
    css = read("static/css/app.css")
    assert "data-chat-search" in chat
    assert "installSwipeGestures" in chat
    assert "threads-collapsed" in chat
    assert "threads-drawer-open" in chat
    assert "visualViewport" in app
    assert "keyboard-open" in app
    assert "setupBookModePanels" in app
    assert "Umnix думает" in app
    assert ".eduai-top-glow" in css
    assert "prefers-reduced-motion: reduce" in css


def test_runtime_schema_is_self_contained_and_does_not_require_sql_files():
    schema = read("services/schema_migrations.py")
    assert "RUNTIME_SCHEMA_STATEMENTS" in schema
    assert "task_drafts" in schema
    assert "pending_review" in schema
    assert "Path(" not in schema
    assert "read_text(" not in schema
    assert "migrations/" not in schema
