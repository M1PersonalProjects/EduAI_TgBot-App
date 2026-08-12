"""Apply TZ19 changes that must be made inside large current project files.
Run from the EduAI repository root after replacing files from this archive.
"""
from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        print(f"[ok] {label}: already applied")
        return
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly 1 match in {path}, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"[ok] {label}")


platform = Path("api/routers/platform.py")
student = Path("static/js/student.js")

replace_once(
    platform,
    "from services.response_formatter import MATH_FORMATTING_RULES",
    "from services.response_formatter import MATH_FORMATTING_RULES, canonicalize_message",
    "platform import canonicalize_message",
)

replace_once(
    platform,
    '''            questions_json = {\n                "title": without_latex(payload.title),\n                "question_text": without_latex(payload.description),\n                "reference_answer": without_latex(payload.reference_answer),\n            }''',
    '''            questions_json = {\n                "title": without_latex(payload.title),\n                # Preserve canonical Markdown + LaTeX. Presentation belongs to clients.\n                "question_text": canonicalize_message(payload.description),\n                "reference_answer": canonicalize_message(payload.reference_answer),\n            }''',
    "manual task canonical math",
)

replace_once(
    platform,
    '''    answer_data = {\n        "provided_answer": without_latex(payload.student_answer),\n        "verification_feedback": without_latex(result.explanation),\n        "is_correct": result.is_correct,\n    }''',
    '''    answer_data = {\n        "provided_answer": without_latex(payload.student_answer),\n        # Keep AI feedback canonical so WebApp can render its mathematics.\n        "verification_feedback": canonicalize_message(result.explanation),\n        "is_correct": result.is_correct,\n    }''',
    "verification feedback canonical math",
)

replace_once(
    platform,
    '''                without_latex(result.explanation),\n                50 if result.is_correct else 0,''',
    '''                canonicalize_message(result.explanation),\n                50 if result.is_correct else 0,''',
    "submission feedback canonical math",
)

replace_once(
    platform,
    '''        title=without_latex(generated.title),\n        description=without_latex(generated.description),\n        reference_answer=without_latex(generated.correct_answer),''',
    '''        title=without_latex(generated.title),\n        description=canonicalize_message(generated.description),\n        reference_answer=canonicalize_message(generated.correct_answer),''',
    "generated task canonical math",
)

replace_once(
    student,
    '''                    ${EduAI.escapeHtml(task.student_answers_json.verification_feedback)}''',
    '''                    ${EduAI.markdown(task.student_answers_json.verification_feedback)}''',
    "student feedback math renderer",
)

print("TZ19 project patches applied successfully.")
