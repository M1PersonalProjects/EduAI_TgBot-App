from services.task_generation import extract_requested_task_count, find_requested_task_count


def test_requested_count_is_extracted_from_russian_and_english():
    assert find_requested_task_count("Создай 20 задач по дробям") == 20
    assert find_requested_task_count("Build 30 derivative tasks") == 30
    assert find_requested_task_count("Объясни дроби") is None
    assert extract_requested_task_count("Объясни дроби", default=7) == 7


def test_requested_count_is_bounded_for_backend_safety():
    assert find_requested_task_count("Создай 999 задач", maximum=100) == 100
