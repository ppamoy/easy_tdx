"""V366/V367: 离线 V102 建议链路端到端运行时回归。

用合成 .day 文件（append_daily_bars 生成）通过 CliRunner 依次调用
offline advice --file / advice-batch --dir / watch --dir --out，
把 V366 联调抓出的 3 类运行时 bug 固化为 pytest 回归：
1. 函数体内使用 pd.DataFrame 但缺 pandas 局部导入（NameError）
2. advice 把 dict 传入只接受 DataFrame 的 print_output（AttributeError）
3. advice-batch 空建议报告读取缺失的 stop_rate/tp_rate/expire_rate（KeyError）
"""

from __future__ import annotations

import json
import math
import random
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from click.testing import CliRunner

from easy_tdx.cli.cmd_offline import _is_within_since_days, _watch_signal_row, offline
from easy_tdx.models.bar import SecurityBar
from easy_tdx.offline.write_daily import append_daily_bars


def _synthetic_bars(n: int = 150, seed: int = 7, base: float = 50.0) -> list[SecurityBar]:
    """构造一段震荡上行的合成日线（与 scripts/offline_chain_demo.py 同风格）。"""
    rng = random.Random(seed)
    bars: list[SecurityBar] = []
    price = base
    for i in range(n):
        drift = 0.12 if i >= n // 3 else 0.0
        wave = 0.6 * math.sin(i / 6.0)
        price = max(1.0, price + drift + wave * 0.12 + rng.uniform(-0.2, 0.2))
        bars.append(
            SecurityBar(
                open=round(price - 0.1, 3),
                close=round(price, 3),
                high=round(price + 0.4, 3),
                low=round(price - 0.4, 3),
                vol=1_000_000.0,
                amount=1_000_000.0 * price,
                year=2023 + i // 250,
                month=1 + (i % 250) // 21,
                day=1 + (i % 250) % 21,
                hour=0,
                minute=0,
            )
        )
    return bars


def _make_lday(tmp_path: Path) -> tuple[Path, Path]:
    """生成两个合成 .day 文件，返回 (lday 目录, 第一只文件路径)。"""
    lday = tmp_path / "lday"
    lday.mkdir()
    day_a = lday / "sh600000.day"
    day_b = lday / "sz000001.day"
    append_daily_bars(day_a, _synthetic_bars(150, seed=7), 0.01, 0.01)
    append_daily_bars(day_b, _synthetic_bars(150, seed=11, base=30.0), 0.01, 0.01)
    return lday, day_a


def test_offline_advice_file_runs(tmp_path: Path) -> None:
    """V366: offline advice --file 运行时不再 NameError（pandas 导入修复）。"""
    _lday, day_a = _make_lday(tmp_path)
    runner = CliRunner()
    res = runner.invoke(
        offline,
        ["advice", "SH", "600000", "--file", str(day_a), "--output", "json"],
    )
    assert res.exit_code == 0, res.output
    assert '"bars": 150' in res.output  # JSON 输出含 K 线数


def test_offline_advice_batch_runs(tmp_path: Path) -> None:
    """V366: advice-batch --dir 运行时无 KeyError（空建议报告字段缺失防护）。"""
    lday, _ = _make_lday(tmp_path)
    runner = CliRunner()
    res = runner.invoke(
        offline,
        ["advice-batch", "--dir", str(lday), "--output", "json"],
    )
    assert res.exit_code == 0, res.output
    # 两只标的都不应出现 error 行（此前空建议报告会 KeyError: 'stop_rate'）
    assert '"error"' not in res.output
    assert '"symbol":"SH600000"' in res.output
    assert '"symbol":"SZ000001"' in res.output


def test_offline_watch_with_out_runs(tmp_path: Path) -> None:
    """V365/V366: watch --dir --out 运行时正常，状态文件被写回。"""
    lday, _ = _make_lday(tmp_path)
    state = tmp_path / "watch_state.json"
    jsonl = tmp_path / "signals.jsonl"
    runner = CliRunner()
    res = runner.invoke(
        offline,
        [
            "watch",
            "--dir",
            str(lday),
            "--state",
            str(state),
            "--out",
            str(jsonl),
            "--output",
            "json",
        ],
    )
    assert res.exit_code == 0, res.output
    # 状态文件必然写回；JSONL 仅在发现新信号时创建（合成数据无 3买/3卖 属预期）
    assert state.is_file()


