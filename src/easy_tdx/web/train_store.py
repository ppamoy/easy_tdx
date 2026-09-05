"""缠论「逐步揭示训练」成绩的 SQLite 持久化（P0 训练页 → 排行榜）。

设计要点（与 strategy_store.py 同风格）：
- 单文件 SQLite，落在统一配置目录（~/.easy_tdx/train_scores.db，
  随 EASY_TDX_CONFIG_DIR 环境变量走）；
- 只提供「提交 / 排行榜 / 全部 / 清空」四个动作；
- 线程安全：公共方法内部短连接（check_same_thread=False）+ 写操作串行
  （SQLite 单写者锁兜底），适配 FastAPI 线程池；
- 排行榜按得分降序，命中率作次要排序，供前端「🏆 训练排行榜」展示。
"""

from __future__ import annotations

import os
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = ["TrainScore", "TrainScoreStore", "get_score_store"]

# 写操作串行锁：SQLite 单写者，多线程并发写时避免 "database is locked"。
_write_lock = threading.Lock()


def _config_dir() -> Path:
    """返回统一配置目录（与 config.py 同约定，受 EASY_TDX_CONFIG_DIR 覆盖）。"""
    return Path(os.environ.get("EASY_TDX_CONFIG_DIR", str(Path.home() / ".easy_tdx")))


def _default_db_path() -> Path:
    return _config_dir() / "train_scores.db"


