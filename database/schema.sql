-- ScreenAI local storage

-- Milestone 1: task run history
CREATE TABLE IF NOT EXISTS task_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    command     TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'working',
    started_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    finished_at TEXT,
    result      TEXT
);

CREATE INDEX IF NOT EXISTS idx_task_runs_started_at ON task_runs (started_at DESC);

-- Milestone 2: per-action history (every executed step)
CREATE TABLE IF NOT EXISTS action_history (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT    NOT NULL DEFAULT (datetime('now')),
    command   TEXT    NOT NULL,
    action    TEXT    NOT NULL,
    success   INTEGER NOT NULL DEFAULT 0,
    duration  REAL    NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_action_history_timestamp ON action_history (timestamp DESC);

-- Milestone 3: learned workflows
CREATE TABLE IF NOT EXISTS workflows (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    app_name   TEXT    NOT NULL,
    task_name  TEXT    NOT NULL,
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS workflow_steps (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id INTEGER NOT NULL REFERENCES workflows (id) ON DELETE CASCADE,
    step_index  INTEGER NOT NULL,
    action      TEXT    NOT NULL,
    target_text TEXT,
    coordinates TEXT,
    delay       REAL    NOT NULL DEFAULT 0,
    metadata    TEXT
);

CREATE INDEX IF NOT EXISTS idx_workflow_steps_workflow
    ON workflow_steps (workflow_id, step_index);

-- Milestone 4: agent memory and structured agent logs
-- (agent_events doubles as the log: task, provider, tool, timing, outcome)
CREATE TABLE IF NOT EXISTS agent_sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT    NOT NULL UNIQUE,
    user_command TEXT   NOT NULL,
    provider    TEXT,
    status      TEXT    NOT NULL DEFAULT 'running',
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS agent_events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id     TEXT    NOT NULL,
    task           TEXT    NOT NULL,
    provider       TEXT,
    kind           TEXT    NOT NULL DEFAULT 'tool_call',
    tool_name      TEXT,
    arguments      TEXT,
    result         TEXT,
    success        INTEGER,
    error_category TEXT,
    started_at     TEXT,
    ended_at       TEXT,
    created_at     TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_agent_events_session ON agent_events (session_id, id);
CREATE INDEX IF NOT EXISTS idx_agent_events_created ON agent_events (created_at DESC);

CREATE VIEW IF NOT EXISTS agent_log AS
    SELECT id, session_id AS session, task, provider, tool_name AS tool,
           started_at, ended_at, success, error_category
    FROM agent_events;