def test_watch_signal_row_includes_advice_fields():
    """V368: watch 新信号 JSONL 行含 V102 建议的入场/止损/止盈字段。"""
    mmd = MagicMock()
    mmd.mmd_type.value = "3buy"
    mmd.confidence = 0.72
    mmd._signal_quality_scorecard = {"overall_grade": "A"}
    mmd._decision_support = {
        "action_recommendation": "买入",
        "entry_price": 10.5,
        "stop_loss": 9.8,
        "take_profit_1": 11.6,
    }
    row = _watch_signal_row("SH600000", mmd, "2024-03-15")
    assert row["symbol"] == "SH600000"
    assert row["type"] == "3buy"
    assert row["date"] == "2024-03-15"
    assert row["v102_grade"] == "A"
    assert row["advice"] == "买入"
    assert row["entry_price"] == 10.5
    assert row["stop_loss"] == 9.8
    assert row["take_profit_1"] == 11.6


def test_watch_signal_row_missing_decision_is_null():
    """V368: 无决策支持数据时，入场/止损/止盈字段为 None（不崩溃）。"""
    mmd = MagicMock()
    mmd.mmd_type.value = "3sell"
    mmd.confidence = 0.6
    mmd._signal_quality_scorecard = None
    mmd._decision_support = None
    row = _watch_signal_row("SZ000001", mmd, "2024-03-15")
    assert row["entry_price"] is None
    assert row["stop_loss"] is None
    assert row["take_profit_1"] is None
    assert row["v102_grade"] is None


class _FakeWatchResult:
    """watch 运行时回归：模拟分析结果，固定产生一个 3buy 信号（日期可注入）。"""

    def __init__(self, signal_date: str) -> None:
        self.mmds = [
            SimpleNamespace(
                mmd_type=SimpleNamespace(value="3buy"),
                bi=SimpleNamespace(end="anchor"),
                confidence=0.71,
                _signal_quality_scorecard=None,
                _decision_support=None,
            )
        ]
        self._signal_date = signal_date

    def _fx_anchor_datetime(self, bi_end: object) -> object:
        return "anchor"

    def _fmt_dt(self, anchor: object) -> str:
        return self._signal_date


class _FakeWatchAnalyser:
    """返回固定信号的假 ChanlunAnalyser（patch easy_tdx.chanlun.ChanlunAnalyser）。"""

    def __init__(self, signal_date: str) -> None:
        self._signal_date = signal_date

    def process_klines(self, df) -> _FakeWatchResult:
        return _FakeWatchResult(self._signal_date)


def _patch_watch_analyser(monkeypatch, signal_date: str) -> None:
    monkeypatch.setattr(
        "easy_tdx.chanlun.ChanlunAnalyser",
        lambda code=None, frequency=None: _FakeWatchAnalyser(signal_date),
    )


# ── V373: _is_within_since_days 纯函数 ──


def test_is_within_since_days_zero_or_negative_means_no_filter() -> None:
    """V373: since_days<=0 不过滤（与 --since-days 0 默认行为一致）。"""
    assert _is_within_since_days("2000-01-01", 0) is True
    assert _is_within_since_days("2000-01-01", -5) is True


def test_is_within_since_days_today_and_boundary_are_included() -> None:
    """V373: 今天与恰好 N 天前（边界含当天）的信号均保留。"""
    today = date.today()
    assert _is_within_since_days(today.strftime("%Y-%m-%d"), 30) is True
    boundary = (today - timedelta(days=30)).strftime("%Y-%m-%d")
    assert _is_within_since_days(boundary, 30) is True


def test_is_within_since_days_old_signal_is_filtered() -> None:
    """V373: 早于 N 天窗口的信号被过滤。"""
    old = date.today() - timedelta(days=31)
    assert _is_within_since_days(old.strftime("%Y-%m-%d"), 30) is False


def test_is_within_since_days_invalid_date_is_filtered_conservatively() -> None:
    """V373: 日期解析失败保守跳过（不报告），与 V372 运行时行为一致。"""
    assert _is_within_since_days("not-a-date", 30) is False
    assert _is_within_since_days("", 30) is False


# ── V373: watch --since-days 运行时回归（mock 分析器产生 3buy） ──


def test_watch_since_days_filters_old_signal(tmp_path: Path, monkeypatch) -> None:
    """V373: 信号日期早于窗口时，watch 不输出也不写 JSONL，但状态文件仍写回。"""
    lday, _ = _make_lday(tmp_path)
    state = tmp_path / "watch_state.json"
    jsonl = tmp_path / "signals.jsonl"
    old_date = (date.today() - timedelta(days=400)).strftime("%Y-%m-%d")
    _patch_watch_analyser(monkeypatch, old_date)

    runner = CliRunner()
    res = runner.invoke(
        offline,
        [
            "watch",
            "--dir",
            str(lday),
            "--state",
            str(state),
            "--limit",
            "1",
            "--since-days",
            "30",
            "--out",
            str(jsonl),
            "--output",
            "json",
        ],
    )
    assert res.exit_code == 0, res.output
    assert "无新信号（状态已是最新）" in res.output
    assert not jsonl.exists()  # 旧信号被过滤 → 无 JSONL 落盘
    assert state.is_file()  # 状态文件仍写回（seen 为空）


