"""数据验证型主机探测（V713）单元测试。

- validation_fresh TTL 语义（None/非法/过期/有效）；
- pick_working_hosts_async 并发探测：可用优先、原顺序保持、全失败回退原列表。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

from easy_tdx.host_probe import pick_working_hosts_async, validation_fresh


def _iso(hours_ago: float) -> str:

    from easy_tdx.config import _SHANGHAI_TZ

    dt = datetime.now(_SHANGHAI_TZ) - timedelta(hours=hours_ago)
    return dt.isoformat()


def test_validation_fresh_semantics() -> None:
    """None/非法串/过期 → False；有效期内 → True。"""
    assert validation_fresh(None) is False
    assert validation_fresh("not-a-date") is False
    assert validation_fresh(_iso(2.0)) is False  # 超过 1h TTL
    assert validation_fresh(_iso(0.1)) is True  # 6 分钟前，有效
    # naive datetime 也接受（按上海时区解释）
    assert validation_fresh(datetime.now().isoformat()) is True


def test_pick_working_hosts_prefers_working_in_order() -> None:
    """可用主机排前且保持原相对顺序；不可用排后。"""
    hosts = ["a", "b", "c", "d"]
    ok_map = {"a": False, "b": True, "c": False, "d": True}

    async def fake_validate(host, port=None, timeout=None):
        return ok_map[host]

    with patch("easy_tdx.host_probe.validate_host_data_async", side_effect=fake_validate):
        import asyncio

        ranked = asyncio.run(pick_working_hosts_async(hosts))
    assert ranked == ["b", "d", "a", "c"]


def test_pick_working_hosts_all_fail_returns_original() -> None:
    """全失败时返回原列表（回退原行为），不抛错。"""
    hosts = ["x", "y"]

    async def fake_validate(host, port=None, timeout=None):
        return False

    with patch("easy_tdx.host_probe.validate_host_data_async", side_effect=fake_validate):
        import asyncio

        ranked = asyncio.run(pick_working_hosts_async(hosts))
    assert ranked == ["x", "y"]