def _now_iso() -> str:
    """UTC ISO8601 时间戳（带 Z 后缀，JSON 友好）。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class TrainScore:
    """一轮逐步揭示训练的成绩记录。

    - score：得分（方向命中 + 精确命中加分）；
    - hit_rate：方向命中率（0~100），二次排序键；
    - code / market / category / count：本轮训练标的与参数，方便按标的复习。
    """

    score: float
    player_name: str = "学员"
    code: str = ""
    market: str = "SZ"
    category: str = "DAY"
    difficulty: str = "medium"
    count: int = 400
    total_asked: int = 0
    hit_count: int = 0
    hit_rate: float = 0.0
    created_at: str = ""
    id: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "player_name": self.player_name,
            "score": self.score,
            "hit_rate": self.hit_rate,
            "total_asked": self.total_asked,
            "hit_count": self.hit_count,
            "code": self.code,
            "market": self.market,
            "category": self.category,
            "difficulty": self.difficulty,
            "count": self.count,
            "created_at": self.created_at,
            "extra": self.extra,
        }

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> TrainScore:
        import json

        return cls(
            id=row["id"],
            player_name=row["player_name"],
            score=row["score"],
            hit_rate=row["hit_rate"],
            total_asked=row["total_asked"],
            hit_count=row["hit_count"],
            code=row["code"],
            market=row["market"],
            category=row["category"],
            difficulty=row["difficulty"] if "difficulty" in row.keys() else "medium",
            count=row["count"],
            created_at=row["created_at"],
            extra=json.loads(row["extra"]) if row["extra"] else {},
        )


class TrainScoreStore:
    """训练成绩的 SQLite 存储（提交 / 排行榜 / 全部 / 清空）。

    单例由 :func:`get_score_store` 提供；测试注入独立 db_path（tmp_path）。
    """

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS train_scores (
        id          TEXT PRIMARY KEY,
        player_name TEXT NOT NULL DEFAULT '学员',
        score       REAL NOT NULL,
        hit_rate    REAL NOT NULL DEFAULT 0,
        total_asked INTEGER NOT NULL DEFAULT 0,
        hit_count   INTEGER NOT NULL DEFAULT 0,
        code        TEXT NOT NULL DEFAULT '',
        market      TEXT NOT NULL DEFAULT 'SZ',
        category    TEXT NOT NULL DEFAULT 'DAY',
        difficulty  TEXT NOT NULL DEFAULT 'medium',
        count       INTEGER NOT NULL DEFAULT 400,
        created_at  TEXT NOT NULL DEFAULT '',
        extra       TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_train_score      ON train_scores(score DESC);
    CREATE INDEX IF NOT EXISTS idx_train_created    ON train_scores(created_at DESC);
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or _default_db_path()
        self._ensure_schema()

    # ── 内部 ─────────────────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(self._SCHEMA)
            # V424: 幂等迁移——旧库补 difficulty 列
            cols = {r[1] for r in conn.execute("PRAGMA table_info(train_scores)")}
            if "difficulty" not in cols:
                conn.execute(
                    "ALTER TABLE train_scores "
                    "ADD COLUMN difficulty TEXT NOT NULL DEFAULT 'medium'"
                )

    @staticmethod
    def _new_id() -> str:
        return uuid.uuid4().hex[:12]

    # ── 公共 API ─────────────────────────────────────────────────────

    def add(self, record: TrainScore) -> TrainScore:
        """提交一条训练成绩；id / created_at 为空时自动填充。"""
        if not record.id:
            record.id = self._new_id()
        if not record.created_at:
            record.created_at = _now_iso()
        import json

        with _write_lock, self._connect() as conn:
            conn.execute(
                """INSERT INTO train_scores
                   (id, player_name, score, hit_rate, total_asked, hit_count,
                    code, market, category, difficulty, count, created_at, extra)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.id,
                    record.player_name,
                    record.score,
                    record.hit_rate,
                    record.total_asked,
                    record.hit_count,
                    record.code,
                    record.market,
                    record.category,
                    record.difficulty,
                    record.count,
                    record.created_at,
                    json.dumps(record.extra, ensure_ascii=False),
                ),
            )
        return record

    def leaderboard(
        self,
        *,
        limit: int = 20,
        category: str | None = None,
        difficulty: str | None = None,
    ) -> list[TrainScore]:
        """返回排行榜：得分降序、命中率降序，可限定周期/难度。"""
        sql = "SELECT * FROM train_scores"
        params: list[Any] = []
        conds: list[str] = []
        if category:
            conds.append("category = ?")
            params.append(category)
        if difficulty:
            conds.append("difficulty = ?")
            params.append(difficulty)
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        sql += " ORDER BY score DESC, hit_rate DESC, created_at DESC LIMIT ?"
        params.append(int(limit))
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [TrainScore.from_row(r) for r in rows]

    def summary(
        self,
        *,
        category: str | None = None,
        difficulty: str | None = None,
    ) -> dict[str, Any]:
        """V424: 排行榜分组汇总（总人数/平均命中率/最高分）。"""
        sql = (
            "SELECT COUNT(*) AS n, AVG(hit_rate) AS avg_hit, "
            "MAX(score) AS max_score FROM train_scores"
        )
        params: list[Any] = []
        conds: list[str] = []
        if category:
            conds.append("category = ?")
            params.append(category)
        if difficulty:
            conds.append("difficulty = ?")
            params.append(difficulty)
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        with self._connect() as conn:
            row = conn.execute(sql, params).fetchone()
        return {
            "count": row["n"] or 0,
            "avg_hit_rate": round(row["avg_hit"] or 0.0, 1),
            "max_score": row["max_score"] or 0.0,
        }

    def progress(self, player: str) -> dict[str, Any]:
        """V424: 学习进度聚合——按 category×difficulty 统计命中率/题数。"""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT category, difficulty, COUNT(*) AS rounds,
                          SUM(total_asked) AS asked, SUM(hit_count) AS hit
                   FROM train_scores WHERE player_name = ?
                   GROUP BY category, difficulty""",
                (player,),
            ).fetchall()
        matrix: dict[str, dict[str, dict[str, Any]]] = {}
        for r in rows:
            cat = r["category"]
            diff = r["difficulty"]
            asked = r["asked"] or 0
            hit = r["hit"] or 0
            matrix.setdefault(cat, {})[diff] = {
                "rounds": r["rounds"],
                "total_asked": asked,
                "hit_count": hit,
                "hit_rate": round((hit / asked * 100) if asked else 0.0, 1),
            }
        return matrix

    def list_all(self) -> list[TrainScore]:
        """全部成绩，创建时间倒序（最近的在最前）。"""
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM train_scores ORDER BY created_at DESC").fetchall()
        return [TrainScore.from_row(r) for r in rows]

    def clear(self) -> int:
        """清空全部成绩，返回删除条数。"""
        with _write_lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM train_scores")
            return cur.rowcount


# ── 单例 ──────────────────────────────────────────────────────────────

_store: TrainScoreStore | None = None
_store_lock = threading.Lock()


def get_score_store() -> TrainScoreStore:
    """返回全局排行榜存储单例（首次调用惰性建库）。"""
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = TrainScoreStore()
    return _store
