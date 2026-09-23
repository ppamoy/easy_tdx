"""长盈全市场树/粮/菜标记（V722）。

与 changying_pool（top 20 精选池）的区别：

- 面向**全市场**总市值 >= 100 亿的标的，全部标记树/粮/菜并落库，
  不做 top-N 截断——白天前端读全量标记表，保证选股结果覆盖面。
- 财报对齐的**半年频**刷新（季报兜底），而不是每天重跑：树/粮/菜
  输入是 point-in-time 财报快照，披露季结束前不会变化。
- 半成品保护：本次合格标的数 < 上次成功快照 80% 时拒绝覆盖，
  防止行情主机中途故障导致白天读到半量数据。

存储：``~/.easy_tdx/changying_marks.db``（changying_marks + marks_meta 两表）。
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 默认硬门槛：总市值 >= 100 亿元（与 changying_pool 一致）
DEFAULT_MIN_MCAP_YI = 100.0
# 默认分类得分下限：与选股产品口径一致（只标记真正够格某一类的标的）。
# 传 0 可放宽为「有分类就标记」。
DEFAULT_MIN_SCORE = 15.0
# 半成品保护：本次合格标的数低于上次成功快照的该比例时拒绝覆盖
_HALF_GUARD_RATIO = 0.8


def _config_dir() -> Path:
    return Path(os.environ.get("EASY_TDX_CONFIG_DIR", str(Path.home() / ".easy_tdx")))


def _db_path() -> Path:
    return _config_dir() / "changying_marks.db"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ChangyingMarkStore:
    """长盈全市场标记 SQLite 存储（全量替换，保留最新一份快照）。"""

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
                CREATE TABLE IF NOT EXISTS changying_marks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    updated_at TEXT NOT NULL,
                    trade_date TEXT NOT NULL,
                    symbol TEXT NOT NULL UNIQUE,
                    market TEXT NOT NULL,
                    code TEXT NOT NULL,
                    category TEXT NOT NULL,
                    score REAL NOT NULL,
                    total_mcap_yi REAL,
                    report_date TEXT,
                    data_source TEXT,
                    scores_json TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    indicators_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_changying_marks_category"
                " ON changying_marks(category)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS marks_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )

    # ── 读取 ────────────────────────────────────────────────────────────

    def last_snapshot_meta(self) -> dict[str, Any] | None:
        """上次成功快照元信息（count/trade_date/updated_at），无数据返回 None。"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM marks_meta WHERE key = 'snapshot'"
            ).fetchone()
        if row is None:
            return None
        try:
            return dict(json.loads(row["value"]))
        except (ValueError, TypeError):
            return None

    def load_marks(
        self,
        *,
        stock_type: str | None = None,
        markets: list[str] | None = None,
        top_n: int | None = None,
    ) -> dict[str, Any] | None:
        """读取标记表（按得分降序），支持分类/市场过滤与 top_n 截断。

        返回形状与 changying_pool.load_pool 兼容，另含 by_category 统计。
        无数据返回 None。
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM changying_marks ORDER BY score DESC, symbol ASC"
            ).fetchall()
        if not rows:
            return None
        by_category: dict[str, int] = {}
        results: list[dict[str, Any]] = []
        for row in rows:
            if stock_type and row["category"] != stock_type:
                continue
            if markets and row["market"] not in markets:
                continue
            by_category[row["category"]] = by_category.get(row["category"], 0) + 1
            results.append(
                {
                    "symbol": row["symbol"],
                    "market": row["market"],
                    "code": row["code"],
                    "category": row["category"],
                    "score": row["score"],
                    "total_mcap_yi": row["total_mcap_yi"],
                    "report_date": row["report_date"],
                    "data_source": row["data_source"],
                    "scores": json.loads(row["scores_json"]),
                    "details": json.loads(row["details_json"]),
                    "indicators": json.loads(row["indicators_json"]),
                }
            )
            if top_n is not None and len(results) >= top_n:
                break
        # by_category 需要在截断前统计完整分布
        full_by_category: dict[str, int] = {}
        for row in rows:
            if stock_type and row["category"] != stock_type:
                continue
            if markets and row["market"] not in markets:
                continue
            full_by_category[row["category"]] = full_by_category.get(row["category"], 0) + 1
        first = rows[0]
        return {
            "date": first["trade_date"],
            "updated_at": first["updated_at"],
            "total": len(results),
            "by_category": full_by_category,
            "results": results,
        }

    # ── 写入 ────────────────────────────────────────────────────────────

    def save_marks(self, trade_date: str, results: list[dict[str, Any]]) -> dict[str, Any]:
        """全量替换标记表并写入快照元信息。"""
        updated_at = _now_iso()
        with self._connect() as conn:
            conn.execute("DELETE FROM changying_marks")
            for r in results:
                score = float(
                    r.get("score", r.get("scores", {}).get(r.get("category", ""), 0) or 0)
                )
                conn.execute(
                    """
                    INSERT INTO changying_marks (
                        updated_at, trade_date, symbol, market, code, category, score,
                        total_mcap_yi, report_date, data_source,
                        scores_json, details_json, indicators_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        r.get("report_date"),
                        r.get("data_source", "gpcw"),
                        json.dumps(r.get("scores", {}), ensure_ascii=False),
                        json.dumps(r.get("details", {}), ensure_ascii=False),
                        json.dumps(r.get("indicators", {}), ensure_ascii=False),
                    ),
                )
            by_category: dict[str, int] = {}
            for r in results:
                c = r.get("category", "")
                by_category[c] = by_category.get(c, 0) + 1
            meta = {
                "updated_at": updated_at,
                "trade_date": trade_date,
                "count": len(results),
                "by_category": by_category,
            }
            conn.execute(
                "INSERT OR REPLACE INTO marks_meta (key, value) VALUES ('snapshot', ?)",
                (json.dumps(meta, ensure_ascii=False),),
            )
        return meta


