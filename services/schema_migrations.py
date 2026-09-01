from logger_config import logger


async def ensure_runtime_schema(pool) -> None:
    """Схема создаётся целиком из database.sql; runtime ALTER больше не выполняются."""
    logger.info("Runtime schema check skipped: use database.sql as the canonical Umnix schema")
