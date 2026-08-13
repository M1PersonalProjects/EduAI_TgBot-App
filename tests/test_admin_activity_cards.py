from pathlib import Path


def test_admin_activity_has_expandable_cards():
    source = Path("static/js/admin.js").read_text(encoding="utf-8")
    assert "ACTIVITY_PREVIEW_LIMIT = 260" in source
    assert "Показать полностью" in source
    assert "Свернуть" in source
    assert "activity-message-full" in source
    assert "renderActivityDetail" in source


def test_admin_activity_backend_keeps_full_message():
    source = Path("api/routers/platform.py").read_text(encoding="utf-8")
    start = source.index('@router.get("/admin/activity")')
    route = source[start:]
    assert "message_text AS detail" in route
    assert "session_id" in route
    assert "username" in route
    assert "user_role" in route
