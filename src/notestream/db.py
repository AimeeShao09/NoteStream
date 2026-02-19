from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Any

from loguru import logger

DEFAULT_DB_PATH = Path(".cache/notestream.db")


class CacheStore:
    def __init__(self, db_path: str | None = None) -> None:
        path = Path(db_path) if db_path else DEFAULT_DB_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS videos (
                video_id TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                title TEXT NOT NULL,
                channel TEXT NOT NULL,
                duration_seconds INTEGER,
                publish_date TEXT,
                thumbnail TEXT,
                description TEXT,
                transcript TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT NOT NULL,
                artifact_type TEXT NOT NULL,
                style TEXT NOT NULL,
                difficulty TEXT NOT NULL DEFAULT '',
                payload_hash TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(video_id, artifact_type, style, difficulty, payload_hash)
            )
            """
        )
        self._conn.commit()

    @staticmethod
    def payload_hash(payload: dict[str, Any]) -> str:
        normalized = "|".join(f"{k}={payload[k]}" for k in sorted(payload))
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def get_video(self, video_id: str) -> sqlite3.Row | None:
        cur = self._conn.execute("SELECT * FROM videos WHERE video_id = ?", (video_id,))
        return cur.fetchone()

    def upsert_video(self, row: dict[str, Any]) -> None:
        self._conn.execute(
            """
            INSERT INTO videos (
                video_id, url, title, channel, duration_seconds, publish_date,
                thumbnail, description, transcript, updated_at
            ) VALUES (
                :video_id, :url, :title, :channel, :duration_seconds, :publish_date,
                :thumbnail, :description, :transcript, CURRENT_TIMESTAMP
            )
            ON CONFLICT(video_id) DO UPDATE SET
                url=excluded.url,
                title=excluded.title,
                channel=excluded.channel,
                duration_seconds=excluded.duration_seconds,
                publish_date=excluded.publish_date,
                thumbnail=excluded.thumbnail,
                description=excluded.description,
                transcript=excluded.transcript,
                updated_at=CURRENT_TIMESTAMP
            """,
            row,
        )
        self._conn.commit()

    def get_artifact(
        self,
        video_id: str,
        artifact_type: str,
        style: str,
        difficulty: str | None,
        payload_hash: str,
    ) -> sqlite3.Row | None:
        cur = self._conn.execute(
            """
            SELECT * FROM artifacts
            WHERE video_id = ?
              AND artifact_type = ?
              AND style = ?
              AND difficulty = ?
              AND payload_hash = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (video_id, artifact_type, style, difficulty or "", payload_hash),
        )
        return cur.fetchone()

    def put_artifact(
        self,
        *,
        video_id: str,
        artifact_type: str,
        style: str,
        difficulty: str | None,
        payload_hash: str,
        content: str,
    ) -> None:
        try:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO artifacts (
                    video_id, artifact_type, style, difficulty, payload_hash, content
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (video_id, artifact_type, style, difficulty or "", payload_hash, content),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            logger.warning("Failed to cache artifact: {}", exc)


_cache_store: CacheStore | None = None


def get_cache_store(db_path: str | None = None) -> CacheStore:
    global _cache_store
    if _cache_store is None:
        _cache_store = CacheStore(db_path=db_path)
    return _cache_store
