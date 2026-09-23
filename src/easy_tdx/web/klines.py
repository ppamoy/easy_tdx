"""共享 K 线取数助手（QFQ 前复权 + MAC 回退）。

历史上只有 chanlun 路由有 MAC 回退，diagnosis / screening / backtest / monitor
直接走标准 AsyncTdxClient。当标准 TDX 主机返回空行情（服务器不提供数据）时，
这些端点会全部取不到 K 线。统一走本模块：优先 MAC（支持前复权），MAC 不可用
或返回空时回退标准 TdxClient，保证各分析入口与 /bars 图表同一价格体系。
"""

from __future__ import annotations

import logging
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
            return out
        _logger.warning("MAC QFQ 返回空，回退标准 TdxClient（不复权）")
    df = await tdx_client.get_security_bars(
        market_from_str(market), code, cat, start, count, bar_time=bar_time
    )
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
            mac_client, tdx_client, market, code, category, start, _PAGE_SIZE,
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
    combined = combined.drop_duplicates(subset=[col], keep="first")
    combined = combined.sort_values(col).reset_index(drop=True)
    return combined
