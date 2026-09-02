"""Education services: context resolution, task/quest generation, scope management."""

from services.education.context_resolver import (
    ResolvedContext,
    resolve_context,
    load_locked_context,
)
from services.education.task_generation import (
    generate_exact_task_set,
    GeneratedTaskSet,
    GeneratedTaskItem,
    extract_requested_task_count,
    find_requested_task_count,
    normalize_task_set,
    generated_count,
    task_set_payload,
)
from services.education.quest_generation import (
    generate_quest_task_set,
    parse_quest_request,
    QuestRequestSpec,
    canonicalize_subject,
    quest_choice_rules,
    format_quest_question,
    parse_quest_choice_answer,
    check_quest_choice_answer,
)
from services.education.scope_guard import (
    validate_request_scope,
    ScopeClassification,
    ScopeGuardResult,
    build_refusal_message,
)
from services.education.assignment_source import (
    normalize_assignment_source,
    infer_difficulty,
    TEACHER,
)

__all__ = [
    "ResolvedContext",
    "resolve_context",
    "load_locked_context",
    "generate_exact_task_set",
    "GeneratedTaskSet",
    "GeneratedTaskItem",
    "extract_requested_task_count",
    "find_requested_task_count",
    "normalize_task_set",
    "generated_count",
    "task_set_payload",
    "generate_quest_task_set",
    "parse_quest_request",
    "QuestRequestSpec",
    "canonicalize_subject",
    "quest_choice_rules",
    "format_quest_question",
    "parse_quest_choice_answer",
    "check_quest_choice_answer",
    "validate_request_scope",
    "ScopeClassification",
    "ScopeGuardResult",
    "build_refusal_message",
]
