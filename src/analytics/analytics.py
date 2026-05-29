import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from src.database.db import db

logger = logging.getLogger(__name__)


class AnalyticsEngine:
    def __init__(self):
        self._hourly_task = None
        self._running = False

    async def record_query(
        self,
        session_id: str,
        game: str,
        platform: str = "api",
        response_ms: float = 0.0,
        error: bool = False,
    ):
        now = datetime.utcnow()
        hour_key = now.strftime("%Y-%m-%dT%H:00:00")
        date_key = now.strftime("%Y-%m-%d")

        await db.connect()
        async with db._conn.execute(
            "SELECT query_count, avg_response_ms, error_count FROM analytics_hourly WHERE hour = ? AND game = ? AND platform = ?",
            (hour_key, game, platform),
        ) as cursor:
            row = await cursor.fetchone()

        if row:
            old_q = row["query_count"]
            old_ms = row["avg_response_ms"]
            old_e = row["error_count"]
            new_q = old_q + 1
            new_ms = (old_ms * old_q + response_ms) / new_q if response_ms else old_ms
            new_e = old_e + (1 if error else 0)
            await db._conn.execute(
                "UPDATE analytics_hourly SET query_count = ?, avg_response_ms = ?, error_count = ? WHERE hour = ? AND game = ? AND platform = ?",
                (new_q, new_ms, new_e, hour_key, game, platform),
            )
        else:
            await db._conn.execute(
                "INSERT OR IGNORE INTO analytics_hourly (hour, game, platform, query_count, avg_response_ms, error_count, unique_sessions) VALUES (?, ?, ?, 1, ?, ?, 1)",
                (hour_key, game, platform, response_ms, 1 if error else 0),
            )
        await db._conn.commit()

    async def get_popular_games(self, days: int = 7, limit: int = 20) -> list:
        await db.connect()
        cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        cursor = await db._conn.execute(
            """SELECT game, SUM(query_count) as total_queries,
                      AVG(avg_response_ms) as avg_ms,
                      COUNT(DISTINCT date) as active_days
               FROM analytics_daily
               WHERE date >= ? AND game != ''
               GROUP BY game
               ORDER BY total_queries DESC
               LIMIT ?""",
            (cutoff, limit),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_daily_stats(self, days: int = 14) -> list:
        await db.connect()
        cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        cursor = await db._conn.execute(
            """SELECT date, SUM(query_count) as total_queries,
                      COALESCE(AVG(avg_response_ms), 0) as avg_ms,
                      SUM(error_count) as total_errors
               FROM analytics_daily
               WHERE date >= ?
               GROUP BY date
               ORDER BY date ASC""",
            (cutoff,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_platform_stats(self) -> dict:
        await db.connect()
        cursor = await db._conn.execute(
            """SELECT platform, SUM(query_count) as total_queries,
                      AVG(avg_response_ms) as avg_ms
               FROM analytics_daily
               WHERE date >= ?
               GROUP BY platform""",
            ((datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d"),),
        )
        rows = await cursor.fetchall()
        return {r["platform"]: dict(r) for r in rows}

    async def get_top_queries(self, days: int = 7, limit: int = 20) -> list:
        await db.connect()
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        cursor = await db._conn.execute(
            """SELECT query, game, COUNT(*) as frequency,
                      AVG(processing_time_ms) as avg_ms
               FROM queries
               WHERE created_at >= ? AND query != ''
               GROUP BY query, game
               ORDER BY frequency DESC
               LIMIT ?""",
            (cutoff, limit),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_hourly_trend(self, hours: int = 24) -> list:
        await db.connect()
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:00:00")
        cursor = await db._conn.execute(
            """SELECT hour, SUM(query_count) as queries, AVG(avg_response_ms) as avg_ms
               FROM analytics_hourly
               WHERE hour >= ?
               GROUP BY hour
               ORDER BY hour ASC""",
            (cutoff,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_summary(self) -> dict:
        await db.connect()
        out = {"total_queries": 0, "total_sessions": 0, "games_detected": 0, "avg_response_ms": 0}

        cursor = await db._conn.execute("SELECT COUNT(*) as c FROM sessions")
        row = await cursor.fetchone()
        out["total_sessions"] = row["c"]

        cursor = await db._conn.execute("SELECT COUNT(*) as c FROM queries")
        row = await cursor.fetchone()
        out["total_queries"] = row["c"]

        cursor = await db._conn.execute(
            "SELECT COUNT(DISTINCT game) as c FROM queries WHERE game != ''"
        )
        row = await cursor.fetchone()
        out["games_detected"] = row["c"]

        cursor = await db._conn.execute(
            "SELECT AVG(processing_time_ms) as avg FROM queries WHERE processing_time_ms > 0"
        )
        row = await cursor.fetchone()
        out["avg_response_ms"] = round(row["avg"] or 0, 1)

        cursor = await db._conn.execute(
            "SELECT platform, is_active FROM platform_status"
        )
        rows = await cursor.fetchall()
        out["platforms"] = {r["platform"]: bool(r["is_active"]) for r in rows}

        return out

    async def start_hourly_rollup(self):
        if self._running:
            return
        self._running = True
        logger.info("Analytics hourly rollup started")
        try:
            while self._running:
                await asyncio.sleep(3600)
                await self._rollup_hourly_to_daily()
        except asyncio.CancelledError:
            pass
        finally:
            self._running = False

    async def _rollup_hourly_to_daily(self):
        await db.connect()
        yesterday = (datetime.utcnow() - timedelta(hours=1)).strftime("%Y-%m-%d")
        cursor = await db._conn.execute(
            """SELECT SUBSTR(hour, 1, 10) as date, game, platform,
                      SUM(query_count) as total_q, AVG(avg_response_ms) as avg_ms,
                      SUM(error_count) as total_e, SUM(unique_sessions) as total_s
               FROM analytics_hourly
               WHERE hour LIKE ?
               GROUP BY date, game, platform""",
            (f"{yesterday}%",),
        )
        rows = await cursor.fetchall()
        for row in rows:
            await db._conn.execute(
                """INSERT OR REPLACE INTO analytics_daily
                   (date, game, platform, query_count, avg_response_ms, error_count, unique_sessions)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (row["date"], row["game"], row["platform"],
                 row["total_q"], row["avg_ms"] or 0,
                 row["total_e"], row["total_s"]),
            )
        await db._conn.commit()
        logger.info(f"Rolled up {len(rows)} analytics rows for {yesterday}")

    def stop(self):
        self._running = False

    async def log_alert(self, level: str, source: str, message: str, details: dict = None):
        await db.connect()
        now = datetime.utcnow().isoformat()
        await db._conn.execute(
            "INSERT INTO alerts (level, source, message, details, created_at) VALUES (?, ?, ?, ?, ?)",
            (level, source, message, json.dumps(details or {}), now),
        )
        await db._conn.commit()

    async def get_alerts(self, limit: int = 50, unread_only: bool = False) -> list:
        await db.connect()
        where = "WHERE is_read = 0" if unread_only else ""
        cursor = await db._conn.execute(
            f"SELECT * FROM alerts {where} ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def mark_alerts_read(self, alert_ids: list[int] = None):
        await db.connect()
        if alert_ids:
            placeholders = ",".join("?" for _ in alert_ids)
            await db._conn.execute(
                f"UPDATE alerts SET is_read = 1 WHERE id IN ({placeholders})",
                alert_ids,
            )
        else:
            await db._conn.execute("UPDATE alerts SET is_read = 1 WHERE is_read = 0")
        await db._conn.commit()

    async def update_platform_status(self, platform: str, active: bool, error: str = ""):
        await db.connect()
        now = datetime.utcnow().isoformat()
        await db._conn.execute(
            """INSERT OR REPLACE INTO platform_status
               (platform, is_active, started_at, stopped_at, error_message)
               VALUES (?, ?, COALESCE((SELECT started_at FROM platform_status WHERE platform = ?), ?),
                       CASE WHEN ? THEN NULL ELSE ? END, ?)""",
            (platform, 1 if active else 0,
             platform, now if active else "",
             active, now if not active else "",
             error),
        )
        await db._conn.commit()