def test_watch_since_days_reports_recent_signal(tmp_path: Path, monkeypatch) -> None:
    """V373: 信号日期在窗口内时正常上报，JSONL 含 V102 建议字段。"""
    lday, _ = _make_lday(tmp_path)
    state = tmp_path / "watch_state.json"
    jsonl = tmp_path / "signals.jsonl"
    today_str = date.today().strftime("%Y-%m-%d")
    _patch_watch_analyser(monkeypatch, today_str)

    runner = CliRunner()
    res = runner.invoke(
        offline,
        [
            "watch",
            "--dir",
            str(lday),
            "--state",
            str(state),
            "--limit",
            "1",
            "--since-days",
            "30",
            "--out",
            str(jsonl),
            "--output",
            "json",
        ],
    )
    assert res.exit_code == 0, res.output
    assert "新信号 1 条" in res.output
    assert '"symbol"' in res.output
    assert "SH600000" in res.output

    lines = jsonl.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["symbol"] == "SH600000"
    assert row["type"] == "3buy"
    assert row["date"] == today_str
    assert row["confidence"] == 0.71
    assert row["v102_grade"] is None
    assert row["advice"] is None


# ── V374: offline advice / advice-batch 的 md/table/csv 输出分支运行时回归 ──
# （V366/V370 曾抓出「help 通过但运行崩溃」：输出分支必须真实走 CliRunner）


def test_offline_advice_md_runs(tmp_path: Path) -> None:
    """V374: offline advice --output md 输出 Markdown 报告结构。"""
    _lday, day_a = _make_lday(tmp_path)
    runner = CliRunner()
    res = runner.invoke(
        offline,
        ["advice", "SH", "600000", "--file", str(day_a), "--output", "md"],
    )
    assert res.exit_code == 0, res.output
    assert "# 离线 V102 建议回放报告（SH600000）" in res.output
    assert "K线 **150** 根" in res.output
    assert "| # | 入场 | 止损 | 止盈1 |" in res.output
    assert "**汇总**" in res.output
    assert "**出场分布**" in res.output


def test_offline_advice_table_runs(tmp_path: Path) -> None:
    """V374: offline advice --output table 输出标量列表格（嵌套列不崩溃）。"""
    _lday, day_a = _make_lday(tmp_path)
    runner = CliRunner()
    res = runner.invoke(
        offline,
        ["advice", "SH", "600000", "--file", str(day_a), "--output", "table"],
    )
    assert res.exit_code == 0, res.output
    assert "count" in res.output
    assert "SH600000" in res.output


def test_offline_advice_csv_runs(tmp_path: Path) -> None:
    """V374: offline advice --output csv 输出标量列 CSV（含 symbol/bars）。"""
    _lday, day_a = _make_lday(tmp_path)
    runner = CliRunner()
    res = runner.invoke(
        offline,
        ["advice", "SH", "600000", "--file", str(day_a), "--output", "csv"],
    )
    assert res.exit_code == 0, res.output
    lines = res.output.strip().splitlines()
    assert lines[0] == "count,win_rate,avg_return,total_return,symbol,bars,signals"
    assert "SH600000" in lines[1]


def test_offline_advice_batch_md_runs(tmp_path: Path) -> None:
    """V374: offline advice-batch --output md 输出批量 Markdown 报告。"""
    lday, _ = _make_lday(tmp_path)
    runner = CliRunner()
    res = runner.invoke(
        offline,
        ["advice-batch", "--dir", str(lday), "--output", "md"],
    )
    assert res.exit_code == 0, res.output
    assert "# 离线 V102 批量建议实证报告" in res.output
    assert "| 标的 | K线 | 信号 |" in res.output
    assert "SH600000" in res.output


def test_offline_advice_batch_table_runs(tmp_path: Path) -> None:
    """V374: offline advice-batch --output table 输出每只汇总行（含 summary 列）。"""
    lday, _ = _make_lday(tmp_path)
    runner = CliRunner()
    res = runner.invoke(
        offline,
        ["advice-batch", "--dir", str(lday), "--output", "table"],
    )
    assert res.exit_code == 0, res.output
    assert "symbol" in res.output
    assert "summary_symbols" in res.output
    assert "SH600000" in res.output


def test_offline_advice_batch_csv_runs(tmp_path: Path) -> None:
    """V374: offline advice-batch --output csv 输出每只汇总 CSV。"""
    lday, _ = _make_lday(tmp_path)
    runner = CliRunner()
    res = runner.invoke(
        offline,
        ["advice-batch", "--dir", str(lday), "--output", "csv"],
    )
    assert res.exit_code == 0, res.output
    lines = res.output.strip().splitlines()
    assert lines[0].startswith("symbol,bars,signals,advice_count")
    assert "summary_win_rate" in lines[0]
    assert "SH600000" in lines[1]


