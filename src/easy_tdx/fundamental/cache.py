"""P2 财务指标缓存（SQLite）：gpcw 解析结果的派生指标帧落盘，避免重复解析大 zip。

背景：``records_from_zip`` 每次都要解压并解析全市场 gpcw zip（每份 1~4s，
全市场扫描要处理 3~8 份）；把 ``build_indicator_frame`` 的**派生指标帧**（22 列，
约 2MB/zip）落盘 SQLite，后续请求直接读库，重复扫描从秒级降到亚秒级。

关键设计：

1. 缓存的是指标帧而不是原始 584 字段（原始字段 JSON 序列化后 ~341MB/3zip，
    指标帧只有 ~6MB/3zip），体积与读回时间都小一个量级；
2. ``FORMAT_VERSION`` 随指标口径变化递增——缓存结构/口径不兼容时自动失效重建；
3. 写库前先删旧行再插入（幂等，重复 warm 不产生重复行）。
"""

from __future__ import annotations

import logging
import os
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# ── 缓存位置与格式版本 ────────────────────────────────────────────────
_HOME = Path(os.environ.get("HOME") or os.path.expanduser("~"))
CACHE_DIR = Path(os.environ.get("EASY_TDX_GPCW_CACHE_DIR", str(_HOME / ".easy_tdx" / "gpcw_cache")))
DB_PATH = CACHE_DIR / "gpcw_frames.db"

# 派生指标帧的列（build_indicator_frame 的输出）。缓存文件与指标口径绑定，
# 新增/重命名字段时递增此版本使旧缓存自动失效。
FORMAT_VERSION = 1

_REPORT_COLS = ("report_date", "disclosure_date")
_FLOAT_COLS = (
    "eps",
    "bps",
    "roe",
    "revenue",
    "net_profit",
    "gross_margin",
    "net_margin",
    "debt_ratio",
    "ocf",
    "ocf_ps",
    "rev_yoy",
    "np_yoy",
    "asset_yoy",
    "op_yoy",
    "total_shares",
    "circ_a",
)

# SELECT 用列（表里另有 zip/idx 作主键，不在业务列中）
_ALL_COLS = ("code", "market") + _REPORT_COLS + _FLOAT_COLS

