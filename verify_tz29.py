from __future__ import annotations

from pathlib import Path

ROOT = Path.cwd()
errors: list[str] = []


def read(rel: str) -> str:
    path = ROOT / rel
    if not path.exists():
        errors.append(f"missing file: {rel}")
        return ""
    return path.read_text(encoding="utf-8")


def require(rel: str, needle: str) -> None:
    if needle not in read(rel):
        errors.append(f"{rel}: missing {needle!r}")


def forbid(rel: str, needle: str) -> None:
    if needle in read(rel):
        errors.append(f"{rel}: obsolete/forbidden marker still present: {needle!r}")


require("services/tutor.py", "build_tutor_prompt")
require("services/tutor.py", "maybe_handle_chat_request")
require("services/tutor.py", "should_use_external_sources")
require("services/tutor.py", "should_search_eduai_materials")
forbid("services/tutor.py", "ЕДИНСТВЕННЫЙ РАЗРЕШЁННЫЙ УЧЕБНЫЙ КОНТЕКСТ")
forbid("services/tutor.py", "отвечай только на вопросы, связанные с обучением")
forbid("services/tutor.py", "ИИ-тьютор отвечает только по материалу выбранного учебника")

policy = read("services/tutor_policy.py")
for marker in (
    "Ordinary everyday conversation is allowed",
    "school, college/vocational education, and university",
    "You may use external sources, including web search",
    "do not refuse solely because the textbook lacks sufficient information",
    "CURRENT USER ROLE: TEACHER",
    "exported .html remains",
    "bridge is for result reporting only",
):
    if marker not in policy:
        errors.append(f"services/tutor_policy.py: missing policy marker {marker!r}")

require("services/response_formatter.py", "def telegram_safe_text(")
require("bot/messages.py", "telegram_safe_text")
require("bot/messages.py", "safe_chunk = telegram_safe_text(chunk).strip()")
require("bot/messages.py", "safe_payload = telegram_safe_text(payload).strip()")

require("api/routers/platform.py", "task_grading_prompt()")
require("api/routers/platform.py", "teacher_task_prompt()")
require("api/routers/tasks.py", "student_task_prompt()")
require("api/routers/tasks.py", "task_grading_prompt()")
forbid("api/routers/platform.py", "Проверь ответ школьника по смыслу")
forbid("api/routers/platform.py", 'if generated.title.strip() == "Недостаточно материала":')
forbid("api/routers/platform.py", "Тема не найдена в выбранном учебнике. Измените тему")
forbid("api/routers/tasks.py", "Тема не найдена в выбранном учебнике. Измените тему")

for rel in ("api/routers/tasks.py", "api/routers/platform.py"):
    source = read(rel)
    for obsolete in (
        "Use only the supplied textbook material",
        "Работай исключительно по предоставленному материалу учебника",
        "Use only the selected textbook/page context and attached materials",
    ):
        if obsolete in source:
            errors.append(f"{rel}: old restrictive prompt remains: {obsolete!r}")

require("main.py", "interactive_v1_router")
require("templates/interactive.html", 'sandbox="allow-scripts"')
forbid("templates/interactive.html", "allow-same-origin")
require("static/js/chat.js", "interactiveCardHtml(app)")
require("static/js/chat.js", "Скачать HTML")
require("static/js/chat.js", "Отправить Ученику")
require("static/js/app.js", "parent: 'Учитель'")
require("static/js/app.js", "student: 'Ученик'")
require("static/js/app.js", "admin: 'Администратор'")
require("static/js/app.js", "parent: '/parent.html'")
require("static/js/app.js", "document.body.dataset.activeSection = id;")
require("static/js/app.js", "const initialSection = document.querySelector('.page-section.active')?.id;")
require("services/tutor.py", 'if role == "admin":')
require("api/routers/tutor.py", 'ALLOWED_TUTOR_ROLES = {"student", "parent", "admin"}')

# Product labels change; technical roles must not.
for rel in ("api/routers/interactive.py", "api/routers/platform.py", "api/routers/tutor.py"):
    source = read(rel)
    if 'role == "teacher"' in source or "role='teacher'" in source or 'require_roles("teacher"' in source:
        errors.append(f"{rel}: technical teacher role was introduced; keep parent/student/admin")

for rel in ("bot/keyboards.py", "templates/admin.html", "templates/parent.html"):
    source = read(rel)
    for obsolete in ("Я Родитель", "Переключиться на Родителя", ">Родитель<", ">Родители<", "Parent Mode"):
        if obsolete in source:
            errors.append(f"{rel}: old visible role label remains: {obsolete!r}")

forbid("bot/handlers/start.py", "для учеников и родителей")
forbid("bot/handlers/start.py", "привязать ребёнка")
forbid("bot/handlers/start.py", "управлять детьми")
forbid("templates/parent.html", "Обзор детей")
forbid("templates/parent.html", "Кабинет родителя")
forbid("static/js/parent.js", "Для генерации ИИ выберите учебник")
forbid("templates/parent.html", "Для генерации задания с помощью ИИ учебник обязателен.")
forbid("templates/parent.html", "ИИ будет работать только по выбранному материалу.")
forbid("static/js/student.js", "Выбери учебник и задай вопрос по его материалу")
forbid("static/js/parent.js", "Могу объяснить материал выбранного учебника, разобрать учебное вложение или помочь подготовить задание")
require("static/js/parent.js", "const bookId = $('task-book').value ? Number($('task-book').value) : null;")

legacy_test = read("tests/test_conversation_context.py") if (ROOT / "tests/test_conversation_context.py").exists() else ""
if "migrations/028_conversation_context.sql" in legacy_test:
    errors.append("tests/test_conversation_context.py still depends on migrations/028_conversation_context.sql")

css = read("static/css/app.css")
if "TZ29 MOBILE TUTOR HEIGHT FIX" not in css:
    errors.append("static/css/app.css: mobile tutor height fix missing")
if "overflow: hidden" in css[css.find("TZ29 MOBILE TUTOR HEIGHT FIX"):]:
    errors.append("static/css/app.css: TZ29 mobile fix must not use global overflow:hidden")

if errors:
    print("TZ29 verification FAILED:\n")
    for item in errors:
        print(" -", item)
    raise SystemExit(1)

print("TZ29 verification passed.")
print("Technical roles remain parent | student | admin.")
print("Tests do not require migrations/028_conversation_context.sql.")
