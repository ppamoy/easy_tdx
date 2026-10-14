"""缠论分析结果 SQLite 缓存。

将笔/线段/中枢/背驰/买卖点/分型/MACD/BOLL 等完整分析结果
连同 K 线数据一并存入 SQLite，按 (market, code, category) 唯一索引。
带版本标记，库升级后旧缓存自动失效。

用法::

    from easy_tdx.web.chanlun_cache import ChanlunCache
    cache = ChanlunCache()
    cached = cache.get("SH", "600066", "MIN_30")
    if cached:
        return cached          # 命中，毫秒级
    # 未命中 → 跑分析 → 存入
    cache.put("SH", "600066", "MIN_30", analysis_dict, version="2026.10.15")
    # 删除单只
    cache.delete("SH", "600066", "MIN_30")
    # 删除全部
    cache.delete_all()
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

_DB_PATH = Path("audit_data") / "chanlun_cache.db"


def _ensure_dir() -> None:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _compute_version() -> str:
    """根据缠论核心模块文件内容生成版本指纹，模块变更后缓存自动失效。"""
    try:
        import easy_tdx.chanlun as cl_pkg

        cl_dir = Path(cl_pkg.__file__).parent
        h = hashlib.md5()
        for py in sorted(cl_dir.glob("*.py")):
            h.update(py.read_bytes())
        return h.hexdigest()[:12]
    except Exception:
        return "unknown"


class ChanlunCache:
    """缠论分析结果 SQLite 缓存（线程安全 via check_same_thread=False）。"""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._path = Path(db_path) if db_path else _DB_PATH
        _ensure_dir()
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_table()

    def _init_table(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS chanlun_cache (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                market      TEXT NOT NULL,
                code        TEXT NOT NULL,
                category    TEXT NOT NULL,
                version     TEXT NOT NULL,
                bars_json   TEXT,
                bis_json    TEXT,
                xds_json    TEXT,
                zss_json    TEXT,
                mmds_json   TEXT,
                bcs_json    TEXT,
                fractals_json      TEXT,
                valid_fractals_json TEXT,
                macd_json   TEXT,
                boll_json   TEXT,
                kline_count INTEGER,
                signal_accuracy_json TEXT,
                levels_json TEXT,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(market, code, category)
            );
            CREATE INDEX IF NOT EXISTS idx_chanlun_cat ON chanlun_cache(category);
            """
        )
        self._conn.commit()

    @property
    def version(self) -> str:
        return _compute_version()

    # ── 读 ──

    def get(self, market: str, code: str, category: str) -> dict[str, Any] | None:
        """命中返回完整分析 dict（含 bars），未命中返回 None。"""
        row = self._conn.execute(
            "SELECT * FROM chanlun_cache WHERE market=? AND code=? AND category=?",
            (market, code, category),
        ).fetchone()
        if row is None:
            return None
        if row["version"] != self.version:
            # 版本不匹配 → 删除旧缓存，返回 None
            self._conn.execute(
                "DELETE FROM chanlun_cache WHERE id=?", (row["id"],)
            )
            self._conn.commit()
            return None

        keys_json = [
            "bars", "bis", "xds", "zss", "mmds", "bcs",
            "fractals", "valid_fractals", "macd", "boll",
            "signal_accuracy", "levels",
        ]
        d: dict[str, Any] = {}
        for k in keys_json:
            col = f"{k}_json"
            if col in row.keys() and row[col] is not None:
                d[k] = json.loads(row[col])
        d["kline_count"] = row["kline_count"]
        d["cached"] = True
        return d

    # ── 写 ──

    def put(
        self,
        market: str,
        code: str,
        category: str,
        data: dict[str, Any],
    ) -> None:
        """存入分析结果（data 应包含 bars, bis, zss, mmds, macd 等字段）。"""
        keys = [
            "bars", "bis", "xds", "zss", "mmds", "bcs",
            "fractals", "valid_fractals", "macd", "boll",
            "signal_accuracy", "levels",
        ]
        vals: dict[str, str | int | None] = {
            f"{k}_json": json.dumps(data.get(k), ensure_ascii=False) if data.get(k) is not None else None
            for k in keys
        }
        vals["kline_count"] = data.get("kline_count", 0)
        vals["version"] = self.version

        cols = ["market", "code", "category"] + list(vals.keys())
        placeholders = ",".join("?" * len(cols))
        sql = (
            "INSERT OR REPLACE INTO chanlun_cache "
            f"({','.join(cols)}) VALUES ({placeholders})"
        )
        self._conn.execute(sql, [market, code, category, *vals.values()])
        self._conn.commit()

    # ── 删 ──

    def delete(self, market: str, code: str, category: str) -> int:
        cur = self._conn.execute(
            "DELETE FROM chanlun_cache WHERE market=? AND code=? AND category=?",
            (market, code, category),
        )
        self._conn.commit()
        return cur.rowcount

    def delete_all(self, category: str | None = None) -> int:
        if category:
            cur = self._conn.execute(
                "DELETE FROM chanlun_cache WHERE category=?", (category,)
            )
        else:
            cur = self._conn.execute("DELETE FROM chanlun_cache")
        self._conn.commit()
        return cur.rowcount

    # ── 列表 ──

    def list_entries(self, category: str | None = None) -> list[dict[str, Any]]:
        if category:
            rows = self._conn.execute(
                "SELECT market, code, category, version, kline_count, created_at "
                "FROM chanlun_cache WHERE category=? ORDER BY code",
                (category,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT market, code, category, version, kline_count, created_at "
                "FROM chanlun_cache ORDER BY code"
            ).fetchall()
        return [dict(r) for r in rows]

    def count(self, category: str | None = None) -> int:
        if category:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM chanlun_cache WHERE category=?", (category,)
            ).fetchone()
        else:
            row = self._conn.execute("SELECT COUNT(*) FROM chanlun_cache").fetchone()
        return int(row[0]) if row else 0

    def close(self) -> None:
        self._conn.close()
