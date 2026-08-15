import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram.filters import CommandObject
from unittest.mock import ANY

# Явно прописываем admin_ids для тестов
from config import settings
settings.admin_ids = {999}

from unittest.mock import AsyncMock, MagicMock, ANY
from bot.handlers.start import cmd_start, callback_toggle_role, callbacks_num


@pytest.mark.asyncio
async def test_cmd_start_self_registration(make_message, mock_db):
    """Проверка: Ребенок не может зарегистрироваться по собственной реферальной ссылке."""
    message = make_message(text="/start reg_111", user_id=111)
    command = CommandObject(prefix="/", command="start", args="reg_111")
    
    await cmd_start(message, command)
    
    message.answer.assert_called_once_with("Вы не можете привязать свой собственный аккаунт в качестве ребенка.")


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

    await cmd_start(message, command)

    assert mock_db.mock_conn.execute.call_count == 2

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
    assert "👨‍👩‍👦 Переключиться на Родителя" in texts


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

    assert "➕ Привязать ребенка" in texts
    assert "📊 Мониторинг в чате" in texts
    assert "📚 Каталог учебников" in texts
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
    
    # Проверяем запись роли и создание профиля геймификации
    assert mock_db.mock_conn.execute.call_count == 2
    callback.message.edit_text.assert_called_once_with("✅ Роль успешно сохранена!\n\nТы зарегистрирован как **Ученик**.", parse_mode="Markdown")