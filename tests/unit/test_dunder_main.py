"""``python -m easy_tdx`` 入口（__main__.py）回归测试（V-40）。

该模块此前 0 覆盖（45 语句），承载三个关键守卫：
1. multiprocessing spawn 子进程保护（防 uvicorn 重复启动死循环）；
2. PyInstaller frozen 模式 None 流重定向（防 uvicorn logging isatty 崩溃）；
3. 三条启动路径分派（子进程/开发态无参→serve/打包态无参→托盘）。

全部单测不真启动 uvicorn/托盘，只验证分派逻辑与副作用。
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from easy_tdx.__main__ import (
    _is_multiprocessing_child,
    _redirect_std_streams_to_log,
    main,
)

# ── _is_multiprocessing_child ────────────────────────────────────────────


class TestMultiprocessingChildDetection:
    def test_standard_flag_with_equals(self) -> None:
        with patch.object(sys, "argv", ["exe", "--multiprocessing-fork=123"]):
            assert _is_multiprocessing_child() is True

    def test_standard_flag_plain(self) -> None:
        with patch.object(sys, "argv", ["exe", "--multiprocessing-fork"]):
            assert _is_multiprocessing_child() is True

    def test_mp_main_flag(self) -> None:
        with patch.object(sys, "argv", ["exe", "--mp-main"]):
            assert _is_multiprocessing_child() is True

    def test_normal_cli_args_not_child(self) -> None:
        with patch.object(sys, "argv", ["easy-tdx", "serve", "--port", "8000"]):
            assert _is_multiprocessing_child() is False

    def test_no_args_not_child(self) -> None:
        with patch.object(sys, "argv", ["easy-tdx"]):
            assert _is_multiprocessing_child() is False


# ── _redirect_std_streams_to_log ─────────────────────────────────────────


class TestStdStreamRedirect:
    def test_dev_mode_no_redirect(self) -> None:
        """开发态（流可用）不重定向、不建目录。"""
        fake_out, fake_err = MagicMock(), MagicMock()
        with (
            patch.object(sys, "stdout", fake_out),
            patch.object(sys, "stderr", fake_err),
            patch("builtins.open") as m_open,
        ):
            _redirect_std_streams_to_log()
            # 流未被替换（函数早退分支）
            assert sys.stdout is fake_out and sys.stderr is fake_err
        m_open.assert_not_called()

    def test_frozen_none_stdout_redirects_to_log(self, tmp_path: Path) -> None:
        """打包态 sys.stdout=None → 重定向到配置目录日志文件。"""
        with (
            patch.object(sys, "stdout", None),
            patch.object(sys, "stderr", None),
            patch.dict("os.environ", {"EASY_TDX_CONFIG_DIR": str(tmp_path)}),
            patch("builtins.open", return_value=MagicMock()) as m_open,
        ):
            _redirect_std_streams_to_log()
        log_path = tmp_path / "easy_tdx_runtime.log"
        m_open.assert_called_once()
        assert str(log_path) in str(m_open.call_args.args[0])

    def test_unwritable_dir_falls_back_to_devnull(self, tmp_path: Path) -> None:
        """家目录不可写 → 退化 os.devnull，不崩。"""
        calls: list[str] = []

        def fake_open(path, *a, **k):
            calls.append(str(path))
            # 第 1 次（日志文件）抛 OSError → 函数应退化 open(os.devnull)
            if calls and calls[0] == str(path):
                raise OSError("read-only")
            return MagicMock()

        with (
            patch.object(sys, "stdout", None),
            patch.object(sys, "stderr", None),
            patch.dict("os.environ", {"EASY_TDX_CONFIG_DIR": str(tmp_path)}),
            patch("builtins.open", side_effect=fake_open),
        ):
            _redirect_std_streams_to_log()
            import os

            assert calls[0].endswith("easy_tdx_runtime.log")
            assert calls[1] == os.devnull


# ── main() 三路径分派 ────────────────────────────────────────────────────


class TestMainDispatch:
    def test_multiprocessing_child_exits_immediately(self) -> None:
        """子进程：freeze_support 后 sys.exit(0)，绝不触碰 CLI。"""
        import multiprocessing

        with (
            patch.object(sys, "argv", ["exe", "--multiprocessing-fork=1"]),
            patch.object(multiprocessing, "freeze_support") as m_fs,
            patch("easy_tdx.cli.cli") as m_cli,
            pytest.raises(SystemExit) as ei,
        ):
            main()
        assert ei.value.code == 0
        m_fs.assert_called_once()
        m_cli.assert_not_called()

    def test_dev_mode_no_args_forces_serve(self) -> None:
        """开发态无参 → argv 改写为 ['exe', 'serve'] 后走 CLI。"""
        argv_seen: list[list[str]] = []

        def fake_cli() -> None:
            argv_seen.append(list(sys.argv))

        with (
            patch.object(sys, "argv", ["easy-tdx"]),
            patch("easy_tdx.cli.cli", side_effect=fake_cli),
            patch.object(sys, "frozen", False, create=True),
        ):
            main()
        assert argv_seen == [["easy-tdx", "serve"]]

    def test_dev_mode_with_args_passthrough(self) -> None:
        """开发态带参 → argv 原样传 CLI。"""
        argv_seen: list[list[str]] = []

        def fake_cli() -> None:
            argv_seen.append(list(sys.argv))

        with (
            patch.object(sys, "argv", ["easy-tdx", "server-info"]),
            patch("easy_tdx.cli.cli", side_effect=fake_cli),
            patch.object(sys, "frozen", False, create=True),
        ):
            main()
        assert argv_seen == [["easy-tdx", "server-info"]]

    def test_frozen_no_args_goes_tray(self) -> None:
        """打包态无参 → 托盘路径，不进 CLI。"""
        with (
            patch.object(sys, "argv", ["easy-tdx.exe"]),
            patch("easy_tdx.cli.cli") as m_cli,
            patch("easy_tdx.tray.run_with_tray") as m_tray,
            patch.object(sys, "frozen", True, create=True),
        ):
            main()
        m_cli.assert_not_called()
        m_tray.assert_called_once()
        kwargs = m_tray.call_args.kwargs
        assert kwargs["port"] == 8000 and kwargs["open_browser"] is True

    def test_frozen_with_args_still_cli(self) -> None:
        """打包态带参（调试场景）→ 仍走 CLI，不进托盘。"""
        with (
            patch.object(sys, "argv", ["easy-tdx.exe", "serve"]),
            patch("easy_tdx.cli.cli") as m_cli,
            patch("easy_tdx.tray.run_with_tray") as m_tray,
            patch.object(sys, "frozen", True, create=True),
        ):
            main()
        m_cli.assert_called_once()
        m_tray.assert_not_called()
