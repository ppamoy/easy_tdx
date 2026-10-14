"""K线数据缓存查询 API。

- GET /api/v1/cache/overview  — 全部缓存股票概览
- GET /api/v1/cache/detail/{market}/{code}  — 单只股票缓存详情
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from easy_tdx.web.kline_cache import get_detail, get_overview

router = APIRouter(prefix="/cache", tags=["cache"])


@router.get("/overview")
async def cache_overview() -> dict:
    """返回所有已缓存K线数据的概览。

    返回结构：
    - total_stocks: 已缓存股票数量
    - total_files: 缓存文件总数
    - total_bars: K线总根数
    - categories: 有数据的级别列表（如 ["30min", "daily", "60min"]）
    - stocks: 每只股票的级别、根数、时间区间
    """
    return get_overview()


@router.get("/detail/{market}/{code}")
async def cache_detail(market: str, code: str) -> dict:
    """返回单只股票的缓存详情。

    返回该股票所有已缓存级别的：级别、K线根数、时间区间、文件大小。
    """
    detail = get_detail(market, code)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"未找到 {market}:{code} 的缓存数据")
    return detail
