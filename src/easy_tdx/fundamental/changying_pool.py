"""长盈标的池本地沉淀（V591）。

设计目标：
- 凌晨系统空闲时用 TDX 在线数据做一次全市场排序检索，把 top 20 长盈标的
  连同评分明细沉淀到本地 SQLite；白天前端直接读本地池，避免反复打 TDX。
- 市值低于 100 亿的标的直接排除（硬门槛）。
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from easy_tdx.client import TdxClient

logger = logging.getLogger(__name__)

# 默认硬门槛：总市值 >= 100 亿元
DEFAULT_MIN_MCAP_YI = 100.0
DEFAULT_TOP_N = 20
# 候选窗口倍数：scan_market 内部按 top_n 的 5 倍取候选窗口算市值，
# 20 只 → 最多对 100 只候选取价，压力可控。
_CAND_WINDOW_FACTOR = 5


def _config_dir() -> Path:
    return Path(os.environ.get("EASY_TDX_CONFIG_DIR", str(Path.home() / ".easy_tdx")))


def _db_path() -> Path:
    return _config_dir() / "changying_pool.db"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ChangyingStore:
    """长盈标的池 SQLite 存储（全量替换，保留最新一份快照）。"""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or _db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS changying_pool (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    updated_at TEXT NOT NULL,
                    trade_date TEXT NOT NULL,
                    symbol TEXT NOT NULL UNIQUE,
                    market TEXT NOT NULL,
                    code TEXT NOT NULL,
                    category TEXT NOT NULL,
                    score REAL NOT NULL,
                    total_mcap_yi REAL,
                    close REAL,
                    report_date TEXT,
                    data_source TEXT,
                    scores_json TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    indicators_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_changying_pool_category ON changying_pool(category)"
            )

    def save_pool(self, trade_date: str, results: list[dict[str, Any]]) -> dict[str, Any]:
        """全量替换标的池，返回快照元信息。"""
        updated_at = _now_iso()
        with self._connect() as conn:
            conn.execute("DELETE FROM changying_pool")
            for r in results:
                score = float(
                    r.get(
                        "score",
                        r.get("scores", {}).get(r.get("category", ""), 0) or 0,
                    )
                )
                conn.execute(
                    """
                    INSERT INTO changying_pool (
                        updated_at, trade_date, symbol, market, code, category, score,
                        total_mcap_yi, close, report_date, data_source,
                        scores_json, details_json, indicators_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        updated_at,
                        trade_date,
                        f"{r.get('market', '')}:{r.get('code', '')}",
                        r.get("market", ""),
                        r.get("code", ""),
                        r.get("category", ""),
                        score,
                        r.get("total_mcap_yi"),
                        (r.get("performance") or {}).get("as_of_close"),
                        r.get("report_date"),
                        r.get("data_source", "gpcw"),
                        json.dumps(r.get("scores", {}), ensure_ascii=False),
                        json.dumps(r.get("details", {}), ensure_ascii=False),
                        json.dumps(r.get("indicators", {}), ensure_ascii=False),
                    ),
                )
        return {"updated_at": updated_at, "trade_date": trade_date, "count": len(results)}

    def load_pool(self) -> dict[str, Any] | None:
        """读取最新快照（无数据返回 None）。"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM changying_pool ORDER BY score DESC, id ASC"
            ).fetchall()
        if not rows:
            return None
        first = rows[0]
        results: list[dict[str, Any]] = []
        for row in rows:
            results.append(
                {
                    "symbol": row["symbol"],
                    "market": row["market"],
                    "code": row["code"],
                    "category": row["category"],
                    "score": row["score"],
                    "total_mcap_yi": row["total_mcap_yi"],
                    "close": row["close"],
                    "report_date": row["report_date"],
                    "data_source": row["data_source"],
                    "scores": json.loads(row["scores_json"]),
                    "details": json.loads(row["details_json"]),
                    "indicators": json.loads(row["indicators_json"]),
                }
            )
        return {
            "updated_at": first["updated_at"],
            "date": first["trade_date"],
            "total": len(results),
            "results": results,
        }


def _refresh(
    target: date,
    *,
    markets: tuple[str, ...],
    top_n: int,
    min_mcap_yi: float,
    min_score: float,
    client: TdxClient | None,
) -> dict[str, Any]:
    from easy_tdx.fundamental.pipeline import scan_market

    # scan_market 内部：候选窗口 = top_n * 5（至少 100），先算市值过滤再截 top_n
    out = scan_market(
        target,
        markets=markets,
        stock_type="all",
        top_n=top_n,
        min_score=min_score,
        # V597: 池构建只需要评分 + 市值，不需要后续表现（后续表现会逐只打标准主机，
        # 慢且取不到）；择时在第二步用 MAC 单独算。
        with_performance=False,
        client=client,
        min_mcap_yi=min_mcap_yi,
        require_profit=True,
    )
    results = out.get("results") or []
    # 统一字段，前端直接消费
    for r in results:
        if "total_mcap_yi" not in r:
            r["total_mcap_yi"] = None
    return {
        "date": out.get("date"),
        "season": out.get("season"),
        "by_category": out.get("by_category"),
        "total_scanned": out.get("total_scanned"),
        "results": results,
    }


def refresh_changying_pool(
    target: date | None = None,
    *,
    markets: tuple[str, ...] = ("SH", "SZ"),
    top_n: int = DEFAULT_TOP_N,
    min_mcap_yi: float = DEFAULT_MIN_MCAP_YI,
    min_score: float = 15.0,
    client: TdxClient | None = None,
) -> dict[str, Any]:
    """跑一次完整刷新并把结果沉淀到本地。"""
    target = target or date.today()
    refreshed = _refresh(
        target,
        markets=markets,
        top_n=top_n,
        min_mcap_yi=min_mcap_yi,
        min_score=min_score,
        client=client,
    )
    store = ChangyingStore()
    meta = store.save_pool(str(target), refreshed["results"])
    return {
        **meta,
        "min_mcap_yi": min_mcap_yi,
        "top_n": top_n,
        "season": refreshed.get("season"),
        "by_category": refreshed.get("by_category"),
        "total_scanned": refreshed.get("total_scanned"),
        "results": refreshed["results"],
    }


def load_changying_pool() -> dict[str, Any] | None:
    """读取本地沉淀池（供 Web 白天快速读取）。"""
    return ChangyingStore().load_pool()
