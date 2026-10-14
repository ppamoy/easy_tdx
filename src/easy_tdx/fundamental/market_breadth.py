"""涨跌家数（市场广度）数据获取。

从东方财富 push2 API 获取 A 股全市场涨跌统计，用于四季周期判断中的
「涨跌家数」信号。

只做一件事：返回当前上涨股票占比（0~1）。
历史日期的涨跌家数无法从 TDX 获取，返回 None（detect_season 自动跳过）。
"""

from __future__ import annotations

import logging
import urllib.request
import json

logger = logging.getLogger(__name__)

# 东方财富 push2 全 A 股列表（沪深主板/创业板/科创板）
_BASE = "https://push2.eastmoney.com/api/qt/clist/get"
_FS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"
_FIELDS = "f3"

_TIMEOUT = 8
_PAGES = 6  # 6 × 100 = 600 只，约 10% 样本


def _fetch_page(pn: int) -> list[dict] | None:
    """抓一页（100 只），返回 diff 列表或 None。"""
    url = (
        f"{_BASE}?pn={pn}&pz=100&po=0&np=1&fltt=2&invt=2"
        f"&fid=f12&fs={_FS}&fields={_FIELDS}"
    )
    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Mozilla/5.0")
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("data", {}).get("diff")
    except Exception as e:
        logger.debug("breadth page %d failed: %s", pn, e)
        return None


def fetch_breadth_ratio() -> float | None:
    """获取当前 A 股上涨占比（0~1）。

    东方财富 clist API 每页最多 100 条，抓 6 页（600 只，按代码排序
    获得无偏样本）后统计涨跌占比。

    返回 None 的情况：
    - 网络不可达
    - 非交易时段（所有股票涨跌幅为 0）
    - 解析失败
    """
    up = 0
    down = 0
    for pn in range(1, _PAGES + 1):
        diff = _fetch_page(pn)
        if not diff:
            continue
        for x in diff:
            try:
                chg = float(x.get("f3") or 0)
            except (TypeError, ValueError):
                continue
            if chg > 0:
                up += 1
            elif chg < 0:
                down += 1
    total = up + down
    if total == 0:
        logger.debug("breadth: 全部样本涨跌幅为 0（可能非交易时段）")
        return None
    ratio = up / total
    logger.debug("breadth: sample=%d up=%d down=%d ratio=%.3f", total, up, down, ratio)
    return ratio


__all__ = ["fetch_breadth_ratio"]
