"""数据验证型主机探测（V713）。

只测 TCP 连通会选出「能连上但返回空行情」的主机——实测 52 个候选标准主机中
7 个连接正常却对股票 K 线返回空 body，导致选股/择时等走标准协议的端点全部
取不到数据。本模块对候选主机**并发取真实 K 线验证**，只有真正返回行情数据
的主机才会被选用/缓存；验证结果带 TTL，避免每次建连都重新探测拖慢调用。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from easy_tdx.config import (
    _SHANGHAI_TZ,
    get_known_hosts,
    get_port,
    get_timeout,
)

_logger = logging.getLogger(__name__)

# 验证结果有效期：在此期间复用已验证的 best_host，不重复探测。
_VALIDATION_TTL_HOURS = 1.0
# 单主机探测硬超时（含连接+取数）与并发上限。
_PROBE_TIMEOUT = 8.0
_PROBE_CONCURRENCY = 16


def validation_fresh(validated_at: str | None, ttl_hours: float = _VALIDATION_TTL_HOURS) -> bool:
    """验证时间戳是否仍在有效期内。"""
    if not validated_at:
        return False
    try:
        dt = datetime.fromisoformat(validated_at)
    except ValueError:
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_SHANGHAI_TZ)
    return datetime.now(_SHANGHAI_TZ) - dt < timedelta(hours=ttl_hours)


async def validate_host_data_async(
    host: str,
    port: int | None = None,
    timeout: float | None = None,
) -> bool:
    """异步探测一台主机：取 5 根日线验证它确实返回行情数据（非空 body）。"""
    from easy_tdx.client import AsyncTdxClient
    from easy_tdx.models.enums import KlineCategory, Market

    async def _one() -> bool:
        client = AsyncTdxClient(
            host=host, port=port or get_port(), timeout=timeout or get_timeout()
        )
        async with client:
            df = await client.get_security_bars(Market.SH, "600519", KlineCategory.DAY, 0, 5)
            return df is not None and len(df) > 0

    try:
        return await asyncio.wait_for(_one(), timeout=_PROBE_TIMEOUT)
    except Exception:  # noqa: BLE001
        return False


async def pick_working_hosts_async(
    hosts: list[str] | None = None,
    port: int | None = None,
    timeout: float | None = None,
) -> list[str]:
    """并发探测候选主机，返回「真实可用优先、原顺序次之」的主机列表。

    可用的排前（保持原相对顺序），不可用的排后——调用方取首个即为
    经过数据验证的工作主机；全失败时返回原列表（回退原行为）。
    """
    if hosts is None:
        hosts = get_known_hosts()
    sem = asyncio.Semaphore(_PROBE_CONCURRENCY)
    results: list[tuple[int, bool]] = []

    async def _one(index: int, host: str) -> None:
        async with sem:
            ok = await validate_host_data_async(host, port, timeout)
            results.append((index, ok))

    await asyncio.gather(*(_one(i, h) for i, h in enumerate(hosts)))
    working = [hosts[i] for i, ok in sorted(results) if ok]
    rest = [hosts[i] for i, ok in sorted(results) if not ok]
    return working + rest