_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS frames (
    zip TEXT NOT NULL,
    idx INTEGER NOT NULL,
    code TEXT NOT NULL,
    market TEXT NOT NULL,
    report_date TEXT,
    disclosure_date TEXT,
    {", ".join(f"{c} REAL" for c in _FLOAT_COLS)},
    PRIMARY KEY (zip, idx)
);
CREATE INDEX IF NOT EXISTS idx_frames_zip ON frames(zip);
CREATE TABLE IF NOT EXISTS meta (
    zip TEXT PRIMARY KEY,
    format_version INTEGER NOT NULL,
    rows INTEGER NOT NULL,
    built_at TEXT NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    """打开缓存库（自动建目录/建表）。"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(_SCHEMA)
    return conn


def _date_to_text(v: Any) -> str | None:
    if v is None or v is pd.NaT:
        return None
    d = v.date() if hasattr(v, "date") else v
    return str(d.isoformat())


def _text_to_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


_INSERT_COLS = ("zip", "idx") + _ALL_COLS
_INSERT_SQL = (
    "INSERT INTO frames ("
    + ",".join(_INSERT_COLS)
    + ") VALUES ("
    + ",".join("?" for _ in _INSERT_COLS)
    + ")"
)


def store_frame(filename: str, frame: pd.DataFrame) -> int:
    """把一份报告期的指标帧写入缓存，返回写入行数。幂等：同 zip 先删后插。"""
    if frame is None or frame.empty:
        return 0
    rows: list[tuple[Any, ...]] = []
    for idx, (_, r) in enumerate(frame.iterrows()):
        rows.append(
            (
                filename,
                idx,
                str(r.get("code")),
                str(r.get("market")),
                _date_to_text(r.get("report_date")),
                _date_to_text(r.get("disclosure_date")),
                *[float(r.get(c)) if r.get(c) is not None else None for c in _FLOAT_COLS],
            )
        )
    conn = _connect()
    try:
        conn.execute("DELETE FROM frames WHERE zip = ?", (filename,))
        conn.executemany(_INSERT_SQL, rows)
        conn.execute(
            "INSERT INTO meta(zip, format_version, rows, built_at) VALUES (?,?,?,?)"
            " ON CONFLICT(zip) DO UPDATE SET format_version=excluded.format_version,"
            " rows=excluded.rows, built_at=excluded.built_at",
            (filename, FORMAT_VERSION, len(rows), datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
    finally:
        conn.close()
    return len(rows)


def load_frame(filename: str) -> pd.DataFrame | None:
    """读回一份报告期的指标帧；未缓存或格式版本不匹配返回 None。"""
    conn = _connect()
    try:
        meta = conn.execute("SELECT format_version FROM meta WHERE zip = ?", (filename,)).fetchone()
        if meta is None or meta[0] != FORMAT_VERSION:
            return None
        cur = conn.execute(
            "SELECT " + ",".join(_ALL_COLS) + " FROM frames WHERE zip = ? ORDER BY idx",
            (filename,),
        )
        data = cur.fetchall()
    finally:
        conn.close()
    if not data:
        return None
    out: list[dict[str, Any]] = []
    for row in data:
        d = dict(zip(_ALL_COLS, row))
        d["report_date"] = _text_to_date(d["report_date"])
        d["disclosure_date"] = _text_to_date(d["disclosure_date"])
        out.append(d)
    return pd.DataFrame(out)


def has_frame(filename: str) -> bool:
    """某份报告期是否已按当前格式版本缓存。"""
    conn = _connect()
    try:
        m = conn.execute("SELECT format_version FROM meta WHERE zip = ?", (filename,)).fetchone()
    finally:
        conn.close()
    return m is not None and m[0] == FORMAT_VERSION


def cache_stats() -> dict[str, Any]:
    """缓存统计：已缓存报告期、总行数、库大小、格式版本。"""
    conn = _connect()
    try:
        metas = conn.execute("SELECT zip, rows, built_at FROM meta ORDER BY zip").fetchall()
    finally:
        conn.close()
    return {
        "db_path": str(DB_PATH),
        "format_version": FORMAT_VERSION,
        "db_bytes": DB_PATH.stat().st_size if DB_PATH.is_file() else 0,
        "zips": [{"filename": z, "rows": r, "built_at": b} for z, r, b in metas],
        "zips_count": len(metas),
        "total_rows": sum(r for _, r, _ in metas),
    }


def clear_cache() -> int:
    """清空全部缓存，返回删除的报告期数量。"""
    conn = _connect()
    try:
        n = int(conn.execute("SELECT COUNT(*) FROM meta").fetchone()[0])
        conn.execute("DELETE FROM frames")
        conn.execute("DELETE FROM meta")
        conn.commit()
    finally:
        conn.close()
    return n


def warm(
    filenames: list[str],
    *,
    client: Any = None,
) -> dict[str, Any]:
    """预生成缓存：解析缺失的报告期并把指标帧写库。

    Args:
        filenames: gpcw 文件名列表。
        client: TdxClient（gpcw 数据源，缺省按 calc host 自动创建）。

    Returns:
        {"warmed": [已新写入的报告期], "already_cached": [...], "failed": [...], "total_rows": n}
    """
    from easy_tdx.fundamental.indicators import build_indicator_frame, records_from_zip

    warmed: list[str] = []
    already: list[str] = []
    failed: list[str] = []
    total_rows = 0
    for fn in filenames:
        if has_frame(fn):
            already.append(fn)
            continue
        try:
            recs = records_from_zip(fn, client)
            frame = build_indicator_frame(recs) if recs else pd.DataFrame()
            n = store_frame(fn, frame)
            if n > 0:
                warmed.append(fn)
                total_rows += n
            else:
                failed.append(fn)
        except Exception as e:  # noqa: BLE001
            logger.warning("gpcw 缓存预热失败 %s: %s", fn, e)
            failed.append(fn)
    return {"warmed": warmed, "already_cached": already, "failed": failed, "total_rows": total_rows}


__all__ = [
    "CACHE_DIR",
    "DB_PATH",
    "FORMAT_VERSION",
    "store_frame",
    "load_frame",
    "has_frame",
    "cache_stats",
    "clear_cache",
    "warm",
]
