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

from easy_tdx.web.actionable import (  # noqa: F401  可操作择时口径（共享，供测试与监控复用）
    _MIN_CONF,
    _novice_advice,
    _recursion_context,
    _verdict,
)
from easy_tdx.web.deps import get_client, get_mac_client_optional
from easy_tdx.web.task_runner import report_progress

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

    date_str = str(req.get("date", ""))
    if not date_str:
        raise HTTPException(status_code=400, detail="缺少 date")
    try:
        target = date.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="date 格式应为 YYYY-MM-DD") from None

    markets = req.get("markets") or ["SZ", "SH"]
    norm_markets = [str(m).upper()[:2] for m in markets if str(m).upper()[:2] in ("SH", "SZ")]
    # V720: pool 形状校验（元素须 {market, code} 对象），非法 400 而非 500。
    norm_pool = _norm_pool_arg(req)
    stock_type = str(req.get("stock_type", "all"))
    if stock_type not in ("all", "tree", "grain", "vegetable"):
        stock_type = "all"
    pool_scope = str(req.get("pool_scope", "pool"))
    top_n = _int_arg(req.get("top_n"), "top_n", 50, 1, 200)

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
        out = _screen_run_sync(
            target,
            norm_markets,
            norm_pool,
            stock_type=stock_type,
            pool_scope=pool_scope,
            top_n=top_n,
            min_score=float(req.get("min_score", 15.0)),
            with_performance=bool(req.get("with_performance", False)),
        )
        return {"date": date_str, **out}

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
    from easy_tdx.web.klines import fetch_qfq_klines

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


