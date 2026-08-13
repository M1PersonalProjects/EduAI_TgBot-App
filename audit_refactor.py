#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Iterable

ROOT = Path.cwd()
REPORT_DIR = ROOT / "refactor_audit"
REPORT_DIR.mkdir(exist_ok=True)

SKIP_DIRS = {
    ".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "node_modules", ".venv", "venv", "refactor_audit", ".idea",
}
TEXT_SUFFIXES = {
    ".py", ".js", ".html", ".css", ".md", ".txt", ".toml", ".ini", ".cfg",
    ".yml", ".yaml", ".json", ".sql", ".env", ".example",
}
MARKERS = ("TODO", "FIXME", "HACK", "TEMP", "DEBUG", "OLD", "LEGACY")
SECRET_PATTERNS = {
    "openai_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "telegram_token": re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{25,}\b"),
    "jwt_like_secret": re.compile(
        r"(?i)\b(?:jwt_secret|secret_key|database_password|db_password)\s*[:=]\s*['\"]([^'\"]{12,})"
    ),
}
ROUTE_RE = re.compile(
    r"@(?:router|app)\.(get|post|put|patch|delete)\(\s*[rubf]*[\"']([^\"']+)"
)

def git_files() -> list[str]:
    try:
        out = subprocess.check_output(
            ["git", "ls-files"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        )
        return [line.strip() for line in out.splitlines() if line.strip()]
    except Exception:
        return []

TRACKED = set(git_files())

def iter_files() -> Iterable[Path]:
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path

def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()

def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""

python_files = [p for p in iter_files() if p.suffix == ".py"]
js_files = [p for p in iter_files() if p.suffix == ".js"]
all_text_files = [
    p for p in iter_files()
    if p.suffix.lower() in TEXT_SUFFIXES or p.name.startswith(".env")
]

# ------------------------------------------------------------------
# Python import / symbol audit
# ------------------------------------------------------------------
imports_by_file: dict[str, list[str]] = {}
definitions: dict[str, list[dict]] = defaultdict(list)
syntax_errors: list[dict] = []

for path in python_files:
    name = rel(path)
    text = read_text(path)
    try:
        tree = ast.parse(text, filename=name)
    except SyntaxError as exc:
        syntax_errors.append({
            "file": name, "line": exc.lineno, "message": exc.msg
        })
        continue

    found_imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found_imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            found_imports.append(module)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            definitions[node.name].append({
                "file": name,
                "line": node.lineno,
                "kind": (
                    "class" if isinstance(node, ast.ClassDef)
                    else "async_function" if isinstance(node, ast.AsyncFunctionDef)
                    else "function"
                ),
            })
    imports_by_file[name] = sorted(set(filter(None, found_imports)))

# References are intentionally conservative textual counts.
reference_counts: dict[str, int] = defaultdict(int)
for path in all_text_files:
    text = read_text(path)
    if not text:
        continue
    for symbol in definitions:
        reference_counts[symbol] += len(re.findall(rf"\b{re.escape(symbol)}\b", text))

possibly_unused_symbols = []
for symbol, defs in definitions.items():
    # definition itself counts once; multiple definitions make the threshold higher.
    if reference_counts[symbol] <= len(defs):
        for item in defs:
            if not symbol.startswith("_"):
                possibly_unused_symbols.append({"symbol": symbol, **item})

# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------
routes = []
for path in python_files:
    text = read_text(path)
    for method, route in ROUTE_RE.findall(text):
        routes.append({"file": rel(path), "method": method.upper(), "path": route})

route_groups: dict[str, list[dict]] = defaultdict(list)
for item in routes:
    route_groups[item["path"]].append(item)
duplicate_routes = [
    {"path": key, "definitions": items}
    for key, items in route_groups.items()
    if len(items) > 1
]

# ------------------------------------------------------------------
# Debug / legacy markers
# ------------------------------------------------------------------
markers = []
for path in all_text_files:
    text = read_text(path)
    for lineno, line in enumerate(text.splitlines(), 1):
        upper = line.upper()
        hits = [marker for marker in MARKERS if marker in upper]
        if hits:
            markers.append({
                "file": rel(path), "line": lineno,
                "markers": hits, "text": line.strip()[:240]
            })

print_calls = []
for path in python_files:
    text = read_text(path)
    for lineno, line in enumerate(text.splitlines(), 1):
        if re.search(r"(?<![\w.])print\s*\(", line):
            print_calls.append({"file": rel(path), "line": lineno, "text": line.strip()})

console_logs = []
for path in js_files:
    for lineno, line in enumerate(read_text(path).splitlines(), 1):
        if "console.log(" in line or "console.debug(" in line:
            console_logs.append({"file": rel(path), "line": lineno, "text": line.strip()})

# ------------------------------------------------------------------
# Repository junk candidates
# ------------------------------------------------------------------
junk_patterns = (
    re.compile(r"(^|/)\.DS_Store$"),
    re.compile(r"(^|/)\.idea(/|$)"),
    re.compile(r"(^|/)(?:venv|\.venv)(/|$)"),
    re.compile(r"(?i)(?:_old|_backup|_copy|_test2|final2|new_utils)(?:\.|$)"),
)
junk_candidates = []
candidate_names = TRACKED or {rel(p) for p in iter_files()}
for name in sorted(candidate_names):
    if any(pattern.search(name) for pattern in junk_patterns):
        junk_candidates.append({
            "path": name,
            "tracked": name in TRACKED,
            "reason": "repository/generated/legacy-name candidate",
        })

# ------------------------------------------------------------------
# Secrets
# ------------------------------------------------------------------
secret_hits = []
for path in all_text_files:
    name = rel(path)
    # Local .env can contain real secrets; report but never echo the value.
    text = read_text(path)
    for kind, pattern in SECRET_PATTERNS.items():
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            secret_hits.append({
                "file": name,
                "line": line,
                "kind": kind,
                "tracked": name in TRACKED,
            })

# ------------------------------------------------------------------
# Dependencies vs imports (advisory only)
# ------------------------------------------------------------------
requirements = []
requirements_path = ROOT / "requirements.txt"
if requirements_path.exists():
    for line in read_text(requirements_path).splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            requirements.append(stripped)

top_level_imports = sorted({
    module.split(".")[0]
    for modules in imports_by_file.values()
    for module in modules
    if module
})

# ------------------------------------------------------------------
# File/module duplicate names
# ------------------------------------------------------------------
basename_groups: dict[str, list[str]] = defaultdict(list)
for path in iter_files():
    basename_groups[path.name].append(rel(path))
duplicate_basenames = {
    key: values for key, values in basename_groups.items() if len(values) > 1
}

summary = {
    "root": str(ROOT),
    "tracked_files": len(TRACKED),
    "python_files": len(python_files),
    "javascript_files": len(js_files),
    "routes": len(routes),
    "duplicate_route_paths": len(duplicate_routes),
    "possibly_unused_symbols": len(possibly_unused_symbols),
    "marker_hits": len(markers),
    "print_calls": len(print_calls),
    "console_logs": len(console_logs),
    "junk_candidates": len(junk_candidates),
    "secret_hits": len(secret_hits),
    "syntax_errors": len(syntax_errors),
}

data = {
    "summary": summary,
    "routes": sorted(routes, key=lambda x: (x["path"], x["method"])),
    "duplicate_routes": duplicate_routes,
    "imports_by_file": imports_by_file,
    "possibly_unused_symbols": possibly_unused_symbols,
    "markers": markers,
    "print_calls": print_calls,
    "console_logs": console_logs,
    "junk_candidates": junk_candidates,
    "secret_hits": secret_hits,
    "requirements": requirements,
    "top_level_imports": top_level_imports,
    "duplicate_basenames": duplicate_basenames,
    "syntax_errors": syntax_errors,
}

(REPORT_DIR / "audit.json").write_text(
    json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
)

def section(title: str, rows: list[str]) -> str:
    body = "\n".join(rows) if rows else "_Ничего не найдено._"
    return f"## {title}\n\n{body}\n"

md = [
    "# EduAI — Phase 1 refactoring audit",
    "",
    "Этот отчёт является статическим аудитом. Кандидат в удаление не означает, "
    "что файл или код можно удалять без ручной проверки зависимостей.",
    "",
    "## Сводка",
    "",
]
for key, value in summary.items():
    md.append(f"- **{key}**: {value}")
md.append("")

md.append(section(
    "Кандидаты на очистку репозитория",
    [f"- `{x['path']}` — tracked={x['tracked']}" for x in junk_candidates]
))
md.append(section(
    "Дублирующиеся route paths",
    [
        "- `" + x["path"] + "`: " + ", ".join(
            f"{d['method']} {d['file']}" for d in x["definitions"]
        )
        for x in duplicate_routes
    ]
))
md.append(section(
    "Возможные неиспользуемые Python symbols",
    [
        f"- `{x['symbol']}` — {x['file']}:{x['line']} ({x['kind']})"
        for x in possibly_unused_symbols
    ]
))
md.append(section(
    "TODO/FIXME/HACK/TEMP/DEBUG/OLD/LEGACY",
    [
        f"- `{x['file']}:{x['line']}` [{', '.join(x['markers'])}] "
        f"`{x['text'].replace('`', '')}`"
        for x in markers[:500]
    ]
))
md.append(section(
    "print(...) в Python",
    [f"- `{x['file']}:{x['line']}` `{x['text']}`" for x in print_calls]
))
md.append(section(
    "console.log/debug в JavaScript",
    [f"- `{x['file']}:{x['line']}` `{x['text']}`" for x in console_logs]
))
md.append(section(
    "Потенциальные секреты",
    [
        f"- `{x['file']}:{x['line']}` — {x['kind']}, tracked={x['tracked']}"
        for x in secret_hits
    ]
))
md.append(section(
    "Syntax errors",
    [
        f"- `{x['file']}:{x['line']}` — {x['message']}"
        for x in syntax_errors
    ]
))

(REPORT_DIR / "AUDIT_REPORT.md").write_text(
    "\n".join(md), encoding="utf-8"
)

print("EduAI refactoring audit completed.")
print("Report:", REPORT_DIR / "AUDIT_REPORT.md")
print("Raw data:", REPORT_DIR / "audit.json")
print(json.dumps(summary, ensure_ascii=False, indent=2))
