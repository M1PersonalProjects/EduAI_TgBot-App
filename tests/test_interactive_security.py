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


def test_interactive_prompt_forbids_embedded_answer_keys():
    from services.tutor_policy import INTERACTIVE_TASK_RULES
    prompt = INTERACTIVE_TASK_RULES.lower()
    assert "questions only" in prompt
    assert "never embed correct answers" in prompt
    assert "answerkey" in prompt
    assert "finished eduai learning product" in prompt


def test_interactive_solution_detector_catches_obvious_client_side_keys():
    from services.interactive_apps import contains_embedded_solution_data
    assert contains_embedded_solution_data("<script>const correctAnswers = {q1: '4'};</script>")
    assert contains_embedded_solution_data("<script>const quiz={correctAnswer: 2};</script>")
    assert not contains_embedded_solution_data("<script>const answers = {}; EduAIInteractive.complete({answers});</script>")


def test_interactive_view_has_teacher_answers_button_and_chat_back_link_contract():
    template = Path("templates/interactive.html").read_text(encoding="utf-8")
    js = Path("static/js/interactive.js").read_text(encoding="utf-8")
    assert 'id="interactive-answers"' in template
    assert "/answers`" in js or "/answers" in js
    assert "?chat=" in js
    assert "history.back()" not in js


def test_stereometry_prompt_requires_real_interaction_and_theory():
    from services.tutor_policy import INTERACTIVE_TASK_RULES
    prompt = INTERACTIVE_TASK_RULES.lower()
    assert "rotate" in prompt
    assert "theory" in prompt
    assert "mouse/touch" in prompt
    assert "dimension" in prompt
    assert "single giant static svg" in prompt


def test_stereometry_quality_helpers_detect_interactive_viewer():
    from services.interactive_apps import (
        _has_dimension_or_label_ui,
        _has_real_interaction,
        _has_theory_section,
    )
    html = """
    <section><h2>Теория и свойства куба</h2><canvas id='scene'></canvas>
    <label>Длина ребра <input type='range' min='1' max='10'></label></section>
    <script>scene.addEventListener('pointermove', () => {});</script>
    """
    assert _has_real_interaction(html)
    assert _has_theory_section(html)
    assert _has_dimension_or_label_ui(html)


def test_interactive_math_detection_covers_sum_integral_and_trig():
    assert interactive_html_has_math(r"<p>\sum_{k=1}^{n} k</p>")
    assert interactive_html_has_math(r"<p>\int_0^1 x^2 dx</p>")
    assert interactive_html_has_math(r"<p>\sin^2 x + \cos^2 x = 1</p>")


def test_universal_shell_is_used_for_generated_specs():
    from services.interactive_apps import InteractiveAppSpec, InteractiveSection, _render_spec
    spec = InteractiveAppSpec(
        title="Дроби",
        app_type="trainer",
        question_count=2,
        sections=[
            InteractiveSection(id="theory", label="Теория", html="<h2>Теория</h2><p>Доли целого</p>"),
            InteractiveSection(id="practice", label="Практика", html="<button id='go'>Начать</button>"),
        ],
        interaction_js="document.getElementById('go').addEventListener('click', () => {});",
    )
    rendered = _render_spec(spec).html_document
    assert 'data-eduai-shell="1"' in rendered
    assert rendered.count("data-eduai-panel=") == 2
    assert "@media" in rendered
    assert "Content-Security-Policy" in rendered


def test_create_detection_supports_full_interactive_apps_and_games():
    from services.interactive_apps import detect_create_request
    assert detect_create_request("Создай интерактивное приложение по стереометрии")
    assert detect_create_request("Сделай интерактивную игру по английским словам")
    assert detect_create_request("Create interactive simulation for fractions")


def test_flat_rotated_canvas_is_rejected_for_hexagonal_prism():
    from services.interactive_apps import InteractiveAppSpec, InteractiveSection, _render_spec, interactive_quality_issues

    spec = InteractiveAppSpec(
        title="Hexagonal Prism Exploration",
        app_type="interactive_model",
        question_count=0,
        sections=[
            InteractiveSection(
                id="theory",
                label="Theory",
                html="<h2>Theory</h2><p>Properties of a hexagonal prism.</p>",
            ),
            InteractiveSection(
                id="model",
                label="3D Model",
                html=(
                    "<p>Rotate the model and adjust its dimensions.</p>"
                    "<canvas id='hexPrismCanvas' width='400' height='400'></canvas>"
                    "<button id='reset'>Reset</button>"
                ),
            ),
        ],
        interaction_js="""
const canvas = document.getElementById('hexPrismCanvas');
const ctx = canvas.getContext('2d');
let angle = 0;
function drawHexPrism() {
  ctx.save();
  ctx.translate(canvas.width / 2, canvas.height / 2);
  ctx.rotate(angle);
  for (let i = 0; i < 6; i++) {
    const x = 50 * Math.cos((Math.PI / 3) * i);
    const y = 50 * Math.sin((Math.PI / 3) * i);
    ctx.lineTo(x, y);
    ctx.lineTo(x, y + 100);
  }
  ctx.restore();
}
canvas.addEventListener('mousemove', event => {
  angle = (event.offsetX / canvas.width) * 2 * Math.PI;
  drawHexPrism();
});
""",
    )
    html = _render_spec(spec).html_document
    issues = interactive_quality_issues(
        "Построить шестигранную призму для будущего исследования свойств веществ олово-сурьма",
        html,
    )
    assert any("flat 2D" in issue for issue in issues)
    assert any("drag start/move/end" in issue for issue in issues)
    assert any("adjustable dimension inputs" in issue for issue in issues)
    assert any("hexagonal prism geometry" in issue for issue in issues)


def test_trusted_hexagonal_prism_fallback_is_true_3d_and_passes_quality():
    from services.interactive_apps import (
        _has_3d_projection_logic,
        _has_adjustable_dimension_controls,
        _has_drag_rotation_controls,
        _has_hexagonal_prism_geometry,
        _inject_visual_safety_css,
        _stereometry_fallback_generation,
        inject_interactive_math_renderer,
        interactive_quality_issues,
        sanitize_interactive_html,
    )

    request = "Построить шестигранную призму для будущего исследования свойств веществ олово-сурьма"
    generated = _stereometry_fallback_generation(request)
    html = sanitize_interactive_html(generated.html_document)
    html = _inject_visual_safety_css(html)
    html = inject_interactive_math_renderer(html)

    assert _has_3d_projection_logic(html)
    assert _has_drag_rotation_controls(html)
    assert _has_adjustable_dimension_controls(html)
    assert _has_hexagonal_prism_geometry(html)
    assert "12" in html and "18" in html and "8" in html
    assert "олово–сурьма" in html
    assert interactive_quality_issues(request, html) == []


def test_interactive_prompt_rejects_fake_2d_3d_and_requires_exact_hex_prism_geometry():
    from services.tutor_policy import INTERACTIVE_TASK_RULES

    prompt = INTERACTIVE_TASK_RULES.lower()
    assert "flat 2d drawing" in prompt
    assert "ctx.rotate()" in prompt
    assert "12 vertices" in prompt
    assert "18 edges" in prompt
    assert "8 faces" in prompt
    assert "pointerdown" in prompt
    assert "pointerup/cancel" in prompt
