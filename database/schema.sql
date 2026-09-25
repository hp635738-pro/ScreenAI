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
