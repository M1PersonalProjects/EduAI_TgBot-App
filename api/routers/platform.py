import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from api.routers.admin import upload_pdf_and_process
from api.routers.tasks import OpenAITaskGeneration, OpenAITaskVerification
from api.security import get_current_user, require_roles
from config import settings
from database import db
from logger_config import logger
from services.tutor import clean_ai_text, ensure_session, respond as tutor_respond


router = APIRouter(prefix="/api/v1", tags=["Web platform v1"])
openai_client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())


def parse_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value or {}


def without_latex(value: Optional[str]) -> str:
    return clean_ai_text(value)


class ChatRequest(BaseModel):
    message_text: str = Field(..., min_length=1, max_length=4000)


class TaskAnswerRequest(BaseModel):
    student_answer: str = Field(..., min_length=1, max_length=4000)


class ParentTaskRequest(BaseModel):
    student_id: int
    title: str = Field(..., min_length=2, max_length=200)
    description: str = Field(..., min_length=2, max_length=4000)
    reference_answer: str = Field(..., min_length=1, max_length=1000)
    subject: str = Field(default="Практика", max_length=100)


class GenerateParentTaskRequest(BaseModel):
    student_id: int
    topic: str = Field(..., min_length=2, max_length=300)


class RewardPayload(BaseModel):
    name: str = Field(..., min_length=2, max_length=256)
    description: str = Field(default="", max_length=500)
    cost_coins: int = Field(..., ge=1, le=1_000_000)
    category: str = Field(default="other", max_length=100)


class BookPayload(BaseModel):
    book_title: str = Field(..., min_length=2, max_length=246)
    book_program: str = Field(..., min_length=2, max_length=100)
    book_class: int = Field(..., ge=1, le=11)
    book_author: str = Field(..., min_length=2, max_length=256)


class PagePayload(BaseModel):
    page_title: Optional[str] = Field(None, max_length=256)
    page_number: int = Field(..., ge=1)
    page_paragraph: Optional[str] = Field(None, max_length=100)
    page_text: str
    page_html: str
    page_markdown: str


async def ensure_child(conn, parent_id: int, student_id: int) -> None:
    exists = await conn.fetchval(
        "SELECT EXISTS(SELECT 1 FROM users WHERE tg_id = $1 AND parent_id = $2 AND role = 'student')",
        student_id,
        parent_id,
    )
    if not exists:
        raise HTTPException(status_code=404, detail="Привязанный ученик не найден")


@router.get("/student/dashboard")
async def student_dashboard(user=Depends(require_roles("student"))):
    async with db.pool.acquire() as conn:
        profile = await conn.fetchrow(
            """
            SELECT u.tg_id, u.username, u.role, u.parent_id,
                   COALESCE(g.balance_coins, 0) AS balance_coins,
                   COALESCE(g.xp_total, 0) AS xp_total,
                   COALESCE(g.streak_days, 0) AS streak_days
            FROM users u LEFT JOIN gamification g ON g.user_id = u.tg_id
            WHERE u.tg_id = $1
            """,
            user["tg_id"],
        )
        tasks = await conn.fetch(
            """
            SELECT task_id, parent_id, topic_context, questions_json, student_answers_json,
                   score, status, created_at
            FROM tasks_history
            WHERE student_id = $1 AND status IN ('created', 'in_progress')
            ORDER BY created_at ASC
            """,
            user["tg_id"],
        )
        rewards = await conn.fetch(
            """
            SELECT reward_id, name, description, cost_coins, category
            FROM rewards WHERE parent_id = $1 ORDER BY cost_coins ASC
            """,
            profile["parent_id"],
        ) if profile["parent_id"] else []
        purchases = await conn.fetch(
            """
            SELECT rp.purchase_id, rp.cost_coins, rp.purchased_at, r.name, r.category
            FROM reward_purchases rp JOIN rewards r ON r.reward_id = rp.reward_id
            WHERE rp.student_id = $1 ORDER BY rp.purchased_at DESC LIMIT 20
            """,
            user["tg_id"],
        )

    task_items = []
    for item in tasks:
        row = dict(item)
        row["topic_context"] = parse_json(row["topic_context"])
        row["questions_json"] = parse_json(row["questions_json"])
        row["student_answers_json"] = parse_json(row["student_answers_json"])
        task_items.append(row)
    return {
        "profile": dict(profile),
        "tasks": task_items,
        "rewards": [dict(item) for item in rewards],
        "purchases": [dict(item) for item in purchases],
    }


