from logger_config import logger


ASSIGNMENT_SOURCE_SCHEMA_SQL = r"""
ALTER TABLE tasks_history
    ADD COLUMN IF NOT EXISTS assignment_source TEXT;

UPDATE tasks_history
SET assignment_source = CASE
    WHEN COALESCE(topic_context->>'source', '') IN (
        'telegram_quest_test',
        'telegram_quest_generation',
        'legacy_random_page_generation',
        'legacy_task_generation'
    ) THEN 'tutor_practice'
    WHEN parent_id IS NOT NULL THEN 'teacher'
    ELSE 'tutor_practice'
END
WHERE assignment_source IS NULL OR BTRIM(assignment_source) = '';

UPDATE tasks_history
SET assignment_source = CASE
    WHEN parent_id IS NOT NULL THEN 'teacher'
    ELSE 'tutor_practice'
END
WHERE assignment_source NOT IN ('teacher', 'tutor_practice');

UPDATE tasks_history
SET assignment_source = 'tutor_practice'
WHERE assignment_source = 'teacher' AND parent_id IS NULL;

UPDATE tasks_history
SET parent_id = NULL
WHERE assignment_source = 'tutor_practice' AND parent_id IS NOT NULL;

ALTER TABLE tasks_history
    ALTER COLUMN assignment_source SET DEFAULT 'tutor_practice';
ALTER TABLE tasks_history
    ALTER COLUMN assignment_source SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'tasks_history_assignment_source_check'
    ) THEN
        ALTER TABLE tasks_history
            ADD CONSTRAINT tasks_history_assignment_source_check
            CHECK (assignment_source IN ('teacher', 'tutor_practice'));
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'tasks_history_source_owner_check'
    ) THEN
        ALTER TABLE tasks_history
            ADD CONSTRAINT tasks_history_source_owner_check
            CHECK (
                (assignment_source = 'teacher' AND parent_id IS NOT NULL)
                OR (assignment_source = 'tutor_practice' AND parent_id IS NULL)
            );
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_tasks_history_student_source_status
    ON tasks_history(student_id, assignment_source, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_history_teacher_source
    ON tasks_history(parent_id, assignment_source, created_at DESC);
"""


TASK_STATUS_SCHEMA_SQL = r"""
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'task_status') THEN
        ALTER TYPE task_status ADD VALUE IF NOT EXISTS 'pending_review';
    END IF;
END $$;
"""


TASK_DRAFTS_AND_REVIEW_SCHEMA_SQL = r"""
CREATE TABLE IF NOT EXISTS task_drafts (
    draft_id UUID PRIMARY KEY,
    teacher_id BIGINT NOT NULL,
    source_message_id BIGINT,
    interactive_app_id UUID,
    title TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    subject TEXT NOT NULL DEFAULT 'Практика',
    topic TEXT NOT NULL DEFAULT '',
    parent_comment TEXT NOT NULL DEFAULT '',
    ai_instructions TEXT,
    reference_answer TEXT NOT NULL DEFAULT '',
    book_id INTEGER,
    page_id INTEGER,
    student_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    attachment_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    attachment_options JSONB NOT NULL DEFAULT '[]'::jsonb,
    generated_items JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_trace JSONB NOT NULL DEFAULT '[]'::jsonb,
    context_mode TEXT,
    used_pages JSONB NOT NULL DEFAULT '[]'::jsonb,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'sent', 'cancelled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sent_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_task_drafts_teacher_updated
    ON task_drafts(teacher_id, updated_at DESC);

ALTER TABLE task_submissions
    ADD COLUMN IF NOT EXISTS teacher_comment TEXT,
    ADD COLUMN IF NOT EXISTS reviewed_by BIGINT;
"""


BRAND_TITLE_SCHEMA_SQL = r"""
UPDATE chat_sessions
SET title = 'Чат Telegram · Umnix'
WHERE title IN ('Чат_Tg-Bot-EduAI', 'Чат_Tg-Bot-Umnix', 'Чат Telegram · umnix.ai');
"""


MENTOR_KIND_SCHEMA_SQL = r"""
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS mentor_kind TEXT;

UPDATE users
SET mentor_kind = 'teacher'
WHERE role = 'parent'
  AND (mentor_kind IS NULL OR mentor_kind NOT IN ('teacher', 'parent'));

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'users_mentor_kind_check'
    ) THEN
        ALTER TABLE users
            ADD CONSTRAINT users_mentor_kind_check
            CHECK (mentor_kind IS NULL OR mentor_kind IN ('teacher', 'parent'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_users_role_mentor_kind
    ON users(role, mentor_kind);
"""


RUNTIME_SCHEMA_STATEMENTS = (
    ("brand_titles", BRAND_TITLE_SCHEMA_SQL),
    ("mentor_kind", MENTOR_KIND_SCHEMA_SQL),
    ("assignment_source", ASSIGNMENT_SOURCE_SCHEMA_SQL),
    ("task_drafts_and_review", TASK_DRAFTS_AND_REVIEW_SCHEMA_SQL),
)


async def ensure_runtime_schema(pool) -> None:
    """Доводит существующую схему БД до минимального состояния, нужного текущему приложению."""
    async with pool.acquire() as conn:
        await conn.execute(TASK_STATUS_SCHEMA_SQL)
        logger.info("Runtime schema check completed: task_status")

        for name, sql in RUNTIME_SCHEMA_STATEMENTS:
            async with conn.transaction():
                await conn.execute(sql)
            logger.info("Runtime schema check completed: %s", name)