def _run_timing_one(
    df: pd.DataFrame,
    symbol: str,
    market: str,
    code: str,
    target: date,
    recursion_depth: int = 2,
) -> dict[str, Any]:
    from easy_tdx.chanlun import ChanlunAnalyser, ChanlunConfig

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
    config = ChanlunConfig(recursion_depth=max(1, int(recursion_depth)))
    analyser = ChanlunAnalyser(code=symbol, frequency=freq, config=config)
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
    by_type = sa.get("by_type") or {}

    def _best_of(direction: str) -> dict[str, Any] | None:
        """取该方向（buy/sell）信号数>0 中 5 根超额命中率最高的类型摘要。"""
        cands = [
            v
            for v in by_type.values()
            if str(v.get("direction", "")).lower() == direction and v.get("signals", 0) > 0
        ]
        if not cands:
            return None

        def _excess(v: dict[str, Any]) -> float:
            hz = v.get("horizons") or {}
            h5 = hz.get("5") or hz.get("3") or {}
            return float(h5.get("excess_hit_rate", 0.0) or 0.0)

        best = max(cands, key=_excess)
        hz = best.get("horizons") or {}
        h5 = hz.get("5") or hz.get("3") or {}
        return {
            "type": best.get("type"),
            "hit_rate": float(h5.get("hit_rate", 0.0) or 0.0),
            "excess_hit_rate": float(h5.get("excess_hit_rate", 0.0) or 0.0),
            "avg_return": float(h5.get("avg_return", 0.0) or 0.0),
            "signals": best.get("signals"),
            "verdict": best.get("verdict"),
        }

    signal_quality = {
        "summary": sa.get("summary"),
        "ranking": sa.get("ranking", [])[:5],
        # V717: 全量 by_type 中该方向最强的类型摘要（ranking[:5] 可能全是卖型）
        "best_buy": _best_of("buy"),
        "best_sell": _best_of("sell"),
    }
    # V709: 多级别递归结构确认——较高级别的买卖点信号给笔级别结论作佐证。
    rec = _recursion_context(result)
    vdir = v.get("direction")
    if rec.get("latest") and vdir:
        rec["alignment"] = "confirm" if rec["latest"]["direction"] == vdir else "conflict"
    else:
        rec["alignment"] = "none"
    rec["base_direction"] = vdir
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
        # V709: 多级别递归结构确认（depth_produced/latest/alignment/note）
        "recursion": rec,
        # 多级别递归完整 levels（bi / xd / xd_l2 …），前端可切换到更高级别画图
        "levels": d["levels"],
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
    # V720: symbols 形状校验——元素必须是含 code 的对象（此前 ["SH600519"] 之类
    # 字符串元素会让 s.get 抛 'str' has no attribute 'get' → 500）。
    if any(not isinstance(s, dict) for s in symbols_raw):
        raise HTTPException(status_code=400, detail="symbols 必须是 {market, code} 对象列表")
    symbols: list[dict[str, str]] = [
        {"market": str(s.get("market", "SZ")).upper()[:2], "code": str(s["code"]).zfill(6)}
        for s in symbols_raw
        if s.get("code")
    ]
    if not symbols:
        raise HTTPException(status_code=400, detail="symbols 不能为空")
    count = _int_arg(req.get("count"), "count", 400, 60, 1600)
    recursion_depth = _int_arg(req.get("recursion_depth"), "recursion_depth", 2, 1, 8)

    # 并发取数 + 分析（串行依赖单连接，简单起见 per-symbol 串行，快于全市场）
    results: list[dict[str, Any]] = []
    for sym in symbols:
        market, code = sym["market"], sym["code"]
        symbol = f"{market}:{code}"
        try:
            df = await _fetch_window(mac_client, client, market, code, count)
            results.append(
                _run_timing_one(df, symbol, market, code, target, recursion_depth=recursion_depth)
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("stock-pick timing %s 失败: %s", symbol, e)
            results.append({"symbol": symbol, "market": market, "code": code, "error": str(e)})

    # V713: 四季判断联动——按目标日给出市场所处季节与仓位建议，前端排行展示。
    from easy_tdx.fundamental.pipeline import detect_season_for_date

    try:
        season = await asyncio.to_thread(detect_season_for_date, target)
    except Exception:  # noqa: BLE001
        logger.warning("四季判断失败", exc_info=True)
        season = None
    return {
        "date": date_str,
        "results": results,
        "season": season.as_dict() if season else None,
    }


@router.post("/stock-pick/screen/async")
async def stock_pick_screen_async(req: dict[str, Any]) -> dict[str, Any]:
    """第一步异步版：提交长盈选股后台任务，立即返回 task_id。

    全市场扫描约 13s，进度经 ``GET /stock-pick/screen/task/{task_id}`` 轮询
    （progress 0~100 + 说明）。请求体与 /stock-pick/screen 一致。
    """
    date_str = str(req.get("date", ""))
    if not date_str:
        raise HTTPException(status_code=400, detail="缺少 date")
    try:
        target = date.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="date 格式应为 YYYY-MM-DD") from None

    markets = req.get("markets") or ["SZ", "SH"]
    norm_markets = [str(m).upper()[:2] for m in markets if str(m).upper()[:2] in ("SH", "SZ")]
    # V720: pool 形状校验（元素须 {market, code} 对象），非法 400 而非 500。
    norm_pool = _norm_pool_arg(req)
    stock_type = str(req.get("stock_type", "all"))
    if stock_type not in ("all", "tree", "grain", "vegetable"):
        stock_type = "all"
    pool_scope = str(req.get("pool_scope", "pool"))
    top_n = _int_arg(req.get("top_n"), "top_n", 50, 1, 200)

    from easy_tdx.web.task_runner import get_runner

    runner = get_runner()

    def _run() -> dict[str, Any]:
        out = _screen_run_sync(
            target,
            norm_markets,
            norm_pool,
            stock_type=stock_type,
            pool_scope=pool_scope,
            top_n=top_n,
            min_score=float(req.get("min_score", 15.0)),
            with_performance=bool(req.get("with_performance", False)),
        )
        return {"date": date_str, **out}

    desc = f"长盈选股 {'全市场' if pool_scope == 'full' else '自选池'} {len(norm_pool)} 只"
    task_id = runner.submit(_run, description=desc)
    return {"task_id": task_id, "description": desc}


@router.get("/stock-pick/screen/task/{task_id}")
async def stock_pick_screen_task(task_id: str) -> dict[str, Any]:
    """轮询选股任务状态（progress 0~100 + 说明 + 结果）。"""
    from easy_tdx.web.task_runner import get_runner

    state = get_runner().peek(task_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"未知任务 '{task_id}'")
    return state.to_dict()


