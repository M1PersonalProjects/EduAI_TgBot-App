import os
import pytest
import pytest_asyncio
import asyncio
from unittest.mock import AsyncMock, MagicMock

# 1. СТРОГО НА САМОМ ВЕРХУ: выставляем переменные окружения для Pydantic Settings
os.environ["BOT_TOKEN"] = "123456789:AABBCCDDEEFFgg"
os.environ["OPENAI_API_KEY"] = "sk-fakekey"
os.environ["DATABASE_URL"] = "postgresql://user:pass@localhost:5432/db"

# 2. Теперь безопасно импортируем библиотеки и модули проекта
from httpx import AsyncClient, ASGITransport
from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

from main import app
from database import db


@pytest_asyncio.fixture
async def api_client(mock_db):
    """Фикстура асинхронного клиента для тестирования FastAPI эндпоинтов.
    
    Использует ASGITransport для прямого вызова приложения без сетевых запросов,
    а также автоматически изолируется через уже существующий mock_db.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture(scope="session")
def event_loop():
    """Создает экземпляр event loop для всего цикла тестирования."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_bot():
    """Возвращает замоканный объект бота aiogram."""
    bot = AsyncMock(spec=Bot)
    bot.id = 123456789
    
    bot_user = AsyncMock()
    bot_user.username = "EduAITestBot"
    bot.get_me = AsyncMock(return_value=bot_user)
    
    return bot


@pytest.fixture
def mock_db(monkeypatch):
    """
    Мокает пул соединений базы данных db.pool.
    Позволяет эмулировать async with db.pool.acquire() as conn:
    и async with conn.transaction():
    """
    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    
    class AsyncContextManager:
        def __init__(self, return_value):
            self.return_value = return_value
        async def __aenter__(self):
            return self.return_value
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    mock_pool.acquire.return_value = AsyncContextManager(mock_conn)
    
    mock_transaction = MagicMock(return_value=AsyncContextManager(None))
    mock_conn.transaction = mock_transaction
    mock_pool.mock_conn = mock_conn
    
    monkeypatch.setattr(db, "pool", mock_pool)
    return mock_pool


@pytest.fixture
def make_message():
    """Фабрика для генерации моков aiogram Message."""
    def _make(text: str, user_id: int = 12345, username: str = "test_user", first_name: str = "User", has_photo: bool = False):
        message = AsyncMock()
        message.text = text
        message.caption = None
        
        message.from_user.id = user_id
        message.from_user.username = username
        message.from_user.first_name = first_name
        
        message.bot = AsyncMock()
        
        mock_me = MagicMock()
        mock_me.username = "EduAITestBot"
        message.bot.get_me = AsyncMock(return_value=mock_me)
        
        if has_photo:
            photo_mock = MagicMock()
            photo_mock.file_id = "mock_photo_file_id_123"
            message.photo = [photo_mock]
            
            file_info_mock = MagicMock()
            file_info_mock.file_path = "photos/mock_path.jpg"
            message.bot.get_file = AsyncMock(return_value=file_info_mock)
        else:
            message.photo = None
            
        message.document = None
        
        status_msg = AsyncMock()
        message.answer = AsyncMock(return_value=status_msg)
        return message
    return _make


@pytest.fixture
def make_callback_query(mock_bot):
    """Фабрика для создания фейковых инлайн-нажатий (CallbackQuery)."""
    def _make(data: str, user_id: int, username: str = "test_user"):
        user = MagicMock()
        user.id = user_id
        user.is_bot = False
        user.username = username
        
        message = AsyncMock()
        message.chat.id = user_id
        message.answer = AsyncMock()
        message.edit_text = AsyncMock()
        
        callback = AsyncMock()
        callback.data = data
        callback.from_user = user
        callback.message = message
        callback.bot = mock_bot
        callback.answer = AsyncMock()
        return callback
    return _make


@pytest.fixture
def mock_fsm_context():
    """Создает реальный или изолированный контекст FSM на базе MemoryStorage."""
    storage = MemoryStorage()
    def _make_context(user_id: int, chat_id: int):
        return FSMContext(storage=storage, key=MagicMock(user_id=user_id, chat_id=chat_id))
    return _make_context


@pytest.fixture
def mock_openai(monkeypatch):
    """Мокает вызовы OpenAI API клиентов (chat.completions.create и beta.chat.completions.parse)"""
    mock_client = AsyncMock()
    
    mock_choice = MagicMock()
    mock_choice.message.content = "Аналитический отчет ИИ: Ребенок отлично справляется!"
    mock_create_response = MagicMock()
    mock_create_response.choices = [mock_choice]
    mock_client.chat.completions.create = AsyncMock(return_value=mock_create_response)
    
    mock_parsed_choice = MagicMock()
    mock_parsed_choice.message.parsed = None 
    mock_parse_response = MagicMock()
    mock_parse_response.choices = [mock_parsed_choice]
    mock_client.beta.chat.completions.parse = AsyncMock(return_value=mock_parse_response)
    
    from bot.handlers import parent
    monkeypatch.setattr(parent, "openai_client", mock_client)
    
    return mock_client