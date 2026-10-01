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
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from easy_tdx.web.deps import get_client, get_mac_client_optional

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


async def _fetch_online_df(
    mac_client: Any | None,
    client: Any | None,
    market: str,
    code: str,
    category: str = "DAY",
    count: int = 400,
) -> pd.DataFrame | None:
    """V427: 在线 TDX 客户端回退取数（离线 .day 无数据时）。

    复用 chanlun.fetch_qfq_klines（QFQ 前复权，与 /bars 同一价格体系）。
    客户端不可用或取数失败返回 None，由调用方降级为 failed。
    """
    if client is None:
        return None
    try:
        # V722: count>800 分流服务端循环翻页（QFQ 口径不变）
        from easy_tdx.web.klines import fetch_paged_bars, fetch_qfq_klines

        if count > 800:
            df = await fetch_paged_bars(mac_client, client, market, code, category, lookback=count)
        else:
            df = await fetch_qfq_klines(mac_client, client, market, code, category, 0, count)
        return df if df is not None and not df.empty else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("在线取数 %s%s(%s) 失败: %s", market, code, category, exc)
        return None


def _analyze(df: pd.DataFrame, market: str, code: str, frequency: str = "daily") -> dict[str, Any]:
    """跑缠论分析并序列化（含 mmd.zs_index 关联同级别中枢）。"""
    from easy_tdx.chanlun import ChanlunAnalyser

    analyser = ChanlunAnalyser(code=f"{market}{code}", frequency=frequency)
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
    # 缠论有效分型（笔端点，相邻分型不共用K线）。展示层应优先用它；原始 fractals
    # 含共用K线的重叠分型，直接渲染会出现「底-顶-底挤在连续三根K线」的伪分型。
    d["valid_fractals"] = result.valid_fractals_to_dict()
    return d


_FREQ_BY_CATEGORY = {
    "DAY": "daily",
    "WEEK": "weekly",
    "MIN_5": "5min",
    "MIN_15": "15min",
    "MIN_30": "30min",
    "MIN_60": "60min",
}


async def _detail_for_category(
    item: dict[str, str],
    category: str,
    client: Any | None,
    mac_client: Any | None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """按指定周期现场取数并分析（用于非日线周期，不写入预跑缓存）。

    V723: start_date 给定时走 fetch_bars_range 区间直达取数（时间旅行）。
    """
    market = item["market"]
    code = item["code"]
    frequency = _FREQ_BY_CATEGORY.get(category, "daily")
    if start_date:
        from easy_tdx.web.klines import fetch_bars_range

        df = await fetch_bars_range(
            mac_client,
            client,
            market,
            code,
            category,
            start_date=start_date,
            end_date=end_date,
            max_bars=8000,
        )
    else:
        count = 400 if category in ("DAY", "WEEK") else 800
        df = await _fetch_online_df(mac_client, client, market, code, category, count)
    if df is None or len(df) < 100:
        return {
            "code": code,
            "name": item["name"],
            "market": market,
            "error": f"无 {category} 在线数据",
        }
    result = await asyncio.to_thread(_analyze, df, market, code, frequency)
    return {
        "code": code,
        "name": item["name"],
        "market": market,
        "mmd_count": len(result["mmds"]),
        "zs_count": len(result["zss"]),
        **result,
    }


_prerun_cache: dict[str, dict[str, Any]] = {}
_prerun_status: dict[str, str] = {}  # code -> pending/ready/failed


async def _prerun_one(
    item: dict[str, str],
    client: Any | None = None,
    mac_client: Any | None = None,
) -> dict[str, Any]:
    """预跑单只标的，返回分析结果（失败返回 error）。

    数据源：离线 .day 优先，无数据时在线 TDX 客户端回退（V427）。
    """
    market = item["market"]
    code = item["code"]
    _prerun_status[code] = "pending"
    try:
        df = _load_offline_df(market, code)
        if df is None or len(df) < 100:
            df = await _fetch_online_df(mac_client, client, market, code)
        if df is None or len(df) < 100:
            _prerun_status[code] = "failed"
            return {
                "code": code,
                "name": item["name"],
                "market": market,
                "error": "无离线/在线数据",
            }
        result = await asyncio.to_thread(_analyze, df, market, code)
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
async def prerun_signals(
    req: PrerunRequest,
    client: Any = Depends(get_client),
    mac_client: Any | None = Depends(get_mac_client_optional),
) -> dict[str, Any]:
    """后台预跑 20 只标的缠论分析（批量，结果缓存）。"""
    if _prerun_cache and not req.force:
        return {"status": "cached", "total": len(_prerun_cache)}
    results = []
    for item in VERIFY_POOL:
        results.append(await _prerun_one(item, client, mac_client))
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
async def detail_signals(
    code: str,
    category: str = "DAY",
    # V723: 任意日期区间查看——给定 start_date 时忽略预跑缓存，按区间现场取数分析
    start_date: str | None = None,
    end_date: str | None = None,
    client: Any = Depends(get_client),
    mac_client: Any | None = Depends(get_mac_client_optional),
) -> dict[str, Any]:
    """单标的详情：买卖点 + 同级别中枢 + 基础 K 线。

    日线优先使用预跑缓存；其它周期现场取数分析，便于前端切换级别。
    V723: start_date 给定时走 fetch_bars_range 区间直达（日线也现场分析）。
    """
    item = next((i for i in VERIFY_POOL if i["code"] == code), None)
    if item is None:
        return {"error": f"未知标的 {code}"}

    if start_date or category.upper() != "DAY":
        return await _detail_for_category(
            item,
            category.upper(),
            client,
            mac_client,
            start_date=start_date,
            end_date=end_date,
        )

    if code not in _prerun_cache:
        # 未预跑则现场分析（含在线回退）
        entry = await _prerun_one(item, client, mac_client)
        if "error" in entry:
            return entry

    cached = _prerun_cache[code]
    # 兼容旧进程遗留的预跑缓存：它当时还没 valid_fractals 字段，直接返回会让前端
    # 渲染出「0 个分型」（比渲染脏分型好，但仍不完整）。缺字段时现场重算补齐，
    # 而不是让调用方拿到残缺结构。重启服务后本分支自然不再命中。
    if "valid_fractals" not in cached:
        entry = await _prerun_one(item, client, mac_client)
        if "error" not in entry:
            cached = _prerun_cache[code]
    return cached