@router.post("/student/tasks/{task_id}/submit")
async def submit_student_task(task_id: int, payload: TaskAnswerRequest, user=Depends(require_roles("student"))):
    async with db.pool.acquire() as conn:
        task = await conn.fetchrow(
            """
            SELECT questions_json FROM tasks_history
            WHERE task_id = $1 AND student_id = $2 AND status IN ('created', 'in_progress')
            """,
            task_id,
            user["tg_id"],
        )
    if not task:
        raise HTTPException(status_code=404, detail="Активное задание не найдено")

    questions = parse_json(task["questions_json"])
    try:
        response = await openai_client.beta.chat.completions.parse(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Проверь ответ школьника по смыслу. Будь доброжелателен. "
                        "Верни структурированный результат на русском языке. Не используй LaTeX и знак $."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Задание: {questions.get('question_text', '')}\n"
                        f"Эталон: {questions.get('reference_answer', '')}\n"
                        f"Ответ ученика: {payload.student_answer}"
                    ),
                },
            ],
            response_format=OpenAITaskVerification,
        )
        result = response.choices[0].message.parsed
    except Exception as exc:
        logger.error("Task verification failed: %s", exc)
        raise HTTPException(status_code=502, detail="Не удалось проверить ответ. Попробуйте позже")

    answer_data = {
        "provided_answer": without_latex(payload.student_answer),
        "verification_feedback": without_latex(result.explanation),
        "is_correct": result.is_correct,
    }
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            updated = await conn.fetchval(
                """
                UPDATE tasks_history
                SET student_answers_json = $1, score = $2,
                    status = $3::task_status
                WHERE task_id = $4 AND student_id = $5
                  AND status IN ('created', 'in_progress')
                RETURNING task_id
                """,
                json.dumps(answer_data),
                50 if result.is_correct else 0,
                "evaluated" if result.is_correct else "in_progress",
                task_id,
                user["tg_id"],
            )
            if not updated:
                raise HTTPException(status_code=409, detail="Задание уже было оценено")
            if result.is_correct:
                gamification = await conn.fetchrow(
                    """
                    INSERT INTO gamification (user_id, balance_coins, xp_total, streak_days)
                    VALUES ($1, 15, 50, 0)
                    ON CONFLICT (user_id) DO UPDATE
                    SET balance_coins = gamification.balance_coins + 15,
                        xp_total = gamification.xp_total + 50
                    RETURNING balance_coins, xp_total
                    """,
                    user["tg_id"],
                )
            else:
                gamification = await conn.fetchrow(
                    "SELECT balance_coins, xp_total FROM gamification WHERE user_id = $1",
                    user["tg_id"],
                )
    return {
        "success": result.is_correct,
        "message": without_latex(result.explanation),
        "balance_coins": (gamification["balance_coins"] if gamification else 0),
        "xp_total": (gamification["xp_total"] if gamification else 0),
        "earned_coins": 15 if result.is_correct else 0,
        "earned_xp": 50 if result.is_correct else 0,
    }


@router.post("/student/rewards/{reward_id}/buy")
async def buy_reward(reward_id: int, user=Depends(require_roles("student"))):
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            reward = await conn.fetchrow(
                """
                SELECT r.reward_id, r.name, r.cost_coins
                FROM rewards r JOIN users u ON u.parent_id = r.parent_id
                WHERE r.reward_id = $1 AND u.tg_id = $2
                """,
                reward_id,
                user["tg_id"],
            )
            if not reward:
                raise HTTPException(status_code=404, detail="Награда вашей семьи не найдена")
            balance = await conn.fetchval(
                """
                UPDATE gamification SET balance_coins = balance_coins - $1
                WHERE user_id = $2 AND balance_coins >= $1
                RETURNING balance_coins
                """,
                reward["cost_coins"],
                user["tg_id"],
            )
            if balance is None:
                raise HTTPException(status_code=409, detail="Недостаточно монет")
            await conn.execute(
                "INSERT INTO reward_purchases (student_id, reward_id, cost_coins) VALUES ($1, $2, $3)",
                user["tg_id"],
                reward_id,
                reward["cost_coins"],
            )
    return {"status": "success", "reward_name": reward["name"], "balance_coins": balance}


@router.get("/chat/history")
async def chat_history(user=Depends(get_current_user)):
    async with db.pool.acquire() as conn:
        session = await ensure_session(conn, user["tg_id"])
        rows = await conn.fetch(
            "SELECT message_id, sender, message_text, created_at FROM chat_messages WHERE user_id = $1 AND session_id = $2 ORDER BY created_at ASC LIMIT 200",
            user["tg_id"],
            session["session_id"],
        )
    return [dict(row) for row in rows]


