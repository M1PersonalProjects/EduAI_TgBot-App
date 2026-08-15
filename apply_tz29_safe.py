from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path.cwd().resolve()
BUNDLE = Path(__file__).resolve().parent
CORE = BUNDLE / "apply_tz29.py"
BACKUP = ROOT / ".tz29_backup_safe"

EXISTING_INPUTS = [
    "services/tutor.py",
    "services/scope_guard.py",
    "services/response_formatter.py",
    "bot/messages.py",
    "api/routers/tutor.py",
    "api/routers/platform.py",
    "api/routers/tasks.py",
    "main.py",
    "static/js/chat.js",
    "static/js/app.js",
    "static/js/student.js",
    "static/js/parent.js",
    "static/css/app.css",
    "templates/student.html",
    "templates/parent.html",
    "bot/handlers/start.py",
    "bot/handlers/parent.py",
    "bot/handlers/tasks.py",
    "bot/keyboards.py",
    "templates/admin.html",
    "static/js/admin.js",
    "tests/test_conversation_context.py",
]

OUTPUTS = [
    "services/tutor.py",
    "services/tutor_policy.py",
    "services/scope_guard.py",
    "services/interactive_apps.py",
    "services/response_formatter.py",
    "bot/messages.py",
    "api/routers/tutor.py",
    "api/routers/interactive.py",
    "api/routers/platform.py",
    "api/routers/tasks.py",
    "main.py",
    "static/js/chat.js",
    "static/js/app.js",
    "static/js/student.js",
    "static/js/parent.js",
    "static/css/app.css",
    "static/js/interactive.js",
    "static/css/interactive.css",
    "templates/student.html",
    "templates/parent.html",
    "templates/admin.html",
    "templates/interactive.html",
    "bot/handlers/start.py",
    "bot/handlers/parent.py",
    "bot/handlers/tasks.py",
    "bot/keyboards.py",
    "static/js/admin.js",
    "tests/test_conversation_context.py",
    "tests/test_tz29_tutor_policy.py",
    "tests/test_tz29_scope_guard.py",
    "tests/test_tz29_telegram_formatter.py",
    "tests/test_tz29_interactive_security.py",
    "tests/test_tz29_role_contract.py",
    "tests/bot/handlers/test_parent.py",
    "tests/bot/handlers/test_start.py",
    "tests/test_bot_main_menu.py",
]

REQUIRED = [
    "services/tutor.py",
    "services/response_formatter.py",
    "bot/messages.py",
    "api/routers/tutor.py",
    "main.py",
    "static/js/chat.js",
    "static/js/app.js",
    "static/css/app.css",
]

for rel in REQUIRED:
    if not (ROOT / rel).exists():
        raise SystemExit(f"Не найден обязательный файл текущего проекта: {rel}")
if not CORE.exists():
    raise SystemExit("В архиве отсутствует apply_tz29.py")


def copy_to_stage(stage: Path, rel: str) -> None:
    source = ROOT / rel
    if not source.exists():
        return
    target = stage / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def copy_project_to_stage(stage: Path) -> None:
    """Copy the executable/testable project tree without VCS, venvs or backups."""
    ignored = shutil.ignore_patterns(
        "__pycache__", "*.pyc", ".git", ".idea", "venv", ".venv",
        ".tz*_backup*", ".tz29_backup*", "node_modules",
    )
    for dirname in ("api", "bot", "services", "static", "templates", "tests"):
        source = ROOT / dirname
        if source.exists():
            shutil.copytree(source, stage / dirname, dirs_exist_ok=True, ignore=ignored)
    for filename in (
        "main.py", "config.py", "database.py", "logger_config.py",
        "pytest.ini", "pyproject.toml", "setup.cfg", ".env",
    ):
        source = ROOT / filename
        if source.exists() and source.is_file():
            shutil.copy2(source, stage / filename)


