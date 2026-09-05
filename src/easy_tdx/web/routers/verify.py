"""买卖点实证复盘路由（V419）。

后台预跑 20 只大市值/大成交量标的的缠论分析，前端逐一呈现：
买卖点标注 + 买卖点后逐根 K 线揭示 + 同级别中枢（MMD.zs 引用）。
数据源：离线 .day 优先，在线客户端回退。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

import pandas as pd
from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(tags=["verify"])

# 20 只大市值/大成交量标的（沪深龙头，代码+名称+市场）
# market: 0=SZ, 1=SH
VERIFY_POOL: list[dict[str, str]] = [
    {"code": "600519", "name": "贵州茅台", "market": "SH"},
    {"code": "601318", "name": "中国平安", "market": "SH"},
    {"code": "600036", "name": "招商银行", "market": "SH"},
    {"code": "601166", "name": "兴业银行", "market": "SH"},
    {"code": "600900", "name": "长江电力", "market": "SH"},
    {"code": "601899", "name": "紫金矿业", "market": "SH"},
    {"code": "600030", "name": "中信证券", "market": "SH"},
    {"code": "601012", "name": "隆基绿能", "market": "SH"},
    {"code": "600276", "name": "恒瑞医药", "market": "SH"},
    {"code": "601888", "name": "中国中免", "market": "SH"},
    {"code": "000858", "name": "五粮液", "market": "SZ"},
    {"code": "000333", "name": "美的集团", "market": "SZ"},
    {"code": "000651", "name": "格力电器", "market": "SZ"},
    {"code": "002594", "name": "比亚迪", "market": "SZ"},
    {"code": "300750", "name": "宁德时代", "market": "SZ"},
    {"code": "000001", "name": "平安银行", "market": "SZ"},
    {"code": "002415", "name": "海康威视", "market": "SZ"},
    {"code": "000725", "name": "京东方A", "market": "SZ"},
    {"code": "002475", "name": "立讯精密", "market": "SZ"},
    {"code": "300059", "name": "东方财富", "market": "SZ"},
]


def _bars_to_df(bars: list[Any]) -> pd.DataFrame:
    """SecurityBar 列表 → analyser 兼容的 OHLCV DataFrame。"""
    rows = []
    for b in bars:
        rows.append(
            {
                "date": datetime(b.year, b.month, b.day),
                "open": float(b.open),
                "high": float(b.high),
                "low": float(b.low),
                "close": float(b.close),
                "vol": float(getattr(b, "vol", 0) or 0),
                "amount": float(getattr(b, "amount", 0) or 0),
            }
        )
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("date").reset_index(drop=True)
    return df


def _load_offline_df(market: str, code: str) -> pd.DataFrame | None:
    """读离线 .day 文件为 analyser 兼容 df；无文件返回 None。"""
    try:
        from easy_tdx.offline.daily_bar import find_daily_bar_file, read_daily_bars

        market_int = 1 if market == "SH" else 0
        path = find_daily_bar_file(market_int, code)
        if path is None:
            return None
        bars = read_daily_bars(path)
        if not bars:
            return None
        return _bars_to_df(bars)
    except Exception as exc:  # noqa: BLE001 — 离线读取失败降级在线
        logger.debug("离线读取 %s%s 失败: %s", market, code, exc)
        return None


def _analyze(df: pd.DataFrame, market: str, code: str) -> dict[str, Any]:
    """跑缠论分析并序列化（含 mmd.zs_index 关联同级别中枢）。"""
    from easy_tdx.chanlun import ChanlunAnalyser

    analyser = ChanlunAnalyser(code=f"{market}{code}", frequency="daily")
    result = analyser.process_klines(df)
    d = result.to_dict()
    # K 线（前端图表需要；与 /bars 同列契约）
    d["bars"] = [
        {
            "datetime": str(row["date"]),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "vol": float(row.get("vol", 0) or 0),
            "amount": float(row.get("amount", 0) or 0),
        }
        for _, row in df.iterrows()
    ]
    # mmd → 所属中枢 index（同级别中枢关联）
    d["mmds"] = [
        {
            **m,
            "zs_index": (mmd.zs.index if (mmd := result.mmds[i]).zs else None),
        }
        for i, m in enumerate(d["mmds"])
    ]
    # 分型（前端标注用）
    d["fractals"] = [
        {
            "fx_type": fx.fx_type.value,
            "date": result._fmt_dt(result._fx_anchor_datetime(fx)),
            "val": round(fx.val, 2),
            "index": fx.index,
            "bar_index": fx.bar_index,
        }
        for fx in result.fractals
    ]
    return d


_prerun_cache: dict[str, dict[str, Any]] = {}
_prerun_status: dict[str, str] = {}  # code -> pending/ready/failed


def _prerun_one(item: dict[str, str]) -> dict[str, Any]:
    """预跑单只标的，返回分析结果（失败返回 error）。"""
    market = item["market"]
    code = item["code"]
    _prerun_status[code] = "pending"
    try:
        df = _load_offline_df(market, code)
        if df is None or len(df) < 100:
            _prerun_status[code] = "failed"
            return {"code": code, "name": item["name"], "market": market, "error": "无离线数据"}
        result = _analyze(df, market, code)
        _prerun_cache[code] = {
            "code": code,
            "name": item["name"],
            "market": market,
            "mmd_count": len(result["mmds"]),
            "zs_count": len(result["zss"]),
            **result,
        }
        _prerun_status[code] = "ready"
        return {
            "code": code,
            "name": item["name"],
            "market": market,
            "mmd_count": len(result["mmds"]),
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("预跑 %s 失败", code)
        _prerun_status[code] = "failed"
        return {"code": code, "name": item["name"], "market": market, "error": str(exc)}


class PrerunRequest(BaseModel):
    force: bool = False


@router.post("/verify/signals/prerun")
async def prerun_signals(req: PrerunRequest) -> dict[str, Any]:
    """后台预跑 20 只标的缠论分析（同步批量，结果缓存）。"""
    if _prerun_cache and not req.force:
        return {"status": "cached", "total": len(_prerun_cache)}
    results = []
    for item in VERIFY_POOL:
        results.append(await asyncio.to_thread(_prerun_one, item))
    ready = [r for r in results if "error" not in r]
    return {"status": "done", "total": len(VERIFY_POOL), "ready": len(ready), "items": results}


@router.get("/verify/signals/list")
async def list_signals() -> dict[str, Any]:
    """20 只标的清单 + 预跑状态。"""
    items = []
    for item in VERIFY_POOL:
        code = item["code"]
        items.append(
            {
                "code": code,
                "name": item["name"],
                "market": item["market"],
                "status": _prerun_status.get(code, "pending"),
                "mmd_count": _prerun_cache[code].get("mmd_count")
                if code in _prerun_cache
                else None,
            }
        )
    return {"total": len(items), "items": items}


@router.get("/verify/signals/detail")
async def detail_signals(code: str) -> dict[str, Any]:
    """单标的详情：买卖点 + 同级别中枢 + 基础 K 线。"""
    if code not in _prerun_cache:
        item = next((i for i in VERIFY_POOL if i["code"] == code), None)
        if item is None:
            return {"error": f"未知标的 {code}"}
        # 未预跑则现场分析
        entry = _prerun_one(item)
        if "error" in entry:
            return entry
    return _prerun_cache[code]
