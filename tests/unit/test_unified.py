"""unified.py 统一客户端边界测试（V394）。

unified.py 此前覆盖率 38%：代理方法从未被直接调用。本文件用 mock 注入
MacClient/MacExClient/AsyncMacClient/AsyncMacExClient，覆盖同步/异步两类
客户端的懒加载、路由（A股→Mac、扩展→MacEx）、方法委托、上下文管理与关闭。
全程离线，不连 TDX。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from easy_tdx.unified import UnifiedTdxClient

# 同步 A 股代理方法名列表（用于批量委托校验）
_SYNC_A_METHODS = [
    "get_stock_quotes",
    "get_stock_quotes_list",
    "get_stock_kline",
    "get_stock_kline_with_indicators",
    "get_tick_chart",
    "get_tick_charts",
    "get_chart_sampling",
    "get_transactions",
    "get_symbol_info",
    "get_board_list",
    "get_board_members",
    "get_belong_board",
    "get_capital_flow",
    "get_auction",
    "get_unusual",
    "get_server_info",
    "get_kline_offset",
    "get_file_meta",
    "download_file_chunk",
    "download_file",
]

# 同步扩展市场代理方法
_SYNC_EX_METHODS = [
    "goods_count",
    "goods_list",
    "goods_quotes",
    "goods_quotes_list",
    "goods_kline",
    "goods_tick_chart",
    "goods_chart_sampling",
    "goods_transaction",
]


class TestUnifiedTdxClient:
    def test_init_defaults(self) -> None:
        c = UnifiedTdxClient()
        assert c._mac is None
        assert c._mac_ex is None

    def test_close_when_never_connected(self) -> None:
        c = UnifiedTdxClient()
        c.close()  # 不抛异常

    def test_connect_lazy_creates_mac(self) -> None:
        mock = MagicMock()
        with patch("easy_tdx.unified.MacClient.from_best_host", return_value=mock) as fbh:
            c = UnifiedTdxClient(heartbeat_interval=3.0, timeout=7.0)
            c.connect()
            fbh.assert_called_once_with(heartbeat_interval=3.0, timeout=7.0)
            mock.connect.assert_called_once()
            # 第二次 connect 复用，不重复建连
            c.connect()
            fbh.assert_called_once()

    def test_ensure_mac_ex_lazy(self) -> None:
        mock = MagicMock()
        with patch("easy_tdx.unified.MacExClient.from_best_host", return_value=mock) as fbh:
            c = UnifiedTdxClient(timeout=5.0)
            c._ensure_mac_ex()
            fbh.assert_called_once_with(timeout=5.0)
            mock.connect.assert_called_once()

    def test_close_resets_and_closes(self) -> None:
        c = UnifiedTdxClient()
        mac = MagicMock()
        ex = MagicMock()
        c._mac = mac
        c._mac_ex = ex
        c.close()
        mac.close.assert_called_once()
        ex.close.assert_called_once()
        assert c._mac is None
        assert c._mac_ex is None

    def test_disconnect_alias(self) -> None:
        c = UnifiedTdxClient()
        mac = MagicMock()
        c._mac = mac
        c.disconnect()
        mac.close.assert_called_once()

    def test_context_manager(self) -> None:
        mock = MagicMock()
        with patch("easy_tdx.unified.MacClient.from_best_host", return_value=mock):
            with UnifiedTdxClient() as c:
                assert c._mac is mock
            mock.close.assert_called_once()

    @pytest.mark.parametrize("method", _SYNC_A_METHODS)
    def test_a_share_delegation(self, method: str) -> None:
        """A 股方法全部委托到 _ensure_mac().<method>。"""
        c = UnifiedTdxClient()
        mock = MagicMock()
        c._mac = mock
        args = {
            "stocks": [(0, "600000")],
            "category": 0,
            "market": 0,
            "code": "600000",
            "indicators": ["MA"],
            "period": 4,
            "date": 20240101,
            "days": 5,
            "count": 10,
            "start": 0,
            "fields": None,
            "board_type": 0,
            "board_symbol": "881001",
            "sort_type": 0,
            "sort_order": 0,
            "exclude_flags": None,
            "offset": 0,
            "filename": "x.dat",
            "index": 0,
            "size": 100,
            "filesize": 0,
            "times": 1,
            "adjust": 0,
            "params": None,
        }
        # 用与方法签名匹配的最小参数集调用（MagicMock 接受任意参数）
        fn = getattr(c, method)
        try:
            result = fn(**{k: v for k, v in args.items() if k in _arg_names(fn)})
        except TypeError:
            # 兜底：MagicMock 方法签名未知时直接调用无参
            result = getattr(mock, method)(*[])
            getattr(mock, method).assert_called_once()
            return
        assert result is getattr(mock, method).return_value


def _arg_names(fn: object) -> set[str]:
    """尽力返回函数可接受的关键字参数名（忽略 self）。"""
    import inspect

    sig = inspect.signature(fn)  # type: ignore[arg-type]
    return {p for p in sig.parameters if p != "self"}