# ── V375: offline watch 状态管理（--reset/--info/互斥/损坏/去重）运行时回归 ──
# （V360 功能此前只有 help 断言；这些分支不依赖 .day 目录，直接走 CliRunner）


def test_watch_info_without_state_file(tmp_path: Path) -> None:
    """V375: --info 在状态文件不存在时输出路径 + 计数 0。"""
    state = tmp_path / "watch_state.json"
    runner = CliRunner()
    res = runner.invoke(offline, ["watch", "--state", str(state), "--info"])
    assert res.exit_code == 0, res.output
    assert f"状态文件: {state}" in res.output
    assert "已记录信号数: 0" in res.output


def test_watch_info_counts_seen(tmp_path: Path) -> None:
    """V375: --info 显示状态文件已记录信号数。"""
    state = tmp_path / "watch_state.json"
    state.write_text(json.dumps({"seen": ["a", "b", "c"]}), encoding="utf-8")
    runner = CliRunner()
    res = runner.invoke(offline, ["watch", "--state", str(state), "--info"])
    assert res.exit_code == 0, res.output
    assert "已记录信号数: 3" in res.output


def test_watch_info_corrupt_state_counts_zero(tmp_path: Path) -> None:
    """V375: 状态文件损坏时 --info 计数为 0（不崩溃）。"""
    state = tmp_path / "watch_state.json"
    state.write_text("{corrupt", encoding="utf-8")
    runner = CliRunner()
    res = runner.invoke(offline, ["watch", "--state", str(state), "--info"])
    assert res.exit_code == 0, res.output
    assert "已记录信号数: 0" in res.output


def test_watch_reset_existing_state(tmp_path: Path) -> None:
    """V375: --reset 删除已有状态文件并提示重建基线。"""
    state = tmp_path / "watch_state.json"
    state.write_text(json.dumps({"seen": ["x"]}), encoding="utf-8")
    runner = CliRunner()
    res = runner.invoke(offline, ["watch", "--state", str(state), "--reset"])
    assert res.exit_code == 0, res.output
    assert "已清空监控基线" in res.output
    assert not state.exists()


def test_watch_reset_without_state(tmp_path: Path) -> None:
    """V375: 无状态文件时 --reset 提示无基线可清除。"""
    state = tmp_path / "watch_state.json"
    runner = CliRunner()
    res = runner.invoke(offline, ["watch", "--state", str(state), "--reset"])
    assert res.exit_code == 0, res.output
    assert "无现有基线可清除（状态文件不存在）" in res.output


def test_watch_reset_and_info_conflict(tmp_path: Path) -> None:
    """V375: --reset 与 --info 互斥，报错退出。"""
    state = tmp_path / "watch_state.json"
    runner = CliRunner()
    res = runner.invoke(offline, ["watch", "--state", str(state), "--reset", "--info"])
    assert res.exit_code == 1, res.output
    assert "--reset 与 --info 不能同时使用" in res.output


def test_watch_corrupt_state_falls_back_fresh(tmp_path: Path, monkeypatch) -> None:
    """V375: 损坏状态文件视为首次运行（不崩溃，信号上报并重建合法基线）。"""
    lday, _ = _make_lday(tmp_path)
    state = tmp_path / "watch_state.json"
    state.write_text("{corrupt", encoding="utf-8")
    today_str = date.today().strftime("%Y-%m-%d")
    _patch_watch_analyser(monkeypatch, today_str)

    runner = CliRunner()
    res = runner.invoke(
        offline,
        [
            "watch",
            "--dir",
            str(lday),
            "--state",
            str(state),
            "--limit",
            "1",
            "--output",
            "json",
        ],
    )
    assert res.exit_code == 0, res.output
    assert "新信号 1 条" in res.output
    # 状态文件被重建为合法 JSON 且含该信号键
    data = json.loads(state.read_text(encoding="utf-8"))
    assert any("SH600000:3buy" in s for s in data["seen"])


def test_watch_second_run_deduplicates(tmp_path: Path, monkeypatch) -> None:
    """V375: 二次运行不重复报告已见信号（基线去重）。"""
    lday, _ = _make_lday(tmp_path)
    state = tmp_path / "watch_state.json"
    today_str = date.today().strftime("%Y-%m-%d")
    _patch_watch_analyser(monkeypatch, today_str)

    runner = CliRunner()
    args = [
        "watch",
        "--dir",
        str(lday),
        "--state",
        str(state),
        "--limit",
        "1",
        "--output",
        "json",
    ]
    res1 = runner.invoke(offline, args)
    assert res1.exit_code == 0, res1.output
    assert "新信号 1 条" in res1.output

    res2 = runner.invoke(offline, args)
    assert res2.exit_code == 0, res2.output
    assert "无新信号（状态已是最新）" in res2.output
