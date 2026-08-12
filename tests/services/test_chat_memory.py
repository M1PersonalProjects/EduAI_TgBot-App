from services.chat_memory import (
    attachment_score,
    build_memory_summary,
    detect_task_number,
    has_context_reference,
    looks_like_task_set,
    update_state_dict,
)


def test_task_set_is_pinned_and_second_reference_is_resolved():
    original = "1. Первый пример\n2. Второй пример\n3. Третий пример\n4. Четвёртый пример"
    assert looks_like_task_set(original)
    state = update_state_dict({}, message_text=original, message_id=100)
    assert state["active_task_set_message_id"] == 100
    assert state["current_task_number"] == 1

    state = update_state_dict(state, message_text="Понял. Теперь перейдём ко второму.", message_id=107)
    assert state["active_task_set_message_id"] == 100
    assert state["current_task_number"] == 2


def test_relative_next_task_uses_existing_state():
    assert detect_task_number("Давай следующее", 2) == 3
    assert detect_task_number("Вернёмся к предыдущему", 3) == 2


def test_natural_context_references_are_detected():
    assert has_context_reference("Объясни таблицу из файла")
    assert has_context_reference("Вернёмся к фотографии решения")
    assert has_context_reference("Теперь второе")


def test_attachment_selection_prefers_named_and_matching_file():
    pdf = {
        "original_name": "fractions-homework.pdf",
        "mime_type": "application/pdf",
        "extracted_text": "Дроби. Упражнение 1. Упражнение 2.",
    }
    other = {
        "original_name": "grammar.txt",
        "mime_type": "text/plain",
        "extracted_text": "Причастие и деепричастие",
    }
    assert attachment_score(pdf, "Вернись к fractions-homework.pdf", newest_rank=3) > attachment_score(other, "Вернись к fractions-homework.pdf", newest_rank=0)


def test_memory_summary_is_internal_and_factual():
    state = {
        "current_topic": "Дроби",
        "active_task_set_message_id": 3812,
        "current_task_number": 2,
        "referenced_attachment_ids": [44],
    }
    summary = build_memory_summary(state, [{"message_id": 3812, "message_text": "1. ... 2. ... 3. ..."}])
    assert "Current topic: Дроби" in summary
    assert "Active task-set message_id: 3812" in summary
    assert "Current task number: 2" in summary
    assert "Do not invent missing history" in summary


def test_new_session_state_does_not_inherit_another_chat():
    chat_a = update_state_dict({}, message_text="1. A\n2. B\n3. C", message_id=1)
    chat_b = update_state_dict({}, message_text="Давай второе", message_id=2)
    assert chat_a.get("active_task_set_message_id") == 1
    assert chat_b.get("active_task_set_message_id") is None
