from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _python_sources(*parts: str):
    for part in parts:
        yield from (ROOT / part).rglob("*.py")


def test_openai_sdk_is_created_only_in_shared_ai_client():
    offenders = []
    for path in _python_sources("api", "bot", "services"):
        text = path.read_text(encoding="utf-8")
        if "AsyncOpenAI(" in text and path.relative_to(ROOT).as_posix() != "services/ai/client.py":
            offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []


def test_application_layers_do_not_import_router_modules():
    offenders = []
    for path in _python_sources("api", "bot", "services"):
        text = path.read_text(encoding="utf-8")
        if "from api.routers" in text or "import api.routers" in text:
            offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []


def test_light_design_system_and_reduced_motion_are_present():
    css = (ROOT / "static/css/app.css").read_text(encoding="utf-8")
    assert "--color-background:" in css
    assert "--color-surface:" in css
    assert "color-scheme: light" in css
    assert "prefers-reduced-motion: reduce" in css



def test_runtime_storage_paths_are_project_rooted():
    """Runtime-файлы не должны появляться внутри пакета services."""
    from services.core.attachment_storage import ATTACHMENTS_ROOT
    from services.digitization.digitization_queue import QUEUE_STORAGE

    project_root = Path(__file__).resolve().parents[1]
    assert ATTACHMENTS_ROOT == project_root / "storage" / "attachments"
    assert QUEUE_STORAGE == project_root / "storage" / "digitization_queue"
