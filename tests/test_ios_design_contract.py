from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_ios_theme_modes_and_tokens_are_present():
    css = _read("static/css/app.css")
    js = _read("static/js/app.js")
    assert "--ios-bg:" in css
    assert 'html[data-theme="dark"]' in css
    assert "prefers-color-scheme: dark" in js
    assert "eduai.ui.theme" in js
    assert "data-theme-choice" in js


def test_compact_navigation_and_sheets_are_present():
    css = _read("static/css/app.css")
    js = _read("static/js/app.js")
    assert ".desktop-quick-nav" in css
    assert ".mobile-bottom-nav" in css
    assert ".chat-context-panel" in css
    assert "setupBookModePanels" in js
    assert "createMobileNavigation" in js


def test_layout_persistence_reset_and_dynamic_scroll_are_present():
    css = _read("static/css/app.css")
    js = _read("static/js/app.js")
    assert "eduai.ui.layout:" in js
    assert "resetInterfaceLayout" in js
    assert ".ui-movable-module" in css
    assert ".global-scroll-control" in css
    assert "targetInfo" in js


def test_accessibility_and_motion_fallbacks_are_present():
    css = _read("static/css/app.css")
    js = _read("static/js/app.js")
    assert "prefers-reduced-motion: reduce" in css
    assert "@supports not" in css
    assert 'aria-label="Настройки интерфейса"' in js
    assert "env(safe-area-inset-bottom)" in css
