from services.response_formatter import (
    MATH_FORMATTING_RULES,
    normalize_latex_transport,
    telegram_formula_fallback,
    telegram_parts,
)


def test_prompt_uses_single_latex_backslashes():
    assert r"\\frac" not in MATH_FORMATTING_RULES
    assert r"\frac" in MATH_FORMATTING_RULES
    assert r"\\[" not in MATH_FORMATTING_RULES
    assert r"\[" in MATH_FORMATTING_RULES


def test_double_escaped_transport_is_normalized():
    source = r"\\[ x + 1 = 14k \\quad \\Rightarrow \\quad x = 14k - 1 \\]"
    normalized = normalize_latex_transport(source)
    assert normalized.startswith(r"\[")
    assert r"\quad" in normalized
    assert r"\Rightarrow" in normalized
    assert r"\\quad" not in normalized


def test_telegram_never_leaks_raw_commands_from_double_escaped_math():
    source = r"\\[ v_1 = \\frac{d}{30} \\quad \\Rightarrow \\quad v_2 = \\sqrt{25} \\]"
    parts = telegram_parts(source)
    assert parts
    raw_text = "".join(part.content for part in parts if part.kind == "text")
    assert r"\\[" not in raw_text
    assert r"\\frac" not in raw_text
    assert r"\\quad" not in raw_text


def test_fallback_strips_raw_latex_commands():
    fallback = telegram_formula_fallback(r"v_1 = \frac{d}{30} \quad \Rightarrow \quad x = \sqrt{25}")
    for command in (r"\frac", r"\quad", r"\Rightarrow", r"\sqrt"):
        assert command not in fallback
    assert "⇒" in fallback
    assert "√(25)" in fallback


def test_code_and_url_are_not_math():
    parts = telegram_parts("URL https://example.com/a/b\n`x = a / b`")
    joined = "".join(part.content for part in parts)
    assert "https://example.com/a/b" in joined
    assert "`x = a / b`" in joined
