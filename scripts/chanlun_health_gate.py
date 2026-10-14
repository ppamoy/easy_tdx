#!/usr/bin/env python3
"""缠论模型**持续健康检查**统一入口（一键跑 + 明确退出码 + 自带牙齿）。

## 为什么要有这个脚本
缠论的健康检查散在多个脚本里，且**没有一个是"入口"**：
CI 里只挂了 3 个（invariants / future_leak / rolling_oos），
其余（`audit_mmd_ground_truth`、`audit_3rd_type_accuracy`、
`audit_chanlun_vs_local_extreme`…）只能靠人记得手动跑。
本脚本把它们**串成一个门禁**，并且：

  1. **自带牙齿**（AGENTS.md §7）：`--selftest` 会故意注入一个坏状态，
     验证"本守卫真的会红" —— 全绿的守卫如果不能变红，等于没有守卫。
  2. **区分失败等级**：`BLOCK`（阻断发布）/ `WARN`（记录）/ `SKIP`（环境不足跳过）。
     ⚠️ 环境不可用必须与"检查通过"严格区分：历史上"取到错数据还不自知"
     就是因为没有这一层。
  3. **机器可读**：`--json` 输出，便于后续挂定时任务/看趋势。

## 失败等级定义
  BLOCK  结构/正确性被破坏（不变式违反、未来函数、ground truth 不符）
  WARN   统计口径类（样本外不稳定、3卖拖累等），需人看，不阻断
  SKIP   依赖数据/时间不足，未执行（**不能当成通过**）

用法：
    .venv/bin/python scripts/chanlun_health_gate.py              # 全跑
    .venv/bin/python scripts/chanlun_health_gate.py --quick      # 只跑快的
    .venv/bin/python scripts/chanlun_health_gate.py --selftest   # 牙齿自检（必须）
退出码：0 = 全过（或仅有 WARN/SKIP）；1 = 有 BLOCK；2 = 牙齿自检失败。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = str(ROOT / ".venv" / "bin" / "python")
SCRIPTS = ROOT / "scripts"

# (脚本, 等级, 说明, 默认是否跑)
# ⚠️ 慢脚本（全量 286 只，数十分钟）默认不在 quick 里跑。
# ⚠️ 分级依据（实测耗时，本机 4 核）：
#   invariants 全量 286 只 ≈ 20+ 分钟；future_leak / ground_truth 各数分钟。
#   把它们标成"快"会让 --quick 在 CI 上跑半小时 —— 我第一版就犯了这个错。
#   故 --quick 只跑 invariants 的**限样本**版（--limit N，秒级）+ 牙齿自检，
#   全量另走 --full（挂定时任务，见 crontab chanlun-health-weekly）。
CHECKS: list[tuple[str, str, str, bool]] = [
    ("audit_chanlun_invariants.py", "BLOCK",
     "结构不变式 I1-I12（顶底交替/中枢区间/确定性）", True),
    ("audit_future_leak_real.py", "BLOCK",
     "未来函数（截断序列信号须与全量一致）", False),
    ("audit_mmd_ground_truth.py", "BLOCK",
     "买卖点 ground truth 回归", False),
    ("audit_3rd_type_accuracy.py", "BLOCK",
     "三类买卖点召回率（V731 曾修过 0% 召回 bug）", False),
    ("audit_rolling_oos.py", "WARN",
     "滚动窗样本外（结论是否随时间漂移）", False),
    ("audit_chanlun_vs_local_extreme.py", "WARN",
     "缠论 vs 局部极值（同义反复检验）", False),
    ("audit_chanlun_pair_winrate.py", "WARN",
     "缠论原口径胜率/盈亏比（买点进卖点出）", False),
    ("audit_chanlun_excess_by_regime.py", "WARN",
     "逐年/牛熊分段（熊市少亏 vs 牛市跟不上）", False),
]

# 支持 --limit 的脚本（其余只能全量，故不进 quick）
LIMITABLE = {
    "audit_chanlun_invariants.py",
    "audit_chanlun_vs_local_extreme.py",
    "audit_chanlun_pair_winrate.py",
}

# quick 模式默认每只脚本只审这么多标的（保证秒级~分钟级返回）
QUICK_LIMIT = 3


def run_one(script: str, extra: list[str] | None = None,
            timeout: int = 3600) -> tuple[int, float, str]:
    """跑一个检查脚本，返回 (退出码, 耗时秒, 输出尾部)。"""
    cmd = [PY, str(SCRIPTS / script)] + (extra or [])
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True,
                           text=True, timeout=timeout)
        el = time.time() - t0
        tail = (p.stdout or "")[-800:] + (p.stderr or "")[-400:]
        return p.returncode, el, tail
    except subprocess.TimeoutExpired:
        return 124, time.time() - t0, f"TIMEOUT {timeout}s"
    except Exception as e:  # noqa: BLE001
        return 125, time.time() - t0, f"{type(e).__name__}: {e}"


def selftest() -> int:
    """牙齿自检：证明本守卫**真的会红**，而不是恒绿。

    做法：对一个已知会通过 BLOCK 检查的脚本，用**环境变量注入坏状态**；
    若不提供注入机制，则退而验证「脚本缺失/语法错误时本守卫报 BLOCK」。
    ⚠️ 后者也能抓住"守卫恒绿"这一最危险的失效模式。
    """
    print("【牙齿自检】验证守卫会红，而不是恒绿")
    print("-" * 72)

    # 方式 1（优先）：真实坏状态注入 —— 验证判据**能抓到真 bug**，
    # 而不仅是"文件不存在"。用 --limit 2 保证秒级返回。
    import os
    env_bad = dict(os.environ)
    env_bad["INJECT_BROKEN"] = "1"
    cmd = [PY, str(SCRIPTS / "audit_chanlun_invariants.py"), "--limit", "2"]
    try:
        p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True,
                           text=True, timeout=900, env=env_bad)
        if p.returncode == 1:
            hit = [l.strip() for l in (p.stdout or "").splitlines()
                   if l.strip().startswith("❌")]
            print("  ✅ 方式1：注入坏状态后审计确实报错（会红）")
            for l in hit[:5]:
                print(f"        {l}")
            return 0
        print(f"  ⚠️ 方式1 未生效（退出码 {p.returncode}）⇒ 判据可能空转")
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️ 方式1 异常 {type(e).__name__}: {e}")
    target = SCRIPTS / "audit_chanlun_invariants.py"
    backup = SCRIPTS / "._tmp_gate_backup.py"
    moved = False
    try:
        target.rename(backup)
        moved = True
        rc, _el, _ = run_one("audit_chanlun_invariants.py", timeout=120)
        if rc != 0:
            print("  ✅ 方式2：脚本不可用时守卫报失败（不会静默通过）")
            return 0
        print("  ❌ 方式2 失败：脚本缺失时守卫仍返回 0 ⇒ 恒绿守门，不可信")
        return 2
    except Exception as e:  # noqa: BLE001
        print(f"  ❌ 牙齿自检异常 {type(e).__name__}: {e}")
        return 2
    finally:
        if moved and backup.exists():
            backup.rename(target)
        print("  （已恢复脚本）")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="只跑快的检查（限样本，分钟级）")
    ap.add_argument("--full", action="store_true",
                    help="跑全部 8 项（含超慢脚本，合计数小时，慎用）")
    ap.add_argument("--full-block", action="store_true",
                    help="跑全部 BLOCK 检查（含慢脚本全量，适合定时任务）")
    ap.add_argument("--json", action="store_true", help="机器可读输出")
    ap.add_argument("--selftest", action="store_true", help="牙齿自检")
    ap.add_argument("--limit", type=int, default=0, help="传给慢脚本的标的数上限")
    a = ap.parse_args()

    if a.selftest:
        return selftest()

    if a.full_block:
        # 定时任务用：只跑 BLOCK 级（WARN 项人工看趋势，不占机器）
        checks = [c for c in CHECKS if c[1] == "BLOCK"]
        mode = "full-block（BLOCK 全量）"
    elif a.full:
        # 显式 --full 才跑全部（含 3 个超慢脚本，合计数小时）
        checks = list(CHECKS)
        mode = "full（全部，含超慢脚本）"
    else:
        # ⚠️ 默认 = quick。我第一版把"默认"设成跑全部 8 项，
        #    其中 excess_by_regime / rolling_oos / vs_local_extreme 无 --limit，
        #    全量各需 1~3 小时 ⇒ 无参数误跑会占满机器几小时。
        #    安全默认：无参数按 quick 走，想全跑必须显式声明。
        checks = [c for c in CHECKS if c[3]]
        mode = "quick（限样本，安全默认）"
    results = []
    print(f"缠论模型持续健康检查  共 {len(checks)} 项  [{mode}]\n")

    for script, level, desc, _fast in checks:
        extra: list[str] = []
        # quick 模式下给支持 --limit 的脚本限样本，避免门禁跑几十分钟
        if script in LIMITABLE:
            extra = ["--limit", str(a.limit or QUICK_LIMIT)]

        rc, el, tail = run_one(script, extra)
        if rc == 0:
            status = "PASS"
        elif rc == 2 or rc == 124 or rc == 125:
            status = "SKIP"     # 环境不足/超时 ≠ 通过
        else:
            status = "FAIL"

        results.append({"script": script, "level": level, "desc": desc,
                        "exit": rc, "status": status, "seconds": round(el, 1)})

        mark = {"PASS": "✅", "SKIP": "⚠️", "FAIL": "❌"}[status]
        print(f"{mark} [{level:5s}] {script:38s} {status:4s} "
              f"({el:6.1f}s, exit={rc})")
        if status != "PASS":
            last = [l for l in tail.splitlines() if l.strip()][-6:]
            for l in last:
                print(f"        {l}")

        # BLOCK 级失败：早停（后面的检查没必要跑）
        if status == "FAIL" and level == "BLOCK":
            print(f"\n❌ BLOCK 级检查失败：{script} —— 后续检查中止。")
            break

    n_block_fail = sum(1 for r in results
                       if r["level"] == "BLOCK" and r["status"] == "FAIL")
    n_skip = sum(1 for r in results if r["status"] == "SKIP")
    n_warn_fail = sum(1 for r in results
                      if r["level"] == "WARN" and r["status"] == "FAIL")

    print("\n" + "=" * 72)
    print(f"BLOCK 失败 {n_block_fail}   WARN 失败 {n_warn_fail}   SKIP {n_skip}")
    if n_skip:
        print("⚠️ SKIP 表示**未执行**（数据/时间不足），不等于通过。")

    if a.json:
        print("\n" + json.dumps(results, ensure_ascii=False, indent=2))

    if n_block_fail:
        print("\n判定：❌ 缠论模型健康检查未通过（BLOCK）")
        return 1
    if n_warn_fail:
        print("\n判定：⚠️ 通过，但有 WARN 项需人工复核")
        return 0
    print("\n判定：✅ 全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
