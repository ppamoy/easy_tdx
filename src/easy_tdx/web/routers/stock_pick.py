"""选股两步流 API 路由（v590）。

第一步 /stock-pick/screen：长盈基本面选股池（树粮菜 + 评分明细）。
   - 复用 easy_tdx.fundamental.pipeline.run_screen（point-in-time，无未来函数）。
   - pool 由请求传入；缺省用内置热门池（与 screening 一致）。
第二步 /stock-pick/timing：对池内标的做截至目标日的缠论择时。
   - 复用 web/routers/chanlun.fetch_qfq_klines（QFQ 前复权，与图表同一价格体系）。
   - 把 K 线按目标日截断后跑 ChanlunAnalyser，输出完整结构 + 择时结论。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException

from easy_tdx.web.deps import get_client, get_mac_client_optional

router = APIRouter(tags=["stock-pick"])
logger = logging.getLogger(__name__)

# 默认热门标的池（市场 → 代码列表），与 screening 保持一致；可被请求 pool 覆盖。
HOT_STOCKS: dict[str, list[str]] = {
    "SZ": [
        "000001",
        "000002",
        "000063",
        "000100",
        "000333",
        "000568",
        "000651",
        "000725",
        "000858",
        "002594",
        "300059",
        "300015",
        "300014",
        "300012",
        "300750",
    ],
    "SH": [
        "600000",
        "600004",
        "600009",
        "600010",
        "600011",
        "600016",
        "600028",
        "600030",
        "600036",
        "600048",
        "600519",
        "601318",
        "601398",
        "600887",
        "600900",
    ],
}


def _default_pool(markets: list[str]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for m in markets or ["SZ", "SH"]:
        m2 = str(m).upper()[:2]
        for code in HOT_STOCKS.get(m2, []):
            out.append({"market": m2, "code": code})
    return out


def _normalize_result_row(r: dict[str, Any]) -> dict[str, Any]:
    """把 run_screen/scan_market 的结果行统一成前端要的字段。

    修复：旧实现从 r.get("quality_score") 取分，但 run_screen/scan_market
    输出的是 scores[category]，导致在线路径质量分恒为 0。
    """
    category = str(r.get("category", ""))
    raw_scores = r.get("scores")
    scores: dict[str, Any] = raw_scores if isinstance(raw_scores, dict) else {}
    quality = r.get("score")
    if quality is None:
        quality = scores.get(category, 0)
    return {
        "symbol": f"{r.get('market', '')}:{r.get('code', '')}",
        "market": r.get("market", ""),
        "code": r.get("code", ""),
        "category": category,
        "quality_score": quality,
        "total_mcap_yi": r.get("total_mcap_yi"),
        "detail": {
            "scores": scores,
            "details": r.get("details") or {},
            "indicators": r.get("indicators") or {},
            "novice_summary": r.get("novice_summary"),
        },
        "post_performance": r.get("post_performance"),
        "data_source": r.get("data_source"),
    }


@router.post("/stock-pick/screen")
async def stock_pick_screen(req: dict[str, Any]) -> dict[str, Any]:
    """第一步：长盈基本面选股池。

    请求体：{"date": "2026-05-01", "markets": ["SH","SZ"], "stock_type": "all",
             "pool": [{"market":"SH","code":"600519"}], "top_n": 30}
    返回：按质量分排序的树粮菜标的池（含评分明细）。
    """
    from easy_tdx.fundamental.pipeline import run_screen

    date_str = str(req.get("date", ""))
    if not date_str:
        raise HTTPException(status_code=400, detail="缺少 date")
    try:
        target = date.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="date 格式应为 YYYY-MM-DD") from None

    markets = req.get("markets") or ["SZ", "SH"]
    norm_markets = [str(m).upper()[:2] for m in markets if str(m).upper()[:2] in ("SH", "SZ")]
    pool_raw = req.get("pool") or _default_pool(norm_markets)
    if not pool_raw:
        raise HTTPException(status_code=400, detail="pool 为空")
    norm_pool = [
        {"market": str(p.get("market", "SZ")).upper()[:2], "code": str(p["code"]).zfill(6)}
        for p in pool_raw
        if p.get("code")
    ]
    stock_type = str(req.get("stock_type", "all"))
    if stock_type not in ("all", "tree", "grain", "vegetable"):
        stock_type = "all"
    pool_scope = str(req.get("pool_scope", "pool"))
    top_n = max(1, min(int(req.get("top_n", 50)), 200))

    # V591: 白天优先读本地沉淀池（凌晨 changying-refresh 生成），避免反复打 TDX。
    from easy_tdx.fundamental.changying_pool import load_changying_pool

    local = await asyncio.to_thread(load_changying_pool)
    if local and local.get("results"):
        local_rows: list[dict[str, Any]] = [
            {
                "symbol": r["symbol"],
                "market": r["market"],
                "code": r["code"],
                "category": r["category"],
                "quality_score": r.get("score", 0),
                "total_mcap_yi": r.get("total_mcap_yi"),
                "detail": {
                    "scores": r.get("scores", {}),
                    "details": r.get("details", {}),
                    "indicators": r.get("indicators", {}),
                },
                "post_performance": None,
                "data_source": r.get("data_source"),
            }
            for r in local["results"]
        ]
        if stock_type != "all":
            local_rows = [r for r in local_rows if r["category"] == stock_type]
        if norm_markets:
            local_rows = [r for r in local_rows if r["market"] in norm_markets]
        return {
            "date": local.get("date", date_str),
            "total": len(local_rows),
            "results": local_rows,
            "source": "local",
            "updated_at": local.get("updated_at"),
        }

    def _run() -> dict[str, Any]:
        # 全市场路径：复用 fundamental.pipeline.scan_market（同步扫描，
        # 前端以 loading + 分批 top_n 呈现；进度轮询版留待 task_runner 集成）。
        if pool_scope == "full":
            from easy_tdx.fundamental.pipeline import scan_market

            out = scan_market(
                target,
                markets=tuple(norm_markets),
                stock_type=stock_type,
                top_n=top_n,
                min_score=float(req.get("min_score", 15.0)),
                # 默认不做后续表现回看：避免逐只取行情（标准 TDX 行情慢/空）
                # 把选股接口拖到 90s 超时。市值门槛走 min_mcap_yi 仍生效。
                with_performance=bool(req.get("with_performance", False)),
                sina_pool=norm_pool,
                min_mcap_yi=100.0,
                require_profit=True,
            )
            full_rows: list[dict[str, Any]] = [
                _normalize_result_row(r) for r in out.get("results") or []
            ]
            full_rows.sort(key=lambda x: x["quality_score"] or 0, reverse=True)
            return {"date": date_str, "total": len(full_rows), "results": full_rows}

        out = run_screen(
            target,
            norm_pool,
            # 同 full 路径：关闭后续表现回看避免行情取数拖慢选股；
            # 盈利硬门槛 + 市值门槛照常生效。
            with_performance=False,
            min_mcap_yi=100.0,
            require_profit=True,
        )
        results = out.get("results") or []
        if stock_type != "all":
            results = [r for r in results if r["category"] == stock_type]
        rows: list[dict[str, Any]] = [_normalize_result_row(r) for r in results]
        rows.sort(key=lambda x: x["quality_score"] or 0, reverse=True)
        return {"date": date_str, "total": len(rows), "results": rows}

    try:
        return await asyncio.to_thread(_run)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        logger.exception("stock-pick screen 失败")
        raise HTTPException(status_code=500, detail=f"stock-pick screen 失败: {e}") from e


async def _fetch_window(
    mac_client: Any,
    tdx_client: Any,
    market: str,
    code: str,
    count: int,
) -> pd.DataFrame:
    from easy_tdx.web.routers.chanlun import fetch_qfq_klines

    return await fetch_qfq_klines(mac_client, tdx_client, market, code, "DAY", start=0, count=count)


def _df_to_bars(df: pd.DataFrame) -> list[dict[str, Any]]:
    col = "date" if "date" in df.columns else "datetime"
    bars: list[dict[str, Any]] = []
    for _i, row in df.iterrows():
        dt = row[col]
        bars.append(
            {
                "datetime": str(dt)[:19].replace(" ", "T"),
                "open": round(float(row["open"]), 3),
                "close": round(float(row["close"]), 3),
                "high": round(float(row["high"]), 3),
                "low": round(float(row["low"]), 3),
                "vol": float(row.get("vol", 0) or 0),
                "amount": float(row.get("amount", 0) or 0),
            }
        )
    return bars


def _novice_advice(result: Any, verdict: dict[str, Any]) -> dict[str, Any]:
    """把缠论信号翻译成小白能照做的择时建议（入场/止损/目标 + 人话）。"""
    mmds = result.mmds
    if not mmds:
        return {
            "explanation": "暂无明显缠论买卖点，建议观望，等结构清晰再动手",
            "entry": None,
            "stop": None,
            "target": None,
            "position_note": "空仓等待也是一种操作",
        }
    last = mmds[-1]
    # 小白保护：低置信度已降级观望，不给具体入场价，避免误导。
    if verdict.get("action") == "观望":
        return {
            "explanation": "当前信号置信度偏低，先观察，等更明确的买卖点再动手",
            "entry": None,
            "stop": None,
            "target": None,
            "position_note": "别因为一个模糊信号就进场，空仓等待也是操作",
            "signal": verdict.get("signal"),
            "direction": None,
        }
    is_buy = "buy" in last.mmd_type.value
    bi = last.bi
    # V625: 信号缺少触发笔时不给具体价位（避免 entry=None 且止损/目标取错窗口）。
    if bi is None:
        return {
            "explanation": "该信号缺少触发笔，暂不给具体价位，建议观望",
            "entry": None,
            "stop": None,
            "target": None,
            "position_note": "结构不完整，先观察",
            "signal": verdict.get("signal"),
            "direction": None,
        }
    idx = bi.end.bar_index
    closes = [float(k.close) for k in result.klines]
    highs = [float(k.high) for k in result.klines]
    lows = [float(k.low) for k in result.klines]
    # 把索引夹在有效范围内，避免越界导致止损/目标取到错误窗口。
    idx = max(0, min(idx, len(closes) - 1))

    def _r(v: Any) -> float | None:
        return round(float(v), 2) if v is not None else None

    entry = (
        _r(closes[idx])
        if idx is not None and 0 <= idx < len(closes)
        else _r(bi.end.val if bi else None)
    )
    zs = last.zs
    if is_buy:
        lo = lows[max(0, (idx or 0) - 10) : (idx or 0) + 1]
        stop = _r(min(lo)) if lo else _r(zs.zd if zs else None)
        hi = highs[max(0, (idx or 0) - 60) : (idx or 0) + 1]
        target = _r(max(hi)) if hi else _r(zs.zg if zs else None)
        explanation = (
            f"出现{last.mmd_type.value}买点：参考买入价 {entry}；"
            f"若跌破 {stop} 先离场，目标先看 {target} 附近。"
        )
        position_note = "新手建议小仓位试仓，确认上涨再加，不要一次满仓"
    else:
        hi = highs[max(0, (idx or 0) - 10) : (idx or 0) + 1]
        stop = _r(max(hi)) if hi else _r(zs.zg if zs else None)
        lo = lows[max(0, (idx or 0) - 60) : (idx or 0) + 1]
        target = _r(min(lo)) if lo else _r(zs.zd if zs else None)
        explanation = (
            f"出现{last.mmd_type.value}卖点：参考卖出价 {entry}；"
            f"若重新站上 {stop} 说明转强，可等回落到 {target} 附近。"
        )
        position_note = "新手建议先减仓落袋，不要因小涨就追回"
    return {
        "explanation": explanation,
        "entry": entry,
        "stop": stop,
        "target": target,
        "position_note": position_note,
        "signal": verdict.get("signal"),
        "direction": "buy" if is_buy else "sell",
    }


# 小白保护阈值：低于该置信度的信号不直接给买卖建议，先观察。
_MIN_CONF = 0.6


def _verdict(mmds: list[Any]) -> dict[str, Any]:
    """根据最新三类买卖点给出择时结论（可解释、非黑盒、低置信度降级观望）。"""
    if not mmds:
        return {"action": "观望", "reason": "截至目标日无缠论买卖点信号"}
    last = mmds[-1]
    typ = last.mmd_type.value
    conf = last.confidence or 0
    if conf < _MIN_CONF:
        return {
            "action": "观望",
            "signal": typ,
            "confidence": round(conf, 2),
            "reason": f"信号置信度偏低（{conf:.0%}），建议先观察，等更明确的买卖点",
        }
    if "buy" in typ:
        action = "买入"
        reason = f"最新信号 {typ}（置信度 {conf:.0%}），可考虑分批建仓"
    elif "sell" in typ:
        action = "卖出"
        reason = f"最新信号 {typ}（置信度 {conf:.0%}），建议减仓/离场"
    else:
        action = "观望"
        reason = f"最新信号 {typ}（置信度 {conf:.0%}），观察确认"
    return {"action": action, "signal": typ, "confidence": round(conf, 2), "reason": reason}


def _run_timing_one(
    df: pd.DataFrame, symbol: str, market: str, code: str, target: date
) -> dict[str, Any]:
    from easy_tdx.chanlun import ChanlunAnalyser

    if df is None or df.empty:
        return {"symbol": symbol, "error": "无K线数据"}
    col = "date" if "date" in df.columns else "datetime"
    ts = pd.to_datetime(df[col])
    df = df[ts.dt.normalize() <= pd.Timestamp(target)].reset_index(drop=True)
    if df.empty or len(df) < 30:
        return {
            "symbol": symbol,
            "error": f"截至 {target} 的 K 线不足（<30 根，实际 {len(df)})",
        }

    freq = "daily"
    analyser = ChanlunAnalyser(code=symbol, frequency=freq)
    result = analyser.process_klines(df)
    d = result.to_dict()
    # 补充分型列表（与 /chanlun/analyze 契约一致）供前端标注
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
    v = _verdict(result.mmds)
    novice = _novice_advice(result, v)
    # V594: 用这只标的自己历史窗口内的信号做前瞻命中率验证，
    # 给小白一个「这类买卖点历史上准不准」的可信度提示。
    from easy_tdx.backtest.signal_accuracy import compute_signal_accuracy_by_type

    closes_for_sa = [float(k.close) for k in result.klines]
    mmd_signals = [
        {
            "type": mmd.mmd_type.value,
            "bar_index": mmd.bi.end.bar_index if mmd.bi else None,
        }
        for mmd in result.mmds
    ]
    sa = compute_signal_accuracy_by_type(closes_for_sa, mmd_signals)
    signal_quality = {
        "summary": sa.get("summary"),
        "ranking": sa.get("ranking", [])[:5],
    }
    return {
        "symbol": symbol,
        "market": market,
        "code": code,
        "date": str(target),
        "bars": _df_to_bars(df),
        "bis": d["bis"],
        "xds": d["xds"],
        "zss": d["zss"],
        "mmds": d["mmds"],
        "bcs": d["bcs"],
        "fractals": d["fractals"],
        # MACD 序列（dif/dea/hist 与 bars 一一对应），前端 ChanlunChart 副图展示，
        # 便于用户核对背驰的 MACD 面积依据。
        "macd": d["macd"],
        "verdict": v,
        # V592: 面向小白的择时建议（入场/止损/目标 + 人话说明 + 仓位提示）
        "novice_advice": novice,
        # V594: 信号类型前瞻命中率（哪类买卖点历史上更靠谱）
        "signal_quality": signal_quality,
        "structure": {
            "bi_count": len(result.bis),
            "zs_count": len(result.zss),
            "mmd_count": len(result.mmds),
            "bc_count": len(result.bcs),
        },
    }


@router.post("/stock-pick/timing")
async def stock_pick_timing(
    req: dict[str, Any],
    client: Any = Depends(get_client),
    mac_client: Any | None = Depends(get_mac_client_optional),
) -> dict[str, Any]:
    """第二步：缠论择时（截至目标日的前复权 K 线）。

    请求体：{"date":"2026-05-01","symbols":[{"market":"SH","code":"600519"}],"count":400}
    返回每只标的的完整缠论结构 + 择时结论，前端可直接喂给 ChanlunChart。
    """
    date_str = str(req.get("date", ""))
    if not date_str:
        raise HTTPException(status_code=400, detail="缺少 date")
    try:
        target = date.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="date 格式应为 YYYY-MM-DD") from None

    symbols_raw = req.get("symbols") or []
    if not symbols_raw:
        raise HTTPException(status_code=400, detail="symbols 不能为空")
    symbols: list[dict[str, str]] = [
        {"market": str(s.get("market", "SZ")).upper()[:2], "code": str(s["code"]).zfill(6)}
        for s in symbols_raw
        if s.get("code")
    ]
    count = max(60, min(int(req.get("count", 400)), 1600))

    # 并发取数 + 分析（串行依赖单连接，简单起见 per-symbol 串行，快于全市场）
    results: list[dict[str, Any]] = []
    for sym in symbols:
        market, code = sym["market"], sym["code"]
        symbol = f"{market}:{code}"
        try:
            df = await _fetch_window(mac_client, client, market, code, count)
            results.append(_run_timing_one(df, symbol, market, code, target))
        except Exception as e:  # noqa: BLE001
            logger.warning("stock-pick timing %s 失败: %s", symbol, e)
            results.append({"symbol": symbol, "market": market, "code": code, "error": str(e)})
    return {"date": date_str, "results": results}
