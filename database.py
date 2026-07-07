import asyncpg
from config import settings
from logger_config import logger

class Database:
    def __init__(self):
        self.pool: asyncpg.Pool = None

    async def connect(self):
        if self.pool is not None:
            return
            
        try:
            self.pool = await asyncpg.create_pool(
                dsn=settings.database_url,
                min_size=5,
                max_size=20
            )
            logger.info("🚀 Пул соединений с PostgreSQL успешно запущен")
        except Exception as e:
            logger.critical(f"❌ Не удалось подключиться к базе данных: {e}")
            raise e

    async def disconnect(self):
        if self.pool:
            await self.pool.close()
            self.pool = None
            logger.info("🛑 Пул соединений с PostgreSQL остановлен")

db = Database()