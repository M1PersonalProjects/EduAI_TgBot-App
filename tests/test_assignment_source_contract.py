from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_runtime_schema_backfills_old_self_practice_before_parent_fallback():
    schema = _text("services/schema_migrations.py")
    assert "assignment_source" in schema
    assert "telegram_quest_test" in schema
    assert "telegram_quest_generation" in schema
    assert "legacy_random_page_generation" in schema
    assert "legacy_task_generation" in schema
    assert "CHECK (assignment_source IN ('teacher', 'tutor_practice'))" in schema
    assert "tasks_history_source_owner_check" in schema
    assert "SET parent_id = NULL" in schema
    assert "assignment_source NOT IN ('teacher', 'tutor_practice')" in schema
    assert "assignment_source = 'teacher' AND parent_id IS NULL" in schema


def test_all_task_history_inserts_set_assignment_source():
    files = [
        "api/routers/tasks.py",
        "api/routers/platform.py",
        "api/routers/interactive.py",
        "bot/handlers/quests.py",
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


def test_telegram_teacher_creation_point_was_intentionally_removed():
    """Старый Telegram-flow не должен создавать tasks_history в обход WebApp draft workflow."""
    source = _text("bot/handlers/parent.py")
    assert "INSERT INTO tasks_history" not in source
    assert "Создание обычных заданий перенесено в WebApp" in source
    assert "'teacher'" in source


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



def test_teacher_attachment_access_also_checks_assignment_source():
    source = _text("services/attachment_storage.py")
    assert source.count("th.assignment_source = 'teacher'") >= 2


def test_answer_workflows_branch_on_assignment_source():
    bot_tasks = _text("bot/handlers/tasks.py")
    api_tasks = _text("api/routers/tasks.py")
    platform = _text("api/routers/platform.py")
    interactive = _text("api/routers/interactive.py")
    assert "if source == TEACHER and parent_id" in bot_tasks
    assert "pending_review" in bot_tasks
    assert "if source == TEACHER" in api_tasks and "pending_review" in api_tasks
    assert "if source == TEACHER" in platform and "pending_review" in platform
    assert "assignment_source = normalize_assignment_source" in interactive
    assert '"evaluated" if assignment_source == TEACHER else "completed"' in interactive
