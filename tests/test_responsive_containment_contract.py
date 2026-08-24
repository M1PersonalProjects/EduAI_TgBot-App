from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_admin_clears_legacy_sidebar_offset_and_stays_in_viewport():
    css = _read("static/css/app.css")
    assert "RESPONSIVE CONTAINMENT + ADMIN VIEWPORT FIX" in css
    assert "body.admin-page .admin-main-area" in css
    assert "margin-left: auto !important" in css
    assert "margin-right: auto !important" in css
    assert "max-width: 100% !important" in css


def test_admin_mobile_navigation_is_swipeable_with_visible_labels():
    css = _read("static/css/app.css")
    assert "body.admin-page .admin-primary-nav" in css
    assert "overflow-x: auto" in css
    assert "-webkit-overflow-scrolling: touch" in css
    assert "span:last-child" in css
    assert "display: inline !important" in css


def test_mobile_controls_and_chat_are_viewport_safe():
    css = _read("static/css/app.css")
    assert "font-size: 16px" in css
    assert "prevents automatic iOS zoom" in css
    assert "width: min(21rem, calc(100vw - 1.2rem))" in css
    assert ".modal-panel" in css
    assert "overscroll-behavior: contain" in css


def test_all_primary_templates_bust_responsive_css_cache():
    for name in ("auth.html", "student.html", "parent.html", "admin.html", "interactive.html", "files.html"):
        source = _read(f"templates/{name}")
        assert "app.css?v=20260824-ux-polish-2" in source
