"""Совместимый фасад. Диалоговая AI-логика находится в services.ai.orchestrator."""

from services.ai.orchestrator import (
    clean_ai_text,
    book_mode_footer,
    ensure_session,
    ensure_telegram_session,
    create_session,
    list_sessions,
    rename_session,
    delete_session,
    get_messages,
    lock_context,
    exit_book_mode,
    search_book_database,
    search_web_for_education,
    generate_response,
)


async def respond(*, message_text: str, **kwargs):
    """Временный compatibility alias для внешнего кода; новые клиенты используют orchestrator."""
    return await generate_response(message=message_text, mode="chat", **kwargs)
