from services.education.quest_generation import canonicalize_subject, parse_quest_request


def test_free_quest_request_extracts_required_fields_and_count():
    spec = parse_quest_request(
        "7 класс, математика, обыкновенные дроби, 6 вопросов"
    )
    assert spec.grade == 7
    assert spec.subject == "математика"
    assert spec.topic == "обыкновенные дроби"
    assert spec.requested_count == 6
    assert spec.missing_fields == ()


def test_selected_context_does_not_need_to_be_repeated():
    spec = parse_quest_request(
        "10 вопросов повышенной сложности",
        grade=8,
        subject="Химия",
        topic="Металлы",
    )
    assert spec.grade == 8
    assert spec.subject == "Химия"
    assert spec.topic == "Металлы"
    assert spec.requested_count == 10
    assert spec.missing_fields == ()


def test_missing_topic_is_reported():
    spec = parse_quest_request("7 класс, математика")
    assert spec.missing_fields == ("тема",)


def test_inflected_subject_can_match_existing_program():
    assert canonicalize_subject(
        "математике", ["Русский язык", "Математика", "Физика"]
    ) == "Математика"


def test_quest_choices_accept_single_and_multiple_numeric_answers():
    from services.education.quest_generation import check_quest_choice_answer, format_quest_question

    single = {
        "question_text": "Сколько будет 2 + 2?",
        "options": ["3", "4", "5"],
        "correct_option_numbers": [2],
        "allow_multiple": False,
    }
    assert check_quest_choice_answer(single, "2") == (True, (2,))
    assert check_quest_choice_answer(single, "1") == (False, (1,))
    assert check_quest_choice_answer(single, "ответ 2")[0] is None
    assert "Выберите один вариант" in format_quest_question(single, 1, 2)

    multiple = {
        "question_text": "Выберите простые числа",
        "options": ["2", "4", "5", "6"],
        "correct_option_numbers": [1, 3],
        "allow_multiple": True,
    }
    assert check_quest_choice_answer(multiple, "3 1") == (True, (1, 3))
    assert check_quest_choice_answer(multiple, "1,3") == (True, (1, 3))
    assert "несколько вариантов" in format_quest_question(multiple, 2, 2)


def test_quest_choice_quality_requires_2_to_6_and_variety():
    from services.education.quest_generation import quest_choice_issues

    good = {
        "items": [
            {"options": ["a", "b"], "correct_option_numbers": [1]},
            {"options": ["a", "b", "c"], "correct_option_numbers": [2]},
            {"options": ["a", "b", "c", "d"], "correct_option_numbers": [1, 3]},
            {"options": ["a", "b", "c"], "correct_option_numbers": [1]},
            {"options": ["a", "b", "c", "d", "e"], "correct_option_numbers": [2]},
            {"options": ["a", "b", "c", "d"], "correct_option_numbers": [2, 4]},
        ]
    }
    assert quest_choice_issues(good) == []
