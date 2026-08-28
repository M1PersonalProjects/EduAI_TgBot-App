from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_all_site_templates_use_shared_background_bundle():
    for name in ("admin", "parent", "student", "auth", "files", "interactive"):
        source = _text(f"templates/{name}.html")
        assert "/static/css/app.css?v=20260825-umnix-2" in source
        assert "/static/js/app.js?v=20260825-umnix-2" in source


def test_shared_app_installs_matrix_and_glow_once():
    source = _text("static/js/app.js")
    assert "function setupMatrixBackground()" in source
    assert "function setupTopGlow()" in source
    assert "setupMatrixBackground();" in source
    assert "setupTopGlow();" in source
    assert "eduai-matrix-canvas" in source
    assert "eduai-top-glow" in source


def test_teacher_and_admin_use_same_role_switch_component():
    admin = _text("templates/admin.html")
    parent = _text("templates/parent.html")
    css = _text("static/css/app.css")
    assert 'href="/parent.html" class="quick-role-switch"' in admin
    assert 'href="/admin.html"' in parent
    assert 'class="quick-role-switch"' in parent
    assert "body.teacher-page .teacher-primary-nav .quick-role-switch" in css
    assert "body.admin-page .admin-primary-nav .quick-role-switch" in css
    assert "width: 34px !important" in css
    assert "height: 34px !important" in css
