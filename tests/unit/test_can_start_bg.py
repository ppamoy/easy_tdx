"""⚠️ `can_start_bg.py` / `run_bg.sh --force` 的**牙齿**测试。

起因：我把 4 核机器占满，**两次**（用户当面指出两回）。
第二次叠加了 pytest 全量 + 基线审计 + 前端 npm test = 328%/400%。
`guard_bg_jobs.py` 只能事后报警，拦不住"已在跑还要再起一个"⇒ 需要起飞前的闸。

⚠️ 本文件同时覆盖一个我自己的**静默失效**：
`run_bg.sh` 的 --force 我第一版放在 `TIMEOUT_S/NAME` 已经 shift 掉之后，
⇒ `--force` 被当成超时秒数（实测输出 `任务=60 超时=--forces`）。
⇒ 提示语写着"用 --force"，代码却收不到 —— 空头承诺。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUARD = ROOT / "scripts" / "can_start_bg.py"
RUNBG = ROOT / "scripts" / "run_bg.sh"


class TestGuardDetectsBusyCPU:
    def test_script_exists(self) -> None:
        assert GUARD.exists()

    def test_measures_actual_cpu_not_names(self) -> None:
        """⚠️ 必须**实测 CPU tick 增量**，不能用进程名白名单 ——
        别的 agent 的任务名字我根本不知道，白名单必然漏。"""
        src = GUARD.read_text(encoding="utf-8")
        assert "/proc/" in src and "utime" in src or "fields[11]" in src, \
            "必须读 /proc/<pid>/stat 的 CPU tick"
        assert "SC_CLK_TCK" in src, "必须用时钟频率换算成百分比"

    def test_no_false_positive_when_idle(self) -> None:
        """⚠️ 负例：门槛高到不可能达到时，必须返回空（不能误挡）。"""
        sys.path.insert(0, str(ROOT / "scripts"))
        import can_start_bg as c
        rows = c.busy(sample_s=2.0, min_pct=500.0)
        assert rows == [], f"空闲时仍报出占用：{rows}"
        del sys.modules["can_start_bg"]


class TestRunBgForceFlag:
    """⚠️ 提示语承诺了 --force，代码就必须真的收到它。"""

    def test_force_parsed_before_shifts(self) -> None:
        """⚠️ --force 的解析必须在 TIMEOUT_S/NAME shift **之前**。"""
        src = RUNBG.read_text(encoding="utf-8")
        lines = src.splitlines()
        i_force = next(i for i, l in enumerate(lines) if l.strip() == "FORCE=0")
        i_shift = next(i for i, l in enumerate(lines) if l.startswith('TIMEOUT_S="$1"; shift'))
        assert i_force < i_shift, (
            f"❌ --force 解析在 shift 之后（第 {i_force} vs {i_shift} 行）"
            "⇒ --force 会被当成超时秒数，这正是我第一版的 bug"
        )

    def test_force_actually_consumes_the_flag(self) -> None:
        """⚠️ 行为级：带 --force 时 `超时=` 必须是秒数，不能是 `--forces`。"""
        r = subprocess.run(
            ["bash", str(RUNBG), "--force", "60", "teeth-fp", sys.executable, "-c", "print(1)"],
            capture_output=True, text=True, cwd=str(ROOT), timeout=180,
        )
        assert "超时=60s" in r.stderr, (
            f"❌ --force 没被消费（应显示 超时=60s）\nstderr={r.stderr[:300]}"
        )
        assert "超时=--forces" not in r.stderr

    def test_refuses_without_force_when_busy(self) -> None:
        """⚠️ 另一侧：没 --force 且确实忙时，必须 exit 3 且**不执行**命令。"""
        r = subprocess.run(
            ["bash", str(RUNBG), "60", "teeth-nofp", sys.executable,
             "-c", "print('SHOULD_NOT_RUN')"],
            capture_output=True, text=True, cwd=str(ROOT), timeout=180,
        )
        # 只在"确实忙"时才有意义；不忙就说明前提不成立（先怀疑测试）
        busy = subprocess.run([sys.executable, str(GUARD)],
                              capture_output=True, cwd=str(ROOT), timeout=120)
        if busy.returncode == 0:
            return  # 机器空闲 ⇒ 本次放行是正确的，不构成牙齿
        assert r.returncode == 3, f"忙时应 exit 3，实为 {r.returncode}"
        assert "SHOULD_NOT_RUN" not in r.stdout
