-- 001_init.sql —— 初始表结构
-- 对应《实验室2025级新生手册 V20250901》

CREATE TABLE IF NOT EXISTS users (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  name        TEXT NOT NULL,
  account     TEXT NOT NULL UNIQUE,
  password    TEXT NOT NULL,          -- werkzeug 哈希，格式 scrypt:...
  role        TEXT NOT NULL CHECK (role IN ('admin','teacher','student')),
  degree      TEXT CHECK (degree IN ('phd','master')),
  assist_type TEXT CHECK (assist_type IN ('I','II')),
  grade       TEXT,
  advisor_id  INTEGER REFERENCES users(id),
  active      INTEGER NOT NULL DEFAULT 1,
  created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS attendance (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id     INTEGER NOT NULL REFERENCES users(id),
  date        TEXT NOT NULL,
  check_in    TEXT,
  check_out   TEXT,
  leave_kind  TEXT,
  leave_half  TEXT,
  makeup      INTEGER NOT NULL DEFAULT 0,
  created_at  TEXT NOT NULL,
  UNIQUE (user_id, date)
);

CREATE TABLE IF NOT EXISTS reports (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id      INTEGER NOT NULL REFERENCES users(id),
  week_key     TEXT NOT NULL,
  mon          TEXT NOT NULL DEFAULT '',
  tue          TEXT NOT NULL DEFAULT '',
  wed          TEXT NOT NULL DEFAULT '',
  thu          TEXT NOT NULL DEFAULT '',
  fri          TEXT NOT NULL DEFAULT '',
  summary      TEXT NOT NULL DEFAULT '',
  next_plan    TEXT NOT NULL DEFAULT '',
  monthly      TEXT NOT NULL DEFAULT '',
  word_count   INTEGER NOT NULL DEFAULT 0,
  submitted_at TEXT NOT NULL,
  comment      TEXT,
  UNIQUE (user_id, week_key)
);

CREATE TABLE IF NOT EXISTS leaves (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id     INTEGER NOT NULL REFERENCES users(id),
  date        TEXT NOT NULL,
  kind        TEXT NOT NULL CHECK (kind IN ('personal','sick')),
  half        TEXT NOT NULL DEFAULT 'full',
  reason      TEXT DEFAULT '',
  status      TEXT NOT NULL DEFAULT 'pending'
              CHECK (status IN ('pending','approved','rejected')),
  approver_id INTEGER REFERENCES users(id),
  created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS duty (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  date    TEXT NOT NULL,
  user_id INTEGER NOT NULL REFERENCES users(id),
  done    INTEGER NOT NULL DEFAULT 0,
  note    TEXT DEFAULT '',
  UNIQUE (date, user_id)
);

-- 月度考评：含规则版本与计算快照，保证事后可追溯
CREATE TABLE IF NOT EXISTS evaluations (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id          INTEGER NOT NULL REFERENCES users(id),
  month_key        TEXT NOT NULL,
  rule_version     TEXT NOT NULL,        -- 按哪版手册算的
  attendance_score REAL NOT NULL DEFAULT 100,
  task_score       REAL,
  enable_score     REAL NOT NULL DEFAULT 0,
  s_value          REAL,
  grade            TEXT,
  ratio            REAL,
  base_amount      REAL,
  final_amount     REAL,
  snapshot         TEXT,                 -- JSON：当时的考勤/周报原始数据
  note             TEXT,
  finalized        INTEGER NOT NULL DEFAULT 0,
  updated_at       TEXT NOT NULL,
  UNIQUE (user_id, month_key)
);

-- 审计日志：谁在什么时候改了什么
CREATE TABLE IF NOT EXISTS audit_log (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id    INTEGER REFERENCES users(id),
  action     TEXT NOT NULL,
  target     TEXT,
  detail     TEXT,
  ip         TEXT,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_att_user_date ON attendance(user_id, date);
CREATE INDEX IF NOT EXISTS idx_rep_user_week ON reports(user_id, week_key);
CREATE INDEX IF NOT EXISTS idx_duty_date ON duty(date);
CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_log(created_at);
