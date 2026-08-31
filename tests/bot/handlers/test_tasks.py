from pathlib import Path

import pytest

from bot.handlers.tasks import QuestStates, check_quest_answer, start_quest


@pytest.mark.asyncio
async def test_start_quest_opens_temporary_builder_for_student(make_message, mock_db, mock_fsm_context):
    user_id = 556
    message = make_message(text="🧩 Квест-тест", user_id=user_id)
    state = mock_fsm_context(user_id, user_id)
    mock_db.mock_conn.fetchval.return_value = "student"

    await start_quest(message, state)

    text = message.answer.await_args.args[0]
    assert "Quest-test" in text
    labels = [button.text for row in message.answer.await_args.kwargs["reply_markup"].inline_keyboard for button in row]
    assert "📚 Выбрать учебник / тему" in labels
    assert "✍️ Создать по запросу" in labels
    assert all("tasks_history" not in str(call.args) for call in mock_db.mock_conn.fetch.await_args_list)


@pytest.mark.asyncio
async def test_quest_advances_in_fsm_without_database_write(make_message, mock_db, mock_fsm_context):
    user_id = 557
    message = make_message(text="1", user_id=user_id)
    state = mock_fsm_context(user_id, user_id)
    await state.set_data({
        "quest_title": "Дроби",
        "quest_index": 0,
        "quest_answers": [],
        "quest_items": [
            {"id": "q1", "question_text": "1+1?", "options": ["2", "3"], "correct_option_numbers": [1]},
            {"id": "q2", "question_text": "2+2?", "options": ["4", "5"], "correct_option_numbers": [1]},
        ],
    })
    await state.set_state(QuestStates.waiting_for_answer)

    await check_quest_answer(message, state)

    data = await state.get_data()
    assert data["quest_index"] == 1
    assert data["quest_answers"][0]["is_correct"] is True
    assert "Вопрос 2 из 2" in message.answer.await_args.args[0]
    mock_db.mock_conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_finished_quest_clears_state(make_message, mock_db, mock_fsm_context):
    user_id = 558
    message = make_message(text="1", user_id=user_id)
    state = mock_fsm_context(user_id, user_id)
    await state.set_data({
        "quest_title": "Тест",
        "quest_index": 0,
        "quest_answers": [],
        "quest_items": [{"id": "q1", "question_text": "1+1?", "options": ["2", "3"], "correct_option_numbers": [1]}],
    })
    await state.set_state(QuestStates.waiting_for_answer)

    await check_quest_answer(message, state)

    assert await state.get_state() is None
    assert "Результат не сохраняется в БД" in message.answer.await_args.args[0]
    mock_db.mock_conn.execute.assert_not_awaited()


def test_quest_handler_has_no_persistent_task_history_storage():
    source = Path("bot/handlers/tasks.py").read_text(encoding="utf-8") + Path("bot/handlers/quests.py").read_text(encoding="utf-8")
    assert "INSERT INTO tasks_history" not in source
    assert "UPDATE tasks_history" not in source
