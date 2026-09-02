"""信号监控路由。

提供实时/准实时的高置信度缠论买卖点监控能力。
用户可订阅一批股票代码，后端支持定时自动轮询（PeriodicTask），
前端通过轮询或 WebSocket 获取新信号。
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, Depends

from easy_tdx.web.convert import category_from_str, market_from_str
from easy_tdx.web.deps import get_client

logger = logging.getLogger(__name__)

router = APIRouter(tags=["monitor"])


@dataclass
class MonitorTask:
    """单个监控任务。"""

    task_id: str
    stocks: list[dict[str, str]]  # [{market, code}]
    category: str  # K线周期
    confidence_threshold: float  # 置信度阈值
    interval_seconds: int = 60  # 自动检查间隔
    last_check: float = 0.0
    last_signals: list[dict[str, Any]] = field(default_factory=list)
    running: bool = False
    scheduled: bool = False  # 是否有后台定时任务在运行


class SignalMonitor:
    """全局信号监控管理器。支持后台定时轮询。"""

    def __init__(self) -> None:
        self._tasks: dict[str, MonitorTask] = {}
        self._lock = asyncio.Lock()
        self._running_tasks: dict[str, asyncio.Task[Any]] = {}  # task_id -> asyncio.Task

    async def create_task(
        self,
        stocks: list[dict[str, str]],
        category: str,
        confidence_threshold: float,
        interval_seconds: int = 60,
    ) -> str:
        """创建新的监控任务。"""
        task_id = uuid.uuid4().hex[:12]
        task = MonitorTask(
            task_id=task_id,
            stocks=stocks,
            category=category,
            confidence_threshold=confidence_threshold,
            interval_seconds=interval_seconds,
        )
        async with self._lock:
            self._tasks[task_id] = task
        return task_id

    async def stop_task(self, task_id: str) -> bool:
        """停止监控任务（含取消后台定时任务）。"""
        async with self._lock:
            if task_id not in self._tasks:
                return False
            # 取消后台定时任务
            bg_task = self._running_tasks.pop(task_id, None)
            if bg_task and not bg_task.done():
                bg_task.cancel()
                try:
                    await bg_task
                except asyncio.CancelledError:
                    pass
            self._tasks[task_id].running = False
            self._tasks[task_id].scheduled = False
            del self._tasks[task_id]
            return True

    async def get_task(self, task_id: str) -> MonitorTask | None:
        """获取监控任务状态。"""
        async with self._lock:
            return self._tasks.get(task_id)

    async def check_signals(self, task_id: str, client: Any) -> list[dict[str, Any]]:
        """检查监控任务中的股票，返回新信号。"""
        from easy_tdx.chanlun import ChanlunAnalyser

        task = await self.get_task(task_id)
        if task is None:
            return []

        new_signals: list[dict[str, Any]] = []
        freq_map: dict[str, str] = {
            "MIN_1": "1min",
            "MIN_5": "5min",
            "MIN_15": "15min",
            "MIN_30": "30min",
            "MIN_60": "60min",
            "DAY": "daily",
            "WEEK": "weekly",
        }
        freq = freq_map.get(task.category.upper(), "daily")

        for stock in task.stocks:
            market = stock.get("market", "SZ")
            code = stock.get("code", "")
            try:
                df = await client.get_security_bars(
                    market_from_str(market),
                    code,
                    category_from_str(task.category),
                    0,
                    500,
                )
                if df is None or len(df) < 100:
                    continue

                analyser = ChanlunAnalyser(code=f"{market}{code}", frequency=freq)
                result = analyser.process_klines(df)

                # 查找高置信度信号
                for mmd in result.mmds:
                    if mmd.confidence >= task.confidence_threshold:
                        # 检查是否是新信号（不在上次结果中）
                        signal_key = f"{mmd.mmd_type.value}_{mmd.bi.end.k.date.strftime('%Y-%m-%d') if mmd.bi and mmd.bi.end else ''}"
                        is_new = not any(s.get("key") == signal_key for s in task.last_signals)
                        if is_new:
                            new_signals.append(
                                {
                                    "stock": f"{market}{code}",
                                    "type": mmd.mmd_type.value,
                                    "date": result._fmt_dt(mmd.bi.end.k.date)
                                    if mmd.bi and mmd.bi.end
                                    else None,
                                    "confidence": round(mmd.confidence, 2),
                                    "msg": mmd.msg,
                                    "key": signal_key,
                                    # V102 决策支持（条件264-267）
                                    "v102_signal_quality": getattr(
                                        mmd, "_signal_quality_scorecard", None
                                    ),
                                    "v102_decision_support": getattr(
                                        mmd, "_decision_support", None
                                    ),
                                    "v102_pattern_match": getattr(
                                        mmd, "_historical_pattern_match", None
                                    ),
                                }
                            )
                            # 标记为已记录
                            task.last_signals.append(
                                {
                                    "key": signal_key,
                                    "checked_at": time.time(),
                                }
                            )
                            # 只保留最近100条记录
                            task.last_signals = task.last_signals[-100:]
            except Exception as e:
                logger.warning("Signal check failed for %s%s: %s", market, code, e)

        task.last_check = time.time()
        return new_signals

    async def cleanup_old_signals(self, task_id: str, max_age_hours: float = 24.0) -> int:
        """清理过旧的已检查信号。"""
        task = await self.get_task(task_id)
        if task is None:
            return 0
        cutoff = time.time() - max_age_hours * 3600
        before = len(task.last_signals)
        task.last_signals = [s for s in task.last_signals if s.get("checked_at", 0) > cutoff]
        return before - len(task.last_signals)

    async def start_periodic_check(self, task_id: str, client: Any) -> None:
        """启动后台定时检查任务（被 monitor_create 调用）。"""
        task = await self.get_task(task_id)
        if task is None:
            return

        async def _periodic_loop() -> None:
            """每隔 interval_seconds 检查一次信号。"""
            while True:
                try:
                    await asyncio.sleep(task.interval_seconds)
                    if task_id not in self._tasks:
                        break  # 任务已被删除
                    await self.check_signals(task_id, client)
                    logger.debug("Periodic check done for task %s", task_id)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.warning("Periodic check error for task %s: %s", task_id, e)

        bg_task = asyncio.create_task(_periodic_loop())
        async with self._lock:
            self._running_tasks[task_id] = bg_task
            if task_id in self._tasks:
                self._tasks[task_id].scheduled = True

    async def stop_periodic_check(self, task_id: str) -> None:
        """停止后台定时检查任务。"""
        bg_task = self._running_tasks.pop(task_id, None)
        if bg_task and not bg_task.done():
            bg_task.cancel()
            try:
                await bg_task
            except asyncio.CancelledError:
                pass
        async with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id].scheduled = False


# 全局单例
_monitor = SignalMonitor()


@router.post("/monitor/create")
async def monitor_create(
    req: dict[str, Any],
    client: Any = Depends(get_client),
) -> dict[str, Any]:
    """创建信号监控任务（支持后台自动轮询）。

    Args:
        stocks: 股票代码列表 [{"market": "SZ", "code": "000001"}, ...]
        category: K线周期（默认 DAY）
        confidence_threshold: 置信度阈值（默认 0.7）
        interval_seconds: 自动检查间隔秒数（默认 60，0=不自动检查）
    """
    stocks = req.get("stocks", [])
    category = req.get("category", "DAY")
    threshold = req.get("confidence_threshold", 0.7)
    interval = req.get("interval_seconds", 60)

    if not stocks:
        return {"error": "stocks 不能为空"}

    task_id = await _monitor.create_task(stocks, category, threshold, interval)

    # 如果 interval > 0，启动后台定时检查
    if interval > 0:
        await _monitor.start_periodic_check(task_id, client)

    return {"task_id": task_id, "stock_count": len(stocks), "interval": interval}


@router.get("/monitor/{task_id}")
async def monitor_status(task_id: str) -> dict[str, Any]:
    """获取监控任务状态。"""
    task = await _monitor.get_task(task_id)
    if task is None:
        return {"error": "任务不存在"}
    return {
        "task_id": task.task_id,
        "stocks": task.stocks,
        "stock_count": len(task.stocks),
        "category": task.category,
        "threshold": task.confidence_threshold,
        "interval": task.interval_seconds,
        "last_check": task.last_check,
        "last_signals_count": len(task.last_signals),
        "running": task.running,
        "scheduled": task.scheduled,
    }


@router.post("/monitor/{task_id}/check")
async def monitor_check(
    task_id: str,
    client: Any = Depends(get_client),
) -> dict[str, Any]:
    """手动触发一次信号检查。"""
    task = await _monitor.get_task(task_id)
    if task is None:
        return {"error": "任务不存在"}

    task.running = True
    try:
        new_signals = await _monitor.check_signals(task_id, client)
    finally:
        task.running = False

    return {
        "task_id": task_id,
        "new_signals": new_signals,
        "count": len(new_signals),
    }


@router.post("/monitor/{task_id}/stop")
async def monitor_stop(task_id: str) -> dict[str, Any]:
    """停止监控任务（含后台定时任务）。"""
    removed = await _monitor.stop_task(task_id)
    return {"removed": removed}


@router.get("/monitor/list")
async def monitor_list() -> dict[str, Any]:
    """列出所有监控任务。"""
    tasks = []
    for tid, task in _monitor._tasks.items():
        tasks.append(
            {
                "task_id": task.task_id,
                "stock_count": len(task.stocks),
                "category": task.category,
                "threshold": task.confidence_threshold,
                "interval": task.interval_seconds,
                "last_check": task.last_check,
                "running": task.running,
                "scheduled": task.scheduled,
            }
        )
    return {"tasks": tasks, "count": len(tasks)}
