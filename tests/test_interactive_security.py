from pathlib import Path

from services.interactive_apps import (
    inject_interactive_math_renderer,
    interactive_html_has_math,
    sanitize_interactive_html,
)


def test_interactive_page_uses_strict_sandbox_without_same_origin():
    template = Path("templates/interactive.html").read_text(encoding="utf-8")
    assert 'sandbox="allow-scripts"' in template
    assert "allow-same-origin" not in template
    assert 'referrerpolicy="no-referrer"' in template


def test_generated_html_is_self_contained_and_network_is_blocked():
    html = sanitize_interactive_html(
        """
        <!doctype html><html><head>
        <script src="https://evil.example/a.js"></script>
        </head><body>
        <iframe src="https://evil.example"></iframe>
        <a href="https://evil.example">go</a>
        <a href="/api/private">relative</a>
        <script>
        document.cookie;
        fetch("https://evil.example/x");
        window.parent.postMessage({secret:true}, "*");
        window.location.href = "https://evil.example/escape";
        </script>
        <h1>Тест</h1>
        </body></html>
        """
    )
    assert "Content-Security-Policy" in html
    assert "connect-src 'none'" in html
    assert "https://evil.example" not in html
    assert 'href="/api/private"' not in html
    assert "<iframe" not in html.lower()
    assert "document.cookie" not in html
    assert "window.location" not in html
    # Only the trusted bridge injected by EduAI is allowed to call parent.postMessage.
    assert html.count("window.parent.postMessage") == 1
    assert "EduAIInteractive" in html



def test_interactive_math_renderer_is_self_contained_and_injected_only_for_math():
    raw = r"""<!doctype html><html><body><p>Решите: \(\frac{x+1}{2}\)</p></body></html>"""
    sanitized = sanitize_interactive_html(raw)
    rendered = inject_interactive_math_renderer(sanitized)
    assert interactive_html_has_math(raw)
    assert "data-eduai-interactive-math" in rendered
    assert "eduai-frac" in rendered
    assert "MutationObserver" in rendered
    assert "cdn.jsdelivr" not in rendered
    assert "MathJax" not in rendered


def test_interactive_math_detection_covers_dynamic_question_strings():
    raw = r"""<!doctype html><html><body><div id="q"></div><script>
    const questions = [{text: "Найдите \\\\sqrt{16}"}];
    document.getElementById("q").textContent = questions[0].text;
    </script></body></html>"""
    assert interactive_html_has_math(raw)
    rendered = inject_interactive_math_renderer(sanitize_interactive_html(raw))
    assert "data-eduai-interactive-math" in rendered


def test_interactive_math_detection_handles_single_dollar_and_double_escaped_tex():
    assert interactive_html_has_math(r"<p>$x^2 + 1$</p>")
    assert interactive_html_has_math(r"<script>const q='\\\\frac{1}{3}'</script>")
