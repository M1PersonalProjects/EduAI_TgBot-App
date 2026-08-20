from services.prompts.educational_context import EDUCATIONAL_CONTEXT_RULES
from services.prompts.task_generation import TEACHER_TASK_GENERATION_RULES


def test_shared_context_rule_is_primary_not_exclusive():
    value = EDUCATIONAL_CONTEXT_RULES.lower()
    assert "primary source, not the exclusive source" in value
    assert "other digitized" in value
    assert "problem collections" in value
    assert "web sources" in value


def test_task_prompt_requires_exact_count_and_diversity():
    value = TEACHER_TASK_GENERATION_RULES.lower()
    assert "exactly requested_count" in value
    assert "do not copy" in value
    assert "diversify" in value
