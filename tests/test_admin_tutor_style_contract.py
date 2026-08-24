from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_admin_uses_tutor_style_capsule_without_sidebar():
    html = _text("templates/admin.html")
    assert '<body class="admin-page">' in html
    assert '<aside class="sidebar">' not in html
    assert 'class="desktop-quick-nav admin-primary-nav"' in html
    for section in ("admin-overview", "books", "digitization", "page-editor", "users", "activity"):
        assert f'data-section="{section}"' in html


def test_admin_teacher_role_switch_is_inside_primary_capsule():
    html = _text("templates/admin.html")
    nav_start = html.index('class="desktop-quick-nav admin-primary-nav"')
    nav_end = html.index('</nav>', nav_start)
    nav = html[nav_start:nav_end]
    assert 'href="/parent.html"' in nav
    assert 'class="quick-role-switch"' in nav
    assert '⇄' in nav
    assert 'Вернуться в режим Учителя' in nav


def test_admin_reuses_tutor_background_and_compact_glass_topbar():
    css = _text("static/css/app.css")
    assert 'body.admin-page .eduai-top-glow' in css
    assert 'opacity:.58 !important' in css
    assert 'eduai-reference-glow-shift 5s linear infinite' in css
    assert 'body.admin-page .eduai-matrix-canvas { opacity:1; }' in css
    assert 'body.admin-page .admin-topbar' in css
    assert 'border-radius:999px !important' in css
    assert 'body.admin-page .admin-primary-nav' in css
