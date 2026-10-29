"""SQLite: одно соединение на процесс под блокировкой, WAL, версионные миграции."""
import json
import sqlite3
import threading
from contextlib import contextmanager

from . import config

MIGRATIONS = [
    # 1 — ядро панели
    """
    CREATE TABLE admins (
        id            INTEGER PRIMARY KEY,
        username      TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        totp_secret   TEXT,
        totp_enabled  INTEGER NOT NULL DEFAULT 0,
        created_at    TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE sessions (
        id         TEXT PRIMARY KEY,          -- sha256 токена из cookie
        admin_id   INTEGER NOT NULL REFERENCES admins(id) ON DELETE CASCADE,
        created_at INTEGER NOT NULL,
        expires_at INTEGER NOT NULL,
        ip         TEXT,
        user_agent TEXT
    );
    CREATE TABLE audit_log (
        id      INTEGER PRIMARY KEY,
        ts      INTEGER NOT NULL,
        admin   TEXT,
        action  TEXT NOT NULL,
        target  TEXT,
        details TEXT,
        ip      TEXT
    );
    CREATE INDEX audit_log_ts ON audit_log(ts);
    CREATE TABLE settings (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL                   -- JSON
    );
    CREATE TABLE nodes (
        id         INTEGER PRIMARY KEY,
        name       TEXT NOT NULL,
        url        TEXT NOT NULL,
        token      TEXT,                      -- NULL: токен читается из файла (локальная нода)
        is_local   INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    """,
    # 2 — клиенты, лимиты, трафик
    """
    CREATE TABLE clients (
        id          INTEGER PRIMARY KEY,
        node_id     INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
        wg_id       INTEGER NOT NULL,         -- id клиента в wg-easy ноды
        public_key  TEXT,
        meta        TEXT NOT NULL DEFAULT '{}',  -- группа, заметка и прочее (JSON)
        created_at  TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (node_id, wg_id)
    );
    CREATE TABLE traffic_last (
        client_id INTEGER PRIMARY KEY REFERENCES clients(id) ON DELETE CASCADE,
        rx        INTEGER NOT NULL,
        tx        INTEGER NOT NULL,
        ts        INTEGER NOT NULL
    );
    CREATE TABLE traffic_daily (
        client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
        day       TEXT NOT NULL,              -- YYYY-MM-DD в часовом поясе настроек
        rx        INTEGER NOT NULL DEFAULT 0,
        tx        INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (client_id, day)
    );
    CREATE TABLE traffic_points (
        ts INTEGER PRIMARY KEY,               -- секунды, точка раз в минуту
        rx INTEGER NOT NULL,                  -- суммарные счётчики всех клиентов
        tx INTEGER NOT NULL
    );
    """,
    # 3 — имя клиента в панели (для статистики, когда клиента уже нет на ноде)
    """
    ALTER TABLE clients ADD COLUMN name TEXT;
    """,
    # 4 — квоты трафика (календарный месяц в часовом поясе панели)
    """
    CREATE TABLE quotas (
        client_id   INTEGER PRIMARY KEY REFERENCES clients(id) ON DELETE CASCADE,
        limit_bytes INTEGER NOT NULL,
        warned      TEXT,                     -- месяц (YYYY-MM), за который отправлено предупреждение 80 %
        blocked     TEXT                      -- месяц, в котором клиент отключён квотой
    );
    """,
    # 5 — группы, справочник списков, маршрутизация клиентов (WireSock)
    """
    CREATE TABLE groups (
        id    INTEGER PRIMARY KEY,
        name  TEXT NOT NULL UNIQUE,
        color TEXT NOT NULL DEFAULT '#94a3b8',
        sort  INTEGER NOT NULL DEFAULT 0
    );
    INSERT INTO groups(name, color, sort) VALUES
        ('Семья', '#f472b6', 1), ('Работа', '#60a5fa', 2), ('Гости', '#fbbf24', 3),
        ('VIP', '#a78bfa', 4), ('Тест', '#34d399', 5);
    INSERT OR IGNORE INTO groups(name, sort)
        SELECT DISTINCT json_extract(meta, '$.group'), 100 FROM clients
        WHERE json_valid(meta) AND json_extract(meta, '$.group') IS NOT NULL
          AND json_extract(meta, '$.group') NOT IN ('', 'Без группы');
    ALTER TABLE clients ADD COLUMN group_id INTEGER REFERENCES groups(id) ON DELETE SET NULL;
    UPDATE clients SET group_id = (SELECT id FROM groups WHERE name = json_extract(clients.meta, '$.group'))
        WHERE json_valid(meta);
    UPDATE clients SET meta = json_remove(meta, '$.group') WHERE json_valid(meta);
    CREATE TABLE lists (
        id         INTEGER PRIMARY KEY,
        kind       TEXT NOT NULL CHECK (kind IN ('net', 'app')),
        name       TEXT NOT NULL,
        data       TEXT NOT NULL DEFAULT '{}',   -- net: {countries, cidrs}; app: {apps}
        updated_at INTEGER NOT NULL DEFAULT (unixepoch()),
        UNIQUE (kind, name)
    );
    CREATE TABLE client_routing (
        client_id INTEGER PRIMARY KEY REFERENCES clients(id) ON DELETE CASCADE,
        net_mode  TEXT NOT NULL DEFAULT 'all',   -- all | include | exclude
        net_lists TEXT NOT NULL DEFAULT '[]',
        app_mode  TEXT NOT NULL DEFAULT 'all',
        app_lists TEXT NOT NULL DEFAULT '[]',
        extra     TEXT NOT NULL DEFAULT ''       -- свои строки конфига (WireSock и прочее)
    );
    """,
    # 6 — страница пользователя: личная ссылка клиента /u/<токен>
    """
    CREATE TABLE user_links (
        client_id  INTEGER PRIMARY KEY REFERENCES clients(id) ON DELETE CASCADE,
        token      TEXT NOT NULL UNIQUE,
        created_at INTEGER NOT NULL,
        last_seen  INTEGER
    );
    """,
    # 7 — удалённые ноды: адрес, порты, закреплённый сертификат агента, ключ SSH-хоста
    """
    ALTER TABLE nodes ADD COLUMN host TEXT;
    ALTER TABLE nodes ADD COLUMN ssh_port INTEGER;
    ALTER TABLE nodes ADD COLUMN wg_port INTEGER;
    ALTER TABLE nodes ADD COLUMN agent_port INTEGER;
    ALTER TABLE nodes ADD COLUMN wg_dns TEXT;
    ALTER TABLE nodes ADD COLUMN tls_cert TEXT;
    ALTER TABLE nodes ADD COLUMN ssh_host_key TEXT;
    ALTER TABLE nodes ADD COLUMN installed_at INTEGER;
    """,
    # 8 — клиент панели = профили на всех нодах с одним IP. Клиент больше не принадлежит ноде:
    # таблица пересобирается без node_id/wg_id (внешние ключи на время миграции выключены).
    # adopted=0 — состояние (включён, срок, IP) ещё не взято с ноды; берётся при первой синхронизации.
    """
    CREATE TABLE clients_new (
        id         INTEGER PRIMARY KEY,
        name       TEXT,
        ipv4       TEXT,
        enabled    INTEGER NOT NULL DEFAULT 1,
        expires_at TEXT,
        meta       TEXT NOT NULL DEFAULT '{}',
        group_id   INTEGER REFERENCES groups(id) ON DELETE SET NULL,
        deleted    INTEGER NOT NULL DEFAULT 0,   -- удаляется: профили на нодах дочищает синхронизация
        adopted    INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    INSERT INTO clients_new(id, name, meta, group_id, created_at, adopted, expires_at)
        SELECT id, name, meta, group_id, created_at, 0,
               CASE WHEN json_valid(meta) THEN json_extract(meta, '$.expiresAt') END FROM clients;
    CREATE TABLE profiles (
        id         INTEGER PRIMARY KEY,
        client_id  INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
        node_id    INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
        wg_id      INTEGER NOT NULL,
        public_key TEXT,
        UNIQUE (node_id, wg_id),
        UNIQUE (client_id, node_id)
    );
    INSERT INTO profiles(client_id, node_id, wg_id, public_key) SELECT id, node_id, wg_id, public_key FROM clients;
    DROP TABLE clients;
    ALTER TABLE clients_new RENAME TO clients;
    CREATE UNIQUE INDEX clients_ipv4 ON clients(ipv4) WHERE ipv4 IS NOT NULL AND deleted = 0;
    DROP TABLE traffic_last;
    CREATE TABLE traffic_last (
        profile_id INTEGER PRIMARY KEY REFERENCES profiles(id) ON DELETE CASCADE,
        rx         INTEGER NOT NULL,
        tx         INTEGER NOT NULL,
        ts         INTEGER NOT NULL
    );
    """,
    # 9 — скрытый постоянный ID клиента: различает клиентов с одинаковыми именами,
    # записывается агентам нод и связывает профили при восстановлении
    """
    ALTER TABLE clients ADD COLUMN uid TEXT;
    UPDATE clients SET uid = lower(hex(randomblob(4))) WHERE uid IS NULL;
    CREATE UNIQUE INDEX clients_uid ON clients(uid);
    """,
]