def _int_arg(raw: Any, name: str, default: int, lo: int, hi: int) -> int:
    """解析整数参数并在越界/非法时给出可读的 400（避免泄漏 int() 内部报错）。"""
    if raw is None or raw == "":
        return default
    try:
        val = int(raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"{name} 必须是整数") from None
    return max(lo, min(val, hi))


def _norm_pool_arg(req: dict[str, Any]) -> list[dict[str, str]]:
    """V720: 校验并规整请求里的 pool——元素必须是 {market, code} 对象。

    此前 pool 传字符串/数字时，后续 ``p.get(...)`` 直接抛
    ``'str' object has no attribute 'get'`` → 500。松散 dict 端点在入口处
    做形状校验，非法一律 400。
    """
    pool_raw = req.get("pool")
    if pool_raw is None or pool_raw == "":
        return _default_pool(["SZ", "SH"])
    if not isinstance(pool_raw, list) or any(not isinstance(p, dict) for p in pool_raw):
        raise HTTPException(status_code=400, detail="pool 必须是 {market, code} 对象列表")
    norm = [
        {"market": str(p.get("market", "SZ")).upper()[:2], "code": str(p["code"]).zfill(6)}
        for p in pool_raw
        if p.get("code")
    ]
    if not norm:
        raise HTTPException(status_code=400, detail="pool 必须是 {market, code} 对象列表")
    return norm


def _screen_run_sync(
    target: date,
    norm_markets: list[str],
    norm_pool: list[dict[str, str]],
    *,
    stock_type: str = "all",
    pool_scope: str = "pool",
    top_n: int = 50,
    min_score: float = 15.0,
    with_performance: bool = False,
) -> dict[str, Any]:
    """选股扫描（同步，供 worker 线程执行；进度经 report_progress 上报）。"""
    report_progress(3.0, "开始选股")
    if pool_scope == "full":
        from easy_tdx.fundamental.pipeline import scan_market

        out = scan_market(
            target,
            markets=tuple(norm_markets),
            stock_type=stock_type,
            top_n=top_n,
            min_score=min_score,
            with_performance=with_performance,
            sina_pool=norm_pool,
            min_mcap_yi=100.0,
            require_profit=True,
        )
        full_rows: list[dict[str, Any]] = [
            _normalize_result_row(r) for r in out.get("results") or []
        ]
        full_rows.sort(key=lambda x: x["quality_score"] or 0, reverse=True)
        report_progress(100.0, "完成")
        return {"total": len(full_rows), "results": full_rows}

    from easy_tdx.fundamental.pipeline import run_screen

    # V719: 池路径同样上报进度（此前 progress 恒 null，前端进度条不显示）。
    out = run_screen(
        target,
        norm_pool,
        with_performance=with_performance,
        min_mcap_yi=100.0,
        require_profit=True,
    )
    report_progress(97.0, "整理选股结果")
    results = out.get("results") or []
    if stock_type != "all":
        results = [r for r in results if r["category"] == stock_type]
    rows: list[dict[str, Any]] = [_normalize_result_row(r) for r in results]
    rows.sort(key=lambda x: x["quality_score"] or 0, reverse=True)
    report_progress(100.0, "完成")
    return {"total": len(rows), "results": rows}


def _fetch_window_sync(market: str, code: str, count: int) -> pd.DataFrame | None:
    """同步取窗口 K 线（MAC 优先 QFQ + 列规整），供 worker 线程使用。

    与 fetch_qfq_klines 同一价格体系；标准 TDX 失效时仍可用（MAC 正常）。
    """
    try:
        from easy_tdx.mac.client import MacClient
        from easy_tdx.mac.enums import Adjust, Period
        from easy_tdx.models.enums import Market

        client = MacClient()
        try:
            client.connect()
            mk = int(Market[market.upper()].value)
            df = client.get_stock_kline(
                mk, code, Period.DAILY, start=0, count=count, adjust=Adjust.QFQ
            )
        finally:
            try:
                client.close()
            except Exception:  # noqa: BLE001
                pass
        if df is None or df.empty:
            return None
        out = df.copy()
        if "float_shares" in out.columns:
            out = out.drop(columns=["float_shares"])
        # 与 fetch_qfq_klines 相同的列规整：日线 datetime→date
        daily_plus = True  # dashboard 固定日线
        if "datetime" in out.columns:
            if daily_plus:
                out["datetime"] = pd.to_datetime(out["datetime"]).dt.normalize()
            out = out.rename(columns={"datetime": "date"})
        return out
    except Exception:  # noqa: BLE001
        logger.warning("dashboard 同步取 %s%s 失败", market, code, exc_info=True)
        return None


