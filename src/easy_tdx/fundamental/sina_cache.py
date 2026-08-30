"""P2 在线数据补充：新浪财报指标的 SQLite 缓存（按股票代码）。

背景：``sina_adapter.load_sina_rows`` 每次都要请求新浪三个报表接口
（利润表/资产负债表/现金流量表，~1.2s/只）。在自选池/历史时点选股里
反复回退新浪时重复请求很浪费；把合并后的指标行按 code 落盘，
后续读取直接命中，网络只发生一次。

与 ``cache.py``（gpcw 指标帧，按报告期 zip 维度）互补：
本模块按**股票代码**维度缓存新浪合并指标，两者共用同一缓存目录。
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── 缓存位置与格式版本 ────────────────────────────────────────────────
_HOME = Path(os.environ.get("HOME") or os.path.expanduser("~"))
CACHE_DIR = Path(os.environ.get("EASY_TDX_GPCW_CACHE_DIR", str(_HOME / ".easy_tdx" / "gpcw_cache")))
DB_PATH = CACHE_DIR / "sina_rows.db"

# 新浪合并指标口径的版本（新增/重命名指标字段时递增，旧缓存自动失效）
FORMAT_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sina_rows (
    code TEXT PRIMARY KEY,
    market TEXT NOT NULL,
    payload TEXT NOT NULL,
            -- JSON: {rows: [{report_date, disclosure_date, indicators}], fetched_at}
    fetched_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sina_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(_SCHEMA)
    return conn


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d is not None else None


def _from_iso(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def store_rows(
    code: str,
    market: str,
    rows: list[Any],
) -> int:
    """缓存一只股票的新浪指标行。rows 为 SinaFinancialRow 列表（最新在前）。"""
    if not rows:
        return 0
    payload = {
        "rows": [
            {
                "report_date": _iso(r.report_date),
                "disclosure_date": _iso(r.disclosure_date),
                "indicators": {
                    k: (float(v) if v is not None else None)
                    for k, v in r.indicators.items()
                },
            }
            for r in rows
        ],
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO sina_rows(code, market, payload, fetched_at) VALUES (?,?,?,?)"
            " ON CONFLICT(code) DO UPDATE SET market=excluded.market, payload=excluded.payload,"
            " fetched_at=excluded.fetched_at",
            (code, market.upper(), json.dumps(payload, ensure_ascii=False), payload["fetched_at"]),
        )
        conn.execute(
            "INSERT INTO sina_meta(key, value) VALUES ('format_version', ?)"
            " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(FORMAT_VERSION),),
        )
        conn.commit()
    finally:
        conn.close()
    return len(rows)


def _deserialize(payload_str: str) -> list[dict[str, Any]] | None:
    try:
        payload = json.loads(payload_str)
    except (json.JSONDecodeError, TypeError):
        return None
    rows: list[dict[str, Any]] = []
    for r in payload.get("rows", []):
        rows.append(
            {
                "report_date": _from_iso(r.get("report_date")),
                "disclosure_date": _from_iso(r.get("disclosure_date")),
                "indicators": r.get("indicators") or {},
            }
        )
    return rows if rows else None


def load_rows(code: str) -> list[dict[str, Any]] | None:
    """读回一只股票的新浪指标行（最新在前）；未缓存/版本不符返回 None。"""
    conn = _connect()
    try:
        fv = conn.execute(
            "SELECT value FROM sina_meta WHERE key = ?", ("format_version",)
        ).fetchone()
        if fv is None or fv[0] != str(FORMAT_VERSION):
            return None
        row = conn.execute(
            "SELECT payload FROM sina_rows WHERE code = ?", (code,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return _deserialize(row[0])


def has_rows(code: str) -> bool:
    return load_rows(code) is not None


def cache_stats() -> dict[str, Any]:
    """新浪缓存统计：已缓存股票数、指标行数、库大小。"""
    conn = _connect()
    try:
        fv = conn.execute(
            "SELECT value FROM sina_meta WHERE key = ?", ("format_version",)
        ).fetchone()
        rows = conn.execute("SELECT code, payload FROM sina_rows").fetchall()
    finally:
        conn.close()
    total_rows = 0
    for _, payload in rows:
        r = _deserialize(payload)
        total_rows += len(r) if r else 0
    return {
        "db_path": str(DB_PATH),
        "format_version": int(fv[0]) if fv else FORMAT_VERSION,
        "db_bytes": DB_PATH.stat().st_size if DB_PATH.is_file() else 0,
        "codes_count": len(rows),
        "total_rows": total_rows,
    }


def clear_cache() -> int:
    """清空新浪缓存，返回删除的股票数。"""
    conn = _connect()
    try:
        n = conn.execute("SELECT COUNT(*) FROM sina_rows").fetchone()[0]
        conn.execute("DELETE FROM sina_rows")
        conn.commit()
    finally:
        conn.close()
    return int(n)


__all__ = [
    "CACHE_DIR", "DB_PATH", "FORMAT_VERSION",
    "store_rows", "load_rows", "has_rows", "cache_stats", "clear_cache",
]