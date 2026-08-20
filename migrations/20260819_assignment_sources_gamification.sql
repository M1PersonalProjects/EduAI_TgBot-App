-- EduAI: separate teacher assignments from tutor practice and add anti-farm gamification.
-- Safe to run repeatedly on PostgreSQL.

ALTER TABLE tasks_history
    ADD COLUMN IF NOT EXISTS assignment_source TEXT;

UPDATE tasks_history
SET assignment_source = CASE
    -- Older EduAI builds sometimes stored self-created practice with a parent_id.
    -- Prefer the explicit historical producer marker when it is available.
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

-- Normalize partially deployed/legacy source labels before installing constraints.
UPDATE tasks_history
SET assignment_source = CASE
    WHEN parent_id IS NOT NULL THEN 'teacher'
    ELSE 'tutor_practice'
END
WHERE assignment_source NOT IN ('teacher', 'tutor_practice');

-- A source without a Teacher owner cannot participate in the Teacher workflow.
UPDATE tasks_history
SET assignment_source = 'tutor_practice'
WHERE assignment_source = 'teacher' AND parent_id IS NULL;

-- Repair the legacy bug where self-created practice inherited the Student's Teacher id.
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

ALTER TABLE gamification
    ADD COLUMN IF NOT EXISTS last_learning_date DATE,
    ADD COLUMN IF NOT EXISTS active_days_total INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS streak_saves INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS gamification_events (
    event_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    event_key TEXT NOT NULL,
    event_type TEXT NOT NULL,
    assignment_source TEXT NOT NULL CHECK (assignment_source IN ('teacher', 'tutor_practice')),
    task_id INTEGER,
    topic_key TEXT NOT NULL DEFAULT '',
    xp_delta INTEGER NOT NULL DEFAULT 0,
    coins_delta INTEGER NOT NULL DEFAULT 0,
    quality_score NUMERIC(5,4) NOT NULL DEFAULT 0,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, event_key)
);
CREATE INDEX IF NOT EXISTS idx_gamification_events_user_created
    ON gamification_events(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_gamification_events_user_topic
    ON gamification_events(user_id, topic_key, created_at DESC);

CREATE TABLE IF NOT EXISTS student_topic_mastery (
    user_id BIGINT NOT NULL,
    topic_key TEXT NOT NULL,
    subject TEXT NOT NULL DEFAULT '',
    topic TEXT NOT NULL DEFAULT '',
    successful_sessions INTEGER NOT NULL DEFAULT 0,
    best_quality NUMERIC(5,4) NOT NULL DEFAULT 0,
    first_mastered_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(user_id, topic_key)
);

CREATE TABLE IF NOT EXISTS student_achievements (
    achievement_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    code TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    unlocked_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, code)
);
CREATE INDEX IF NOT EXISTS idx_student_achievements_user
    ON student_achievements(user_id, unlocked_at DESC);

CREATE TABLE IF NOT EXISTS learning_goals (
    goal_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    period_type TEXT NOT NULL CHECK (period_type IN ('daily', 'weekly')),
    goal_code TEXT NOT NULL,
    title TEXT NOT NULL,
    target_value INTEGER NOT NULL CHECK (target_value > 0),
    progress_value INTEGER NOT NULL DEFAULT 0,
    reward_xp INTEGER NOT NULL DEFAULT 0,
    reward_coins INTEGER NOT NULL DEFAULT 0,
    starts_on DATE NOT NULL,
    ends_on DATE NOT NULL,
    completed_at TIMESTAMPTZ,
    rewarded_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, period_type, goal_code, starts_on)
);
CREATE INDEX IF NOT EXISTS idx_learning_goals_user_period
    ON learning_goals(user_id, starts_on DESC, ends_on DESC);
