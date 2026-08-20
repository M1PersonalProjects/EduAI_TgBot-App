from services.quest_generation import canonicalize_subject, parse_quest_request


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
