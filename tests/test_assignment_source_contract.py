from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_only_teacher_and_interactive_flows_persist_task_history():
    for path in ("api/routers/platform.py", "api/routers/interactive.py"):
        source = _text(path)
        inserts = re.findall(r"INSERT\s+INTO\s+tasks_history\s*\((.*?)\)\s*VALUES", source, flags=re.I | re.S)
        assert inserts
        for columns in inserts:
            assert "assignment_source" in columns
        assert "'teacher'" in source


def test_telegram_quest_is_temporary_and_never_persists_tasks():
    source = _text("bot/handlers/tasks.py") + _text("bot/handlers/quests.py")
    assert "INSERT INTO tasks_history" not in source
    assert "UPDATE tasks_history" not in source
    assert "telegram_quest_test" in source


def test_student_dashboard_contains_only_teacher_assignments():
    platform = _text("api/routers/platform.py")
    assert "assignment_source = 'teacher'" in platform
    assert "practice_tasks" not in platform
    assert "pending_review" in platform


def test_teacher_attachment_access_checks_assignment_source():
    source = _text("services/core/attachment_storage.py")
    assert source.count("th.assignment_source = 'teacher'") >= 2


def test_interactive_assignment_is_teacher_source_but_server_graded_exception():
    source = _text("api/routers/interactive.py")
    assert "generate_response" in source
    assert 'mode="interactive_grade"' in source
    assert "'teacher'" in source
    assert "interactive_version" in source
