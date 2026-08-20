from pathlib import Path

from logger_config import logger

_BASE_DIR = Path(__file__).resolve().parent.parent
_MIGRATIONS = (
    _BASE_DIR / "migrations" / "20260819_assignment_sources_gamification.sql",
)


async def ensure_runtime_schema(pool) -> None:
    """Apply idempotent compatibility migrations required by the running build.

    EduAI historically shipped without a migration runner. Keeping this tiny runner
    makes upgrades safe for existing installations while the SQL files remain usable
    by normal deployment tooling.
    """
    async with pool.acquire() as conn:
        for migration in _MIGRATIONS:
            sql = migration.read_text(encoding="utf-8")
            async with conn.transaction():
                await conn.execute(sql)
            logger.info("Applied runtime migration: %s", migration.name)
