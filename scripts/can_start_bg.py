#!/usr/bin/env python3
"""⚠️ 起飞前检查：**还有没有别的长任务在跑**。

## 为什么有这个脚本（2026-10-08，用户**两次**当面指出 CPU 被占满）
本机只有 4 核。我两次犯同一个错：起第二个长任务前**不检查**第一个还在不在跑。
第二次的叠加实测 328%/400%（pytest 全量 + 基线审计 2 worker + 前端 npm test），
还叠了另一个 agent 的 e2e。

`guard_bg_jobs.py` 只能**事后报警**，拦不住"我已经在跑了还再起一个"。
这个脚本是**起飞前**的那道闸：被 `scripts/run_bg.sh` 调用，
有长任务在跑就 exit 1，让 `run_bg.sh` 拒绝启动。

## 判定：不看进程名，看**实际 CPU 消耗**
⚠️ 不能用进程名白名单——另一 agent 的任务名字我根本不知道。
这里实测一段时间的 CPU tick 增量，只看"**真的在烧 CPU**"的进程。

## 用法
    scripts/can_start_bg.py            # 0 = 可以起；1 = 别起
    scripts/can_start_bg.py --verbose  # 打印是谁在占

退出码：0 可以启动；1 已有长任务在跑。
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
import time

# 长任务的判定门槛：采样窗口内 CPU 占用超过这个值（%）就算"在跑"
BUSY_PCT = 25.0
SAMPLE_S = 3.0

# ⚠️ 这些是**我自己**和常驻服务，不算"别人的长任务"吗？
# 不 —— 常驻服务（dsh web / moli / next-server）平时只占个位数，
# 达不到 BUSY_PCT。真烧 CPU 的必然是任务，不该白名单豁免。


def _snap() -> dict[int, tuple[int, str]]:
    d: dict[int, tuple[int, str]] = {}
    for p in glob.glob("/proc/[0-9]*"):
        pid = int(p.rsplit("/", 1)[-1])
        try:
            with open(p + "/stat") as f:
                st = f.read()
            rp = st.rfind(")")
            fields = st[rp + 2:].split()
            utime, stime = int(fields[11]), int(fields[12])
            with open(p + "/cmdline", "rb") as f:
                cmd = f.read().replace(b"\0", b" ").decode("utf-8", "replace")[:90]
            d[pid] = (utime + stime, cmd)
        except Exception:
            continue
    return d


def busy(sample_s: float = SAMPLE_S, min_pct: float = BUSY_PCT) -> list[tuple[float, int, str]]:
    a = _snap()
    time.sleep(sample_s)
    b = _snap()
    hz = os.sysconf("SC_CLK_TCK")
    out: list[tuple[float, int, str]] = []
    for pid, (t, cmd) in b.items():
        if pid not in a:
            continue
        pct = (t - a[pid][0]) / hz / sample_s * 100
        if pct >= min_pct:
            out.append((pct, pid, cmd))
    out.sort(reverse=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()

    rows = busy()
    if not rows:
        if a.verbose:
            print("✅ 没有长任务在跑，可以启动")
        return 0

    total = sum(r[0] for r in rows)
    print("❌ 已有长任务在烧 CPU：")
    for pct, pid, cmd in rows[:6]:
        print(f"   {pct:5.1f}%  pid={pid}  {cmd}")
    print(f"   合计 {total:.0f}%（本机 4 核 = 400%）")
    print()
    print("   ⚠️ 再起一个就会把 4 核占满（这件事我已经栽过两次）。")
    print("   先等它跑完，或用 scripts/guard_bg_jobs.py --kill-stalled 清掉。")
    return 1


if __name__ == "__main__":
    sys.exit(main())