def refresh_changying_marks(
    target: date | None = None,
    *,
    markets: tuple[str, ...] = ("SH", "SZ"),
    min_mcap_yi: float = DEFAULT_MIN_MCAP_YI,
    min_score: float = DEFAULT_MIN_SCORE,
    force: bool = False,
    client: Any = None,
) -> dict[str, Any]:
    """全市场扫描并把市值 ≥100 亿标的的树/粮/菜标记全量落库。

    Args:
        target: 目标日期（point-in-time 财报裁剪基准）。
        markets: 扫描市场，默认沪深两市。
        min_mcap_yi: 总市值下限（亿元）。
        min_score: 分类得分下限（15 = 只标记真正够格的标的；0 = 有分类即标记）。
        force: 跳过半成品保护校验（手动修复时用）。
        client: 可选注入 TdxClient（测试用）。

    Returns:
        快照元信息 + results 全量列表。

    Raises:
        RuntimeError: 半成品保护触发（本次标的数 < 上期 80% 且未 force）。
    """
    target = target or date.today()
    store = ChangyingMarkStore()
    prev_meta = store.last_snapshot_meta()
    prev_count = int(prev_meta.get("count", 0)) if prev_meta else 0

    from easy_tdx.fundamental.pipeline import scan_market

    # top_n 传超大值：scan_market 的市值候选窗口 = top_n*5，等于对全部
    # 打分合格标的取市值过滤，最终 kept = 全部合格标的（无截断）。
    out = scan_market(
        target,
        markets=markets,
        stock_type="all",
        top_n=100000,
        min_score=min_score,
        with_performance=False,
        client=client,
        min_mcap_yi=min_mcap_yi,
        require_profit=True,
    )
    results = out.get("results") or []

    # 半成品保护：本次合格标的数 < 上次成功快照 80% 时拒绝覆盖
    if not force and prev_count > 0 and len(results) < prev_count * _HALF_GUARD_RATIO:
        raise RuntimeError(
            f"changying-mark 半成品保护触发：本次 {len(results)} 只 < 上次 "
            f"{prev_count} 只的 {_HALF_GUARD_RATIO:.0%}，拒绝覆盖全量标记。"
            "行情主机故障或财报数据缺失时可能出现；确认数据正常后用 --force 强制刷新。"
        )

    meta = store.save_marks(str(target), results)
    _record_periods()
    logger.info(
        "长盈全市场标记完成：count=%s by_category=%s date=%s",
        meta.get("count"),
        meta.get("by_category"),
        meta.get("trade_date"),
    )
    return {
        **meta,
        "min_mcap_yi": min_mcap_yi,
        "min_score": min_score,
        "total_scanned": out.get("total_scanned"),
        "results": results,
    }


