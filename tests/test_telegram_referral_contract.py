from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_teacher_link_button_matches_a_dedicated_handler_before_ai_fallback():
    keyboard = read("bot/keyboards.py")
    webapp = read("bot/handlers/webapp.py")
    main = read("main.py")

    assert 'KeyboardButton(text="➕ Привязать Ученика")' in keyboard
    assert 'F.text == "➕ Привязать Ученика"' in webapp
    assert main.index("dp.include_router(webapp.router)") < main.index("dp.include_router(ai_chat.router)")


def test_referral_flow_keeps_existing_reg_deep_link_and_guards_reassignment():
    webapp = read("bot/handlers/webapp.py")
    start = read("bot/handlers/start.py")

    assert '?start=reg_{user_id}' in webapp
    assert 'inviter["role"] not in ("parent", "admin")' in start
    assert 'уже привязан к другому Учителю' in start
    assert 'уже привязан к этому Учителю' in start
