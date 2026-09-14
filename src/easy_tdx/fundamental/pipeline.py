"""P1 长赢基本面选股 —— 编排管线：财报加载 → point-in-time 指标 → 树粮菜分类 → 后续表现 → 季节。"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import pandas as pd

from easy_tdx.client import TdxClient
from easy_tdx.fundamental.indicators import (
    load_all_periods_frame,
    pick_report,
    pick_reports_bulk,
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
        # V89：每份报告期走 SQLite 指标帧缓存，重复选股/扫描只解析一次
        frame = load_all_periods_frame(zips, client, codes=codes, markets=markets)
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


def _as_of_close(
    market: str,
    code: str,
    target: date,
    *,
    client: TdxClient | None = None,
) -> float | None:
    """目标日收盘价（用于计算市值门槛）。"""
    from easy_tdx.models.enums import KlineCategory, Market

    if client is None:
        client = TdxClient()
    mk = Market[market.upper()] if isinstance(market, str) else market
    try:
        df = client.get_security_bars(mk, code, KlineCategory.DAY, 0, 400)
    except Exception as e:
        logger.warning("获取 %s%s 目标日收盘失败: %s", market, code, e)
        return None
    return _returns_at(df, target, ()).get("as_of_close")


def _total_mcap_yi(indicators: dict[str, Any], close: float | None) -> float | None:
    """总市值（亿元）= 总股本 × 目标日收盘价。"""
    shares = indicators.get("total_shares")
    if shares is None or close is None or float(close) <= 0:
        return None
    try:
        return float(shares) * float(close) / 1e8
    except (TypeError, ValueError):
        return None


def _annualize_eps(eps: float, report_date: Any) -> float:
    """V504/V517: 按报告期月数把单期 EPS 年化为全年口径（动态市盈率）。

    委托给 ``indicators.annualize_ytd`` 共享实现（V517 消除与 screener 的重复）。
    """
    from easy_tdx.fundamental.indicators import annualize_ytd

    result = annualize_ytd(eps, report_date)
    return float(result) if result is not None else eps


def _valuation(
    ind: dict[str, Any],
    close: float | None,
    report_date: Any = None,
) -> dict[str, float | None]:
    """V497/V504: 用目标日收盘价 + 每股收益/净资产计算 PE/PB 估值。

    Args:
        ind: ``screen_stock`` 输出的 indicators（含 eps/bps）。
        close: 目标日收盘价（``subsequent_performance`` 返回的 ``as_of_close``）。
        report_date: 报告期（date/str/None），用于把单期 EPS 年化（动态市盈率）。

    Returns:
        ``{"pe": float|None, "pb": float|None}``；无价格/亏损/无净资产时对应项为 None。
    """
    out: dict[str, float | None] = {"pe": None, "pb": None}
    if close is None or not isinstance(close, (int, float)) or close <= 0:
        return out
    eps = ind.get("eps")
    bps = ind.get("bps")
    if eps is not None and float(eps) > 0:
        eps_ann = _annualize_eps(float(eps), report_date)
        out["pe"] = round(float(close) / eps_ann, 2)
    # V588: PB 用每股净资产（point-in-time，非累计值），不年化——与动态 PE（年化 EPS）区分
    if bps is not None and float(bps) > 0:
        out["pb"] = round(float(close) / float(bps), 2)
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
                "hit_rate": round(sum(1 for v in vals if v > 0) / len(vals), 2) if vals else None,
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
    min_mcap_yi: float | None = None,
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
                perf = subsequent_performance(sr.market, sr.code, target, client=client)
                d["performance"] = perf
                # V497/V504: 估值（PE/PB）用目标日收盘价 + 每股收益/净资产，EPS 按报告期年化
                d["valuation"] = _valuation(
                    d["indicators"], perf.get("as_of_close"), sr.report_date
                )
                # V591: 市值门槛（总股本 × 目标日收盘价），低于阈值直接排除
                if min_mcap_yi is not None:
                    mcap = _total_mcap_yi(
                        d.get("indicators", {}), (perf or {}).get("as_of_close")
                    )
                    if mcap is None or mcap < min_mcap_yi:
                        continue
                d["total_mcap_yi"] = (
                    mcap if (min_mcap_yi is not None and mcap is not None) else None
                )
            results.append(d)
    season = detect_season_for_date(target, client=client)
    # V512: 同分时按三维总分作次级排序（与 scan_market 的 V511 一致）
    results.sort(
        key=lambda r: (
            r["scores"].get(r["category"], 0),
            sum(float(v) for v in r["scores"].values()),
        ),
        reverse=True,
    )
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


def scan_market(
    target: date,
    *,
    markets: tuple[str, ...] = ("SH", "SZ"),
    stock_type: str = "all",
    top_n: int = 50,
    min_score: float = 15.0,
    with_performance: bool = True,
    zips: list[str] | None = None,
    client: TdxClient | None = None,
    horizons: tuple[int, ...] = (20, 60, 250),
    sina_pool: list[dict[str, str]] | None = None,
    min_mcap_yi: float | None = None,
) -> dict[str, Any]:
    """P2 全市场扫描：对目标日期 tdx 财报覆盖的全部股票做树粮菜打分并排序。

    与 :func:`run_screen`（自选池）的区别：不传代码池，直接对选中报告期的
    **全市场记录**做批量 point-in-time（:func:`pick_reports_bulk`），每只股票
    取披露日 ≤ target 的最新一期，逐只跑树粮菜三维打分，按分类得分降序返回
    top_n 只（默认 50）。可选附加后续 N 日表现（只对返回的 top_n 计算，
    避免全市场几千次行情请求）。

    V91：当 gpcw 财报未覆盖目标日期（更早历史/下载受限）时，可用
    ``sina_pool``（自选代码列表）走新浪财报补充——每行标注 ``data_source``
    （gpcw/sina），前端可区分数据来源。

    Args:
        target: 历史时点（只用披露日 ≤ target 的财报）。
        markets: 扫描的市场子集，默认沪深两市。
        stock_type: "all"/"tree"/"grain"/"vegetable"。
        top_n: 每类/总数最多返回的股票数。
        min_score: 分类得分下限（过滤明显不及格标的）。
        with_performance: top_n 结果是否附带后续 20/60/250 日表现。
        zips: 指定的 gpcw 财报文件列表（缺省按 target 自动选择）。
        client: 注入 TdxClient（测试或省连接用）。
        sina_pool: 可选，[{"market": "SH"/"SZ", "code": "600519"}, ...]。
            gpcw 覆盖不足时用新浪补充这些代码（结果行 data_source="sina"）。

    Returns:
        {"date", "total_scanned", "results": [...], "by_category": {...},
         "season": {...}|None, "warning": 可选}
    """
    if zips is None:
        zips = pick_report_zips(target, client=client)
    # V89：全市场记录经 SQLite 指标帧缓存加载，重复扫描不再重复解析 zip
    frame = load_all_periods_frame(zips, client, codes=None, markets=set(markets))
    season = detect_season_for_date(target, client=client)
    base_out: dict[str, Any] = {
        "date": str(target),
        "markets": list(markets),
        "season": season.as_dict() if season else None,
        "by_category": {cat: 0 for cat in ("tree", "grain", "vegetable")},
        "total_scanned": 0,
        "results": [],
    }

    picked = (
        pick_reports_bulk(frame, target, markets=set(markets))
        if not frame.empty
        else pd.DataFrame()
    )

    # V91：新浪补充——gpcw 未覆盖的股票（frame 空或单只缺失）走新浪财报
    if sina_pool and frame.empty:
        from easy_tdx.fundamental.sina_adapter import load_sina_rows

        extra: list[dict[str, Any]] = []
        for p in sina_pool:
            code = str(p.get("code", "")).zfill(6)
            if not code:
                continue
            try:
                srows = load_sina_rows(code, p.get("market", "SZ"))
            except Exception as e:  # noqa: BLE001
                logger.warning("新浪补充 %s 失败: %s", code, e)
                continue
            if not srows:
                continue
            sframe = _sina_frame(srows)
            srow = pick_report(sframe, code, target, market=p.get("market"))
            if srow is not None:
                r2 = srow.to_dict() if hasattr(srow, "to_dict") else dict(srow)
                r2["data_source"] = "sina"
                extra.append(r2)
        if extra:
            picked = pd.DataFrame(extra)

    if picked is None or picked.empty:
        base_out["warning"] = "截至目标日期无可用财报数据（gpcw/新浪均无覆盖）"
        return base_out

    scored: list[dict[str, Any]] = []
    by_category: dict[str, int] = {"tree": 0, "grain": 0, "vegetable": 0}
    pool_size = len(picked)
    for _, row in picked.iterrows():
        sr = screen_stock(row, pool_size=pool_size)
        if sr is None:
            continue
        sc = sr.scores.get(sr.category, 0)
        if sc < min_score:
            continue
        by_category[sr.category] = by_category.get(sr.category, 0) + 1
        if stock_type != "all" and sr.category != stock_type:
            continue
        d = sr.as_dict()
        d["score"] = round(sc, 1)
        d["data_source"] = str(row.get("data_source", "gpcw"))
        scored.append(d)

    # V511: 同分（如多只「粮型」都 100 分）时按三维总分作次级排序，
    # 让「多维度都强」的标的排前，避免仅按代码顺序任取 top_n。
    scored.sort(
        key=lambda r: (r["score"], sum(float(v) for v in r["scores"].values())),
        reverse=True,
    )

    # V591: 市值门槛需要候选池内每只的目标日收盘价。为避免全市场逐只取行情，
    # 先按得分取一个扩大候选窗口（top_n 的 5 倍，至少 100），只对这个窗口
    # 取价算市值，过滤后截取最终 top_n。凌晨批量跑，压力可控。
    if min_mcap_yi is not None:
        window_n = max(min(len(scored), top_n * 5), min(len(scored), 100))
    else:
        window_n = min(len(scored), top_n)
    window = scored[:window_n]
    if with_performance:
        for d in window:
            perf = subsequent_performance(
                d["market"], d["code"], target, client=client, horizons=horizons
            )
            d["performance"] = perf
            # V497/V504: 估值（PE/PB）用目标日收盘价 + 每股收益/净资产，EPS 按报告期年化
            d["valuation"] = _valuation(
                d["indicators"], perf.get("as_of_close"), d.get("report_date")
            )
            close = (perf or {}).get("as_of_close")
            if min_mcap_yi is not None:
                mcap = _total_mcap_yi(d.get("indicators", {}), close)
                d["total_mcap_yi"] = mcap
                if mcap is None or mcap < min_mcap_yi:
                    d["_mcap_excluded"] = True
    if min_mcap_yi is not None:
        kept = [d for d in window if not d.get("_mcap_excluded")][:top_n]
    else:
        kept = window[:top_n]

    base_out.update(
        {
            "by_category": by_category,
            "total_scanned": pool_size,
            "results": kept,
        }
    )
    if scored and len(scored) > len(kept):
        base_out["truncated"] = len(scored) - len(kept)
    return base_out