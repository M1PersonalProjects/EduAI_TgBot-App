import pytest
from aiogram.filters import CommandObject
from unittest.mock import ANY

# Явно прописываем admin_ids для тестов
from config import settings
settings.admin_ids = {999}

from bot.handlers.start import cmd_start, callback_toggle_role, callbacks_num


@pytest.mark.asyncio
async def test_cmd_start_self_registration(make_message, mock_db):
    """Проверка: Ребенок не может зарегистрироваться по собственной реферальной ссылке."""
    message = make_message(text="/start reg_111", user_id=111)
    command = CommandObject(prefix="/", command="start", args="reg_111")
    
    await cmd_start(message, command)
    
    message.answer.assert_called_once_with("Вы не можете привязать свой собственный аккаунт в качестве Ученика.")


@pytest.mark.asyncio
async def test_cmd_start_successful_child_registration(make_message, mock_db):
    """Проверка: успешная регистрация Ученика по инвайту Учителя и отправка уведомления."""
    parent_id = 555
    student_id = 777

    message = make_message(
        text=f"/start reg_{parent_id}",
        user_id=student_id,
        username="young_genius",
    )
    command = CommandObject(
        prefix="/",
        command="start",
        args=f"reg_{parent_id}",
    )
    mock_db.mock_conn.fetchrow.side_effect = [
        {"role": "parent"},
        None,
    ]

    await cmd_start(message, command)

    # Регистрация создаёт только пользователя и связь с Учителем.
    mock_db.mock_conn.execute.assert_awaited_once()
    assert "INSERT INTO users" in mock_db.mock_conn.execute.call_args.args[0]

    answer_text = message.answer.call_args[0][0]

    assert "Аккаунт успешно связан с Учителем!" in answer_text
    assert "В Telegram можно:" in answer_text
    assert "В EduAI WebApp доступно больше:" in answer_text
    assert "🌐 Открыть EduAI" in answer_text

    message.bot.send_message.assert_called_once_with(
        chat_id=parent_id,
        text=(
            "🔔 Ученик (@young_genius) успешно привязал "
            "свой аккаунт к вашему профилю!"
        ),
    )


@pytest.mark.asyncio
async def test_cmd_start_rejects_invalid_teacher_invite(make_message, mock_db):
    message = make_message(text="/start reg_555", user_id=777)
    command = CommandObject(prefix="/", command="start", args="reg_555")
    mock_db.mock_conn.fetchrow.return_value = None

    await cmd_start(message, command)

    assert "ссылка привязки недействительна" in message.answer.call_args.args[0]
    mock_db.mock_conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_cmd_start_does_not_steal_student_from_other_teacher(make_message, mock_db):
    message = make_message(text="/start reg_555", user_id=777)
    command = CommandObject(prefix="/", command="start", args="reg_555")
    mock_db.mock_conn.fetchrow.side_effect = [
        {"role": "parent"},
        {"role": "student", "parent_id": 999},
    ]

    await cmd_start(message, command)

    assert "уже привязан к другому Учителю" in message.answer.call_args.args[0]
    mock_db.mock_conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_cmd_start_same_teacher_invite_is_idempotent(make_message, mock_db):
    message = make_message(text="/start reg_555", user_id=777)
    command = CommandObject(prefix="/", command="start", args="reg_555")
    mock_db.mock_conn.fetchrow.side_effect = [
        {"role": "parent"},
        {"role": "student", "parent_id": 555},
    ]

    await cmd_start(message, command)

    assert "уже привязан к этому Учителю" in message.answer.call_args.args[0]
    mock_db.mock_conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_cmd_start_admin_first_time(make_message, mock_db):
    """Проверка: Первый запуск бота Главным Администратором."""
    admin_id = 999
    message = make_message(text="/start", user_id=admin_id)
    command = CommandObject(prefix="/", command="start", args=None)
    
    # Имитируем, что админа еще нет в БД
    mock_db.mock_conn.fetchrow.return_value = None
    
    await cmd_start(message, command)
    
    # Проверяем, что его роль сохранилась как admin
    mock_db.mock_conn.execute.assert_called_once()
    assert "admin" in mock_db.mock_conn.execute.call_args[0][0]
    answer_text = message.answer.call_args[0][0]

    assert "режим Администратора" in answer_text
    assert "В Telegram" in answer_text
    assert "В EduAI WebApp:" in answer_text
    assert "🌐 Открыть EduAI" in answer_text

    markup = message.answer.call_args.kwargs["reply_markup"]
    texts = [
        button.text
        for row in markup.inline_keyboard
        for button in row
    ]

    assert "🌐 Открыть EduAI" in texts
    assert "👩‍🏫 Переключиться на Учителя" in texts


@pytest.mark.asyncio
async def test_cmd_start_existing_parent(make_message, mock_db):
    """Проверка: Авторизованный вход пользователя с ролью Родитель."""
    parent_id = 888
    message = make_message(text="/start", user_id=parent_id)
    command = CommandObject(prefix="/", command="start", args=None)
    
    # База возвращает роль parent
    mock_db.mock_conn.fetchrow.return_value = {"role": "parent"}
    
    await cmd_start(message, command)
    
    # Меняем pytest.any_str на ANY
    message.answer.assert_called_once()

    answer_text = message.answer.call_args.args[0]
    kwargs = message.answer.call_args.kwargs

    assert "Добро пожаловать в EduAI!" in answer_text
    assert "В Telegram можно:" in answer_text
    assert "В EduAI WebApp доступно больше:" in answer_text
    assert "🌐 Открыть EduAI" in answer_text

    assert kwargs["parse_mode"] == "Markdown"

    markup = kwargs["reply_markup"]
    texts = [
        button.text
        for row in markup.keyboard
        for button in row
    ]

    assert "➕ Привязать Ученика" in texts
    assert "📊 Мониторинг в чате" in texts
    assert "📚 Учебники" in texts
    assert "🌐 Открыть EduAI" in texts

    assert "📊 Панель Родителя (Web App)" not in texts
    assert "📝 Создать ИИ-тест (Web App)" not in texts




@pytest.mark.asyncio
async def test_cmd_start_new_user_role_selection(make_message, mock_db):
    """Проверка: Совершенно новый пользователь получает клавиатуру выбора ролей."""
    user_id = 444
    message = make_message(text="/start", user_id=user_id, first_name= "Иван")
    command = CommandObject(prefix="/", command="start", args=None)
    
    mock_db.mock_conn.fetchrow.return_value = None
    
    await cmd_start(message, command)
    
    answer_text = message.answer.call_args[0][0]

    assert "Добро пожаловать в EduAI!" in answer_text
    assert "Telegram" in answer_text
    assert "WebApp" in answer_text
    assert "выберите свою роль:" in answer_text


@pytest.mark.asyncio
async def test_callback_set_role_student(make_callback_query, mock_db):
    """Проверка: Выбор инлайн-кнопки 'Я Ученик' обычным пользователем."""
    callback = make_callback_query(data="set_role_student", user_id=333, username="student_user")
    
    await callbacks_num(callback)
    
    # При выборе роли сохраняется только пользователь с выбранной ролью.
    mock_db.mock_conn.execute.assert_awaited_once()
    assert "INSERT INTO users" in mock_db.mock_conn.execute.call_args.args[0]
    callback.message.edit_text.assert_called_once_with("✅ Роль успешно сохранена!\n\nТы зарегистрирован как **Ученик**.", parse_mode="Markdown")