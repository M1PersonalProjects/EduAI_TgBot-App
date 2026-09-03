from services.web.tutor_policy import build_tutor_prompt


def test_student_rag_prompt_contains_learning_role_and_context():
    prompt = build_tutor_prompt(
        "student",
        None,
        database_context="Квадратное уравнение: ax^2 + bx + c = 0",
        session_memory="Ученик изучает квадратные уравнения.",
    )
    assert "CURRENT USER ROLE: STUDENT" in prompt
    assert "Explain reasoning, concepts, and mistakes" in prompt
    assert "ax^2 + bx + c = 0" in prompt
    assert "Ученик изучает квадратные уравнения" in prompt
