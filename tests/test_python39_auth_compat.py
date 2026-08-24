from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_auth_helper_avoids_runtime_pep604_union_on_python39():
    source = (ROOT / "api/routers/auth.py").read_text(encoding="utf-8")
    assert "from typing import Optional" in source
    assert "telegram_photo_url: Optional[str] = None" in source
    assert "telegram_photo_url: str | None" not in source
