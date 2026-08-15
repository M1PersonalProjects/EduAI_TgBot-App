"""Canonical Markdown+LaTeX formatting helpers for EduAI clients."""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import List, Literal

# IMPORTANT: this is a raw Python string, therefore LaTeX commands below use
# ONE backslash. Writing ``\\frac`` here would literally instruct the model to
# emit two backslashes and would leak transport escaping into the UI.
MATH_FORMATTING_RULES = r"""
MATHEMATICAL OUTPUT RULES
- Keep educational responses in Markdown with valid canonical LaTeX for mathematical notation.
- Use exactly one LaTeX backslash for commands and delimiters. Never double-escape LaTeX for display.
- Use \( ... \) for inline mathematics and \[ ... \] for display mathematics.
- Write fractions as \frac{numerator}{denominator}.
- Use \sqrt{x} for roots, ^ for powers, and _ for subscripts inside math delimiters.
- Keep normal explanatory prose outside mathematical delimiters.
- Never output malformed or partially escaped LaTeX.
- In Russian-language school arithmetic, write division as ':' in human-readable text, for example 12 : 4 = 3.
- Never replace or reinterpret slashes inside URLs, file paths, dates, identifiers, API routes, inline code, or fenced code blocks.
- Preserve programming code exactly as code. A slash used as a programming operator must remain '/'.
- The client is responsible for rendering canonical LaTeX; do not expose explanations of LaTeX syntax unless the user explicitly asks for LaTeX source code.
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
_DOUBLE_ESCAPED_MATH_RE = re.compile(
    r"\\\\(?=(?:\[|\]|\(|\)|frac\b|dfrac\b|tfrac\b|sqrt\b|times\b|cdot\b|div\b|pm\b|mp\b|"
    r"le\b|leq\b|ge\b|geq\b|ne\b|neq\b|approx\b|equiv\b|pi\b|infty\b|quad\b|qquad\b|"
    r"Rightarrow\b|Leftarrow\b|Leftrightarrow\b|rightarrow\b|leftarrow\b|text\b|mathrm\b|mathbf\b|"
    r"begin\b|end\b|left\b|right\b))"
)
_BARE_LATEX_RE = re.compile(
    r"\\(?:frac|dfrac|tfrac|sqrt|times|cdot|div|pm|mp|le|leq|ge|geq|ne|neq|approx|equiv|pi|infty|"
    r"quad|qquad|Rightarrow|Leftarrow|Leftrightarrow|rightarrow|leftarrow|text|mathrm|mathbf|begin|end|left|right)\b"
)
_RAW_LATEX_RE = re.compile(
    r"(?:\\){1,2}(?:frac|dfrac|tfrac|sqrt|times|cdot|div|pm|mp|le|leq|ge|geq|ne|neq|approx|equiv|pi|infty|"
    r"quad|qquad|Rightarrow|Leftarrow|Leftrightarrow|rightarrow|leftarrow|text|mathrm|mathbf|begin|end|left|right)\b"
    r"|(?:\\){1,2}[\[\]()]"
)


def contains_raw_latex(value: object) -> bool:
    """Return True when user-facing text still contains raw TeX commands or delimiters.

    Both canonical one-backslash LaTeX and accidentally transport-double-escaped
    legacy content are detected. Code preservation is handled by telegram_parts().
    """
    return bool(_RAW_LATEX_RE.search(canonicalize_message(value)))


def normalize_latex_transport(value: object) -> str:
    """Collapse one accidental transport-escape layer for known math tokens only."""
    return _DOUBLE_ESCAPED_MATH_RE.sub(r"\\", canonicalize_message(value))


def _replace_nested_frac(text: str) -> str:
    pattern = re.compile(r"\\frac\{([^{}]*)\}\{([^{}]*)\}")
    previous = None
    while previous != text:
        previous = text
        text = pattern.sub(r"(\1)/(\2)", text)
    return text


def _latex_fallback(expr: str) -> str:
    text = normalize_latex_transport(expr).strip()
    text = text.replace(r"\[", "").replace(r"\]", "").replace(r"\(", "").replace(r"\)", "")
    text = _replace_nested_frac(text)
    text = re.sub(r"\\sqrt\[([^]]+)\]\{([^{}]+)\}", r"root[\1](\2)", text)
    text = re.sub(r"\\sqrt\{([^{}]+)\}", r"√(\1)", text)
    text = re.sub(r"\\text\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\(?:mathrm|mathbf)\{([^{}]*)\}", r"\1", text)
    replacements = {
        r"\times": "×", r"\cdot": "·", r"\div": ":", r"\pm": "±", r"\mp": "∓",
        r"\le": "≤", r"\leq": "≤", r"\ge": "≥", r"\geq": "≥",
        r"\ne": "≠", r"\neq": "≠", r"\approx": "≈", r"\equiv": "≡",
        r"\Rightarrow": "⇒", r"\Leftarrow": "⇐", r"\Leftrightarrow": "⇔",
        r"\rightarrow": "→", r"\leftarrow": "←", r"\pi": "π", r"\infty": "∞",
        r"\qquad": "  ", r"\quad": " ",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    text = text.replace(r"\\", "\n")
    text = re.sub(r"\\begin\{cases\}|\\end\{cases\}", "", text)
    text = re.sub(r"\\(?:left|right)\b", "", text)
    # Last-resort safety: a Telegram user must never see a raw TeX command.
    text = re.sub(r"\\[A-Za-z]+\*?", "", text)
    text = text.replace("{", "").replace("}", "")
    return text.strip()


def is_complex_formula(expr: str) -> bool:
    value = normalize_latex_transport(expr).strip()
    return bool(
        len(value) > 36
        or r"\frac" in value
        or r"\begin{" in value
        or r"\sqrt[" in value
        or r"\matrix" in value
        or value.count("^") >= 2
    )


def _looks_like_bare_formula(line: str) -> bool:
    value = line.strip()
    if not _BARE_LATEX_RE.search(value):
        return False
    if value.startswith(("http://", "https://")):
        return False
    return bool(re.search(r"[=+\-*/^_<>]", value) or value.startswith("\\"))


def telegram_parts(value: object) -> List[TelegramPart]:
    """Split canonical content while preserving fenced/inline code verbatim."""
    text = canonicalize_message(value)
    parts: List[TelegramPart] = []
    code_re = re.compile(r"```[\s\S]*?```|`[^`\n]*`")
    cursor = 0
    for match in code_re.finditer(text):
        if match.start() > cursor:
            parts.extend(_math_parts_segment(normalize_latex_transport(text[cursor:match.start()])))
        parts.append(TelegramPart("text", match.group(0)))
        cursor = match.end()
    if cursor < len(text):
        parts.extend(_math_parts_segment(normalize_latex_transport(text[cursor:])))
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
            result.extend(_bare_parts(text[cursor:match.start()]))
        expr = match.group(1).strip()
        if is_complex_formula(expr):
            result.append(TelegramPart("formula", expr, False))
        else:
            result.append(TelegramPart("text", _latex_fallback(expr)))
        cursor = match.end()
    if cursor < len(text):
        result.extend(_bare_parts(text[cursor:]))
    return result


def _bare_parts(text: str) -> List[TelegramPart]:
    result: List[TelegramPart] = []
    lines = text.splitlines(keepends=True)
    for line in lines:
        stripped = line.rstrip("\r\n")
        suffix = line[len(stripped):]
        if _looks_like_bare_formula(stripped):
            if is_complex_formula(stripped):
                result.append(TelegramPart("formula", stripped.strip(), True))
            else:
                result.append(TelegramPart("text", _latex_fallback(stripped) + suffix))
        else:
            result.append(TelegramPart("text", stripped + suffix))
    return result


def telegram_formula_fallback(expr: str) -> str:
    return _latex_fallback(expr)



def telegram_safe_text(value: object) -> str:
    """Final Telegram text firewall: never expose recognized raw TeX commands."""
    work = canonicalize_message(value)
    if contains_raw_latex(work):
        # Product requirement: no raw LaTeX may reach Telegram, including old
        # stored messages or TeX accidentally wrapped in code spans. Only known
        # math tokens are transformed; unrelated programming backslashes remain.
        work = "\n".join(
            _latex_fallback(line) if contains_raw_latex(line) else line
            for line in work.splitlines()
        )
        # _latex_fallback is the human-readable conversion. This final pass only
        # removes any still-recognized TeX token; it does not touch ordinary \n,
        # Windows paths, regex escapes, or programming backslashes.
        work = _RAW_LATEX_RE.sub("", work)
    return work.strip()

def render_formula_png(expr: str) -> bytes | None:
    """Best-effort PNG renderer. Returns None when matplotlib/mathtext cannot render."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        from matplotlib import pyplot as plt
        fig = plt.figure(figsize=(0.01, 0.01), dpi=180)
        fig.patch.set_alpha(0)
        source = normalize_latex_transport(expr)
        text = fig.text(0.02, 0.5, f"${source.strip()}$", fontsize=18, va="center")
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