def _dashboard_run_sync(
    target: date,
    norm_markets: list[str],
    norm_pool: list[dict[str, str]],
    *,
    stock_type: str = "all",
    pool_scope: str = "pool",
    top_n: int = 50,
    time_n: int = 20,
    recursion_depth: int = 2,
    min_score: float = 15.0,
) -> dict[str, Any]:
    """「今日可操作」一屏决策看板（同步，供 worker 线程执行）。

    聚合三步：选股池 → 逐票批量择时（verdict/建议/递归确认/历史胜率）→
    四季仓位建议；输出按可操作性排序的行动榜。
    """
    from easy_tdx.fundamental.pipeline import detect_season_for_date

    # ── 1. 选股池 ──────────────────────────────────────────────
    report_progress(5.0, "选股中")
    screen_out = _screen_run_sync(
        target,
        norm_markets,
        norm_pool,
        stock_type=stock_type,
        pool_scope=pool_scope,
        top_n=top_n,
        min_score=min_score,
        with_performance=False,
    )
    rows: list[dict[str, Any]] = screen_out.get("results") or []
    report_progress(40.0, f"选股完成 {len(rows)} 只")

    # ── 2. 逐票批量择时（同步 MAC 取数 + chanlun 分析）──────────
    batch = rows[: max(1, time_n)]
    timing_rows: list[dict[str, Any]] = []
    for i, r in enumerate(batch):
        market = str(r.get("market", "SZ"))
        code = str(r.get("code", "")).zfill(6)
        symbol = f"{market}:{code}"
        report_progress(40.0 + 50.0 * i / max(1, len(batch)), f"择时 {i + 1}/{len(batch)} {symbol}")
        try:
            df = _fetch_window_sync(market, code, 1200)
            tr = _run_timing_one(df, symbol, market, code, target, recursion_depth=recursion_depth)
        except Exception as e:  # noqa: BLE001
            logger.warning("dashboard 择时 %s 失败: %s", symbol, e)
            tr = {"symbol": symbol, "market": market, "code": code, "error": str(e)}
        if "error" in tr:
            continue
        tr["category"] = r.get("category")
        tr["quality_score"] = r.get("quality_score")
        timing_rows.append(tr)
    report_progress(92.0, f"择时完成 {len(timing_rows)}/{len(batch)}")

    # ── 3. 四季判断 ────────────────────────────────────────────
    season = detect_season_for_date(target)
    report_progress(96.0, "四季判断完成")

    # ── 4. 聚合行动榜（买入→卖出→观望，置信度降序）──────────────
    action_rank = {"买入": 0, "卖出": 1, "观望": 2}
    for tr in timing_rows:
        v = tr.get("verdict") or {}
        tr["action"] = v.get("action") or "观望"
        tr["confidence"] = v.get("confidence") or 0
        rec = tr.get("recursion") or {}
        tr["alignLabel"] = (
            "同向"
            if rec.get("alignment") == "confirm"
            else "背离"
            if rec.get("alignment") == "conflict"
            else "—"
        )
        top_buy = (tr.get("signal_quality") or {}).get("best_buy")
        tr["top_hit_label"] = (
            f"{top_buy['type']} {round(float(top_buy['hit_rate']) * 100)}%" if top_buy else "—"
        )
        tr["top_hit_good"] = bool(
            top_buy
            and float(top_buy.get("hit_rate") or 0) >= 0.6
            and float(top_buy.get("excess_hit_rate") or 0) > 0
        )
    timing_rows.sort(key=lambda x: (action_rank.get(x["action"], 2), -x["confidence"]))
    summary = {
        "buy": sum(1 for x in timing_rows if x["action"] == "买入"),
        "sell": sum(1 for x in timing_rows if x["action"] == "卖出"),
        "wait": sum(1 for x in timing_rows if x["action"] == "观望"),
        "timed": len(timing_rows),
        "pool": len(rows),
    }
    # V718: 看板行动榜的买入/卖出信号写入全局提醒流（自动提醒）。
    from easy_tdx.web.actionable import season_position_note
    from easy_tdx.web.alert_store import push_alert

    season_note = season_position_note(season.as_dict() if season else None)
    for tr in timing_rows:
        if tr.get("action") not in ("买入", "卖出"):
            continue
        adv = tr.get("novice_advice") or {}
        push_alert(
            {
                "source": "dashboard",
                "stock": str(tr.get("symbol")),
                "type": (tr.get("verdict") or {}).get("signal"),
                "action": tr.get("action"),
                "confidence": tr.get("confidence"),
                "date": str(target),
                "msg": adv.get("explanation"),
                "entry": adv.get("entry"),
                "stop": adv.get("stop"),
                "target": adv.get("target"),
                "position_note": adv.get("position_note"),
                "top_hit_label": tr.get("top_hit_label"),
                "align_label": tr.get("alignLabel"),
                "season_note": season_note,
                "key": f"dashboard_{tr.get('symbol')}_{tr.get('action')}_{target.isoformat()}",
            }
        )

    report_progress(100.0, "完成")
    return {
        "date": str(target),
        "season": season.as_dict() if season else None,
        "summary": summary,
        "actions": timing_rows,
    }