def load_changying_marks(
    *,
    stock_type: str | None = None,
    markets: list[str] | None = None,
    top_n: int | None = None,
) -> dict[str, Any] | None:
    """读取本地全量标记（供 Web 白天快速读取），无数据返回 None。"""
    return ChangyingMarkStore().load_marks(
        stock_type=stock_type, markets=markets, top_n=top_n
    )


def marks_selfcheck() -> dict[str, Any]:
    """调度自检：返回快照元信息（无快照时 count=None），供自检日志消费。"""
    meta = ChangyingMarkStore().last_snapshot_meta()
    return meta or {"count": None, "trade_date": None, "updated_at": None}


# ── 报告期检测（季报兜底）───────────────────────────────────────────────


def _gpcw_periods() -> list[str]:
    """gpcw 缓存中已下载的报告期列表（如 20260331），按期号排序。"""
    cache = _config_dir() / "gpcw_cache"
    if not cache.exists():
        return []
    return sorted(p.stem.replace("gpcw", "") for p in cache.glob("gpcw*.zip"))


def detect_new_report_period() -> bool:
    """gpcw 缓存出现上次标记后没有的新报告期时返回 True（季报兜底触发）。"""
    store = ChangyingMarkStore()
    with store._connect() as conn:
        row = conn.execute(
            "SELECT value FROM marks_meta WHERE key = 'periods'"
        ).fetchone()
    known: list[str] = json.loads(row["value"]) if row else []
    current = _gpcw_periods()
    return any(p not in known for p in current)


def _record_periods() -> None:
    """把当前 gpcw 报告期列表写入元信息（标记成功后调用）。"""
    store = ChangyingMarkStore()
    with store._connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO marks_meta (key, value) VALUES ('periods', ?)",
            (json.dumps(_gpcw_periods()),),
        )


# ── 精选池派生（兼容旧 changying_pool 消费方）────────────────────────────


def derive_pool_from_marks(top_n: int = 20) -> dict[str, Any] | None:
    """从全量标记取 top_n 派生精选池（回写 changying_pool.db）。

    changying_pool 是 marks 的「精选视图」：白天 /stock-pick 优先读 marks，
    marks 缺失时回退 pool。标记刷新成功后调用本函数保持两者一致。
    无标记数据时返回 None。
    """
    marks = ChangyingMarkStore().load_marks(top_n=top_n)
    if not marks or not marks.get("results"):
        return None
    from easy_tdx.fundamental.changying_pool import ChangyingStore

    rows: list[dict[str, Any]] = []
    for r in marks["results"]:
        rows.append(
            {
                "market": r["market"],
                "code": r["code"],
                "category": r["category"],
                "score": r["score"],
                "total_mcap_yi": r.get("total_mcap_yi"),
                "report_date": r.get("report_date"),
                "data_source": r.get("data_source"),
                "scores": r.get("scores", {}),
                "details": r.get("details", {}),
                "indicators": r.get("indicators", {}),
                "performance": {},
            }
        )
    return ChangyingStore().save_pool(marks["date"], rows)

