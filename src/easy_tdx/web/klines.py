"""共享 K 线取数助手（QFQ 前复权 + MAC 回退）。

历史上只有 chanlun 路由有 MAC 回退，diagnosis / screening / backtest / monitor
直接走标准 AsyncTdxClient。当标准 TDX 主机返回空行情（服务器不提供数据）时，
这些端点会全部取不到 K 线。统一走本模块：优先 MAC（支持前复权），MAC 不可用
或返回空时回退标准 TdxClient，保证各分析入口与 /bars 图表同一价格体系。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from easy_tdx.web.convert import (
    adjust_from_str,
    category_from_str,
    market_from_str,
    market_value_from_str,
    period_times_from_category,
)

_logger = logging.getLogger(__name__)


# ── 分钟线磁盘缓存（read-through）──────────────────────────────────
# 30min/60min 取数必须逐页翻回历史（TDX 协议锚定最新 bar），实测一次
# multi-level 请求要 32s —— 超过浏览器 fetch 的 30s 上限（Moli 实测
# "curl request failed ... after 30000ms"），前端直接拿到 failed to fetch。
# 而 scripts/fetch_minute_data.py 已经把 30min/60min 全量落到
# audit_data_min/{market}{code}_{period}.json，直接读盘可秒回。
_MIN_CACHE_DIR = Path(__file__).resolve().parents[3] / "audit_data_min"
_MIN_CACHE_PERIODS = {"MIN_30": "30min", "MIN_60": "60min"}


def _read_min_cache(market: str, code: str, category: str) -> pd.DataFrame | None:
    """命中磁盘分钟线缓存则返回 DataFrame，否则 None。"""
    slug = _MIN_CACHE_PERIODS.get(str(category).upper())
    if not slug:
        return None
    fp = _MIN_CACHE_DIR / f"{str(market).lower()}{code}_{slug}.json"
    if not fp.is_file():
        return None
    try:
        import json

        rows = json.loads(fp.read_text(encoding="utf-8"))
        if not isinstance(rows, list) or not rows:
            return None
        df = pd.DataFrame(rows)
        if "datetime" not in df.columns:
            return None
        df["datetime"] = pd.to_datetime(df["datetime"])
        return df.sort_values("datetime").reset_index(drop=True)
    except Exception:  # noqa: BLE001
        return None


def _slice_cache(
    df: pd.DataFrame, start_ts: Any, end_exclusive: Any
) -> pd.DataFrame:
    ts = pd.to_datetime(df["datetime"])
    mask = ts >= start_ts
    if end_exclusive is not None:
        mask &= ts < end_exclusive
    return df.loc[mask].reset_index(drop=True)


async def fetch_qfq_klines(
    mac_client: Any,
    tdx_client: Any,
    market: str,
    code: str,
    category: str,
    start: int,
    count: int,
    bar_time: str = "start",
) -> pd.DataFrame:
    """按与前端 /bars 一致的方式取 K 线（默认 QFQ 前复权），保证缠论
    结构与图表 K 线使用同一价格体系，避免复权差导致分型/笔/线段端点
    画在错误价位上。

    - 优先 AsyncMacClient.get_stock_kline(adjust=QFQ)（支持前复权）；
    - MAC 不可用时回退标准 AsyncTdxClient.get_security_bars（无复权，
      与 /bars 的回退行为一致）。
    返回的 DataFrame 列契约与 analyser 兼容（date/datetime + OHLCV）。
    """
    from easy_tdx.models.enums import KlineCategory

    # V735 Round 10：本地缓存优先（30min/60min 已由 fetch_minute_data.py 落盘；
    # 日线等级别在 fetch_qfq_klines 拉取后也会自动保存）。
    from easy_tdx.web.kline_cache import read_klines, save_klines

    cached = read_klines(market, code, category)
    if cached is not None and not cached.empty:
        return cached

    cat = category_from_str(category)
    if mac_client is not None:
        period, times = period_times_from_category(cat)
        # V721: D15 MAC 客户端异常同样回退 TDX（此前只对空 df 回退，MAC 故障
        # 窗口内会直接向上抛异常，screening/scan 静默 200+0 结果）。
        try:
            df = await mac_client.get_stock_kline(
                market_value_from_str(market),
                code,
                period,
                start,
                count,
                times,
                adjust=adjust_from_str("QFQ"),
                bar_time=bar_time,
            )
        except Exception as exc:  # noqa: BLE001
            _logger.warning("MAC 客户端异常，回退 TDX: %s", exc)
            df = pd.DataFrame()
        if not df.empty:
            # 与 /bars 相同的列规整：日线及以上 datetime→date，保证 analyser 识别
            daily_plus = int(cat) >= int(KlineCategory.DAY)
            _time_col = "date" if daily_plus else "datetime"
            out = df.copy()
            if "float_shares" in out.columns:
                out = out.drop(columns=["float_shares"])
            if "datetime" in out.columns:
                if daily_plus:
                    out["datetime"] = pd.to_datetime(out["datetime"]).dt.normalize()
                out = out.rename(columns={"datetime": _time_col})
            # 保存到本地缓存
            try:
                save_klines(market, code, category, out)
            except Exception:  # noqa: BLE001
                _logger.debug("缓存保存失败 %s%s %s", market, code, category)
            return out
        _logger.warning("MAC QFQ 返回空，回退标准 TdxClient（不复权）")
    df = await tdx_client.get_security_bars(
        market_from_str(market), code, cat, start, count, bar_time=bar_time
    )
    # 保存到本地缓存
    if df is not None and not df.empty:
        try:
            save_klines(market, code, category, df)
        except Exception:  # noqa: BLE001
            _logger.debug("缓存保存失败 %s%s %s", market, code, category)
    return df


# ── 全历史分页取数（V722，R3 图表全历史回溯）──────────────────────────────

# TDX/MAC 协议单次请求上限（/bars 的 count 上限一致）
_PAGE_SIZE = 800
# lookback 参数硬上限（约 80 年日线，防御性限制）
MAX_LOOKBACK = 20000


async def fetch_paged_bars(
    mac_client: Any,
    tdx_client: Any,
    market: str,
    code: str,
    category: str,
    lookback: int = _PAGE_SIZE,
    bar_time: str = "start",
) -> pd.DataFrame:
    """从最新 bar 向过去循环翻页，凑满 lookback 根并去重拼接。

    TDX 协议 start 偏移为 uint16 且单次 count ≤800：前端要看更早的
    历史（同级别 K 线往前翻）必须由服务端循环翻页拼接。

    - 每页 800 根，第 k 页 start = k*800（0 = 最新一页）；
    - 每页拼接后按时间戳去重（跨页重叠场景），凑满即停；
    - 拼接后按时间升序排列（与单页契约一致）；
    - lookback 超过标的上市历史时返回全部可得 bar（不报错）。
    """
    lookback = max(1, min(int(lookback), MAX_LOOKBACK))
    frames: list[pd.DataFrame] = []
    have = 0
    for page in range((lookback + _PAGE_SIZE - 1) // _PAGE_SIZE):
        start = page * _PAGE_SIZE
        if start > 65535:  # uint16 偏移上限保护（V720 同款语义）
            break
        df = await fetch_qfq_klines(
            mac_client,
            tdx_client,
            market,
            code,
            category,
            start,
            _PAGE_SIZE,
            bar_time=bar_time,
        )
        if df is None or df.empty:
            break
        frames.append(df)
        have += len(df)
        if len(df) < _PAGE_SIZE:
            break  # 已到上市最早一页
        if have >= lookback:
            break
    if not frames:
        return pd.DataFrame()
    col = "date" if "date" in frames[0].columns else "datetime"
    combined = pd.concat(frames, ignore_index=True)
    # 归一 date 列类型：跨页 str/Timestamp 混杂会让 sort_values 抛
    # "'<' not supported between 'str' and 'Timestamp'"（实测 /stock-pick/timing 8/12 标的失败）。
    # 下游 _df_to_bars 用 str(dt)、_run_timing_one 用 pd.to_datetime，二者对 datetime 均安全。
    combined[col] = pd.to_datetime(combined[col], errors="coerce")
    combined = combined.drop_duplicates(subset=[col], keep="first")
    combined = combined.sort_values(col).reset_index(drop=True)
    # 截断为最新 lookback 根：翻页以「凑满 lookback」为停页条件，最后一页往往
    # 会多带回一整页（lookback=2000 → 3 页 ≈ 2400 根）。若不截断，返回的 bar
    # 数会大于请求的 lookback，与前端 /bars（按 count 截断为恰好 lookback 根、
    # 与本函数同源同价）帧长不一致——缠论分析的 bar_index 落在前端 props.bars
    # 的错误位置，导致分型/笔/中枢等所有索引锚定的标记整体错位
    # （用户反馈「顶底分型标记错乱」的根因）。两帧同以「最新 bar」对齐，
    # 取尾部 lookback 根即与 /bars 完全一致。
    if len(combined) > lookback:
        combined = combined.tail(lookback).reset_index(drop=True)
    return combined


async def fetch_bars_range(
    mac_client: Any,
    tdx_client: Any,
    market: str,
    code: str,
    category: str,
    start_date: str,
    end_date: str | None = None,
    max_bars: int = MAX_LOOKBACK,
    bar_time: str = "start",
) -> pd.DataFrame:
    """取任意历史区间 [start_date, end_date] 的 K 线（闭区间）。

    TDX 协议把一切取数锚定在最新 bar 上：start 只能是往回的偏移量。
    因此「看 2019 年的日线」无法单次直达——本函数从最新 bar 逐页向过去
    翻页，直到某页最早一根 ≤ start_date（或历史耗尽），再整体去重排序、
    按闭区间切片返回。

    - 分页节奏与 fetch_paged_bars 相同（每页 800 根，start = k*800）；
    - 页数由 max_bars 封顶（默认 MAX_LOOKBACK ≈ 80 年日线，防御性限制）；
    - 区间过滤对日线/分钟线一致：start_date 当日 00:00 起、
      end_date 次日 00:00 前（含 end_date 全天）；
    - 区间内无数据（如 start_date 早于上市日）返回空 DataFrame。
    """
    start_ts = pd.to_datetime(start_date, errors="coerce")
    if pd.isna(start_ts):
        return pd.DataFrame()
    end_ts_exclusive: pd.Timestamp | None = None
    if end_date:
        end_ts = pd.to_datetime(end_date, errors="coerce")
        if not pd.isna(end_ts):
            end_ts_exclusive = end_ts + pd.Timedelta(days=1)

    # 分钟线优先读磁盘缓存：逐页翻历史太慢（实测 32s > 浏览器 30s 上限）
    cached = _read_min_cache(market, code, category)
    _logger.warning("CACHEPROBE %s %s %s -> %s", market, code, category,
                    "HIT" if cached is not None else "MISS")
    if cached is not None:
        return _slice_cache(cached, start_ts, end_ts_exclusive)

    max_pages = max(1, min(int(max_bars), MAX_LOOKBACK) // _PAGE_SIZE)
    frames: list[pd.DataFrame] = []
    col: str | None = None
    reached_start = False
    for page in range(max_pages):
        start = page * _PAGE_SIZE
        if start > 65535:  # uint16 偏移上限保护（V720 同款语义）
            break
        df = await fetch_qfq_klines(
            mac_client,
            tdx_client,
            market,
            code,
            category,
            start,
            _PAGE_SIZE,
            bar_time=bar_time,
        )
        if df is None or df.empty:
            break
        col = col or ("date" if "date" in df.columns else "datetime")
        frames.append(df)
        if len(df) < _PAGE_SIZE:
            reached_start = True  # 上市最早一页，历史已耗尽
            break
        page_oldest = pd.to_datetime(df[col].iloc[0])
        if page_oldest <= start_ts:
            reached_start = True  # noqa: F841  循环出口标记（下轮循环前提前结束）
            break
    if not frames or col is None:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True)
    # 归一 date 列类型：跨页 str/Timestamp 混杂会让 sort_values 抛
    # "'<' not supported between 'str' and 'Timestamp'"（实测 /stock-pick/timing 8/12 标的失败）。
    # 下游 _df_to_bars 用 str(dt)、_run_timing_one 用 pd.to_datetime，二者对 datetime 均安全。
    combined[col] = pd.to_datetime(combined[col], errors="coerce")
    combined = combined.drop_duplicates(subset=[col], keep="first")
    combined = combined.sort_values(col).reset_index(drop=True)
    ts = pd.to_datetime(combined[col])
    mask = ts >= start_ts
    if end_ts_exclusive is not None:
        mask &= ts < end_ts_exclusive
    return combined.loc[mask].reset_index(drop=True)