@router.post("/chat/messages")
async def chat_message(payload: ChatRequest, user=Depends(get_current_user)):
    try:
        return await tutor_respond(
            user_id=user["tg_id"],
            role=user["role"],
            message_text=payload.message_text,
        )
    except Exception as exc:
        logger.error("Web chat failed: %s", exc)
        raise HTTPException(status_code=502, detail="ИИ-ассистент временно недоступен")


@router.delete("/chat/history", status_code=status.HTTP_204_NO_CONTENT)
async def clear_chat(user=Depends(get_current_user)):
    async with db.pool.acquire() as conn:
        session = await ensure_session(conn, user["tg_id"])
        await conn.execute(
            "DELETE FROM chat_messages WHERE user_id = $1 AND session_id = $2",
            user["tg_id"], session["session_id"],
        )


@router.get("/parent/dashboard")
async def parent_dashboard(user=Depends(require_roles("parent", "admin"))):
    async with db.pool.acquire() as conn:
        children = await conn.fetch(
            """
            SELECT u.tg_id, u.username,
                   COALESCE(g.balance_coins, 0) AS balance_coins,
                   COALESCE(g.xp_total, 0) AS xp_total,
                   COALESCE(g.streak_days, 0) AS streak_days,
                   COUNT(DISTINCT t.task_id) AS tasks_total,
                   COUNT(DISTINCT t.task_id) FILTER (WHERE t.status IN ('completed', 'evaluated')) AS tasks_done,
                   COALESCE(ROUND(AVG(t.score))::int, 0) AS average_score,
                   COUNT(DISTINCT rp.purchase_id) AS purchases_total
            FROM users u
            LEFT JOIN gamification g ON g.user_id = u.tg_id
            LEFT JOIN tasks_history t ON t.student_id = u.tg_id
            LEFT JOIN reward_purchases rp ON rp.student_id = u.tg_id
            WHERE u.parent_id = $1 AND u.role = 'student'
            GROUP BY u.tg_id, u.username, g.balance_coins, g.xp_total, g.streak_days
            ORDER BY u.username NULLS LAST
            """,
            user["tg_id"],
        )
        purchases = await conn.fetch(
            """
            SELECT rp.purchase_id, rp.student_id, rp.cost_coins, rp.purchased_at,
                   r.name, u.username
            FROM reward_purchases rp
            JOIN rewards r ON r.reward_id = rp.reward_id
            JOIN users u ON u.tg_id = rp.student_id
            WHERE u.parent_id = $1 ORDER BY rp.purchased_at DESC LIMIT 30
            """,
            user["tg_id"],
        )
    return {"children": [dict(row) for row in children], "purchases": [dict(row) for row in purchases]}


@router.post("/parent/tasks", status_code=status.HTTP_201_CREATED)
async def create_parent_task(payload: ParentTaskRequest, user=Depends(require_roles("parent", "admin"))):
    async with db.pool.acquire() as conn:
        await ensure_child(conn, user["tg_id"], payload.student_id)
        task_id = await conn.fetchval(
            """
            INSERT INTO tasks_history (student_id, parent_id, topic_context, questions_json, score, status)
            VALUES ($1, $2, $3, $4, 0, 'created') RETURNING task_id
            """,
            payload.student_id,
            user["tg_id"],
            json.dumps({"subject": payload.subject, "source": "parent_web"}),
            json.dumps({
                "title": without_latex(payload.title),
                "question_text": without_latex(payload.description),
                "reference_answer": without_latex(payload.reference_answer),
            }),
        )
    return {"status": "created", "task_id": task_id}


@router.post("/parent/tasks/generate", status_code=status.HTTP_201_CREATED)
async def generate_parent_task(payload: GenerateParentTaskRequest, user=Depends(require_roles("parent", "admin"))):
    async with db.pool.acquire() as conn:
        await ensure_child(conn, user["tg_id"], payload.student_id)
        page = await conn.fetchrow(
            """
            SELECT p.page_id, p.page_title, p.page_markdown, b.book_title, b.book_program
            FROM page p JOIN book b ON b.book_id = p.book_id
            WHERE p.page_markdown ILIKE $1 OR p.page_title ILIKE $1
            ORDER BY p.page_id DESC LIMIT 1
            """,
            f"%{payload.topic}%",
        )
        if not page:
            page = await conn.fetchrow(
                """SELECT p.page_id, p.page_title, p.page_markdown, b.book_title, b.book_program
                   FROM page p JOIN book b ON b.book_id = p.book_id ORDER BY p.page_id DESC LIMIT 1"""
            )
    if not page:
        raise HTTPException(status_code=404, detail="В базе знаний нет страниц учебников")
    try:
        response = await openai_client.beta.chat.completions.parse(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Создай одно школьное задание на русском. LaTeX и знак $ запрещены."},
                {"role": "user", "content": f"Тема: {payload.topic}\nУчебник: {page['book_title']}\n{page['page_markdown'][:7000]}"},
            ],
            response_format=OpenAITaskGeneration,
        )
        generated = response.choices[0].message.parsed
    except Exception as exc:
        logger.error("Parent task generation failed: %s", exc)
        raise HTTPException(status_code=502, detail="Не удалось сгенерировать задание")
    manual = ParentTaskRequest(
        student_id=payload.student_id,
        title=without_latex(generated.title),
        description=without_latex(generated.description),
        reference_answer=without_latex(generated.correct_answer),
        subject=page["book_program"],
    )
    result = await create_parent_task(manual, user)
    result["task"] = manual.model_dump()
    return result


