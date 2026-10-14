"""吴伟志+缠论融合系统 API 路由。

端点：
- POST /api/v1/hybrid/analyze
      单只股票融合分析：树粮草分类 + 四季判断 + 缠论买卖点 + 方向过滤 + 技术评分
- POST /api/v1/hybrid/scan
      批量扫描：对标的池中所有股票执行融合分析，输出可操作信号清单
- GET  /api/v1/hybrid/season
      当前市场季节判断
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from easy_tdx.web.deps import get_client, get_mac_client_optional

logger = logging.getLogger(__name__)
router = APIRouter(tags=["hybrid"])
ROOT_DIR = Path(__file__).resolve().parents[4]  # easy_tdx 仓库根目录

# 周期映射
FREQ_MAP = {
    "MIN_30": "30min",
    "MIN_60": "60min",
    "DAY": "daily",
    "MIN_5": "5min",
    "MIN_15": "15min",
}


class HybridAnalyzeRequest(BaseModel):
    """融合分析请求。"""
    market: str = Field("SH", description="市场 SH/SZ")
    code: str = Field(..., min_length=6, max_length=6, description="6位股票代码")
    period: str = Field("MIN_30", description="操作级别 MIN_30/MIN_60")
    count: int = Field(500, ge=100, le=4000, description="K线条数")


class HybridScanRequest(BaseModel):
    """批量扫描请求。"""
    codes: list[dict[str, str]] = Field(..., description='[{"market":"SH","code":"600000"},...]')
    period: str = Field("MIN_30", description="操作级别")
    count: int = Field(500, ge=100, le=4000)


@router.post("/hybrid/analyze")
async def hybrid_analyze(
    req: HybridAnalyzeRequest,
    client: Any = Depends(get_client),
    mac_client: Any | None = Depends(get_mac_client_optional),
) -> dict[str, Any]:
    """单只股票融合分析。

    返回：树粮草分类 + 四季 + 缠论买卖点 + 方向过滤 + 技术评分 + 最终信号。
    """
    from easy_tdx.chanlun import ChanlunAnalyser, ChanlunConfig
    from easy_tdx.fusion import HybridEngine, ChanlunSignal
    from pathlib import Path
    import json as _json

    symbol = f"{req.market}{req.code}"
    freq = FREQ_MAP.get(req.period.upper(), "30min")

    # 1. 获取K线数据 — 优先本地缓存（避免TDX连接阻塞事件循环）
    prefix = "sh" if req.market == "SH" else "sz"
    freq_file = {"MIN_30": "30min", "MIN_60": "60min", "MIN_5": "5min", "MIN_15": "15min", "DAY": "daily"}.get(req.period.upper(), "30min")
    df = pd.DataFrame()

    # 尝试分钟缓存
    cache_path = Path("audit_data_min") / f"{prefix}{req.code}_{freq_file}.json"
    if not cache_path.is_file() and freq_file != "daily":
        # 尝试日线缓存
        cache_path = Path("audit_data") / f"{prefix}{req.code}_daily.json"
        freq = "daily"

    if cache_path.is_file():
        try:
            rows = _json.loads(cache_path.read_text("utf-8"))
            df = pd.DataFrame(rows)
            if "datetime" in df.columns:
                df["datetime"] = pd.to_datetime(df["datetime"])
            elif "date" in df.columns:
                df["datetime"] = pd.to_datetime(df["date"])
            df = df.tail(req.count).reset_index(drop=True)
            logger.info("使用本地缓存 %s（%d条）", cache_path.name, len(df))
        except Exception as exc:
            logger.warning("读取缓存失败 %s: %s", cache_path);

    # 无缓存时尝试在线获取（用 asyncio 线程隔离防止阻塞）
    if df.empty and mac_client is not None:
        import asyncio
        try:
            from easy_tdx.web.klines import fetch_qfq_klines
            df = await asyncio.wait_for(
                fetch_qfq_klines(mac_client, client, req.market, req.code, req.period, 0, req.count),
                timeout=15.0,
            )
        except Exception as exc:
            logger.warning("在线取数失败 %s: %s", symbol);

    if df.empty:
        return {"error": f"无法获取 {symbol} 的K线数据（无缓存且TDX不可用）", "code": req.code, "market": req.market}

    # 获取日线用于趋势确认
    daily_df = pd.DataFrame()
    daily_cache = Path("audit_data") / f"{prefix}{req.code}_daily.json"
    if daily_cache.is_file():
        try:
            rows = _json.loads(daily_cache.read_text("utf-8"))
            daily_df = pd.DataFrame(rows)
            if "datetime" in daily_df.columns:
                daily_df["datetime"] = pd.to_datetime(daily_df["datetime"])
            elif "date" in daily_df.columns:
                daily_df["datetime"] = pd.to_datetime(daily_df["date"])
        except Exception:
            pass

    # 2. 缠论分析
    cfg = ChanlunConfig()
    analyser = ChanlunAnalyser(code=symbol, frequency=freq, config=cfg)
    result = analyser.process_klines(df)

    # 提取缠论信号
    signals: list[ChanlunSignal] = []
    type_map = {
        "1buy": "buy_1", "2buy": "buy_2", "2buy_s": "buy_2", "3buy": "buy_3",
        "1sell": "sell_1", "2sell": "sell_2", "2sell_s": "sell_2", "3sell": "sell_3",
    }
    for mmd in result.mmds:
        sig_type = type_map.get(mmd.mmd_type.value, mmd.mmd_type.value)
        bar_idx = mmd.bi.end.bar_index if mmd.bi else 0
        price = float(mmd.bi.end.val) if mmd.bi else 0.0
        zs_range = []
        if mmd.zs:
            zs_range = [float(mmd.zs.zd), float(mmd.zs.zg)]
        # 背驰力度
        beichi = 0.0
        if hasattr(mmd, "beichi_force") and mmd.beichi_force:
            beichi = float(mmd.beichi_force)
        elif mmd.confidence:
            beichi = float(mmd.confidence) * 0.5  # 近似

        signals.append(ChanlunSignal(
            signal_type=sig_type,
            level=freq,
            price=price,
            bar_index=bar_idx,
            confidence=float(mmd.confidence) if mmd.confidence else 0.0,
            beichi_force=beichi,
            zhongshu_range=zs_range,
            detail={"bi_index": bar_idx},
        ))

    # 日线信号
    daily_signals: list[ChanlunSignal] = []
    if not daily_df.empty:
        daily_analyser = ChanlunAnalyser(code=symbol, frequency="daily", config=ChanlunConfig())
        daily_result = daily_analyser.process_klines(daily_df)
        for mmd in daily_result.mmds:
            sig_type = type_map.get(mmd.mmd_type.value, mmd.mmd_type.value)
            daily_signals.append(ChanlunSignal(
                signal_type=sig_type,
                level="daily",
                price=float(mmd.bi.end.val) if mmd.bi else 0,
                confidence=float(mmd.confidence) if mmd.confidence else 0,
            ))

    # 2b. 真·区间套确认（P1-5）：日线高级别信号 × 30分钟低级别结构
    # 原文含义：大级别背驰段，在小级别上也确认为背驰。
    # 此前「零件齐全但没接上」——日线和30分钟都在跑，但从未调用
    # compute_qujiantao_cross_period 把两者连起来。
    qujiantao_results: list[dict[str, Any] | None] = []
    if freq == "30min" and not daily_df.empty and daily_signals:
        try:
            from easy_tdx.chanlun.qujiantao import compute_qujiantao_cross_period
            qujiantao_results = compute_qujiantao_cross_period(
                daily_result.mmds,
                bis_low=getattr(result, "bis", None),
                zss_low=getattr(result, "zss", None),
                bcs_low=getattr(result, "bcs", None),
                mmds_low=getattr(result, "mmds", None),
            )
            qt_confirmed = sum(1 for q in qujiantao_results if q and q.get("nested"))
            logger.info("区间套确认 %s: %d/%d 日线信号被30分钟确认",
                        symbol, qt_confirmed, len(qujiantao_results))
        except Exception as exc:
            logger.warning("区间套确认失败 %s: %s", symbol, exc)

    # 3. 树粮草分类（按 PRD F6：gpcw 财报 → 指标层 → 三维打分）
    screen_result = None
    indicators: dict[str, Any] = {}
    try:
        from easy_tdx.fundamental.indicators import (
            load_all_periods_frame, pick_report, indicator_values,
        )
        from easy_tdx.fundamental.screener import screen_stock
        from easy_tdx.fundamental.pipeline import pick_report_zips
        from easy_tdx.fundamental.cache import cache_stats

        target = date.today()
        zips = pick_report_zips(target)
        if not zips:
            # 离线回退：用本地缓存的报告期
            zips = [z["filename"] for z in cache_stats().get("zips", [])]
        if zips:
            frame = load_all_periods_frame(
                zips, codes={req.code}, markets={req.market},
            )
            if not frame.empty:
                row = pick_report(frame, req.code, target, market=req.market)
                if row is not None:
                    row_dict = row.to_dict() if hasattr(row, "to_dict") else dict(row)
                    indicators = {k: v for k, v in row_dict.items()
                                  if k not in ("code", "market")}
                    screen_row = {"code": req.code, "market": req.market, **row_dict}
                    screen_result = screen_stock(screen_row)
                    logger.info("树粮草分类 %s: %s (scores=%s)", req.code,
                                screen_result.category if screen_result else "无",
                                screen_result.scores if screen_result else None)
    except Exception as exc:
        logger.warning("树粮草分类失败 %s: %s", symbol, exc)

    # 4. 四季判断
    season_result = None
    try:
        from easy_tdx.fundamental.pipeline import detect_season_for_date
        season_result = detect_season_for_date(date.today())
    except Exception as exc:
        logger.warning("四季判断失败: %s", exc)

    # 5. 融合分析
    engine = HybridEngine()
    hybrid = engine.analyze(
        code=req.code,
        market=req.market,
        klines_df=df,
        signals=signals,
        screen_result=screen_result,
        season_result=season_result,
        daily_df=daily_df,
        daily_signals=daily_signals,
        indicators=indicators,
    )

    result_dict = hybrid.as_dict()
    # P1-5：区间套确认结果（真实低级别，非合成）
    if qujiantao_results:
        result_dict["qujiantao"] = [
            {
                "nested": q.get("nested") if q else False,
                "score": q.get("score", 0) if q else 0,
                "method": q.get("method", "none") if q else "none",
                "msg": q.get("msg", "") if q else "",
            }
            for q in qujiantao_results
        ]
    return result_dict


@router.post("/hybrid/scan")
async def hybrid_scan(
    req: HybridScanRequest,
    client: Any = Depends(get_client),
    mac_client: Any | None = Depends(get_mac_client_optional),
) -> dict[str, Any]:
    """批量扫描标的池，输出可操作信号清单。"""
    results: list[dict[str, Any]] = []
    execute_signals: list[dict[str, Any]] = []

    for item in req.codes[:50]:  # 最多50只
        market = item.get("market", "SH")
        code = item.get("code", "")
        if not code:
            continue

        try:
            sub_req = HybridAnalyzeRequest(
                market=market, code=code, period=req.period, count=req.count,
            )
            res = await hybrid_analyze(sub_req, client, mac_client)
            results.append(res)
            if res.get("final_signal") == "execute":
                execute_signals.append(res)
        except Exception as exc:
            logger.warning("扫描 %s%s 失败: %s", market, code, exc)

    return {
        "total": len(results),
        "execute_count": len(execute_signals),
        "results": results,
        "execute_signals": execute_signals,
    }


@router.get("/hybrid/season")
async def hybrid_season(
    client: Any = Depends(get_client),
) -> dict[str, Any]:
    """当前市场季节判断。"""
    try:
        from easy_tdx.fundamental.pipeline import detect_season_for_date
        sr = detect_season_for_date(date.today())
        if sr:
            return sr.as_dict()
    except Exception as exc:
        logger.warning("季节判断失败: %s", exc)
    return {"season": "unknown", "label": "未知", "error": "无法判断"}


@router.get("/hybrid/watchlist")
async def hybrid_watchlist() -> dict[str, Any]:
    """读取 scan_pool.py 的扫描结果，供前端看板展示。

    返回 scan_result.json 的完整内容；如果文件不存在返回空结构。
    """
    scan_path = ROOT_DIR / "audit_data" / "scan_result.json"
    if not scan_path.exists():
        return {
            "scan_time": None,
            "total_scanned": 0,
            "execute_count": 0,
            "results": [],
            "message": "尚无扫描结果。请先运行 scripts/scan_pool.py",
        }
    import json as _json
    try:
        return _json.loads(scan_path.read_text("utf-8"))
    except Exception as exc:
        logger.warning("读取扫描结果失败: %s", exc)
        return {"error": str(exc), "results": []}


@router.get("/hybrid/marks/history")
async def hybrid_marks_history(target: str | None = None) -> dict[str, Any]:
    """P1-6：查询历史树粮草分类标记。

    Args:
        target: 日期 (YYYY-MM-DD)，不传则列出所有已回填的日期。
    """
    import sqlite3
    db_path = ROOT_DIR / "audit_data" / "changying_marks.db"
    if not db_path.exists():
        return {"dates": [], "message": "无历史标记数据库"}
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        if target is None:
            rows = conn.execute(
                "SELECT trade_date, COUNT(*) as cnt FROM changying_marks_history"
                " GROUP BY trade_date ORDER BY trade_date DESC"
            ).fetchall()
            return {"dates": [{"date": r["trade_date"], "count": r["cnt"]} for r in rows]}
        rows = conn.execute(
            "SELECT * FROM changying_marks_history WHERE trade_date = ?"
            " ORDER BY score DESC", (target,)
        ).fetchall()
        by_cat: dict[str, int] = {}
        results = []
        for r in rows:
            cat = r["category"]
            by_cat[cat] = by_cat.get(cat, 0) + 1
            results.append({
                "code": r["code"], "market": r["market"],
                "category": cat, "score": r["score"],
            })
        return {"date": target, "count": len(results),
                "by_category": by_cat, "results": results}
    finally:
        conn.close()
