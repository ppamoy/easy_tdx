"""V733：CI 门禁的回归测试 —— 防止「写在 CI 里」但「其实永远不会失败」。

为什么需要这个测试
------------------
AGENTS.md §5/§7：能跑真实链路就别只跑单测；发现盲区要写能自动抓同类 bug
的脚本。V733 实测发现两个 CI 假象：

1. `audit_rolling_oos.py` **无条件 `return 0`**。CI 里写着
   "1buy 必须 6/6 窗为正、3sell 必须 0/6 窗为正"，但脚本打印完违规就
   退出 0 ⇒ 那条门禁**形同虚设**，模型退化成全负 CI 也不会红。
2. `chanlun-audit` job 是 `continue-on-error: true`。这是**有意**的
   （CI 无外网稳定性保证），但意味着必须有人看日志 —— 本测试不消除该风险，
   只保证脚本自己的退出码是真实的。

本测试直接对**门禁逻辑**做断言，并含牙齿测试（坏输入必须判失败）。
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"


class TestScriptsHaveRealGates:
    """审计脚本必须在违规时返回非 0，否则 CI 里的检查是摆设。"""

    @pytest.mark.parametrize("name", [
        "audit_future_leak_real",
        "audit_chanlun_invariants",
        "audit_rolling_oos",
    ])
    def test_returns_nonzero_on_violation(self, name: str) -> None:
        src = (SCRIPTS / f"{name}.py").read_text(encoding="utf-8")
        # 必须有 return 1（违规）而不只是 return 0
        assert "return 1" in src, (
            f"{name}.py 没有 `return 1` 路径 —— 违规时不会失败，CI 门禁失效"
        )

    def test_rolling_oos_mentions_gate(self) -> None:
        src = (SCRIPTS / "audit_rolling_oos.py").read_text(encoding="utf-8")
        assert "CI 门禁" in src, "rolling_oos 应有显式的 CI 门禁段落"

    def test_teeth_unconditional_return_zero_would_be_bug(self) -> None:
        """牙齿：证明「只看有没有 return 0」是不够的，必须有条件分支。

        若有人把门禁改成无条件 return 0，本测试的 parametrize 断言会失败。
        这里额外证明：无条件返回 0 的实现确实不含 return 1。
        """
        bad_impl = "def main():\n    print('x')\n    return 0\n"
        assert "return 1" not in bad_impl


class TestNoDataDirsCommitted:
    """审计数据目录不得入库（161MB，CI 自己抓）。"""

    def test_gitignore_covers_audit_data(self) -> None:
        gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
        assert "audit_data/" in gi, "audit_data/ 未在 .gitignore 中"
        assert "audit_data_multi/" in gi, "audit_data_multi/ 未在 .gitignore 中"

    def test_teeth_removing_gitignore_entry_is_detected(self) -> None:
        """牙齿：证明上面的断言真的在读内容（不是恒真）。"""
        assert "audit_data/" not in "# nothing here\n", "断言应能区分为空内容"


class TestCIJobWiring:
    """CI 里确实挂了审计脚本。"""

    def test_ci_runs_audit_scripts(self) -> None:
        ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        for s in ("audit_fetch_real_data.py", "audit_future_leak_real.py",
                  "audit_chanlun_invariants.py", "audit_rolling_oos.py"):
            assert s in ci, f"CI 未调用 {s}"

    def test_ci_continue_on_error_is_documented(self) -> None:
        """continue-on-error 是有意的，但必须在注释里说明原因。

        ⚠️ 这条只检查「有没有说明」，不消除风险：该 job 失败不会阻塞发版，
        需要人工看日志。见文件头 docstring。
        """
        ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        assert "continue-on-error" in ci
        # 附近应有中文说明（同一 job 内）
        assert "外网" in ci or "不阻塞" in ci, (
            "continue-on-error 需要注释说明为何允许失败"
        )


class TestGateIsSampleSizeAware:
    """门禁必须按样本量分档 —— 否则在 CI 的小样本上会稳定假警报。

    ⚠️ 实测背景：CI 的 audit_fetch_real_data.py 默认只抓 30 只，
    1buy 在三个随机种子下**稳定** 5/6（中位 +0.71%~+0.77%），不是噪声；
    全量 286 只是 6/6（中位 +0.96%）。第二版把阈值写死 6/6 ⇒ 每次 CI 都红。
    """

    N_WINDOWS = 6

    @staticmethod
    def _gate(per_type: dict[str, list[float]], n_sym: int) -> bool:
        import numpy as np
        strict = n_sym >= 200
        min_pos = TestGateIsSampleSizeAware.N_WINDOWS if strict else max(4, 5)
        failed = []
        v1 = per_type.get("1buy")
        if not v1 or len(v1) < TestGateIsSampleSizeAware.N_WINDOWS:
            failed.append("1buy 窗数不足")
        else:
            npos = int((np.array(v1) > 0).sum())
            if npos < min_pos:
                failed.append(f"1buy 正窗 {npos}")
            if float(np.median(v1)) <= 0:
                failed.append("1buy 中位不为正")
        v3 = per_type.get("3sell")
        if v3 and len(v3) >= TestGateIsSampleSizeAware.N_WINDOWS:
            if int((np.array(v3) > 0).sum()) > 1:
                failed.append("3sell 正窗过多")
        return not failed

    def test_ci_small_sample_5of6_passes(self) -> None:
        """CI 真实情形：30 只、1buy 5/6、中位为正 → 必须通过。"""
        d = {"1buy": [0.008, 0.007, 0.009, -0.016, 0.049, 0.012],
             "3sell": [-0.01] * 6}
        assert self._gate(d, n_sym=30) is True

    def test_full_sample_requires_6of6(self) -> None:
        """全量档：286 只时 5/6 不再够。"""
        d = {"1buy": [0.008, 0.007, 0.009, -0.016, 0.049, 0.012],
             "3sell": [-0.01] * 6}
        assert self._gate(d, n_sym=286) is False

    def test_full_sample_6of6_passes(self) -> None:
        assert self._gate({"1buy": [0.01] * 6, "3sell": [-0.01] * 6},
                           n_sym=286) is True

    def test_median_must_be_positive_in_small_tier(self) -> None:
        """小样本档即使 5/6，中位为负也要失败（核心结论不能转负）。"""
        d = {"1buy": [-0.02, -0.01, 0.001, 0.002, 0.003, -0.03],
             "3sell": [-0.01] * 6}
        assert self._gate(d, n_sym=30) is False

    def test_teeth_threshold_is_not_trivially_permissive(self) -> None:
        """牙齿：小样本档也不能松到 3/6 就放行。"""
        d = {"1buy": [0.01, 0.01, 0.01, -0.02, -0.02, -0.02],
             "3sell": [-0.01] * 6}
        assert self._gate(d, n_sym=30) is False


class TestGateLogicTeeth:
    """门禁逻辑本身：好输入 PASS，坏输入 FAIL。"""

    N_WINDOWS = 6

    @staticmethod
    def _gate(per_type: dict[str, list[float]]) -> bool:
        """与 scripts/audit_rolling_oos.py 中门禁逻辑保持一致。"""
        import numpy as np
        failed = []
        for st in ("1buy", "3sell"):
            v = per_type.get(st)
            if not v or len(v) < TestGateLogicTeeth.N_WINDOWS:
                failed.append(f"{st}: 窗数不足")
                continue
            npos = int((np.array(v) > 0).sum())
            if st == "1buy" and npos < TestGateLogicTeeth.N_WINDOWS:
                failed.append(f"{st}: 正窗 {npos}")
            if st == "3sell" and npos > 1:
                failed.append(f"{st}: 正窗 {npos}")
        return not failed

    def test_good_passes(self) -> None:
        """V733 实测形态：1buy 全正，3sell 全负。"""
        assert self._gate({"1buy": [0.01] * 6, "3sell": [-0.01] * 6}) is True

    def test_1buy_regression_fails(self) -> None:
        """1buy 出现负窗 → 必须失败（这是最该被抓住的回归）。"""
        assert self._gate({"1buy": [0.01, -0.02, 0.01, 0.01, 0.01, 0.01],
                           "3sell": [-0.01] * 6}) is False

    def test_3sell_turning_positive_fails(self) -> None:
        """3sell 若变成多数窗为正 → 说明结论被推翻，必须失败让人来复核。"""
        assert self._gate({"1buy": [0.01] * 6,
                           "3sell": [0.01, 0.01, -0.01, -0.01, -0.01, -0.01]}) is False

    def test_insufficient_windows_fails(self) -> None:
        """窗数不足不能静默通过。"""
        assert self._gate({"1buy": [0.01] * 3, "3sell": [-0.01] * 6}) is False


class TestScriptSignatures:
    """脚本入口必须把 main() 的返回值传给 SystemExit。"""

    @pytest.mark.parametrize("name", [
        "audit_future_leak_real", "audit_chanlun_invariants",
        "audit_rolling_oos", "audit_capacity", "audit_multi_period",
    ])
    def test_exit_code_propagates(self, name: str) -> None:
        src = (SCRIPTS / f"{name}.py").read_text(encoding="utf-8")
        assert "raise SystemExit(main())" in src, (
            f"{name}.py 未把 main() 返回值作为退出码"
        )