@router.post("/stock-pick/dashboard/async")
async def stock_pick_dashboard_async(req: dict[str, Any]) -> dict[str, Any]:
    """「今日可操作」一屏决策看板：提交后台任务，立即返回 task_id。

    聚合选股池 + 批量择时 + 四季仓位（进度经 task/{id} 轮询）。
    请求体：{"date":"2026-09-01","pool_scope":"pool","top_n":50,"time_n":20,"recursion_depth":2}
    """
    date_str = str(req.get("date", ""))
    if not date_str:
        raise HTTPException(status_code=400, detail="缺少 date")
    try:
        target = date.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="date 格式应为 YYYY-MM-DD") from None

    markets = req.get("markets") or ["SZ", "SH"]
    norm_markets = [str(m).upper()[:2] for m in markets if str(m).upper()[:2] in ("SH", "SZ")]
    # V720: pool 形状校验（元素须 {market, code} 对象），非法 400 而非 500。
    norm_pool = _norm_pool_arg(req)
    stock_type = str(req.get("stock_type", "all"))
    if stock_type not in ("all", "tree", "grain", "vegetable"):
        stock_type = "all"
    pool_scope = str(req.get("pool_scope", "pool"))
    top_n = _int_arg(req.get("top_n"), "top_n", 50, 1, 200)
    time_n = _int_arg(req.get("time_n"), "time_n", 20, 1, 50)
    recursion_depth = _int_arg(req.get("recursion_depth"), "recursion_depth", 2, 1, 8)

    from easy_tdx.web.task_runner import get_runner

    runner = get_runner()

    def _run() -> dict[str, Any]:
        return _dashboard_run_sync(
            target,
            norm_markets,
            norm_pool,
            stock_type=stock_type,
            pool_scope=pool_scope,
            top_n=top_n,
            time_n=time_n,
            recursion_depth=recursion_depth,
            min_score=float(req.get("min_score", 15.0)),
        )

    desc = f"今日可操作 {'全市场' if pool_scope == 'full' else '自选池'} 择时{time_n} 只"
    task_id = runner.submit(_run, description=desc)
    return {"task_id": task_id, "description": desc}


@router.get("/stock-pick/dashboard/task/{task_id}")
async def stock_pick_dashboard_task(task_id: str) -> dict[str, Any]:
    """轮询「今日可操作」任务状态（progress + 结果）。"""
    from easy_tdx.web.task_runner import get_runner

    state = get_runner().peek(task_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"未知任务 '{task_id}'")
    return state.to_dict()