@router.get("/parent/rewards")
async def list_parent_rewards(user=Depends(require_roles("parent", "admin"))):
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT reward_id, name, description, cost_coins, category, created_at FROM rewards WHERE parent_id = $1 ORDER BY created_at DESC",
            user["tg_id"],
        )
    return [dict(row) for row in rows]


@router.post("/parent/rewards", status_code=status.HTTP_201_CREATED)
async def create_parent_reward(payload: RewardPayload, user=Depends(require_roles("parent", "admin"))):
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO rewards (parent_id, name, description, cost_coins, category)
               VALUES ($1, $2, $3, $4, $5)
               RETURNING reward_id, name, description, cost_coins, category, created_at""",
            user["tg_id"], payload.name, payload.description, payload.cost_coins, payload.category,
        )
    return dict(row)


@router.put("/parent/rewards/{reward_id}")
async def update_parent_reward(reward_id: int, payload: RewardPayload, user=Depends(require_roles("parent", "admin"))):
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(
            """UPDATE rewards SET name=$1, description=$2, cost_coins=$3, category=$4
               WHERE reward_id=$5 AND parent_id=$6
               RETURNING reward_id, name, description, cost_coins, category, created_at""",
            payload.name, payload.description, payload.cost_coins, payload.category,
            reward_id, user["tg_id"],
        )
    if not row:
        raise HTTPException(status_code=404, detail="Награда не найдена")
    return dict(row)


@router.delete("/parent/rewards/{reward_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_parent_reward(reward_id: int, user=Depends(require_roles("parent", "admin"))):
    async with db.pool.acquire() as conn:
        deleted = await conn.fetchval(
            "DELETE FROM rewards WHERE reward_id=$1 AND parent_id=$2 RETURNING reward_id",
            reward_id, user["tg_id"],
        )
    if not deleted:
        raise HTTPException(status_code=404, detail="Награда не найдена")


@router.get("/admin/overview")
async def admin_overview(user=Depends(require_roles("admin"))):
    async with db.pool.acquire() as conn:
        counts = await conn.fetchrow(
            """SELECT (SELECT COUNT(*) FROM users) AS users,
                      (SELECT COUNT(*) FROM book) AS books,
                      (SELECT COUNT(*) FROM page) AS pages,
                      (SELECT COUNT(*) FROM tasks_history) AS tasks"""
        )
    return dict(counts)


@router.get("/admin/books")
async def admin_books(user=Depends(require_roles("admin"))):
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT b.book_id, b.book_title, b.book_program, b.book_class, b.book_author,
                      b.created_at, COUNT(p.page_id) AS pages_count
               FROM book b LEFT JOIN page p ON p.book_id=b.book_id
               GROUP BY b.book_id ORDER BY b.created_at DESC"""
        )
    return [dict(row) for row in rows]


@router.post("/admin/books", status_code=status.HTTP_201_CREATED)
async def admin_create_book(payload: BookPayload, user=Depends(require_roles("admin"))):
    async with db.pool.acquire() as conn:
        duplicate = await conn.fetchval(
            """SELECT book_id FROM book WHERE lower(book_title)=lower($1) AND lower(book_program)=lower($2)
               AND book_class=$3 AND lower(book_author)=lower($4)""",
            payload.book_title, payload.book_program, payload.book_class, payload.book_author,
        )
        if duplicate:
            raise HTTPException(status_code=409, detail="Такой учебник уже существует")
        row = await conn.fetchrow(
            """INSERT INTO book (book_title, book_program, book_class, book_author)
               VALUES ($1,$2,$3,$4) RETURNING *""",
            payload.book_title, payload.book_program, payload.book_class, payload.book_author,
        )
    return dict(row)


