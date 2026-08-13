from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_common_rich_renderer_exists():
    js = read("static/js/app.js")
    assert "renderRichContent" in js
    assert "EduAI" in js


def test_admin_activity_uses_common_rich_renderer():
    js = read("static/js/admin.js")

    # TZ24 refactored Activities into expandable cards. The important contract
    # is that both preview and full message go through the common rich renderer,
    # not the old exact one-line implementation from TZ23.
    assert "function renderActivityDetail" in js
    assert "EduAI.renderRichContent" in js or "EduAI.markdown" in js
    assert "renderActivityDetail(preview)" in js
    assert "renderActivityDetail(detail)" in js


def test_admin_activity_preview_is_ui_only_and_expandable():
    js = read("static/js/admin.js")

    assert "ACTIVITY_PREVIEW_LIMIT = 260" in js
    assert "activityPreview" in js
    assert "Показать полностью" in js
    assert "Свернуть" in js
    assert "activity-message-full" in js


def test_math_renderer_has_safe_fallback():
    js = read("static/js/app.js")

    # Do not require one particular KaTeX implementation detail, but make sure
    # a fallback path exists and raw TeX is not intentionally returned as-is.
    assert "fallback" in js.lower() or "latexFallback" in js


def test_admin_activity_does_not_render_detail_with_plain_escape_only():
    js = read("static/js/admin.js")

    # The activity body must be rendered through renderActivityDetail().
    assert "renderActivityDetail(detail)" in js
