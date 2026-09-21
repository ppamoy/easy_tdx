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
