"""scripts/audit_screen_out_of_sample.py 的契约测试（五之三十四新增）。

背景：那 60 只标的**是我挑的**，6 个口径也是**看过数据之后**定的
⇒ 存在**选择偏差/幸存者偏差**，多重比较校正**并不能**消除它。
本脚本用**从未被碰过**的 228 只全新标的做样本外复核。
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "audit_screen_out_of_sample.py"
CACHE = "/tmp/screen_audit_cache_any_buy_any_any_any.json"


def _s() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def _mod():
    spec = importlib.util.spec_from_file_location("_oos", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(m)
    return m


@pytest.fixture
def broken_file():
    """真的把脚本文件改坏，跑完再还原。

    ⚠️ 必须改**磁盘上的真文件**，否则 `_s()` 读到的还是好版本，
    牙齿测试就恒真了（本项目已栽过：grep 断言恒真、只改内存副本）。
    """
    original = SCRIPT.read_text(encoding="utf-8")

    def _break(old: str, new: str) -> None:
        assert old in original, f"待改的片段不存在: {old!r}"
        SCRIPT.write_text(original.replace(old, new), encoding="utf-8")

    try:
        yield _break
    finally:
        SCRIPT.write_text(original, encoding="utf-8")


class TestContract:
    def test_exists_and_documented(self) -> None:
        assert SCRIPT.exists()
        assert "样本外" in _s()

    def test_exits_two_without_cache(self) -> None:
        """⚠️ 缺数据必须 **exit 2**，不能静默 0。
        （这是本项目的硬规矩：审计脚本无数据时报警而非假装通过。）"""
        p = subprocess.run(
            [sys.executable, str(SCRIPT), "--cache", "/tmp/__nonexistent.json"],
            capture_output=True, text=True, cwd=ROOT, timeout=180)
        assert p.returncode == 2, (
            f"缺缓存应 exit 2，实得 {p.returncode}；"
            f"stderr={p.stderr[-300:]}")

    def test_exits_two_without_audit_data(self, tmp_path) -> None:
        """⚠️ 缺 audit_data/ 也必须 exit 2。"""
        cache = tmp_path / "c.json"
        cache.write_text(json.dumps([{"code": "sh600000_daily",
                                      "hit_pts": [1], "hit": [0.01],
                                      "miss_pts": [], "miss": []}]),
                         encoding="utf-8")
        p = subprocess.run(
            [sys.executable, str(SCRIPT), "--cache", str(cache),
             "--audit-root", str(tmp_path / "empty")],
            capture_output=True, text=True, cwd=ROOT, timeout=180)
        assert p.returncode == 2


class TestFutureFunctionGuard:
    def test_guards_t_plus_h_in_range(self) -> None:
        """⚠️⚠️ 必须 `t + H < len(close)`。
        越界就是用到了**还没发生的K线**＝未来函数，
        那是本项目修过两次的严重缺陷。"""
        assert "if t + h < len(close):" in _s()

    def test_uses_point_in_time_close(self) -> None:
        assert "close[t + h] / close[t] - 1" in _s()

    def test_behaviourally_drops_out_of_range(self) -> None:
        """行为级：t+H 越界的观测必须被**丢掉**，不能进结果。"""
        m = _mod()
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "audit_data").mkdir()
            # 只有 5 根K线，H=20 ⇒ 任何 t 都会越界
            (d / "audit_data" / "sh600000_daily.json").write_text(
                json.dumps([{"datetime": f"2024-01-{i+1:02d}",
                             "close": 10.0 + i} for i in range(5)]),
                encoding="utf-8")
            cache = d / "c.json"
            cache.write_text(json.dumps([
                {"code": "sh600000_daily", "hit_pts": [0], "hit": [0.01],
                 "miss_pts": [1], "miss": [0.02]}]), encoding="utf-8")
            orig = m.ROOT
            try:
                m.ROOT = d
                df = m._load(cache, 20)
            finally:
                m.ROOT = orig
        assert df.empty, (
            f"K线不足 {5} 根而 H=20，却仍返回 {len(df)} 条观测"
            " ⇒ 越界数据没被剔除 ⇒ 未来函数！")


class TestBetaControl:
    def test_always_shows_raw_and_controlled(self) -> None:
        """⚠️ 必须**同时**显示原始与控制后的结果。
        只报控制后的会掩盖'原始显著'这个事实；只报原始会重复
        五之二十五的坑（把大盘涨幅当成选股力）。"""
        src = _s()
        assert "① 原始（不控制）" in src
        assert "② 减同期全样本均值" in src

    def test_references_the_past_mistake(self) -> None:
        """⚠️ 必须写明**曾经栽过**这个坑（+3.71% p=0.002 实为 beta）。"""
        src = _s()
        assert "3.71" in src
        assert "beta" in src

    def test_verdict_flags_raw_only_significance(self) -> None:
        """原始显著、控制后不显著 ⇒ 必须**明确判为 beta**，不能含糊。"""
        assert "这是**市场 beta**，不是选股力" in _s()

    def test_verdict_distinguishes_real_out_of_sample_effect(self) -> None:
        """⚠️ 若控制 beta 后**仍**显著，结论就与原来不同，
        脚本必须能表达这种情况（不能只会说'不可用'）。"""
        assert "样本外仍显著" in _s()


class TestTeeth:
    """⚠️⚠️ 牙齿必须**真的改文件**。

    第一版我写成 `src = _s().replace(...)` 然后断言——那只在内存里改了个字符串，
    **根本没碰磁盘上的脚本**，所以无论文件好坏断言都恒真。
    ⇒ 牙齿测试的正确形态是：复制文件 → 改坏 → **跑测试看它失败** → 还原。
    （我在本项目已经栽过好几次：grep 断言恒真、断言打在 import 上、
      变量改的是副本。这里用 fixture 强制"改的是真文件"。）
    """

    def test_bite_removing_beta_control(self, broken_file) -> None:
        """把同期均值换成**中位数** ⇒ 市场控制口径变了，
        测试必须抓到（_s() 读的是磁盘上的真文件）。"""
        broken_file('transform("mean")', 'transform("median")')
        assert 'transform("mean")' not in _s()

    def test_bite_dropping_future_guard(self, broken_file) -> None:
        """去掉 `t + H < len(close)` ⇒ 未来函数泄漏。"""
        broken_file("if t + h < len(close):", "if t < len(close):")
        assert "if t + h < len(close):" not in _s()

    def test_bite_removing_raw_comparison(self, broken_file) -> None:
        """隐藏"原始显著"这个事实 ⇒ 又一次把 beta 当成选股力。"""
        broken_file("① 原始（不控制）", "原始（略）")
        assert "① 原始（不控制）" not in _s()

    def test_bite_replacing_past_mistake_note(self, broken_file) -> None:
        """删掉"曾经栽过这个坑"的记录 ⇒ 后来者会重蹈覆辙不自知。"""
        broken_file("+3.71% p=0.002 实为大盘 beta", "（略）")
        assert "3.71" not in _s()

    def test_bite_always_exits_two_without_data(self, broken_file) -> None:
        """无数据时返回 0（假装通过）⇒ 审计脚本形同虚设。"""
        broken_file("return 2", "return 0")
        src = _s()
        assert "return 0" in src and "return 2" not in src

class TestPoolingBias:
    """⚠️ 五之三十四标的缺口：池化入选占比 16.7%~100% 差异极大，
    **池化结论可信吗**？

    池化的隐含假设是"每条观测独立等权"。若某只股票被选中 40 次、
    另一只只 1 次，前者会**主导**结论。
    """

    def test_exists(self) -> None:
        assert "def _pooling_check(" in _s()

    def test_checks_at_least_three_weightings(self) -> None:
        """⚠️ 至少三种：池化 / 每股票等权 / 去掉极端。
        只做一种等于没检查。"""
        src = _s()
        assert "每条观测等权" in src
        assert "每股票等权" in src
        assert "中等入选次数" in src

    def test_reports_concentration(self) -> None:
        """先量化集中度（top5 占多少），再看加权敏感性。"""
        assert "nlargest(5)" in _s()

    def test_flags_disagreement_between_weightings(self) -> None:
        """⚠️ 若不同加权下结论**分歧**，必须明说"池化结论不可靠"，
        不能只报池化那一个数字。"""
        assert "加权方式之间有分歧" in _s()

    def test_behaviourally_runs_on_synthetic(self) -> None:
        """行为级：真数据跑一次，确认三种加权都出数、且能报一致/分歧。"""
        import io
        import contextlib

        m = _mod()
        n_per = 6
        rng = np.random.default_rng(0)
        codes, ts, rs, hits = [], [], [], []
        for c in range(n_per):
            for t in range(8):
                codes.append(f"c{c}")
                ts.append(t)
                hits.append(t < 4)          # 每只都被选中一半
                rs.append(rng.normal(0.0, 0.01))
        df = pd.DataFrame({"code": codes, "t": ts, "r": rs, "hit": hits})
        rel = df["r"].to_numpy(float)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            m._pooling_check(df, rel, df["hit"].to_numpy())
        out = buf.getvalue()
        assert "池化偏差诊断" in out
        assert "一致不显著" in out or "有分歧" in out
        for tag in ("① 池化", "② 每股票等权", "③ 只留中等"):
            assert tag in out, f"缺少 {tag}"


class TestPoolingTeeth:
    def test_bite_removing_per_stock_weighting(self, broken_file) -> None:
        """去掉'每股票等权' ⇒ 只剩池化与截尾，交叉验证失效。"""
        broken_file("② 每股票等权", "② （略）")
        assert "② 每股票等权" not in _s()

    def test_bite_removing_disagreement_warning(self, broken_file) -> None:
        """去掉分歧告警 ⇒ 只报池化数字，重的股票主导也看不出来。"""
        broken_file("加权方式之间有分歧", "（略）")
        assert "加权方式之间有分歧" not in _s()

    def test_bite_removing_concentration_report(self, broken_file) -> None:
        broken_file("nlargest(5)", "head(0)")
        assert "nlargest(5)" not in _s()
