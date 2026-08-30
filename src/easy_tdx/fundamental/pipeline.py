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
        logger.warning("无可用 gpcw 财报文件")
        return pd.DataFrame()
    recs = load_all_periods(zips, client, codes=codes, markets=markets)
    if not recs:
        return pd.DataFrame()
    frame = build_indicator_frame(recs)
    rows: list[pd.Series] = []
    for p in pool:
        row = pick_report(frame, p["code"], target, market=p.get("market"))
        if row is None:
            continue
        r2 = row.copy()
        r2["market"] = p.get("market", r2.get("market"))
        rows.append(r2)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def subsequent_performance(
    market: str,
    code: str,
    target: date,
    *,
    client: TdxClient | None = None,
    horizons: tuple[int, ...] = (20, 60, 250),
) -> dict[str, Any]:
    """自 target 后 N 个交易日（约 N 个交易日）的实际涨幅。

    取 target 之后最近的 K 线作为基准价，计算第 N 根 K 线的相对涨幅（%）。
    无足够数据时返回 None。
    """
    from easy_tdx.models.enums import KlineCategory, Market

    if client is None:
        client = TdxClient()
    mk = Market[market.upper()] if isinstance(market, str) else market
    try:
        df = client.get_security_bars(mk, code, KlineCategory.DAY, 0, 400)
    except Exception as e:
        logger.warning("获取 %s%s 后续行情失败: %s", market, code, e)
        return {}
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
