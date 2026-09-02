"""Web application services: tutor, policies, mentor identity."""

from services.web.mentor_identity import mentor_label, normalize_mentor_kind
from services.web.tutor import respond as get_tutor_response
from services.web.tutor_policy import (
    role_rules,
    teacher_task_prompt,
    student_task_prompt,
    task_grading_prompt,
    private_answer_key_prompt,
)

__all__ = [
    "mentor_label",
    "normalize_mentor_kind",
    "get_tutor_response",
    "role_rules",
    "teacher_task_prompt",
    "student_task_prompt",
    "task_grading_prompt",
    "private_answer_key_prompt",
]