def backup_real(rel: str) -> bool:
    source = ROOT / rel
    if not source.exists():
        return False
    target = BACKUP / rel
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return True


def atomic_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tz29_tmp")
    shutil.copy2(source, temporary)
    os.replace(temporary, target)


with tempfile.TemporaryDirectory(prefix="eduai_tz29_stage_") as tmp:
    stage = Path(tmp)
    copy_project_to_stage(stage)
    # Keep this explicit list as a compatibility fallback for unusually arranged checkouts.
    for rel in EXISTING_INPUTS:
        copy_to_stage(stage, rel)

    # The core installer runs only against the staging tree. If any exact anchor,
    # syntax check, or compatibility check fails, the user's real checkout is untouched.
    proc = subprocess.run(
        [sys.executable, str(CORE)],
        cwd=stage,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if proc.stdout:
        print(proc.stdout.rstrip())
    if proc.returncode != 0:
        raise SystemExit(
            "\nTZ29 staging check failed. Реальные файлы проекта НЕ изменены. "
            "Пришлите вывод выше, если локальный checkout отличается от текущего main."
        )

    verify = subprocess.run(
        [sys.executable, str(BUNDLE / "verify_tz29.py")],
        cwd=stage,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if verify.stdout:
        print(verify.stdout.rstrip())
    if verify.returncode != 0:
        raise SystemExit(
            "\nTZ29 staging verification failed. Реальные файлы проекта НЕ изменены."
        )

    syntax = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", "api", "bot", "services", "tests", "main.py"],
        cwd=stage,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if syntax.stdout:
        print(syntax.stdout.rstrip())
    if syntax.returncode != 0:
        raise SystemExit(
            "\nTZ29 staging Python syntax check failed. Реальные файлы проекта НЕ изменены."
        )

    node = shutil.which("node")
    if node:
        for rel in (
            "static/js/app.js", "static/js/chat.js", "static/js/student.js",
            "static/js/parent.js", "static/js/admin.js", "static/js/interactive.js",
        ):
            target = stage / rel
            if not target.exists():
                continue
            check = subprocess.run(
                [node, "--check", str(target)],
                cwd=stage,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            if check.stdout:
                print(check.stdout.rstrip())
            if check.returncode != 0:
                raise SystemExit(
                    f"\nTZ29 staging JavaScript syntax check failed for {rel}. "
                    "Реальные файлы проекта НЕ изменены."
                )

    tests = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=stage,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if tests.stdout:
        print(tests.stdout.rstrip())
    if tests.returncode != 0:
        raise SystemExit(
            "\nTZ29 staging pytest failed. Реальные файлы проекта НЕ изменены. "
            "Исправьте показанные тесты/совместимость до установки."
        )

    missing = [rel for rel in OUTPUTS if rel != "tests/test_conversation_context.py" and not (stage / rel).exists()]
    if missing:
        raise SystemExit("TZ29 staging incomplete; missing outputs: " + ", ".join(missing))

    BACKUP.mkdir(exist_ok=True)
    existed_before = {rel: backup_real(rel) for rel in OUTPUTS}
    committed: list[str] = []
    try:
        for rel in OUTPUTS:
            source = stage / rel
            if not source.exists():
                continue
            atomic_copy(source, ROOT / rel)
            committed.append(rel)
    except Exception:
        # Best-effort rollback of the very small commit window.
        for rel in reversed(committed):
            backup_file = BACKUP / rel
            target = ROOT / rel
            if backup_file.exists():
                atomic_copy(backup_file, target)
            elif not existed_before.get(rel, False) and target.exists():
                target.unlink()
        raise

print("TZ29 applied successfully after staging validation and full pytest.")
print("Backup:", BACKUP)
print("Run TZ29_interactive_apps.sql in DataGrip before restarting EduAI.")
print("DB/API roles remain unchanged: parent | student | admin.")
print("Pytest does not require migrations/028_conversation_context.sql.")
