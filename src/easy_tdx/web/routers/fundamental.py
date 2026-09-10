"""P1 长赢基本面选股 API 路由。

端点：
- GET  /api/v1/fundamental/indicator/{market}/{code}?as_of=YYYY-MM-DD
      单只股票在目标日期的 point-in-time 财务指标。
- POST /api/v1/fundamental/screen
      历史时点选股：date + pool + stock_type → 树粮菜清单 + 后续表现 + 四季。
- POST /api/v1/fundamental/season
      历史日期四季判断（上证指数）。
- POST /api/v1/fundamental/verify
      批量时点验证：多个历史日期选股 → 树粮菜命中率汇总 + 上证指数基准对比。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(tags=["fundamental"])
logger = logging.getLogger(__name__)

# V499: 单标的财务指标 API 暴露的字段（与 indicator_values 派生指标对齐，
# 含每股净资产 bps；抽为常量便于测试与维护，避免新增指标时遗漏同步）。
_INDICATOR_COLS: tuple[str, ...] = (
    "report_date",
    "disclosure_date",
    "eps",
    "bps",
    "roe",
    "revenue",
    "net_profit",
    "gross_margin",
    "net_margin",
    "debt_ratio",
    "ocf",
    "rev_yoy",
    "np_yoy",
    "asset_yoy",
    "op_yoy",
    "total_shares",
    "circ_a",
)


@router.get("/fundamental/indicator/{market}/{code}")
async def fundamental_indicator(
    market: str,
    code: str,
    as_of: str = Query(..., description="目标日期 YYYY-MM-DD（point-in-time）"),
    period: str | None = Query(None, description="指定报告期 YYYYMMDD（缺省自动取最新已披露）"),
) -> dict[str, Any]:
    """单只股票在目标日期的财务指标（已按披露日截断）。"""
    try:
        target = date.fromisoformat(as_of)
    except ValueError:
        raise HTTPException(status_code=400, detail="as_of 格式应为 YYYY-MM-DD") from None

    from easy_tdx.fundamental.indicators import (
        load_all_periods_frame,
        pick_report,
    )
    from easy_tdx.fundamental.pipeline import pick_report_zips

    def _run() -> dict[str, Any]:
        zips = pick_report_zips(target)
        if not zips:
            raise HTTPException(status_code=503, detail="无可用的 gpcw 财报文件")
        frame = load_all_periods_frame(zips, codes={code}, markets={market.upper()[:2]})
        if frame.empty:
            return {"code": code, "market": market.upper(), "rows": [], "error": "无财报数据"}
        if period:
            sel = frame[frame["report_date"].astype(str).str.replace("-", "").str[:8] == period]
            row = sel.iloc[-1] if not sel.empty else None
        else:
            row = pick_report(frame, code, target, market=market.upper()[:2])
        if row is None:
            return {
                "code": code,
                "market": market.upper(),
                "rows": [],
                "warning": "截至目标日期无已披露财报",
            }
        cols = list(_INDICATOR_COLS)

        def _clean(c: str) -> Any:
            v = row.get(c)
            if v is None:
                return None
            if isinstance(v, float) and v != v:  # NaN
                return None
            if hasattr(v, "isoformat"):
                return str(v)
            return v

        d = {c: _clean(c) for c in cols}
        # V91：数据来源标注（gpcw / sina，screen/scan 补齐）
        d["data_source"] = str(row.get("data_source", "gpcw")) if "data_source" in row else "gpcw"
        return {"code": code, "market": market.upper(), "rows": [d]}

    try:
        return await asyncio.to_thread(_run)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        logger.exception("fundamental indicator 失败")
        raise HTTPException(status_code=500, detail=f"fundamental indicator 失败: {e}") from e


@router.post("/fundamental/screen")
async def fundamental_screen(req: dict[str, Any]) -> dict[str, Any]:
    """历史时点基本面选股（树粮菜）。

    请求体：
    {
      "date": "2026-05-01",
      "stock_type": "all" | "tree" | "grain" | "vegetable",
      "pool": [{"market": "SH", "code": "600519"}, ...],
    }
    """
    from easy_tdx.fundamental.pipeline import run_screen

    date_str = req.get("date", "")
    stock_type = req.get("stock_type", "all")
    pool = req.get("pool") or []

    if not date_str:
        raise HTTPException(status_code=400, detail="缺少 date")
    try:
        target = date.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="date 格式应为 YYYY-MM-DD") from None
    if not pool:
        raise HTTPException(status_code=400, detail="pool 不能为空，至少一只股票")

    norm_pool = [
        {"market": str(p.get("market", "SZ")).upper()[:2], "code": str(p["code"]).zfill(6)}
        for p in pool
        if p.get("code")
    ]

    def _run() -> dict[str, Any]:
        out = run_screen(target, norm_pool)
        if stock_type and stock_type != "all":
            out["results"] = [r for r in out["results"] if r["category"] == stock_type]
        return out

    try:
        return await asyncio.to_thread(_run)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        logger.exception("fundamental screen 失败")
        raise HTTPException(status_code=500, detail=f"fundamental screen 失败: {e}") from e


@router.post("/fundamental/season")
async def fundamental_season(req: dict[str, Any]) -> dict[str, Any]:
    """历史日期四季判断（用上证指数截至该日的数据）。"""
    from easy_tdx.fundamental.pipeline import detect_season_for_date

    date_str = req.get("date", "")
    if not date_str:
        raise HTTPException(status_code=400, detail="缺少 date")
    try:
        target = date.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="date 格式应为 YYYY-MM-DD") from None

    def _run() -> dict[str, Any]:
        sr = detect_season_for_date(target)
        if sr is None:
            raise HTTPException(status_code=503, detail="无法获取上证指数数据")
        return sr.as_dict()

    try:
        return await asyncio.to_thread(_run)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        logger.exception("fundamental season 失败")
        raise HTTPException(status_code=500, detail=f"fundamental season 失败: {e}") from e


@router.post("/fundamental/verify")
async def fundamental_verify(req: dict[str, Any]) -> dict[str, Any]:
    """批量时点验证（F9）：多个历史日期分别选股，汇总树粮菜命中率并对比上证指数。

    请求体：
    {
      "dates": ["2024-04-01", "2025-04-01", ...],
      "pool": [{"market": "SH", "code": "600519"}, ...],
    }
    """
    from easy_tdx.fundamental.pipeline import run_verify

    date_strs = req.get("dates") or []
    pool = req.get("pool") or []

    if not date_strs:
        raise HTTPException(status_code=400, detail="缺少 dates（至少一个 YYYY-MM-DD）")
    if not pool:
        raise HTTPException(status_code=400, detail="pool 不能为空，至少一只股票")

    targets: list[date] = []
    for ds in date_strs:
        try:
            targets.append(date.fromisoformat(str(ds)))
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"日期格式错误: {ds!r}（应为 YYYY-MM-DD）"
            ) from None

    norm_pool = [
        {"market": str(p.get("market", "SZ")).upper()[:2], "code": str(p["code"]).zfill(6)}
        for p in pool
        if p.get("code")
    ]

    def _run() -> dict[str, Any]:
        return run_verify(targets, norm_pool)

    try:
        return await asyncio.to_thread(_run)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        logger.exception("fundamental verify 失败")
        raise HTTPException(status_code=500, detail=f"fundamental verify 失败: {e}") from e


@router.post("/fundamental/scan")
async def fundamental_scan(req: dict[str, Any]) -> dict[str, Any]:
    """P2 全市场扫描：对目标日期全市场股票做树粮菜打分并返回 top_n。

    请求体：
    {
      "date": "2026-08-25",
      "markets": ["SH", "SZ"],
      "stock_type": "all" | "tree" | "grain" | "vegetable",
      "top_n": 50,
      "min_score": 15.0,
      "with_performance": true,
    }
    """
    from easy_tdx.fundamental.pipeline import scan_market

    date_str = req.get("date", "")
    if not date_str:
        raise HTTPException(status_code=400, detail="缺少 date")
    try:
        target = date.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="date 格式应为 YYYY-MM-DD") from None

    markets = req.get("markets") or ["SH", "SZ"]
    norm_markets = tuple(str(m).upper()[:2] for m in markets if str(m).upper()[:2] in ("SH", "SZ"))
    if not norm_markets:
        raise HTTPException(status_code=400, detail="markets 至少包含 SH 或 SZ")

    stock_type = str(req.get("stock_type", "all"))
    if stock_type not in ("all", "tree", "grain", "vegetable"):
        raise HTTPException(status_code=400, detail="stock_type 应为 all/tree/grain/vegetable")

    top_n = max(1, min(int(req.get("top_n", 50)), 200))
    min_score = float(req.get("min_score", 15.0))
    with_performance = bool(req.get("with_performance", True))

    # V91：新浪补充——gpcw 覆盖不足时的自选代码池
    sina_pool_raw = req.get("sina_pool") or []
    sina_pool = [
        {
            "market": str(p.get("market", "SZ")).upper()[:2],
            "code": str(p["code"]).zfill(6),
        }
        for p in sina_pool_raw
        if p.get("code")
    ]

    def _run() -> dict[str, Any]:
        from easy_tdx.fundamental import cache_stats, sina_cache_stats

        out = scan_market(
            target,
            markets=norm_markets,
            stock_type=stock_type,
            top_n=top_n,
            min_score=min_score,
            with_performance=with_performance,
            sina_pool=sina_pool or None,
        )
        # V89：附缓存信息（命中的报告期/行数），前端展示缓存命中状态
        cache = cache_stats()
        out["cache"] = {
            "zips_count": cache["zips_count"],
            "total_rows": cache["total_rows"],
            "db_bytes": cache["db_bytes"],
            "zips": [z["filename"] for z in cache["zips"]],
            "sina_codes": sina_cache_stats()["codes_count"],
        }
        return out

    try:
        return await asyncio.to_thread(_run)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        logger.exception("fundamental scan 失败")
        raise HTTPException(status_code=500, detail=f"fundamental scan 失败: {e}") from e


@router.get("/fundamental/cache")
async def fundamental_cache() -> dict[str, Any]:
    """V89 财务指标缓存状态（SQLite gpcw_frames.db）。

    返回已缓存报告期清单、总行数、库大小与格式版本。
    """
    from easy_tdx.fundamental import cache_stats, sina_cache_stats

    def _run() -> dict[str, Any]:
        out = cache_stats()
        out["sina"] = sina_cache_stats()
        return out

    try:
        return await asyncio.to_thread(_run)
    except Exception as e:  # noqa: BLE001
        logger.exception("fundamental cache 失败")
        raise HTTPException(status_code=500, detail=f"fundamental cache 失败: {e}") from e
