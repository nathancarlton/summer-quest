"""Persistence: a tiny key/value JSON store with two backends.

Default is SQLite at data/quest.db — zero setup for local dev. Set
DATABASE_URL to a Postgres URL for production: Koyeb/Zeabur free instances
have EPHEMERAL disks (wiped on redeploy and scale-to-zero), so the kids' XP
only survives if it lives in a real database. Both platforms (and Neon)
offer a free Postgres that works here unchanged.

Keys in use:
  player:{id}   -> full profile JSON (same shape the CLI stores locally)
  quest:{id}    -> an in-flight session (questions WITH answers, results so far)
  pool:{pid}    -> pre-generated themed sessions for that player
  history:{pid} -> list of completed-session summaries
"""
import json
import os
import sqlite3
import threading

from quest import config

DATABASE_URL = os.getenv("DATABASE_URL", "")


class SQLiteStore:
    def __init__(self, path):
        self.path = str(path)
        self._lock = threading.Lock()  # sqlite writers must not interleave
        with self._connect() as c:
            c.execute(
                "CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )

    def _connect(self):
        return sqlite3.connect(self.path)

    def get(self, key):
        with self._connect() as c:
            row = c.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def set(self, key, value):
        with self._lock, self._connect() as c:
            c.execute("INSERT OR REPLACE INTO kv (key, value) VALUES (?, ?)", (key, value))

    def delete(self, key):
        with self._lock, self._connect() as c:
            c.execute("DELETE FROM kv WHERE key = ?", (key,))

    def keys(self, prefix):
        with self._connect() as c:
            rows = c.execute(
                "SELECT key FROM kv WHERE key LIKE ?", (prefix + "%",)
            ).fetchall()
        return [r[0] for r in rows]


class PostgresStore:
    """Postgres kv store with CONNECTION POOLING.

    A fresh connection per operation costs a full TLS handshake to the
    (possibly cross-region) database — ~300ms each, and one answered
    question touches the store ~5-7 times, which is where "why does
    clicking A take 3 seconds?" came from. The pool keeps a few
    connections warm so each op is just a query round trip."""

    def __init__(self, url):
        # Imported lazily so local dev (SQLite) never needs these packages.
        from psycopg_pool import ConnectionPool

        self.pool = ConnectionPool(
            url,
            min_size=0,
            max_size=5,  # single free-tier instance; Supabase pooler-friendly
            open=True,
            kwargs={"autocommit": True},
        )
        with self.pool.connection() as c:
            c.execute(
                "CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )

    def get(self, key):
        with self.pool.connection() as c:
            row = c.execute("SELECT value FROM kv WHERE key = %s", (key,)).fetchone()
        return row[0] if row else None

    def set(self, key, value):
        with self.pool.connection() as c:
            c.execute(
                "INSERT INTO kv (key, value) VALUES (%s, %s) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                (key, value),
            )

    def delete(self, key):
        with self.pool.connection() as c:
            c.execute("DELETE FROM kv WHERE key = %s", (key,))

    def keys(self, prefix):
        with self.pool.connection() as c:
            rows = c.execute(
                "SELECT key FROM kv WHERE key LIKE %s", (prefix + "%",)
            ).fetchall()
        return [r[0] for r in rows]


def _make_store():
    if DATABASE_URL:
        return PostgresStore(DATABASE_URL)
    return SQLiteStore(config.DATA_DIR / "quest.db")


store = _make_store()


def get_json(key, default=None):
    raw = store.get(key)
    return json.loads(raw) if raw is not None else default


def set_json(key, value):
    store.set(key, json.dumps(value))
