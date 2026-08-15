import pytest

from services.response_formatter import contains_raw_latex, telegram_safe_text


@pytest.mark.parametrize(
    "source",
    [
        r"Ответ: \\frac{1}{3}",
        r"Корень: \\sqrt{16} = 4",
        r"2 \\times 3 = 6",
        r"\\[ x^2 + 2x + 1 \\]",
        r"\\text{Ответ}: \\frac{1}{\\frac{2}{3}}",
        r"Система: \\begin{cases}x+y=3\\\\x-y=1\\end{cases}",
    ],
)
def test_telegram_firewall_never_returns_raw_latex(source):
    rendered = telegram_safe_text(source)
    assert rendered.strip()
    assert not contains_raw_latex(rendered), rendered
    for command in (r"\\frac", r"\\sqrt", r"\\times", r"\\text", r"\\begin", r"\\end"):
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