@router.put("/admin/books/{book_id}")
async def admin_update_book(book_id: int, payload: BookPayload, user=Depends(require_roles("admin"))):
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(
            """UPDATE book SET book_title=$1, book_program=$2, book_class=$3, book_author=$4
               WHERE book_id=$5 RETURNING *""",
            payload.book_title, payload.book_program, payload.book_class, payload.book_author, book_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Учебник не найден")
    return dict(row)


@router.delete("/admin/books/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_book(book_id: int, user=Depends(require_roles("admin"))):
    async with db.pool.acquire() as conn:
        deleted = await conn.fetchval("DELETE FROM book WHERE book_id=$1 RETURNING book_id", book_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Учебник не найден")


@router.post("/admin/books/{book_id}/upload", status_code=status.HTTP_200_OK)
async def admin_upload_book(book_id: int, file: UploadFile = File(...), user=Depends(require_roles("admin"))):
    return await upload_pdf_and_process(book_id, file)


@router.get("/admin/books/{book_id}/pages")
async def admin_pages(book_id: int, user=Depends(require_roles("admin"))):
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT page_id, book_id, page_title, page_number, page_paragraph,
                      page_html, page_image, page_text, page_markdown
               FROM page WHERE book_id=$1 ORDER BY page_number""",
            book_id,
        )
    return [dict(row) for row in rows]


@router.put("/admin/pages/{page_id}")
async def admin_update_page(page_id: int, payload: PagePayload, user=Depends(require_roles("admin"))):
    markdown = without_latex(payload.page_markdown)
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(
            """UPDATE page SET page_title=$1, page_number=$2, page_paragraph=$3,
                      page_text=$4, page_html=$5, page_markdown=$6
               WHERE page_id=$7 RETURNING page_id""",
            payload.page_title, payload.page_number, payload.page_paragraph,
            payload.page_text, payload.page_html, markdown, page_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Страница не найдена")
    return {"status": "success", "page_id": page_id}


@router.get("/admin/users")
async def admin_users(role: Optional[str] = None, search: Optional[str] = None, user=Depends(require_roles("admin"))):
    params: List[Any] = []
    query = "SELECT tg_id, username, role, parent_id, created_at FROM users WHERE TRUE"
    if role:
        params.append(role)
        query += f" AND role = ${len(params)}::user_role"
    if search:
        params.append(f"%{search}%")
        query += f" AND (username ILIKE ${len(params)} OR tg_id::text ILIKE ${len(params)})"
    query += " ORDER BY created_at DESC LIMIT 500"
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    return [dict(row) for row in rows]


@router.get("/admin/family-tree")
async def admin_family_tree(user=Depends(require_roles("admin"))):
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT p.tg_id AS parent_id, p.username AS parent_username,
                      c.tg_id AS student_id, c.username AS student_username
               FROM users p LEFT JOIN users c ON c.parent_id=p.tg_id AND c.role='student'
               WHERE p.role IN ('parent','admin') ORDER BY p.username NULLS LAST, c.username NULLS LAST"""
        )
    families: Dict[int, Dict[str, Any]] = {}
    for row in rows:
        family = families.setdefault(row["parent_id"], {
            "parent_id": row["parent_id"], "parent_username": row["parent_username"], "children": []
        })
        if row["student_id"]:
            family["children"].append({"tg_id": row["student_id"], "username": row["student_username"]})
    return list(families.values())


@router.get("/admin/activity")
async def admin_activity(user=Depends(require_roles("admin"))):
    async with db.pool.acquire() as conn:
        chats = await conn.fetch(
            "SELECT message_id AS id, user_id, sender, message_text AS detail, created_at FROM chat_messages ORDER BY created_at DESC LIMIT 40"
        )
        tasks = await conn.fetch(
            "SELECT task_id AS id, student_id AS user_id, status::text AS detail, created_at FROM tasks_history ORDER BY created_at DESC LIMIT 40"
        )
        purchases = await conn.fetch(
            "SELECT purchase_id AS id, student_id AS user_id, ('Награда #' || reward_id || ', ' || cost_coins || ' монет') AS detail, purchased_at AS created_at FROM reward_purchases ORDER BY purchased_at DESC LIMIT 40"
        )
    result = ([{"type": "chat", **dict(row)} for row in chats]
              + [{"type": "task", **dict(row)} for row in tasks]
              + [{"type": "purchase", **dict(row)} for row in purchases])
    result.sort(key=lambda item: item["created_at"], reverse=True)
    return result[:100]
