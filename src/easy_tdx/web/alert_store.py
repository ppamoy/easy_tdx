"""全局提醒流（V718）：信号监控 + 今日看板统一写入的自动提醒存储。

- 信号监控的定时检查把新发现的高置信度信号写成提醒（含入场/止损/目标、
  历史胜率、递归确认、季节仓位建议）；
- 「今日可操作」看板任务完成后把行动榜的买入/卖出信号写成提醒；
- 前端经 ``GET /monitor/alerts`` 轮询该流，实现自动提醒。

内存有界（deque 上限），进程重启清空——提醒是短期/准实时的，历史回看
请用选股后验与回测。
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

_MAX_ALERTS = 200

_feed: deque[dict[str, Any]] = deque(maxlen=_MAX_ALERTS)
_lock = threading.Lock()


def push_alert(alert: dict[str, Any]) -> None:
    """写入一条提醒（带时间戳与来源；去重键可选）。"""
    entry = dict(alert)
    entry.setdefault("ts", time.time())
    entry.setdefault("source", "monitor")
    key = entry.get("key")
    if key:
        # 同键提醒（同一信号同一天）已在流中则跳过，避免重复提醒
        with _lock:
            if any(a.get("key") == key for a in _feed):
                return
    with _lock:
        _feed.append(entry)


def recent_alerts(limit: int = 50) -> list[dict[str, Any]]:
    """最近的提醒（最新在前）。limit<=0 返回空列表（语义：不取任何条）。"""
    # V720: 此前 max(1, …) 把 limit=0/-1 夹成 1 条，"要 0 条" 却返回了 1 条。
    if limit <= 0:
        return []
    with _lock:
        items = list(_feed)
    items.reverse()
    return items[: min(int(limit), _MAX_ALERTS)]


def clear_alerts() -> int:
    """清空提醒流，返回清除条数。"""
    with _lock:
        n = len(_feed)
        _feed.clear()
    return n
