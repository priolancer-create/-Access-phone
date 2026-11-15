"""PostgreSQL access layer (asyncpg)."""
from __future__ import annotations

import json

import asyncpg

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  telegram_id BIGINT PRIMARY KEY, username TEXT, first_name TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW());
CREATE TABLE IF NOT EXISTS captures(
  id BIGSERIAL PRIMARY KEY,
  telegram_id BIGINT REFERENCES users(telegram_id) ON DELETE CASCADE,
  telegram_file_id TEXT NOT NULL, mime_type TEXT NOT NULL,
  byte_size INTEGER NOT NULL, metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  consented_at TIMESTAMPTZ DEFAULT NOW());
ALTER TABLE captures ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE captures ADD COLUMN IF NOT EXISTS photo_message_id BIGINT;
ALTER TABLE captures ADD COLUMN IF NOT EXISTS report_message_id BIGINT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS lang TEXT NOT NULL DEFAULT 'bn';
ALTER TABLE users ADD COLUMN IF NOT EXISTS detailed BOOLEAN NOT NULL DEFAULT TRUE;
CREATE INDEX IF NOT EXISTS captures_user_idx ON captures(telegram_id, id DESC);
CREATE INDEX IF NOT EXISTS captures_time_idx ON captures(consented_at);
"""


class Database:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.pool: asyncpg.Pool | None = None

    async def connect(self):
        async def _init(conn):
            await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads,
                                      schema="pg_catalog")
        self.pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=8, init=_init)
        async with self.pool.acquire() as c:
            await c.execute(SCHEMA)

    async def close(self):
        if self.pool:
            await self.pool.close()

    async def ping(self) -> bool:
        try:
            async with self.pool.acquire() as c:
                return await c.fetchval("SELECT 1") == 1
        except Exception:
            return False

    # ---- users
    async def upsert_user(self, uid, username, first_name, language_code=None):
        lang = "en" if (language_code and not language_code.lower().startswith("bn")) else "bn"
        async with self.pool.acquire() as c:
            return await c.fetchrow(
                """INSERT INTO users(telegram_id,username,first_name,lang) VALUES($1,$2,$3,$4)
                   ON CONFLICT(telegram_id) DO UPDATE SET username=EXCLUDED.username,
                   first_name=EXCLUDED.first_name RETURNING lang, detailed""",
                uid, username, first_name, lang)

    async def set_lang(self, uid, lang):
        async with self.pool.acquire() as c:
            return await c.fetchrow(
                "UPDATE users SET lang=$2 WHERE telegram_id=$1 RETURNING lang, detailed", uid, lang)

    async def set_detailed(self, uid, value: bool):
        async with self.pool.acquire() as c:
            return await c.fetchrow(
                "UPDATE users SET detailed=$2 WHERE telegram_id=$1 RETURNING lang, detailed", uid, value)

    # ---- captures
    async def add_capture(self, uid, file_id, mime, size, meta, photo_mid, report_mid):
        async with self.pool.acquire() as c:
            return await c.fetchval(
                """INSERT INTO captures(telegram_id,telegram_file_id,mime_type,byte_size,metadata,
                   photo_message_id,report_message_id) VALUES($1,$2,$3,$4,$5,$6,$7) RETURNING id""",
                uid, file_id, mime, size, meta, photo_mid, report_mid)

    async def today_count(self, uid) -> int:
        async with self.pool.acquire() as c:
            return await c.fetchval(
                "SELECT COUNT(*) FROM captures WHERE telegram_id=$1 AND consented_at > NOW() - INTERVAL '24 hours'", uid)

    async def count_captures(self, uid) -> int:
        async with self.pool.acquire() as c:
            return await c.fetchval("SELECT COUNT(*) FROM captures WHERE telegram_id=$1", uid)

    async def list_captures(self, uid, limit, offset):
        async with self.pool.acquire() as c:
            return await c.fetch(
                """SELECT id, consented_at, byte_size FROM captures WHERE telegram_id=$1
                   ORDER BY id DESC LIMIT $2 OFFSET $3""", uid, limit, offset)

    async def get_capture(self, uid, cid):
        async with self.pool.acquire() as c:
            return await c.fetchrow(
                "SELECT id, telegram_file_id, consented_at FROM captures WHERE id=$1 AND telegram_id=$2", cid, uid)

    async def delete_capture(self, uid, cid):
        async with self.pool.acquire() as c:
            return await c.fetchrow(
                """DELETE FROM captures WHERE id=$1 AND telegram_id=$2
                   RETURNING photo_message_id, report_message_id""", cid, uid)

    async def erase_user(self, uid):
        """Delete every record and the user row; return (count, message_ids)."""
        async with self.pool.acquire() as c:
            async with c.transaction():
                rows = await c.fetch(
                    "DELETE FROM captures WHERE telegram_id=$1 RETURNING photo_message_id, report_message_id", uid)
                await c.execute("DELETE FROM users WHERE telegram_id=$1", uid)
        ids = [m for r in rows for m in (r["photo_message_id"], r["report_message_id"]) if m]
        return len(rows), ids

    async def export_user(self, uid):
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                "SELECT id, consented_at, mime_type, byte_size, metadata FROM captures WHERE telegram_id=$1 ORDER BY id", uid)
        return [{"id": r["id"], "submitted_at": r["consented_at"].isoformat(), "mime": r["mime_type"],
                 "bytes": r["byte_size"], "metadata": r["metadata"]} for r in rows]

    async def stats(self):
        async with self.pool.acquire() as c:
            return await c.fetchrow(
                """SELECT (SELECT COUNT(*) FROM users) AS users, COUNT(*) AS captures,
                   COUNT(*) FILTER (WHERE consented_at > NOW() - INTERVAL '24 hours') AS day,
                   COUNT(*) FILTER (WHERE consented_at > NOW() - INTERVAL '7 days') AS week,
                   COALESCE(SUM(byte_size),0) AS bytes FROM captures""")

    async def purge_older_than(self, days: int) -> int:
        async with self.pool.acquire() as c:
            return await c.fetchval(
                """WITH d AS (DELETE FROM captures WHERE consented_at < NOW() - make_interval(days => $1)
                   RETURNING 1) SELECT COUNT(*) FROM d""", days)
