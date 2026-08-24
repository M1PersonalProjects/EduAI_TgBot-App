import pytest
from unittest.mock import AsyncMock, ANY
from bot.handlers.webapp import generate_child_link, show_parent_monitoring


@pytest.mark.asyncio
async def test_generate_child_link_not_parent(make_message, mock_db):
    """Проверка: обычный пользователь или ученик не может сгенерировать инвайт-ссылку."""
    message = make_message(text="➕ Привязать Ученика", user_id=123)
    
    # Имитируем, что у пользователя роль 'student'
    mock_db.mock_conn.fetchrow.return_value = {"role": "student"}
    
    await generate_child_link(message)
    
    message.answer.assert_called_once_with("Эта команда доступна только Учителю или Администратору.")


@pytest.mark.asyncio
async def test_generate_child_link_success(make_message, mock_db):
    """Проверка: Успешная генерация реферальной ссылки для Родителя."""
    parent_id = 987
    message = make_message(text="➕ Привязать Ученика", user_id=parent_id)
    
    # Имитируем роль Родителя
    mock_db.mock_conn.fetchrow.return_value = {"role": "parent"}
    
    await generate_child_link(message)
    
    # Проверяем, что бот спросил свое имя для формирования ссылки
    message.bot.get_me.assert_called_once()
    
    # Проверяем, что в ответе содержится правильная диплинк-ссылка с parent_id
    response_text = message.answer.call_args[0][0]
    assert f"https://t.me/EduAITestBot?start=reg_{parent_id}" in response_text
    assert "Markdown" in message.answer.call_args[1].values()
    markup = message.answer.call_args.kwargs["reply_markup"]
    assert markup.inline_keyboard[0][0].text == "Поделиться ссылкой"
    assert "t.me/share/url" in markup.inline_keyboard[0][0].url


@pytest.mark.asyncio
async def test_show_parent_monitoring_no_children(make_message, mock_db):
    """Проверка: Вывод сообщения, если у родителя еще нет привязанных детей."""
    parent_id = 555
    message = make_message(text="📊 Мониторинг", user_id=parent_id)
    
    # Сначала проверяем роль родителя
    mock_db.mock_conn.fetchrow.return_value = {"role": "parent"}
    # Имитируем, что fetch вернул пустой список детей
    mock_db.mock_conn.fetch.return_value = []
    
    await show_parent_monitoring(message)
    
    assert "У вас пока нет привязанных Учеников." in message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_show_parent_monitoring_with_children(make_message, mock_db):
    """Проверка: Корректное формирование отчета по успеваемости детей."""
    parent_id = 555
    message = make_message(text="📊 Мониторинг", user_id=parent_id)
    
    mock_db.mock_conn.fetchrow.return_value = {"role": "parent"}
    
    # Имитируем список привязанных детей из базы данных
    mock_db.mock_conn.fetch.return_value = [
        {"tg_id": 111, "username": "alex_math", "tasks_total": 5, "tasks_done": 4, "average_score": 88},
        {"tg_id": 222, "username": None, "tasks_total": 2, "tasks_done": 1, "average_score": 75}
    ]
    
    await show_parent_monitoring(message)
    
    response_text = message.answer.call_args[0][0]
    
    # Проверяем, что в отчет попали данные по первому ребенку (с юзернеймом)
    assert "@alex_math" in response_text
    assert "4/5 выполнено" in response_text
    assert "Средняя оценка: 88" in response_text
    
    # Проверяем, что в отчет попал второй ребенок (без юзернейма, по ID)
    assert "Ученик ID: 222" in response_text
