"""Канонические помощники для форматирования Markdown+LaTeX для клиентов EduAI.

База данных и API поддерживают канонический формат Markdown + LaTeX, чтобы клиенты WebApp могли корректно отображать математические формулы.  Исключение составляет Telegram: необработанный TeX ни в коем случае не должен отправляться пользователям.
Поэтому этот модуль преобразует формулы в читаемый текст в кодировке Unicode или в
отрендеренное изображение.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import List, Literal

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
    """Нормализовать пробелы в переносах, не нарушая Markdown или LaTeX."""
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()


@dataclass(frozen=True)
class TelegramPart:
    kind: Literal["text", "formula"]
    content: str
    display: bool = False


_MATH_COMMANDS = (
    "frac", "dfrac", "tfrac", "sqrt", "times", "cdot", "div", "pm", "mp",
    "le", "leq", "ge", "geq", "ne", "neq", "approx", "equiv", "sim", "simeq",
    "propto", "in", "notin", "ni", "subset", "subseteq", "supset", "supseteq",
    "cap", "cup", "setminus", "emptyset", "forall", "exists", "nabla", "partial",
    "sum", "prod", "int", "iint", "iiint", "oint", "lim", "min", "max",
    "sin", "cos", "tan", "tg", "cot", "ctg", "log", "ln", "lg", "exp",
    "pi", "infty", "alpha", "beta", "gamma", "delta", "epsilon", "varepsilon",
    "zeta", "eta", "theta", "vartheta", "iota", "kappa", "lambda", "mu", "nu",
    "xi", "rho", "sigma", "tau", "upsilon", "phi", "varphi", "chi", "psi", "omega",
    "Gamma", "Delta", "Theta", "Lambda", "Xi", "Pi", "Sigma", "Phi", "Psi", "Omega",
    "quad", "qquad", "Rightarrow", "Leftarrow", "Leftrightarrow", "rightarrow",
    "leftarrow", "to", "mapsto", "implies", "iff", "text", "textrm", "mathrm",
    "mathbf", "mathit", "mathsf", "mathtt", "operatorname", "begin", "end", "left",
    "right", "overline", "underline", "vec", "hat", "bar", "dot", "ddot", "boxed",
    "ldots", "cdots", "vdots", "ddots",
)
_MATH_COMMAND_PATTERN = "|".join(sorted((re.escape(x) for x in _MATH_COMMANDS), key=len, reverse=True))

_DISPLAY_RE = re.compile(r"\\\[(.+?)\\\]|\$\$(.+?)\$\$", re.S)
_INLINE_RE = re.compile(r"\\\((.+?)\\\)|(?<!\$)\$([^$\n]{1,2000})\$(?!\$)", re.S)
_DOUBLE_ESCAPED_MATH_RE = re.compile(rf"\\\\(?=(?:\[|\]|\(|\)|(?:{_MATH_COMMAND_PATTERN})(?![A-Za-z])))")
_BARE_LATEX_RE = re.compile(rf"\\(?:{_MATH_COMMAND_PATTERN})(?![A-Za-z])")
_RAW_LATEX_RE = re.compile(rf"(?:\\){{1,2}}(?:{_MATH_COMMAND_PATTERN})(?![A-Za-z])|(?:\\){{1,2}}[\[\]()]|(?:\\){{1,2}}[,;:!]|(?:\\){{1,2}}[A-Za-z]+\*?(?=\s*(?:\{{|_|\^))", re.S)


def contains_raw_latex(value: object) -> bool:
    """Return True when user-facing text still contains recognized TeX."""
    return bool(_RAW_LATEX_RE.search(canonicalize_message(value)))


def normalize_latex_transport(value: object) -> str:
    """Collapse one accidental transport-escape layer for math tokens only."""
    return _DOUBLE_ESCAPED_MATH_RE.sub(r"\\", canonicalize_message(value))


def _replace_nested_frac(text: str) -> str:
    pattern = re.compile(r"\\(?:dfrac|tfrac|frac)\{([^{}]*)\}\{([^{}]*)\}")
    previous = None
    while previous != text:
        previous = text
        text = pattern.sub(r"(\1)/(\2)", text)
    return text


_SUPERSCRIPT = str.maketrans("0123456789+-=()n", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿ")
_SUBSCRIPT = str.maketrans("0123456789+-=()aeoxhklmnpst", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₒₓₕₖₗₘₙₚₛₜ")


def _simple_scripts(text: str) -> str:
    def sup(match: re.Match[str]) -> str:
        value = match.group(1)
        mapped = value.translate(_SUPERSCRIPT)
        return mapped if len(mapped) == len(value) else "^" + value

    def sub(match: re.Match[str]) -> str:
        value = match.group(1)
        mapped = value.translate(_SUBSCRIPT)
        return mapped if len(mapped) == len(value) else "_" + value

    text = re.sub(r"\^\{([0-9+\-=()n]+)\}", sup, text)
    text = re.sub(r"_\{([0-9+\-=()aeoxhklmnpst]+)\}", sub, text)
    text = re.sub(r"\^([0-9])", lambda m: m.group(1).translate(_SUPERSCRIPT), text)
    text = re.sub(r"_([0-9])", lambda m: m.group(1).translate(_SUBSCRIPT), text)
    return text


def _latex_fallback(expr: str) -> str:
    """Convert TeX to readable Unicode/plain text without exposing commands."""
    text = normalize_latex_transport(expr).strip()
    text = text.replace(r"\[", "").replace(r"\]", "").replace(r"\(", "").replace(r"\)", "")
    text = _replace_nested_frac(text)
    text = re.sub(r"\\sqrt\[([^]]+)\]\{([^{}]+)\}", r"root[\1](\2)", text)
    text = re.sub(r"\\sqrt\{([^{}]+)\}", r"√(\1)", text)

    # Text/style wrappers keep their content.
    wrapper = r"(?:text|textrm|mathrm|mathbf|mathit|mathsf|mathtt|operatorname|overline|underline|vec|hat|bar|boxed)"
    previous = None
    while previous != text:
        previous = text
        text = re.sub(rf"\\{wrapper}\s*\{{([^{{}}]*)\}}", r"\1", text)

    replacements = {
        r"\times": "×", r"\cdot": "·", r"\div": ":", r"\pm": "±", r"\mp": "∓",
        r"\le": "≤", r"\leq": "≤", r"\ge": "≥", r"\geq": "≥", r"\ne": "≠", r"\neq": "≠",
        r"\approx": "≈", r"\equiv": "≡", r"\sim": "∼", r"\simeq": "≃", r"\propto": "∝",
        r"\in": "∈", r"\notin": "∉", r"\ni": "∋", r"\subset": "⊂", r"\subseteq": "⊆",
        r"\supset": "⊃", r"\supseteq": "⊇", r"\cap": "∩", r"\cup": "∪", r"\setminus": "∖",
        r"\emptyset": "∅", r"\forall": "∀", r"\exists": "∃", r"\nabla": "∇", r"\partial": "∂",
        r"\sum": "∑", r"\prod": "∏", r"\int": "∫", r"\iint": "∬", r"\iiint": "∭", r"\oint": "∮",
        r"\Rightarrow": "⇒", r"\Leftarrow": "⇐", r"\Leftrightarrow": "⇔", r"\rightarrow": "→",
        r"\leftarrow": "←", r"\to": "→", r"\mapsto": "↦", r"\implies": "⇒", r"\iff": "⇔",
        r"\pi": "π", r"\infty": "∞", r"\alpha": "α", r"\beta": "β", r"\gamma": "γ", r"\delta": "δ",
        r"\epsilon": "ε", r"\varepsilon": "ϵ", r"\zeta": "ζ", r"\eta": "η", r"\theta": "θ",
        r"\vartheta": "ϑ", r"\iota": "ι", r"\kappa": "κ", r"\lambda": "λ", r"\mu": "μ", r"\nu": "ν",
        r"\xi": "ξ", r"\rho": "ρ", r"\sigma": "σ", r"\tau": "τ", r"\upsilon": "υ", r"\phi": "φ",
        r"\varphi": "ϕ", r"\chi": "χ", r"\psi": "ψ", r"\omega": "ω", r"\Gamma": "Γ", r"\Delta": "Δ",
        r"\Theta": "Θ", r"\Lambda": "Λ", r"\Xi": "Ξ", r"\Pi": "Π", r"\Sigma": "Σ", r"\Phi": "Φ",
        r"\Psi": "Ψ", r"\Omega": "Ω", r"\ldots": "…", r"\cdots": "⋯", r"\vdots": "⋮", r"\ddots": "⋱",
        r"\qquad": "  ", r"\quad": " ",
    }
    for source in sorted(replacements, key=len, reverse=True):
        text = text.replace(source, replacements[source])

    text = re.sub(r"\\(sin|cos|tan|tg|cot|ctg|log|ln|lg|exp|lim|min|max)\b", r"\1", text)
    text = text.replace(r"\\", "\n")
    text = re.sub(r"\\begin\{(?:cases|aligned|align\*?|matrix|pmatrix|bmatrix|vmatrix)\}|\\end\{(?:cases|aligned|align\*?|matrix|pmatrix|bmatrix|vmatrix)\}", "", text)
    text = re.sub(r"\\(?:left|right)\b", "", text)
    text = re.sub(r"\\[,;:]", " ", text)
    text = text.replace(r"\!", "")
    text = _simple_scripts(text)

    text = re.sub(r"\\[A-Za-z]+\*?", "", text)
    text = text.replace("{", "").replace("}", "")
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def is_complex_formula(expr: str) -> bool:
    value = normalize_latex_transport(expr).strip()
    return bool(
        len(value) > 36
        or re.search(r"\\(?:frac|dfrac|tfrac|begin|sum|prod|int|iint|iiint|lim)\b", value)
        or r"\sqrt[" in value
        or value.count("^") >= 2
    )


def _looks_like_bare_formula(line: str) -> bool:
    value = line.strip()
    if not _BARE_LATEX_RE.search(value):
        return False
    if value.startswith(("http://", "https://")):
        return False
    return True


def telegram_parts(value: object) -> List[TelegramPart]:
    """Split canonical content while preserving ordinary code/URLs."""
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
        expr = (match.group(1) or match.group(2) or "").strip()
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
    for line in text.splitlines(keepends=True):
        stripped = line.rstrip("\r\n")
        suffix = line[len(stripped):]
        if _looks_like_bare_formula(stripped):
            result.append(TelegramPart("text", _latex_fallback(stripped) + suffix))
        else:
            result.append(TelegramPart("text", stripped + suffix))
    return result


def telegram_formula_fallback(expr: str) -> str:
    return _latex_fallback(expr)


def telegram_safe_text(value: object) -> str:
    """Финальный текстовый файрвол Telegram: распознанный необработанный TeX никогда не доходит до пользователей."""
    work = canonicalize_message(value)
    if contains_raw_latex(work):
        work = "\n".join(
            _latex_fallback(line) if contains_raw_latex(line) else line
            for line in work.splitlines()
        )
        work = _RAW_LATEX_RE.sub("", work)
    return work.strip()


def render_formula_png(expr: str) -> bytes | None:
    """Рендерер PNG, работающий по принципу «сделаем всё возможное». Возвращает None, если matplotlib/mathtext не может выполнить рендеринг."""
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
