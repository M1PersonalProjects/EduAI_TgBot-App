from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_public_templates_use_umnix_brand_and_unified_css():
    for name in ("student.html", "parent.html", "admin.html", "files.html", "interactive.html", "auth.html"):
        source = read(f"templates/{name}")
        assert "Umnix" in source
        assert "umnix.ai" not in source
        assert "app.css?v=20260825-umnix-2" in source
    css = read("static/css/app.css")
    assert ".umnix-brand" in css
    assert "--umnix-page-gutter" in css
    assert "UMNIX UNIFIED PRODUCT LAYOUT" in css


def test_teacher_and_student_tutor_have_voice_button_and_backend_route():
    assert "data-chat-voice" in read("templates/student.html")
    assert "data-chat-voice" in read("templates/parent.html")
    chat = read("static/js/chat.js")
    assert "MediaRecorder" in chat
    assert "toggleVoiceRecording" in chat
    assert "/api/v1/tutor/transcribe" in chat
    router = read("api/routers/tutor.py")
    assert '@router.post("/transcribe")' in router
    assert "transcribe_audio" in router


def test_interactive_prompt_infers_rich_free_form_product():
    prompt = read("services/prompts/interactive_apps.py").lower()
    assert "free-form request interpretation" in prompt
    assert "reference quality bar" in prompt
    assert "do not require them to specify implementation details" in prompt
    assert "task-specific drawings are part of the task condition" in prompt
    assert "more than 50 exercises" in prompt
    service = read("services/interactive_apps.py")
    assert "_default_practice_target" in service
    assert "INFERRED PRODUCT SCOPE" in service


def test_quest_generator_has_closed_choice_contract():
    source = read("services/quest_generation.py")
    assert "between 2 and 6" in source
    assert "correct_option_numbers" in source
    assert "format_quest_question" in source
    assert "check_quest_choice_answer" in source


def test_mobile_tutor_keeps_umnix_brand_visible_and_bridge_compatible():
    student = read("templates/student.html")
    teacher = read("templates/parent.html")
    css = read("static/css/app.css")
    prompt = read("services/prompts/interactive_apps.py")
    assert 'class="umnix-brand chat-screen-brand"' in student
    assert 'class="umnix-brand chat-screen-brand"' in teacher
    assert 'UMNIX MOBILE CHAT BRAND FINALIZATION' in css
    assert 'EduAIInteractive.complete' in prompt
    assert 'UmnixInteractive.complete' not in prompt
