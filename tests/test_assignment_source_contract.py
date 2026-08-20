from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_migration_backfills_old_self_practice_before_parent_fallback():
    sql = _text("migrations/20260819_assignment_sources_gamification.sql")
    assert "assignment_source" in sql
    assert "telegram_quest_test" in sql
    assert "telegram_quest_generation" in sql
    assert "legacy_random_page_generation" in sql
    assert "legacy_task_generation" in sql
    assert "CHECK (assignment_source IN ('teacher', 'tutor_practice'))" in sql
    assert "tasks_history_source_owner_check" in sql
    assert "SET parent_id = NULL" in sql
    assert "assignment_source NOT IN ('teacher', 'tutor_practice')" in sql
    assert "assignment_source = 'teacher' AND parent_id IS NULL" in sql


def test_all_task_history_inserts_set_assignment_source():
    files = [
        "api/routers/tasks.py",
        "api/routers/platform.py",
        "api/routers/interactive.py",
        "bot/handlers/quests.py",
        "bot/handlers/parent.py",
    ]
    for path in files:
        source = _text(path)
        inserts = re.findall(
            r"INSERT\s+INTO\s+tasks_history\s*\((.*?)\)\s*VALUES",
            source,
            flags=re.IGNORECASE | re.DOTALL,
        )
        assert inserts, f"expected at least one tasks_history INSERT in {path}"
        for columns in inserts:
            assert "assignment_source" in columns, f"missing assignment_source in {path}"


def test_student_practice_and_teacher_creation_use_different_sources():
    task_api = _text("api/routers/tasks.py")
    quest_bot = _text("bot/handlers/quests.py")
    platform = _text("api/routers/platform.py")
    teacher_bot = _text("bot/handlers/parent.py")

    assert "'tutor_practice'" in task_api
    assert "'tutor_practice'" in quest_bot
    assert "'teacher'" in platform
    assert "'teacher'" in teacher_bot


def test_teacher_lists_and_statistics_filter_by_source():
    platform = _text("api/routers/platform.py")
    teacher_bot = _text("bot/handlers/parent.py")
    assert platform.count("assignment_source = 'teacher'") >= 4
    assert "assignment_source='teacher'" in teacher_bot or "assignment_source = 'teacher'" in teacher_bot


def test_gamification_ledger_is_idempotent_per_task_completion():
    sql = _text("migrations/20260819_assignment_sources_gamification.sql")
    service = _text("services/gamification.py")
    assert "UNIQUE(user_id, event_key)" in sql
    assert 'f"task:{task_id}:complete"' in service
    assert "duplicate_event=True" in service


def test_teacher_attachment_access_also_checks_assignment_source():
    source = _text("services/attachment_storage.py")
    assert source.count("th.assignment_source = 'teacher'") >= 2


def test_answer_workflows_branch_on_assignment_source():
    bot_tasks = _text("bot/handlers/tasks.py")
    api_tasks = _text("api/routers/tasks.py")
    platform = _text("api/routers/platform.py")
    interactive = _text("api/routers/interactive.py")
    assert "if source == TEACHER and parent_id" in bot_tasks
    assert '"evaluated" if source == TEACHER else "completed"' in bot_tasks
    assert '"evaluated" if source == "teacher" else "completed"' in api_tasks
    assert '"evaluated" if source == TEACHER else "completed"' in platform
    assert "assignment_source = normalize_assignment_source" in interactive
    assert '"evaluated" if assignment_source == TEACHER else "completed"' in interactive
