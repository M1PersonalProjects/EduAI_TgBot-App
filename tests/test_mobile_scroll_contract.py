from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_mobile_layout_uses_actual_content_height_and_single_page_scroll():
    css = (ROOT / "static/css/app.css").read_text(encoding="utf-8")
    marker = "2026-08-19 MOBILE CONTENT-HEIGHT FIX"
    assert marker in css
    fix = css.split(marker, 1)[1]
    assert "min-height: 0 !important" in fix
    assert "height: auto !important" in fix
    assert ".min-h-screen" in fix
    assert "overflow-y: auto" in fix
    assert "body.eduai-modal-open" in fix
    assert ".sidebar" in fix and ".chat-thread-sidebar" in fix
    assert "@media (max-width: 1023px)" in fix
    assert "overflow-y: visible !important" in fix


def test_mobile_fix_does_not_hide_page_overflow_globally():
    css = (ROOT / "static/css/app.css").read_text(encoding="utf-8")
    fix = css.split("2026-08-19 MOBILE CONTENT-HEIGHT FIX", 1)[1]
    # Overflow is locked only while a modal is actually open.
    assert "body.eduai-modal-open" in fix
    assert "html,\nbody {\n  overflow: hidden" not in fix


def test_telegram_keyboard_prefers_live_visual_viewport_over_stable_height():
    js = (ROOT / "static/js/app.js").read_text(encoding="utf-8")
    live = js.index("window.visualViewport?.height")
    stable = js.index("tg?.viewportStableHeight")
    assert live < stable


def test_interactive_page_no_longer_forces_large_viewport_min_height():
    css = (ROOT / "static/css/interactive.css").read_text(encoding="utf-8")
    assert "min-height: 70dvh" not in css
    assert "min-height: 68dvh" not in css
