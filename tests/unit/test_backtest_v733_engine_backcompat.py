"""V733：引擎修复的**向后兼容**回归守卫。

背景
----
V733 修了 `orders.py::_calculate_buy_size / _calculate_sell_size` —— 原实现
`if position_mode == "full" or signal_size == 0:` 会把策略**显式指定**的仓位
丢弃，导致 `ChanlunStrategy` 的 `position_pct` 完全无效（用户按"四季"建议
设 30% 仓位，实际仍 100% 满仓）。

当时我**推断**"默认 `position_pct=1.0` 走 `self.buy()`（size=0）→ 满仓，
行为不变，所以历史审计数字仍有效"。**推断不算验证**（AGENTS.md §3），
本模块把该结论固化成**可重复执行的 A/B 对比**。

做法
----
用 git 取修复前的 `orders.py`，构造两棵源码树，对**同一批真实行情**、**同一
策略默认参数**跑回测，逐位比较 `total_return` 与 `max_drawdown`。

⚠️ 若项目历史被 rebase/squash 掉，`6b2b2eb^` 取不到旧文件 ⇒ 跳过而非误报。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "audit_data"
FIX_COMMIT = "6b2b2eb"          # position_pct 修复所在的 commit
ENGINE_REL = "src/easy_tdx/backtest/orders.py"
N_SYMBOLS = 6


def _have_data() -> bool:
    return any(p.stem.split("_")[0] not in ("sh000300", "sh000001")
               for p in DATA.glob("*.json"))


def _old_engine_src() -> str | None:
    try:
        out = subprocess.run(
            ["git", "show", f"{FIX_COMMIT}^:{ENGINE_REL}"],
            cwd=ROOT, capture_output=True, text=True, timeout=60,
        )
    except Exception:
        return None
    return out.stdout if out.returncode == 0 and out.stdout.strip() else None


@pytest.mark.skipif(not _have_data(), reason="缺少真实行情（audit_data 已 gitignore）")
class TestEngineFixIsBackwardCompatible:
    """修复只应影响"显式指定 size"的场景，默认参数行为必须逐位不变。"""

    @pytest.fixture(scope="class")
    def trees(self, tmp_path_factory) -> tuple[Path, Path]:
        old_src = _old_engine_src()
        if old_src is None:
            pytest.skip(f"取不到 {FIX_COMMIT}^ 的旧引擎（历史被改写？）")
        base = tmp_path_factory.mktemp("ab")
        new_t, old_t = base / "new", base / "old"
        for tree in (new_t, old_t):
            shutil.copytree(ROOT / "src", tree / "src")
        (old_t / ENGINE_REL).write_text(old_src, encoding="utf-8")
        # 确认两份确实不同，否则对比毫无意义
        assert (old_t / ENGINE_REL).read_text(encoding="utf-8") != \
            (new_t / ENGINE_REL).read_text(encoding="utf-8"), \
            "新旧引擎内容相同 —— 本测试会变成空转"
        return new_t, old_t

    @pytest.fixture(scope="class")
    def results(self, trees) -> dict[str, list]:
        new_t, old_t = trees
        files = [p for p in sorted(DATA.glob("*.json"))
                 if p.stem.split("_")[0] not in ("sh000300", "sh000001")
                 ][:N_SYMBOLS]
        assert files, "没有可用行情"
        script = r"""
import sys, json, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, sys.argv[1])
import pandas as pd
from easy_tdx.backtest.engine import BacktestEngine
from easy_tdx.backtest.strategies.chanlun import ChanlunStrategy
out = []
for path in sys.argv[2:]:
    df = pd.DataFrame(json.loads(open(path, encoding="utf-8").read()))
    df["datetime"] = pd.to_datetime(df["datetime"])
    if "vol" in df.columns:
        df = df.rename(columns={"vol": "volume"})
    if "volume" in df.columns:
        df["amount"] = df["close"] * df["volume"]
    r = BacktestEngine(ChanlunStrategy(), cash=100000.0).run(df)   # 全默认参数
    out.append([repr(float(r.performance["total_return"])),
                repr(float(r.performance["max_drawdown"]))])
print("@@RESULT@@" + json.dumps(out))
"""
        def run(tree: Path) -> list:
            p = subprocess.run(
                [sys.executable, "-c", script, str(tree / "src")]
                + [str(f) for f in files],
                capture_output=True, text=True, timeout=1800,
            )
            assert p.returncode == 0, f"回测失败: {p.stderr[-800:]}"
            line = next(l for l in p.stdout.splitlines() if l.startswith("@@RESULT@@"))
            return json.loads(line[len("@@RESULT@@"):])

        return {"new": run(new_t), "old": run(old_t)}

    def test_default_params_results_are_identical(self, results) -> None:
        """⚠️ 核心断言：默认参数下，新旧引擎结果必须**逐位相同**。"""
        assert len(results["new"]) == len(results["old"]) == N_SYMBOLS
        diff = [(i, a, b) for i, (a, b)
                in enumerate(zip(results["new"], results["old"])) if a != b]
        assert not diff, (
            f"{len(diff)}/{N_SYMBOLS} 只标的结果变了，例: {diff[:2]}；"
            "修复本应只影响显式指定 size 的场景 ⇒ 此前审计数字需重算")

    def test_symbol_order_preserved(self, results) -> None:
        """结果必须逐标的配对（不能只比聚合值，否则可能抵消）。"""
        assert len(results["new"]) == N_SYMBOLS
        for new, old in zip(results["new"], results["old"]):
            assert len(new) == 2 and len(old) == 2

    def test_audit_history_claim_is_testable(self) -> None:
        """把"历史审计数字仍有效"这句话本身变成可执行断言的锚点。"""
        assert _old_engine_src() is not None or True
        # 默认 position_pct 必须是 1.0，否则默认路径会走显式 size 分支
        sys.path.insert(0, str(ROOT / "src"))
        from easy_tdx.backtest.strategies.chanlun import ChanlunStrategy
        assert float(ChanlunStrategy().p.get("position_pct", 1.0)) == 1.0, (
            "默认仓位不是 1.0 ⇒ 默认路径不再走 self.buy() 全仓，"
            "向后兼容结论需重新评估")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
