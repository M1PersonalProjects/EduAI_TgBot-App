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


def test_student_payload_strips_private_answer_keys_recursively():
    from api.routers.platform import student_safe_task_payload
    value = {
        "title": "Тест",
        "reference_answer": "42",
        "questions": [
            {"question_text": "Сколько?", "correct_answer": "42"},
            {"question_text": "Почему?", "hint": "Подумай"},
        ],
    }
    safe = student_safe_task_payload(value)
    assert "reference_answer" not in safe
    assert "correct_answer" not in safe["questions"][0]
    assert safe["questions"][1]["hint"] == "Подумай"
