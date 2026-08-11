"""Canonical Markdown+LaTeX formatting helpers for EduAI clients."""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import List, Literal

MATH_FORMATTING_RULES = r"""
MATHEMATICAL FORMATTING RULES
- Keep the response in Markdown with canonical LaTeX for mathematical notation.
- Use \\( ... \\) for inline mathematics and \\[ ... \\] for display mathematics.
- Write mathematical fractions as \\frac{numerator}{denominator}; do not use a plain slash for fractions.
- In Russian-language school arithmetic, write division as ':' in human-readable equations, for example 12 : 4 = 3.
- Never replace slashes inside URLs, file paths, dates, identifiers, API routes, inline code, or fenced code blocks.
- Use consistent LaTeX for powers, roots, equations, inequalities, subscripts, systems, percentages, multiplication, functions, geometry, physics, and chemistry formulas when appropriate.
- Do not wrap ordinary arithmetic such as 5 + 3 = 8 in an image-specific format; keep simple mathematics readable inline.
- Preserve programming code exactly as code. A slash used as a programming operator must remain '/'.
""".strip()


def canonicalize_message(value: object) -> str:
    """Normalize transport whitespace without destroying Markdown or LaTeX."""
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()


@dataclass(frozen=True)
class TelegramPart:
    kind: Literal["text", "formula"]
    content: str
    display: bool = False


_DISPLAY_RE = re.compile(r"\\\[(.+?)\\\]|\$\$(.+?)\$\$", re.S)
_INLINE_RE = re.compile(r"\\\((.+?)\\\)", re.S)


def _latex_fallback(expr: str) -> str:
    text = expr.strip()
    # Local conversion only inside explicit math delimiters.
    previous = None
    while previous != text:
        previous = text
        text = re.sub(r"\\frac\{([^{}]+)\}\{([^{}]+)\}", r"(\1)/(\2)", text)
    text = re.sub(r"\\sqrt\[([^]]+)\]\{([^{}]+)\}", r"root[\1](\2)", text)
    text = re.sub(r"\\sqrt\{([^{}]+)\}", r"√(\1)", text)
    replacements = {
        r"\\times": "×", r"\\cdot": "·", r"\\div": ":", r"\\pm": "±",
        r"\\le": "≤", r"\\leq": "≤", r"\\ge": "≥", r"\\geq": "≥",
        r"\\ne": "≠", r"\\neq": "≠", r"\\pi": "π", r"\\infty": "∞",
    }
    for source, target in replacements.items():
        text = re.sub(source + r"\b", target, text)
    text = text.replace(r"\\", "\n")
    text = re.sub(r"\\begin\{cases\}|\\end\{cases\}", "", text)
    text = re.sub(r"\\(?:left|right)", "", text)
    text = re.sub(r"\{([^{}]+)\}", r"\1", text)
    return text.strip()


def is_complex_formula(expr: str) -> bool:
    value = expr.strip()
    return bool(
        len(value) > 36
        or r"\frac" in value
        or r"\begin{" in value
        or r"\sqrt[" in value
        or r"\matrix" in value
        or value.count("^") >= 2
    )


def telegram_parts(value: object) -> List[TelegramPart]:
    """Split canonical content while preserving fenced/inline code verbatim."""
    text = canonicalize_message(value)
    parts: List[TelegramPart] = []
    code_re = re.compile(r"```[\s\S]*?```|`[^`\n]*`")
    cursor = 0
    for match in code_re.finditer(text):
        if match.start() > cursor:
            parts.extend(_math_parts_segment(text[cursor:match.start()]))
        parts.append(TelegramPart("text", match.group(0)))
        cursor = match.end()
    if cursor < len(text):
        parts.extend(_math_parts_segment(text[cursor:]))
    return [part for part in parts if part.content]


def _math_parts_segment(text: str) -> List[TelegramPart]:
    parts: List[TelegramPart] = []
    cursor = 0
    for match in _DISPLAY_RE.finditer(text):
        if match.start() > cursor:
            parts.extend(_inline_parts(text[cursor:match.start()]))
        expr = match.group(1) or match.group(2) or ""
        parts.append(TelegramPart("formula", expr.strip(), True))
        cursor = match.end()
    if cursor < len(text):
        parts.extend(_inline_parts(text[cursor:]))
    return parts

def _inline_parts(text: str) -> List[TelegramPart]:
    result: List[TelegramPart] = []
    cursor = 0
    for match in _INLINE_RE.finditer(text):
        if match.start() > cursor:
            result.append(TelegramPart("text", text[cursor:match.start()]))
        expr = match.group(1).strip()
        if is_complex_formula(expr):
            result.append(TelegramPart("formula", expr, False))
        else:
            result.append(TelegramPart("text", _latex_fallback(expr)))
        cursor = match.end()
    if cursor < len(text):
        result.append(TelegramPart("text", text[cursor:]))
    return result


def telegram_formula_fallback(expr: str) -> str:
    return _latex_fallback(expr)


def render_formula_png(expr: str) -> bytes | None:
    """Best-effort PNG renderer. Returns None when matplotlib/mathtext cannot render."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        from matplotlib import pyplot as plt

        fig = plt.figure(figsize=(0.01, 0.01), dpi=180)
        fig.patch.set_alpha(0)
        text = fig.text(0.02, 0.5, f"${expr.strip()}$", fontsize=18, va="center")
        fig.canvas.draw()
        bbox = text.get_window_extent(renderer=fig.canvas.get_renderer()).expanded(1.08, 1.35)
        width, height = bbox.width / fig.dpi, bbox.height / fig.dpi
        fig.set_size_inches(max(width, 0.4), max(height, 0.35))
        text.set_position((0.02, 0.5))
        buffer = io.BytesIO()
        fig.savefig(buffer, format="png", transparent=True, bbox_inches="tight", pad_inches=0.08)
        plt.close(fig)
        return buffer.getvalue()
    except Exception:
        return None
