from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_teacher_students_and_tasks_have_no_global_sidebar():
    parent = read("templates/parent.html")
    assert '<body class="teacher-page">' in parent
    assert '<aside class="sidebar">' not in parent
    assert 'class="desktop-quick-nav teacher-primary-nav"' in parent
    assert 'data-section="overview"' in parent
    assert 'data-section="assistant"' in parent
    assert 'data-section="task-builder"' in parent


def test_admin_teacher_switch_is_compact_and_next_to_primary_tabs():
    parent = read("templates/parent.html")
    css = read("static/css/app.css")
    nav_start = parent.index('class="desktop-quick-nav teacher-primary-nav"')
    nav_end = parent.index('</nav>', nav_start)
    nav = parent[nav_start:nav_end]
    assert 'data-admin-only' in nav
    assert 'class="quick-role-switch"' in nav
    assert 'href="/admin.html"' in nav
    assert '⇄' in nav
    assert '.quick-role-switch[hidden] { display:none !important; }' in css


def test_teacher_primary_tabs_have_exactly_one_icon_each():
    parent = read("templates/parent.html")
    expected = {
        'overview': '◎',
        'assistant': '✦',
        'task-builder': '✓',
    }
    for section, icon in expected.items():
        marker = f'data-section="{section}"'
        start = parent.index(marker)
        end = parent.index('</button>', start)
        button = parent[start:end]
        assert button.count(icon) == 1
