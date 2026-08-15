BEGIN;

-- TZ29 adds only interactive-app feature tables.
-- Existing user_role values parent/student/admin are intentionally untouched.

CREATE TABLE IF NOT EXISTS interactive_apps (
    app_id UUID PRIMARY KEY,
    owner_id BIGINT NOT NULL REFERENCES users(tg_id) ON DELETE CASCADE,
    session_id UUID NOT NULL REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
    source_message_id BIGINT REFERENCES chat_messages(message_id) ON DELETE SET NULL,
    title VARCHAR(180) NOT NULL,
    app_type VARCHAR(40) NOT NULL DEFAULT 'interactive_test',
    question_count INTEGER NOT NULL DEFAULT 0 CHECK (question_count >= 0),
    original_request TEXT NOT NULL DEFAULT '',
    current_version INTEGER NOT NULL DEFAULT 1 CHECK (current_version >= 1),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS interactive_app_versions (
    app_id UUID NOT NULL REFERENCES interactive_apps(app_id) ON DELETE CASCADE,
    version_no INTEGER NOT NULL CHECK (version_no >= 1),
    html_document TEXT NOT NULL,
    change_request TEXT NOT NULL DEFAULT '',
    created_by BIGINT NOT NULL REFERENCES users(tg_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (app_id, version_no)
);

CREATE TABLE IF NOT EXISTS interactive_assignments (
    assignment_id BIGSERIAL PRIMARY KEY,
    app_id UUID NOT NULL REFERENCES interactive_apps(app_id) ON DELETE CASCADE,
    teacher_id BIGINT NOT NULL REFERENCES users(tg_id) ON DELETE CASCADE,
    student_id BIGINT NOT NULL REFERENCES users(tg_id) ON DELETE CASCADE,
    task_id BIGINT REFERENCES tasks_history(task_id) ON DELETE SET NULL,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (app_id, student_id)
);

CREATE TABLE IF NOT EXISTS interactive_results (
    result_id BIGSERIAL PRIMARY KEY,
    app_id UUID NOT NULL REFERENCES interactive_apps(app_id) ON DELETE CASCADE,
    version_no INTEGER NOT NULL,
    student_id BIGINT NOT NULL REFERENCES users(tg_id) ON DELETE CASCADE,
    assignment_id BIGINT REFERENCES interactive_assignments(assignment_id) ON DELETE SET NULL,
    score NUMERIC(10,2) NOT NULL DEFAULT 0,
    max_score NUMERIC(10,2) NOT NULL DEFAULT 0,
    progress JSONB NOT NULL DEFAULT '{}'::jsonb,
    completed BOOLEAN NOT NULL DEFAULT FALSE,
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (app_id, version_no)
        REFERENCES interactive_app_versions(app_id, version_no) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_interactive_apps_owner_session
    ON interactive_apps(owner_id, session_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_interactive_apps_source_message
    ON interactive_apps(source_message_id) WHERE source_message_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_interactive_assignments_student
    ON interactive_assignments(student_id, assigned_at DESC);
CREATE INDEX IF NOT EXISTS idx_interactive_results_student_app
    ON interactive_results(student_id, app_id, submitted_at DESC);

COMMIT;