_conn: sqlite3.Connection | None = None
_lock = threading.RLock()


def connect():
    global _conn
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    _conn = sqlite3.connect(config.DB_FILE, check_same_thread=False, isolation_level=None)
    _conn.row_factory = sqlite3.Row
    _conn.execute("PRAGMA journal_mode=WAL")
    _conn.execute("PRAGMA foreign_keys=ON")
    _migrate()


def _migrate():
    with tx() as c:
        version = c.execute("PRAGMA user_version").fetchone()[0]
        if version >= len(MIGRATIONS):
            return
        # Пересборка таблиц (миграция 8) с включёнными внешними ключами каскадно удалила бы
        # связанные строки; PRAGMA foreign_keys меняется только вне транзакции.
        c.execute("PRAGMA foreign_keys=OFF")
        try:
            for i, sql in enumerate(MIGRATIONS[version:], start=version + 1):
                c.executescript(f"BEGIN; {sql}; PRAGMA user_version={i}; COMMIT;")
            bad = c.execute("PRAGMA foreign_key_check").fetchall()
            if bad:
                raise RuntimeError(f"нарушены внешние ключи после миграции: {bad[:5]}")
        finally:
            c.execute("PRAGMA foreign_keys=ON")


@contextmanager
def tx():
    """Соединение под блокировкой процесса. Транзакцию открывает вызывающий при необходимости."""
    with _lock:
        yield _conn


def query(sql, args=()):
    with tx() as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]


def one(sql, args=()):
    rows = query(sql, args)
    return rows[0] if rows else None


def execute(sql, args=()):
    with tx() as c:
        cur = c.execute(sql, args)
        return cur.lastrowid


# ── настройки (JSON в key/value) ────────────────────────────────
def get_setting(key, default=None):
    row = one("SELECT value FROM settings WHERE key=?", (key,))
    return json.loads(row["value"]) if row else default


def set_setting(key, value):
    execute("INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, json.dumps(value)))
