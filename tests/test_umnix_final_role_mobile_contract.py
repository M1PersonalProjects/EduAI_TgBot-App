from pathlib import Path

from services.mentor_identity import mentor_label, normalize_mentor_kind


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_teacher_and_parent_share_backend_role_but_keep_public_identity():
    start = read("bot/handlers/start.py")
    database = read("database.sql")
    auth = read("api/routers/auth.py")
    assert 'db_role = "parent" if selected_role in {"teacher", "parent"}' in start
    assert 'mentor_kind = selected_role if selected_role in {"teacher", "parent"}' in start
    assert "Я Учитель" in read("bot/keyboards.py")
    assert "Я Родитель" in read("bot/keyboards.py")
    assert "mentor_kind TEXT" in database
    assert '"mentor_kind"' in auth
    assert normalize_mentor_kind("parent") == "parent"
    assert mentor_label("parent") == "Родитель"
    assert mentor_label("teacher", "dative") == "Учителю"


def test_mobile_chat_history_is_full_screen_swipe_only():
    css = read("static/css/app.css")
    chat = read("static/js/chat.js")
    assert "width: 100dvw !important" in css
    assert "min-width: 100dvw !important" in css
    assert "[data-chat-sidebar-toggle]" in css
    assert "display: none !important" in css
    assert "installSwipeGestures" in chat
    assert "threads-drawer-open" in chat
    assert "touchmove" in chat


def test_all_role_dashboards_use_single_mobile_section_launcher():
    app = read("static/js/app.js")
    css = read("static/css/app.css")
    assert "setupMobileSectionNavigation" in app
    assert "teacher-primary-nav, .student-primary-nav, .admin-primary-nav" in app
    assert ".mobile-section-menu-toggle" in css
    assert ".desktop-quick-nav.student-primary-nav" in css
    assert ".desktop-quick-nav.teacher-primary-nav" in css
    assert ".desktop-quick-nav.admin-primary-nav" in css


def test_student_teacher_have_about_section_and_compact_task_cards():
    student = read("templates/student.html")
    teacher = read("templates/parent.html")
    student_js = read("static/js/student.js")
    teacher_js = read("static/js/parent.js")
    for source in (student, teacher):
        assert "О нашем приложении" in source
        assert 'id="about"' in source
        assert "Umnix" in source
        assert "umnix.ai" not in source
    assert "compact-record-card" in student_js
    assert "compact-record-card" in teacher_js
    assert "compact-record-grid" in teacher


def test_admin_and_existing_telegram_chat_titles_use_public_umnix_brand():
    platform = read("api/routers/platform.py")
    conversation = read("services/conversation_context.py")
    admin = read("static/js/admin.js")
    assert "mentor_kind" in platform
    assert "Чат Telegram · Umnix" in conversation
    assert "Родитель" in admin and "Учитель" in admin


def test_teacher_copy_is_not_rewritten_from_neutral_parent_wording():
    app = read("static/js/app.js")
    assert "if (!parentMode) return;" in app
    assert "['Родитель','Учитель']" not in app
