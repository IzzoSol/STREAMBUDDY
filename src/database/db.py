import asyncio
import json
import sqlite3
import hashlib
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import aiosqlite

from src.config import config

logger = logging.getLogger(__name__)

DB_PATH = Path(config.data_dir) / "game_assist.db"
SCHEMA_PATH = Path(__file__).parent / "models.py"


class Database:
    _instance: Optional["Database"] = None
    _conn: Optional[aiosqlite.Connection] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def connect(self):
        if self._conn is not None:
            return

        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(str(DB_PATH))
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        await self._init_schema()

    async def _init_schema(self):
        schema = SCHEMA_PATH.read_text(encoding="utf-8")
        for statement in schema.split(";"):
            stmt = statement.strip()
            if stmt:
                try:
                    await self._conn.execute(stmt)
                except Exception as e:
                    logger.warning(f"Schema exec warning: {e}")
        await self._conn.commit()

    async def close(self):
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def get_or_create_session(self, session_id: str) -> dict:
        await self.connect()
        now = datetime.utcnow().isoformat()

        cursor = await self._conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        )
        row = await cursor.fetchone()

        if row is None:
            await self._conn.execute(
                "INSERT INTO sessions (id, created_at, updated_at) VALUES (?, ?, ?)",
                (session_id, now, now),
            )
            await self._conn.commit()
            return {"id": session_id, "game": "", "created_at": now, "updated_at": now, "query_count": 0}
        return dict(row)

    async def save_query(self, session_id: str, result: dict):
        await self.connect()
        now = datetime.utcnow().isoformat()

        await self._conn.execute(
            """INSERT INTO queries
               (session_id, query, game, topic, answer, confidence,
                sources, processing_time_ms, vision_data,
                web_results, reddit_results, wiki_results, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id,
                result.get("query", ""),
                result.get("game", ""),
                result.get("topic", ""),
                result.get("answer", ""),
                result.get("confidence", 0.0),
                json.dumps(result.get("sources", [])),
                result.get("processing_time_ms", 0.0),
                json.dumps(result.get("vision_analysis", {})),
                json.dumps(result.get("web_results", [])),
                json.dumps(result.get("reddit_results", [])),
                json.dumps(result.get("wiki_results", [])),
                now,
            ),
        )

        await self._conn.execute(
            "UPDATE sessions SET query_count = query_count + 1, updated_at = ? WHERE id = ?",
            (now, session_id),
        )
        await self._conn.commit()

    async def get_session_history(self, session_id: str, limit: int = 20) -> list[dict]:
        await self.connect()
        cursor = await self._conn.execute(
            "SELECT * FROM queries WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
            (session_id, limit),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_cached(self, cache_key: str) -> Optional[str]:
        await self.connect()
        hashed = hashlib.sha256(cache_key.encode()).hexdigest()
        now = datetime.utcnow().isoformat()

        cursor = await self._conn.execute(
            "SELECT response FROM cache WHERE cache_key = ? AND expires_at > ?",
            (hashed, now),
        )
        row = await cursor.fetchone()
        return row["response"] if row else None

    async def set_cache(self, cache_key: str, response: str, ttl_seconds: int = 86400):
        await self.connect()
        hashed = hashlib.sha256(cache_key.encode()).hexdigest()
        now = datetime.utcnow()
        expires = (now + timedelta(seconds=ttl_seconds)).isoformat()

        await self._conn.execute(
            "INSERT OR REPLACE INTO cache (cache_key, response, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (hashed, response, now.isoformat(), expires),
        )
        await self._conn.commit()

    async def validate_api_key(self, api_key: str) -> Optional[dict]:
        await self.connect()
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()

        cursor = await self._conn.execute(
            "SELECT * FROM api_keys WHERE key_hash = ? AND is_active = 1",
            (key_hash,),
        )
        row = await cursor.fetchone()

        if row:
            now = datetime.utcnow().isoformat()
            await self._conn.execute(
                "UPDATE api_keys SET last_used_at = ? WHERE id = ?",
                (now, row["id"]),
            )
            await self._conn.commit()
            return dict(row)
        return None

    async def create_api_key(self, label: str, tier: str = "free") -> str:
        await self.connect()
        import secrets

        raw_key = f"ga_{secrets.token_hex(24)}"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        now = datetime.utcnow().isoformat()

        await self._conn.execute(
            "INSERT INTO api_keys (key_hash, label, tier, created_at) VALUES (?, ?, ?, ?)",
            (key_hash, label, tier, now),
        )
        await self._conn.commit()
        return raw_key

    async def save_game_context(self, session_id: str, game: str, scene: str = "", objectives: list = None):
        await self.connect()
        now = datetime.utcnow().isoformat()

        await self._conn.execute(
            """INSERT INTO game_context (session_id, game_name, scene, objectives, last_seen_at)
               VALUES (?, ?, ?, ?, ?)""",
            (session_id, game, scene, json.dumps(objectives or []), now),
        )
        await self._conn.commit()

    async def get_game_context(self, session_id: str) -> Optional[dict]:
        await self.connect()
        cursor = await self._conn.execute(
            "SELECT * FROM game_context WHERE session_id = ? ORDER BY last_seen_at DESC LIMIT 1",
            (session_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


db = Database()
