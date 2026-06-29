import asyncpg
from config import settings

class Database:
    def __init__(self):
        self.pool: asyncpg.Pool = None

    async def connect(self):
        if not self.pool:
            self.pool = await asyncpg.create_pool(
                dsn=settings.database_url,
                min_size=5,
                max_size=20
            )
            print("🚀 Пул соединений с PostgreSQL успешно запущен")

    async def disconnect(self):
        if self.pool:
            await self.pool.close()
            print("🛑 Пул соединений с PostgreSQL остановлен")

db = Database()