from api.routers.platform import GenerateParentTaskRequest, ParentTaskRequest


def test_generate_request_separates_public_comment_and_private_instructions():
    payload = GenerateParentTaskRequest(
        student_ids=[123],
        topic="Дроби",
        book_id=10,
        parent_comment="Удачи! Решай внимательно.",
        ai_instructions="Последние три задания сделай сложнее.",
    )

    assert payload.parent_comment == "Удачи! Решай внимательно."
    assert payload.ai_instructions == "Последние три задания сделай сложнее."


def test_legacy_instructions_are_input_only():
    payload = GenerateParentTaskRequest(
        student_ids=[123],
        topic="Дроби",
        book_id=10,
        instructions="Сделай восемь вопросов.",
    )

    dumped = payload.model_dump()
    assert "instructions" not in dumped
    assert payload.instructions == "Сделай восемь вопросов."


def test_manual_task_has_distinct_fields():
    fields = ParentTaskRequest.model_fields
    assert "parent_comment" in fields
    assert "ai_instructions" in fields
