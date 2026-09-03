import pytest

from services.core.response_formatter import contains_raw_latex, format_for_telegram, telegram_safe_text


@pytest.mark.parametrize(
    "source",
    [
        r"Ответ: \\frac{1}{3}",
        r"Корень: \\sqrt{16} = 4",
        r"2 \\times 3 = 6",
        r"\\[ x^2 + 2x + 1 \\]",
        r"\\text{Ответ}: \\frac{1}{\\frac{2}{3}}",
        r"Система: \\begin{cases}x+y=3\\\\x-y=1\\end{cases}",
        r"Сумма: \\sum_{k=1}^{n} k",
        r"Интеграл: \\int_0^1 x^2 \\, dx",
        r"Тригонометрия: \\sin^2 x + \\cos^2 x = 1",
        r"Греческие буквы: \\alpha + \\beta = \\gamma",
    ],
)
def test_telegram_firewall_never_returns_raw_latex(source):
    rendered = telegram_safe_text(source)
    assert rendered.strip()
    assert not contains_raw_latex(rendered), rendered
    for command in (r"\\frac", r"\\sqrt", r"\\times", r"\\text", r"\\begin", r"\\end", r"\\sum", r"\\int", r"\\sin", r"\\alpha"):
        assert command not in rendered


def test_simple_arithmetic_stays_readable_text():
    assert telegram_safe_text("12 : 4 = 3") == "12 : 4 = 3"


def test_raw_latex_inside_code_span_is_still_blocked_for_telegram():
    rendered = telegram_safe_text(r"`\\frac{2}{5}`")
    assert not contains_raw_latex(rendered)
    assert r"\\frac" not in rendered


def test_programming_backslashes_are_not_removed_when_there_is_no_tex():
    source = r"C:\\Users\\student\\project and regex \\d+"
    assert telegram_safe_text(source) == source


def test_telegram_formatter_removes_markdown_controls_but_keeps_urls_and_code():
    source = "# Заголовок\n**Важно**: 12 / 3. https://example.com/a/b?q=x*y `a / b * c`"
    rendered = format_for_telegram(source)
    assert rendered.startswith("Заголовок\nВажно")
    assert "12 : 3" in rendered
    assert "https://example.com/a/b?q=x*y" in rendered
    assert "`a / b * c`" in rendered
    assert "**" not in rendered


def test_telegram_formatter_preserves_windows_path_next_to_latex():
    source = r"Путь C:\Users\student\project\main.py и корень \sqrt{9}"
    rendered = format_for_telegram(source)
    assert r"C:\Users\student\project\main.py" in rendered
    assert "√(9)" in rendered
    assert not contains_raw_latex(rendered)
