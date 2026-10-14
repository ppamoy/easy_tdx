"""K线数据本地缓存管理。

将所有从服务器下载的K线数据保存到本地磁盘，并提供查询接口：
- 股票代码列表
- 每只股票有数据的级别（日线/30分钟/60分钟等）
- 每个级别的时间区间和K线根数

缓存目录：
- audit_data/      — 日线及以上级别（daily, weekly, monthly）
- audit_data_min/  — 分钟级别（1min, 5min, 15min, 30min, 60min）

文件命名：{market}{code}_{slug}.json（如 sh600000_daily.json）
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

# ── 缓存目录 ──────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
CACHE_DIR_DAILY = _PROJECT_ROOT / "audit_data"
CACHE_DIR_MIN = _PROJECT_ROOT / "audit_data_min"

# ── 级别 → slug 映射 ───────────────────────────────────────────────────
_CATEGORY_SLUGS: dict[str, str] = {
    "DAY": "daily",
    "WEEK": "weekly",
    "MONTH": "monthly",
    "MIN_1": "1min",
    "MIN_5": "5min",
    "MIN_15": "15min",
    "MIN_30": "30min",
    "MIN_60": "60min",
}

# 分钟级别（存到 audit_data_min/）
_MIN_CATEGORIES = {"MIN_1", "MIN_5", "MIN_15", "MIN_30", "MIN_60"}

# slug → 中文显示名
_SLUG_LABELS: dict[str, str] = {
    "daily": "日线",
    "weekly": "周线",
    "monthly": "月线",
    "1min": "1分钟",
    "5min": "5分钟",
    "15min": "15分钟",
    "30min": "30分钟",
    "60min": "60分钟",
}


def _cache_dir(category: str) -> Path:
    """根据级别返回缓存目录。"""
    if str(category).upper() in _MIN_CATEGORIES:
        return CACHE_DIR_MIN
    return CACHE_DIR_DAILY


def _cache_path(market: str, code: str, category: str) -> Path:
    """返回缓存文件路径。"""
    slug = _CATEGORY_SLUGS.get(str(category).upper())
    if not slug:
        return _cache_dir(category) / f"{str(market).lower()}{code}_{str(category).lower()}.json"
    return _cache_dir(category) / f"{str(market).lower()}{code}_{slug}.json"


def _df_to_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    """DataFrame → 可 JSON 序列化的行列表。"""
    out = df.copy()
    # 统一 datetime 列
    for col in ("datetime", "date"):
        if col in out.columns:
            out[col] = pd.to_datetime(out[col])
            out[col] = out[col].dt.strftime("%Y-%m-%dT%H:%M:%S")
    # vol → amount 兼容（部分来源用 vol）
    if "vol" in out.columns and "amount" not in out.columns:
        out = out.rename(columns={"vol": "amount"})
    return json.loads(out.to_json(orient="records", force_ascii=False))


def _rows_to_df(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """JSON 行列表 → DataFrame。"""
    df = pd.DataFrame(rows)
    if "datetime" in df.columns:
        df["datetime"] = pd.to_datetime(df["datetime"])
    elif "date" in df.columns:
        df["datetime"] = pd.to_datetime(df["date"])
    return df


def save_klines(market: str, code: str, category: str, df: pd.DataFrame) -> None:
    """将 K 线 DataFrame 保存到本地缓存。

    如果已有缓存，合并去重后保存（保留最新数据）。
    """
    if df is None or df.empty:
        return

    fp = _cache_path(market, code, category)
    fp.parent.mkdir(parents=True, exist_ok=True)

    # 读取已有缓存（如有）
    existing_rows: list[dict[str, Any]] = []
    if fp.is_file():
        try:
            existing_rows = json.loads(fp.read_text(encoding="utf-8"))
            if not isinstance(existing_rows, list):
                existing_rows = []
        except Exception:  # noqa: BLE001
            existing_rows = []

    # 合并去重
    new_rows = _df_to_rows(df)
    all_rows = existing_rows + new_rows

    # 按时间去重（保留最新）
    seen: dict[str, dict[str, Any]] = {}
    time_key = "datetime" if "datetime" in (new_rows[0] if new_rows else {}) else "date"
    for row in all_rows:
        ts = str(row.get(time_key, ""))
        if ts:
            seen[ts] = row  # 后写入的覆盖先写入的
    deduped = sorted(seen.values(), key=lambda r: str(r.get(time_key, "")))

    fp.write_text(json.dumps(deduped, ensure_ascii=False), encoding="utf-8")


def read_klines(market: str, code: str, category: str) -> pd.DataFrame | None:
    """从本地缓存读取 K 线。命中返回 DataFrame，否则 None。

    支持所有级别（日线/周线/分钟线），替代原先仅支持 30min/60min 的 _read_min_cache。
    """
    fp = _cache_path(market, code, category)
    if not fp.is_file():
        return None
    try:
        rows = json.loads(fp.read_text(encoding="utf-8"))
        if not isinstance(rows, list) or not rows:
            return None
        df = _rows_to_df(rows)
        if "datetime" not in df.columns:
            return None
        return df.sort_values("datetime").reset_index(drop=True)
    except Exception:  # noqa: BLE001
        return None


def _scan_dir(directory: Path, is_min_dir: bool) -> list[dict[str, Any]]:
    """扫描一个缓存目录，返回每只股票每个级别的元信息。"""
    results: list[dict[str, Any]] = []
    if not directory.is_dir():
        return results

    for fp in sorted(directory.glob("*.json")):
        name = fp.stem  # e.g. sh600000_daily
        parts = name.rsplit("_", 1)
        if len(parts) != 2:
            continue
        market_code, slug = parts
        # 解析 market 和 code
        market = ""
        code = ""
        for mkt in ("sh", "sz", "bj"):
            if market_code.startswith(mkt):
                market = mkt.upper()
                code = market_code[len(mkt):]
                break
        if not market:
            continue

        try:
            rows = json.loads(fp.read_text(encoding="utf-8"))
            if not isinstance(rows, list) or not rows:
                continue
            bar_count = len(rows)
            time_key = "datetime" if "datetime" in rows[0] else "date"
            dates = sorted(str(r.get(time_key, "")) for r in rows)
            start_date = dates[0][:10] if dates else ""
            end_date = dates[-1][:10] if dates else ""

            results.append({
                "market": market,
                "code": code,
                "symbol": f"{market}:{code}",
                "category": slug,
                "category_label": _SLUG_LABELS.get(slug, slug),
                "bar_count": bar_count,
                "start_date": start_date,
                "end_date": end_date,
                "file_size": fp.stat().st_size,
                "is_minute": is_min_dir,
            })
        except Exception:  # noqa: BLE001
            continue

    return results


def get_overview() -> dict[str, Any]:
    """扫描所有缓存目录，返回汇总信息。

    返回结构：
    {
        "total_stocks": 285,
        "total_files": 570,
        "total_bars": 1500000,
        "categories": ["daily", "30min", "60min", ...],
        "stocks": [
            {
                "symbol": "SH:600000",
                "market": "SH",
                "code": "600000",
                "levels": [
                    {"category": "daily", "label": "日线", "bar_count": 1500, "start_date": "2020-07-28", "end_date": "2026-09-30"},
                    {"category": "30min", "label": "30分钟", "bar_count": 3976, "start_date": "2024-09-13", "end_date": "2026-10-09"},
                ],
                "level_count": 2,
                "total_bars": 5476,
            },
            ...
        ]
    }
    """
    all_entries = _scan_dir(CACHE_DIR_DAILY, is_min_dir=False) + _scan_dir(CACHE_DIR_MIN, is_min_dir=True)

    # 按股票分组
    stocks_map: dict[str, dict[str, Any]] = {}
    categories_set: set[str] = set()
    total_bars = 0

    for entry in all_entries:
        key = f"{entry['market']}:{entry['code']}"
        if key not in stocks_map:
            stocks_map[key] = {
                "symbol": key,
                "market": entry["market"],
                "code": entry["code"],
                "levels": [],
                "level_count": 0,
                "total_bars": 0,
            }
        stock = stocks_map[key]
        stock["levels"].append({
            "category": entry["category"],
            "label": entry["category_label"],
            "bar_count": entry["bar_count"],
            "start_date": entry["start_date"],
            "end_date": entry["end_date"],
            "file_size": entry["file_size"],
        })
        stock["level_count"] += 1
        stock["total_bars"] += entry["bar_count"]
        categories_set.add(entry["category"])
        total_bars += entry["bar_count"]

    stocks = sorted(stocks_map.values(), key=lambda s: s["symbol"])

    return {
        "total_stocks": len(stocks),
        "total_files": len(all_entries),
        "total_bars": total_bars,
        "categories": sorted(categories_set),
        "stocks": stocks,
    }


def get_detail(market: str, code: str) -> dict[str, Any] | None:
    """返回单只股票的缓存详情。"""
    market = market.upper()
    market_lower = market.lower()
    key = f"{market}:{code}"

    levels: list[dict[str, Any]] = []
    total_bars = 0

    for category, slug in _CATEGORY_SLUGS.items():
        fp = _cache_path(market_lower, code, category)
        if not fp.is_file():
            continue
        try:
            rows = json.loads(fp.read_text(encoding="utf-8"))
            if not isinstance(rows, list) or not rows:
                continue
            bar_count = len(rows)
            time_key = "datetime" if "datetime" in rows[0] else "date"
            dates = sorted(str(r.get(time_key, "")) for r in rows)
            start_date = dates[0][:10] if dates else ""
            end_date = dates[-1][:10] if dates else ""

            levels.append({
                "category": category,
                "slug": slug,
                "label": _SLUG_LABELS.get(slug, slug),
                "bar_count": bar_count,
                "start_date": start_date,
                "end_date": end_date,
                "file_size": fp.stat().st_size,
                "file_path": str(fp.relative_to(_PROJECT_ROOT)),
            })
            total_bars += bar_count
        except Exception:  # noqa: BLE001
            continue

    if not levels:
        return None

    return {
        "symbol": key,
        "market": market,
        "code": code,
        "levels": sorted(levels, key=lambda l: l["slug"]),
        "level_count": len(levels),
        "total_bars": total_bars,
    }
