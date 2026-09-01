from pathlib import Path


def test_frontend_role_labels_do_not_change_technical_role_values():
    source = Path("static/js/app.js").read_text(encoding="utf-8")
    assert "student: 'Ученик'" in source
    assert "parent: 'Учитель / Родитель'" in source
    assert "mentor_kind" in source
    assert "Родитель" in source
    assert "admin: 'Администратор'" in source
    assert "parent: '/parent.html'" in source


def test_interactive_backend_keeps_parent_student_permissions():
    source = Path("api/routers/interactive.py").read_text(encoding="utf-8")
    assert 'user["role"] not in {"parent", "admin"}' in source
    assert "role='student'" in source
    assert 'user["role"] != "student"' in source
    assert '"teacher"' not in source


def test_admin_can_keep_admin_role_and_use_teacher_tutor_mode():
    tutor = Path("services/ai/orchestrator.py").read_text(encoding="utf-8")
    api = Path("api/routers/tutor.py").read_text(encoding="utf-8")
    assert 'resolved_role = "parent" if role == "admin" else str(role)' in tutor
    assert 'ALLOWED_TUTOR_ROLES = {"student", "parent", "admin"}' in api


def test_mobile_chat_layout_tracks_actual_active_section():
    app = Path("static/js/app.js").read_text(encoding="utf-8")
    css = Path("static/css/app.css").read_text(encoding="utf-8")
    assert "document.body.dataset.activeSection = id;" in app
    assert "const initialSection = document.querySelector('.page-section.active')?.id;" in app
    assert 'body[data-active-section="tutor"]' in css
    assert 'body[data-active-section="assistant"]' in css
