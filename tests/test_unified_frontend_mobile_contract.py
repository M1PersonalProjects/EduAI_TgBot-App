from pathlib import Path


def _text(path: str) -> str:
    return Path(path).read_text(encoding='utf-8')


def test_student_uses_top_navigation_without_legacy_page_sidebar():
    html = _text('templates/student.html')
    assert 'class="sidebar"' not in html
    assert 'student-primary-nav' in html
    assert 'data-section="tutor"' in html
    assert 'data-section="tasks"' in html
    assert 'data-section="practice"' in html


def test_fixed_mobile_bottom_navigation_is_not_generated_anymore():
    app = _text('static/js/app.js')
    css = _text('static/css/app.css')
    assert 'function createMobileNavigation' not in app
    assert '.mobile-bottom-nav { display: none !important; }' in css


def test_theme_settings_are_theme_only_and_viewport_bound():
    app = _text('static/js/app.js')
    css = _text('static/css/app.css')
    assert 'data-theme-choice="light"' in app
    assert 'data-theme-choice="dark"' in app
    assert 'data-theme-choice="system"' in app
    assert 'data-ui-reset-layout' not in app
    assert 'position: fixed !important;' in css
    assert 'max-height: calc(var(--eduai-viewport-height, 100dvh) - 5.2rem)' in css


def test_tutor_rail_has_no_duplicate_settings_button():
    chat = _text('static/js/chat.js')
    assert 'data-rail-settings' not in chat
    assert 'data-rail-profile' in chat
    assert 'data-rail-chats' in chat


def test_mobile_thread_drawer_swipes_from_page_not_only_edge():
    chat = _text('static/js/chat.js')
    assert 'const fromEdge' not in chat
    assert "this.layout.classList.add('threads-drawer-open')" in chat
    assert "this.layout.classList.remove('threads-drawer-open')" in chat
    assert "thread-swipe-dragging" in chat
    assert "--thread-drawer-progress" in chat
    assert "input,textarea,select,button,a" in chat


def test_mobile_tutor_has_overlay_composer_stack():
    student = _text('templates/student.html')
    parent = _text('templates/parent.html')
    css = _text('static/css/app.css')
    assert 'class="chat-composer-stack"' in student
    assert 'class="chat-composer-stack"' in parent
    assert '.chat-composer-stack {' in css
    assert 'position: absolute !important;' in css
    assert 'padding: calc(4.25rem + env(safe-area-inset-top)) .65rem calc(6.6rem + env(safe-area-inset-bottom))' in css
