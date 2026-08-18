from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from api.security import get_current_user
from database import db
from logger_config import logger
from services.attachment_storage import get_attachment, load_attachment_for_ai, save_upload
from services.tutor import (
    create_session,
    delete_session,
    ensure_session,
    exit_book_mode,
    get_messages,
    list_sessions,
    lock_context as lock_session_context,
    rename_session,
    respond,
)

router = APIRouter(prefix="/api/v1/tutor", tags=["AI Tutor v1"])
ALLOWED_TUTOR_ROLES = {"student", "parent", "admin"}


def ensure_tutor_role(user) -> None:
    if user["role"] not in ALLOWED_TUTOR_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ИИ-тьютор доступен Ученикам и Учителям",
        )


class SessionCreate(BaseModel):
    title: str = Field(default="Новый чат", max_length=35)


class SessionRename(BaseModel):
    title: str = Field(..., min_length=1, max_length=35)


class ContextSelection(BaseModel):
    book_class: Optional[int] = Field(None, ge=1, le=11)
    book_program: Optional[str] = Field(None, max_length=100)
    book_id: Optional[int] = None
    page_id: Optional[int] = None
    page_number: Optional[int] = Field(None, ge=1)
    page_paragraph: Optional[str] = Field(None, max_length=100)


def _not_found(error: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))


@router.get("/sessions")
async def sessions(user=Depends(get_current_user)):
    ensure_tutor_role(user)
    return await list_sessions(user["tg_id"])


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def new_session(payload: SessionCreate, user=Depends(get_current_user)):
    ensure_tutor_role(user)
    return await create_session(user["tg_id"], payload.title)


@router.patch("/sessions/{session_id}")
async def update_session(session_id: str, payload: SessionRename, user=Depends(get_current_user)):
    ensure_tutor_role(user)
    try:
        return await rename_session(user["tg_id"], session_id, payload.title)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except LookupError as exc:
        raise _not_found(exc)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_session(session_id: str, user=Depends(get_current_user)):
    ensure_tutor_role(user)
    try:
        await delete_session(user["tg_id"], session_id)
    except (LookupError, ValueError) as exc:
        raise _not_found(exc)


@router.get("/sessions/{session_id}/messages")
async def session_messages(session_id: str, user=Depends(get_current_user)):
    ensure_tutor_role(user)
    try:
        return await get_messages(user["tg_id"], session_id)
    except (LookupError, ValueError) as exc:
        raise _not_found(exc)


@router.put("/sessions/{session_id}/context")
async def set_session_context(
    session_id: str,
    payload: ContextSelection,
    user=Depends(get_current_user),
):
    ensure_tutor_role(user)
    try:
        context = await lock_session_context(
            user["tg_id"], session_id, payload.model_dump(exclude_none=True)
        )
        return {"book_mode": True, "context": context.to_dict()}
    except (LookupError, ValueError) as exc:
        raise _not_found(exc)


@router.delete("/sessions/{session_id}/context")
async def clear_session_context(session_id: str, user=Depends(get_current_user)):
    ensure_tutor_role(user)
    try:
        return await exit_book_mode(user["tg_id"], session_id)
    except (LookupError, ValueError) as exc:
        raise _not_found(exc)


@router.post("/messages")
async def send_message(
    session_id: str = Form(...),
    message_text: str = Form(default=""),
    attachment: Optional[UploadFile] = File(default=None),
    book_class: Optional[int] = Form(default=None),
    book_program: Optional[str] = Form(default=None),
    book_id: Optional[int] = Form(default=None),
    page_id: Optional[int] = Form(default=None),
    page_number: Optional[int] = Form(default=None),
    page_paragraph: Optional[str] = Form(default=None),
    lock_context: bool = Form(default=False),
    interactive_app_id: Optional[str] = Form(default=None),
    interactive_action: Optional[str] = Form(default=None),
    user=Depends(get_current_user),
):
    ensure_tutor_role(user)
    if not message_text.strip() and attachment is None:
        raise HTTPException(status_code=422, detail="Введите сообщение или добавьте вложение")

    logger.info(
        "Web tutor request: user=%s session=%s attachment=%s",
        user["tg_id"],
        session_id,
        attachment.filename if attachment else "none",
    )

    # Validate ownership before persisting a potentially large file.
    try:
        async with db.pool.acquire() as conn:
            await ensure_session(conn, user["tg_id"], session_id)
    except (LookupError, ValueError) as exc:
        raise _not_found(exc)

    parsed_attachment = None
    stored_attachment_id = None
    if attachment is not None:
        try:
            stored = await save_upload(upload=attachment, owner_id=user["tg_id"])
            stored_attachment_id = stored.attachment_id
            stored_row = await get_attachment(stored.attachment_id)
            parsed_attachment = await load_attachment_for_ai(stored_row)
            parsed_attachment.attachment_id = stored.attachment_id
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Attachment persistence/parsing failed: %s", exc)
            raise HTTPException(status_code=422, detail="Не удалось обработать вложение")

    manual_context = {
        "book_class": book_class,
        "book_program": book_program,
        "book_id": book_id,
        "page_id": page_id,
        "page_number": page_number,
        "page_paragraph": page_paragraph,
    }
    try:
        return await respond(
            user_id=user["tg_id"],
            role=user["role"],
            session_id=session_id,
            message_text=message_text,
            attachment=parsed_attachment,
            attachment_id=stored_attachment_id,
            manual_context=manual_context,
            lock_selected_context=lock_context,
            interactive_app_id=interactive_app_id,
            interactive_action=interactive_action,
        )
    except LookupError as exc:
        raise _not_found(exc)
    except Exception as exc:
        logger.exception("Tutor request failed: %s", exc)
        raise HTTPException(status_code=502, detail="ИИ-тьютор временно недоступен")


@router.get("/context/classes")
async def context_classes(user=Depends(get_current_user)):
    async with db.pool.acquire() as conn:
        rows = await conn.fetch("SELECT DISTINCT book_class FROM book ORDER BY book_class")
    return [row["book_class"] for row in rows]


@router.get("/context/subjects")
async def context_subjects(book_class: int, user=Depends(get_current_user)):
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT book_program FROM book WHERE book_class=$1 ORDER BY book_program",
            book_class,
        )
    return [row["book_program"] for row in rows]


@router.get("/context/books")
async def context_books(
    book_class: int,
    book_program: str,
    user=Depends(get_current_user),
):
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT book_id, book_title, book_author, book_program, book_class
            FROM book WHERE book_class=$1 AND book_program=$2 ORDER BY book_title
            """,
            book_class,
            book_program,
        )
    return [dict(row) for row in rows]


@router.get("/context/pages")
async def context_pages(book_id: int, user=Depends(get_current_user)):
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT page_id, page_number, page_title, page_paragraph
            FROM page WHERE book_id=$1 ORDER BY page_number
            """,
            book_id,
        )
    return [dict(row) for row in rows]
