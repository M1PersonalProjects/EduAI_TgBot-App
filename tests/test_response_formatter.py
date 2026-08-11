from services.response_formatter import canonicalize_message, telegram_parts, telegram_formula_fallback


def test_canonical_latex_is_preserved():
    source = r"Дробь: \(\frac{1}{3}\)"
    assert canonicalize_message(source) == source


def test_url_and_code_slashes_are_not_replaced():
    source = "https://example.com/a/b\n`result = a / b`\n12 : 4 = 3"
    joined = "".join(part.content for part in telegram_parts(source))
    assert "https://example.com/a/b" in joined
    assert "result = a / b" in joined
    assert "12 : 4 = 3" in joined


def test_simple_inline_math_stays_text():
    parts = telegram_parts(r"Ответ: \(5 + 3 = 8\)")
    assert all(part.kind == "text" for part in parts)


def test_complex_fraction_is_formula_part():
    parts = telegram_parts(r"Считаем: \(\frac{x+2}{x-1}\).")
    assert any(part.kind == "formula" for part in parts)


def test_formula_fallback_is_readable():
    assert telegram_formula_fallback(r"\frac{x+2}{x-1}") == "(x+2)/(x-1)"

def test_math_markers_inside_code_are_not_rendered():
    source = r"```python\nformula = r'\\(\\frac{1}{2}\\)'\n```"
    parts = telegram_parts(source)
    assert len(parts) == 1
    assert parts[0].kind == "text"
    assert r"\\frac{1}{2}" in parts[0].content
