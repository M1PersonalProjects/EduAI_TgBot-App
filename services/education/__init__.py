"""Education services: context resolution, task/quest generation, scope management."""

from services.education.context_resolver import (
    ResolvedContext,
    resolve_context,
    load_locked_context,
)
from services.education.educational_context import get_book_context
from services.education.task_generation import generate_task
from services.education.quest_generation import generate_quest
from services.education.scope_guard import validate_scope
from services.education.assignment_source import get_assignment_source
from services.education.conversation_context import get_conversation_history

__all__ = [
    "ResolvedContext",
    "resolve_context",
    "load_locked_context",
    "get_book_context",
    "generate_task",
    "generate_quest",
    "validate_scope",
    "get_assignment_source",
    "get_conversation_history",
]
