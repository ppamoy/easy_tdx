"""P1 长赢基本面选股 —— 编排管线：财报加载 → point-in-time 指标 → 树粮菜分类 → 后续表现 → 季节。"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import pandas as pd

from easy_tdx.client import TdxClient
from easy_tdx.fundamental.indicators import (
    build_indicator_frame,
    load_all_periods,
    pick_report,
)
from easy_tdx.fundamental.screener import screen_stock
from easy_tdx.fundamental.season import SeasonResult, detect_season

logger = logging.getLogger(__name__)


def available_report_zips(client: TdxClient | None = None) -> list[tuple[str, int]]:
    """列出可用的 gpcw 报告期文件（文件名, 报告期 YYYYMMDD），报告期倒序。"""
    try:
        df = (
            client.get_financial_file_list()
            if client is not None
            else TdxClient().get_financial_file_list()
        )
    except Exception as e:
        logger.warning("获取 gpcw 文件列表失败: %s", e)
        return []
    if df is None or df.empty or "filename" not in df.columns:
        return []
    out: list[tuple[str, int]] = []
    for fn in df["filename"].tolist():
        s = str(fn)
        if not s.startswith("gpcw"):
            continue
        digits = "".join(ch for ch in s if ch.isdigit())
        if len(digits) >= 8:
            out.append((s, int(digits[:8])))
    out.sort(key=lambda x: x[1], reverse=True)
    return out


def pick_report_zips(
    target: date,
    all_zips: list[tuple[str, int]] | None = None,
    *,
    lookback_days: int = 550,
    client: TdxClient | None = None,
) -> list[str]:
    """选择报告期 <= target 且与 target 相差不超过 lookback_days 的财报文件。

    这样既覆盖 target 附近的最新披露，又提供同比/环比所需的历史期。
    """
    if all_zips is None:
        all_zips = available_report_zips(client)
    target_int = int(target.strftime("%Y%m%d"))
    sel: list[tuple[str, int]] = []
    for fn, period in all_zips:
        if period > target_int:
            continue
        if target_int - period <= lookback_days * 100:
            sel.append((fn, period))
    sel.sort(key=lambda x: x[1], reverse=True)
    return [fn for fn, _ in sel[:8]]


def load_pool(
    target: date,
    pool: list[dict[str, str]],
    *,
    client: TdxClient | None = None,
    zips: list[str] | None = None,
) -> pd.DataFrame:
    """加载股票池的 point-in-time 指标 DataFrame（每只股票一行，最新已披露期）。

    Args:
        pool: [{"market": "SH"/"SZ", "code": "600519"}, ...]
        zips: 指定财报文件列表；缺省自动按 target 选择。
    """
    if not pool:
        return pd.DataFrame()
    codes = {p["code"] for p in pool}
    markets = {p["market"] for p in pool}
    if zips is None:
        zips = pick_report_zips(target, client=client)
    if not zips:
        logger.warning("无可用 gpcw 财报文件，回退新浪财报")
        frame = pd.DataFrame()
    else:
        recs = load_all_periods(zips, client, codes=codes, markets=markets)
        frame = build_indicator_frame(recs) if recs else pd.DataFrame()
    rows: list[pd.Series] = []
    missing: list[dict[str, str]] = []
    for p in pool:
        row = None
        if not frame.empty:
            row = pick_report(frame, p["code"], target, market=p.get("market"))
        if row is None:
            missing.append(p)
            continue
        r2 = row.copy()
        r2["market"] = p.get("market", r2.get("market"))
        rows.append(r2)

    # gpcw 未覆盖（更早历史/下载受限）时回退新浪财报
    if missing:
        from easy_tdx.fundamental.sina_adapter import load_sina_rows

        for p in missing:
            try:
                sina_rows = load_sina_rows(p["code"], p.get("market", "SZ"))
            except Exception as e:  # noqa: BLE001
                logger.warning("新浪财报 %s 失败: %s", p["code"], e)
                continue
            if not sina_rows:
                continue
            sframe = _sina_frame(sina_rows)
            srow = pick_report(sframe, p["code"], target, market=p.get("market"))
            if srow is not None:
                r2 = srow.copy()
                r2["market"] = p.get("market", r2.get("market"))
                rows.append(r2)

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def _sina_frame(sina_rows: list[Any]) -> pd.DataFrame:
    """把新浪财报行转成与 build_indicator_frame 同构的 DataFrame。"""
    out: list[dict[str, Any]] = []
    for r in sina_rows:
        out.append(
            {
                "code": r.code,
                "market": r.market,
                "report_date": r.report_date,
                "disclosure_date": r.disclosure_date,
                **r.indicators,
            }
        )
    return pd.DataFrame(out)


def _returns_at(df: Any, target: date, horizons: tuple[int, ...]) -> dict[str, Any]:
    """给定 OHLC DataFrame（含 date/close 列），算 target 之后 N 个交易日的相对涨幅。"""
    if df is None or df.empty:
        return {}
    dates = pd.to_datetime(df["date"]).dt.date
    idx = None
    for i, d in enumerate(dates):
        if d >= target:
            idx = i
            break
    if idx is None:
        return {}
    base = float(df["close"].iloc[idx])
    out: dict[str, Any] = {"as_of_close": base, "bars_after": len(df) - idx - 1}
    for h in horizons:
        j = idx + h
        if j < len(df):
            c2 = float(df["close"].iloc[j])
            out[f"ret_{h}d"] = round((c2 / base - 1) * 100, 2) if base else None
        else:
            out[f"ret_{h}d"] = None
    return out


def subsequent_performance(
    market: str,
    code: str,
    target: date,
    *,
    client: TdxClient | None = None,
    horizons: tuple[int, ...] = (20, 60, 250),
) -> dict[str, Any]:
    """自 target 后 N 个交易日（约 N 个交易日）的实际涨幅。"""
    from easy_tdx.models.enums import KlineCategory, Market

    if client is None:
        client = TdxClient()
    mk = Market[market.upper()] if isinstance(market, str) else market
    try:
        df = client.get_security_bars(mk, code, KlineCategory.DAY, 0, 400)
    except Exception as e:
        logger.warning("获取 %s%s 后续行情失败: %s", market, code, e)
        return {}
    return _returns_at(df, target, horizons)


def index_performance(
    target: date,
    *,
    client: TdxClient | None = None,
    horizons: tuple[int, ...] = (20, 60, 250),
) -> dict[str, Any]:
    """上证指数（SH 000001）在 target 之后的 N 交易日涨幅，用作基准对比。"""
    from easy_tdx.models.enums import KlineCategory, Market

    if client is None:
        client = TdxClient()
    try:
        df = client.get_index_bars(Market.SH, "000001", KlineCategory.DAY, 0, 400)
    except Exception as e:
        logger.warning("获取上证指数后续行情失败: %s", e)
        return {}
    return _returns_at(df, target, horizons)


def _summarize_periods(
    periods: list[dict[str, Any]],
    horizons: tuple[int, ...],
) -> dict[str, Any]:
    """汇总多个历史时点的验证结果：按分类 + 总体 + 指数基准 + 是否跑赢。"""
    cats = ["tree", "grain", "vegetable"]

    def _stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
        st: dict[str, Any] = {"count": len(rows)}
        for h in horizons:
            vals = [
                r["performance"].get(f"ret_{h}d")
                for r in rows
                if r.get("performance") and r["performance"].get(f"ret_{h}d") is not None
            ]
            st[f"ret_{h}d"] = {
                "count": len(vals),
                "avg": round(sum(vals) / len(vals), 2) if vals else None,
                "hit_rate": round(sum(1 for v in vals if v > 0) / len(vals), 2)
                if vals
                else None,
            }
        return st

    by_category: dict[str, Any] = {}
    for cat in cats:
        rows = [r for p in periods for r in p.get("results", []) if r["category"] == cat]
        by_category[cat] = _stats(rows)

    all_rows = [r for p in periods for r in p.get("results", [])]
    overall = _stats(all_rows)

    idx_vals: dict[str, list[float]] = {}
    for p in periods:
        idx = p.get("index") or {}
        for h in horizons:
            v = idx.get(f"ret_{h}d")
            if v is not None:
                idx_vals.setdefault(f"ret_{h}d", []).append(v)
    index_stats: dict[str, Any] = {}
    for h in horizons:
        vals = idx_vals.get(f"ret_{h}d", [])
        index_stats[f"ret_{h}d"] = {
            "count": len(vals),
            "avg": round(sum(vals) / len(vals), 2) if vals else None,
        }

    beats: dict[str, Any] = {}
    for h in horizons:
        ov = overall[f"ret_{h}d"].get("avg")
        bm = index_stats[f"ret_{h}d"].get("avg")
        beats[f"ret_{h}d"] = {
            "alpha": round(ov - bm, 2) if ov is not None and bm is not None else None,
            "beats": (ov is not None and bm is not None and ov > bm),
        }

    return {
        "by_category": by_category,
        "overall": overall,
        "index": index_stats,
        "beats_index": beats,
    }


def run_verify(
    targets: list[date],
    pool: list[dict[str, str]],
    *,
    client: TdxClient | None = None,
    horizons: tuple[int, ...] = (20, 60, 250),
) -> dict[str, Any]:
    """批量时点验证：对多个历史日期分别选股，汇总树粮菜命中率并对比上证指数。

    Returns:
        {"periods": [{date, season, results, index}], "summary": {...}}
    """
    periods: list[dict[str, Any]] = []
    for t in targets:
        screen = run_screen(t, pool, client=client)
        idx = index_performance(t, horizons=horizons, client=client)
        periods.append(
            {
                "date": str(t),
                "season": screen.get("season"),
                "pool_size": screen.get("pool_size"),
                "results": screen.get("results", []),
                "index": idx,
            }
        )
    summary = _summarize_periods(periods, horizons)
    return {"periods": periods, "summary": summary}


def run_screen(
    target: date,
    pool: list[dict[str, str]],
    *,
    client: TdxClient | None = None,
    zips: list[str] | None = None,
    with_performance: bool = True,
) -> dict[str, Any]:
    """整条 P1 管线：指标 → 分类 → 后续表现。

    Returns:
        {"date", "pool_size", "results": [screen dict + perf], "season": ...}
    """
    frame = load_pool(target, pool, client=client, zips=zips)
    results: list[dict[str, Any]] = []
    if not frame.empty:
        for _, row in frame.iterrows():
            sr = screen_stock(row, pool_size=len(pool))
            if sr is None:
                continue
            d = sr.as_dict()
            if with_performance:
                d["performance"] = subsequent_performance(
                    sr.market, sr.code, target, client=client
                )
            results.append(d)
    season = detect_season_for_date(target, client=client)
    results.sort(key=lambda r: r["scores"].get(r["category"], 0), reverse=True)
    return {
        "date": str(target),
        "pool_size": len(pool),
        "results": results,
        "season": season.as_dict() if season else None,
    }


def detect_season_for_date(
    target: date,
    *,
    client: TdxClient | None = None,
) -> SeasonResult | None:
    """用上证指数日线判断 target 当日所处的四季。"""
    from easy_tdx.models.enums import KlineCategory, Market

    if client is None:
        client = TdxClient()
    try:
        df = client.get_index_bars(Market.SH, "000001", KlineCategory.DAY, 0, 320)
    except Exception as e:
        logger.warning("获取上证指数失败: %s", e)
        return None
    if df is None or df.empty:
        return None
    dates = list(pd.to_datetime(df["date"]).dt.date)
    closes = [float(x) for x in df["close"].tolist()]
    vols = [float(x) for x in df["vol"].tolist()] if "vol" in df.columns else None
    return detect_season(dates, closes, target, volumes=vols)
