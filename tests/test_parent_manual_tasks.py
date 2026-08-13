from api.routers.platform import ParentTaskRequest, TaskAttachmentOption


def test_manual_fields_are_optional():
    payload = ParentTaskRequest(student_ids=[1])
    assert payload.title == ""
    assert payload.description == ""
    assert payload.reference_answer == ""


def test_parent_answer_can_be_omitted():
    payload = ParentTaskRequest(
        student_ids=[1],
        topic="Дроби",
        description="Решите: 1/2 + 1/2",
    )
    assert payload.reference_answer == ""


def test_file_only_payload_is_representable():
    payload = ParentTaskRequest(
        student_ids=[1],
        topic="Контрольная работа",
        attachment_options=[
            TaskAttachmentOption(
                attachment_id=44,
                visible_to_student=True,
                use_as_ai_context=True,
            )
        ],
    )
    assert payload.description == ""
    assert payload.attachment_options[0].visible_to_student is True


def test_per_file_visibility_and_ai_context_are_independent():
    payload = ParentTaskRequest(
        student_ids=[1],
        attachment_options=[
            TaskAttachmentOption(attachment_id=1, visible_to_student=True, use_as_ai_context=False),
            TaskAttachmentOption(attachment_id=2, visible_to_student=False, use_as_ai_context=True),
        ],
    )
    assert payload.attachment_options[0].use_as_ai_context is False
    assert payload.attachment_options[1].visible_to_student is False
