"""Web application services: tutor, policies, mentor identity."""

from services.web.mentor_identity import mentor_label, normalize_mentor_kind
from services.web.tutor import get_tutor_response
from services.web.tutor_policy import (
    get_student_policy,
    get_parent_policy,
    get_admin_policy,
)

__all__ = [
    "mentor_label",
    "normalize_mentor_kind",
    "get_tutor_response",
    "get_student_policy",
    "get_parent_policy",
    "get_admin_policy",
]