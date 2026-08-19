"""缠论分析路由。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import Field

from easy_tdx.web.convert import category_from_str, market_from_str
from easy_tdx.web.deps import get_client
from easy_tdx.web.schemas import ChanlunRequest

router = APIRouter(tags=["chanlun"])


@router.post("/chanlun/analyze")
async def chanlun_analyze(
    req: ChanlunRequest,
    client: Any = Depends(get_client),
) -> dict[str, Any]:
    """执行缠论分析。

    自动从 TDX 服务器获取 K 线数据，运行完整缠论计算管道，
    返回笔、中枢、线段、买卖点、背驰、分型等分析结果。
    """
    from easy_tdx.chanlun import ChanlunAnalyser

    # 1. Fetch kline data
    df = await client.get_security_bars(
        market_from_str(req.market),
        req.code,
        category_from_str(req.category),
        req.start,
        req.count,
    )

    # 2. Run chanlun analysis
    symbol = f"{req.market}{req.code}"
    frequency_map: dict[str, str] = {
        "MIN_1": "1min",
        "MIN_5": "5min",
        "MIN_15": "15min",
        "MIN_30": "30min",
        "MIN_60": "60min",
        "DAY": "daily",
        "WEEK": "weekly",
        "MONTH": "monthly",
        "YEAR": "yearly",
    }
    freq = frequency_map.get(req.category.upper(), req.category)
    analyser = ChanlunAnalyser(code=symbol, frequency=freq)
    result = analyser.process_klines(df)

    # 3. 返回完整分析结果，包括分型数据和BOLL
    d = result.to_dict()

    # 添加分型数据
    d["fractals"] = [
        {
            "fx_type": fx.fx_type.value,
            "date": result._fmt_dt(fx.k.date),
            "val": round(fx.val, 2),
            "index": fx.index,
        }
        for fx in result.fractals
    ]

    # 添加BOLL数据
    if result.boll:
        n = len(result.boll.upper)
        d["boll"] = {
            "upper": [round(x, 2) for x in result.boll.upper[-100:]],
            "mid": [round(x, 2) for x in result.boll.mid[-100:]],
            "lower": [round(x, 2) for x in result.boll.lower[-100:]],
            "width": [round(x, 2) for x in result.boll.width[-100:]],
            "percent_b": [round(x, 2) for x in result.boll.percent_b[-100:]],
            "latest_upper": round(result.boll.latest_upper, 2),
            "latest_mid": round(result.boll.latest_mid, 2),
            "latest_lower": round(result.boll.latest_lower, 2),
            "latest_percent_b": round(result.boll.latest_percent_b, 2),
            "latest_width": round(result.boll.latest_width, 4),
        }

    return d


class ChanlunMultiLevelRequest(ChanlunRequest):
    """多级别缠论分析请求。"""

    low_level: str = Field(default="MIN_30", description="低级别周期（如 MIN_30, MIN_5）")


@router.post("/chanlun/multi-level")
async def chanlun_multi_level(
    req: ChanlunMultiLevelRequest,
    client: Any = Depends(get_client),
) -> dict[str, Any]:
    """多级别缠论分析：同时分析高级别和低级别，返回一致性评分。

    用于区间套判断：大级别背驰在小级别先确认。
    """
    from easy_tdx.chanlun import ChanlunAnalyser
    from easy_tdx.chanlun.multi_level import MultiLevelAnalyser

    frequency_map: dict[str, str] = {
        "MIN_1": "1min",
        "MIN_5": "5min",
        "MIN_15": "15min",
        "MIN_30": "30min",
        "MIN_60": "60min",
        "DAY": "daily",
        "WEEK": "weekly",
    }
    high_freq = frequency_map.get(req.category.upper(), "daily")
    low_freq = frequency_map.get(req.low_level.upper(), "30min")

    symbol = f"{req.market}{req.code}"

    # 获取高级别数据
    df_high = await client.get_security_bars(
        market_from_str(req.market),
        req.code,
        category_from_str(req.category),
        req.start,
        req.count,
    )
    # 获取低级别数据（需要更多K线覆盖时间范围）
    df_low = await client.get_security_bars(
        market_from_str(req.market),
        req.code,
        category_from_str(req.low_level),
        req.start,
        min(req.count * 6, 3000),
    )

    # 分别分析
    high_analyser = ChanlunAnalyser(code=symbol, frequency=high_freq)
    low_analyser = ChanlunAnalyser(code=symbol, frequency=low_freq)
    high_result = high_analyser.process_klines(df_high)
    low_result = low_analyser.process_klines(df_low)

    # 多级别一致性分析
    mla = MultiLevelAnalyser()
    mla.add_level("high", high_analyser)
    mla.add_level("low", low_analyser)

    confluence = mla.compute_confluence_score("high", "low")

    # 最后一级笔的低级别走势
    low_qs: dict[str, Any] = {}
    if high_result.bis:
        last_bi = high_result.bis[-1]
        low_qs = mla.query_low_level_qs("high", "low", last_bi)

    # 格式化结果
    def fmt_result(result: Any) -> dict[str, Any]:
        d = result.to_dict()
        d["fractals"] = [
            {
                "fx_type": fx.fx_type.value,
                "date": result._fmt_dt(fx.k.date),
                "val": round(fx.val, 2),
                "index": fx.index,
            }
            for fx in result.fractals
        ]
        return d

    return {
        "high_level": {
            "category": req.category,
            "result": fmt_result(high_result),
        },
        "low_level": {
            "category": req.low_level,
            "result": fmt_result(low_result),
        },
        "confluence": confluence,
        "low_level_qs": low_qs,
    }
