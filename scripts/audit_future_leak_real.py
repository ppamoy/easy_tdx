#!/usr/bin/env python3
"""缠论模型「未来函数」审计（真实数据）——PIT 纪律的核心闸门。

为什么这是最重要的一层
----------------------
若模型在 bar N 上标出的买卖点，会在「后面多来一批数据」后被改写/新增/删除，
那么：
  * 回测里那些"命中"是**用未来信息挑出来的** → 命中率虚高、不可实现；
  * 实盘在 bar N 看到的信号 ≠ 回测在 bar N 用的信号 → 回测与实盘不一致。
这一层不通过，后面所有「正确率/胜率/选股力」结论都作废。

方法（逐 bar 滚动推进，行为级判定，不依赖代码形状）
--------------------------------------------------
对每个标的、每个检查点 N（取若干截断长度）：
  1. 只用前 N 根 K 线跑一次缠论，记录 bar_index < N - H 的全部买卖点
     （H = 前瞻缓冲，避免把"尚未走完的最后一根"计入）；
  2. 用全量（N + M 根）再跑一次，记录同样范围的买卖点；
  3. 两次必须**完全一致**。任何新增/消失/漂移 = 未来函数泄漏。

有效性自检（防止"空集相等"假通过，这是本项目已踩过的坑）
--------------------------------------------------------
* 每组必须至少 MIN_SIGNALS 个可比信号，否则标记为 INVALID 而非通过；
* 以**短序列**的信号数判定（若用交集，"未来函数删掉早期信号"会让交集变 0
  → 被误报成"样本不足"而放过泄漏，实测该漏洞已修）。

用法：  .venv/bin/python scripts/audit_future_leak_real.py

性能：单次 process_klines 随 K 线数近似平方增长（实测 1500 根约 6s），
      故全量结果每标的只算一次并复用；进程池并行按标的切分（默认 8 进程）。
"""

from __future__ import annotations

import json
import sys
from multiprocessing import Pool
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from easy_tdx.chanlun.analyser import ChanlunAnalyser  # noqa: E402
from easy_tdx.chanlun.config import ChanlunConfig  # noqa: E402

DATA_DIR = ROOT / "audit_data"
# 前瞻缓冲：最后 20 根的结构仍在变化（笔/中枢未确认），不计入可比范围
LOOKAHEAD_BUFFER = 20
# 每个检查点至少要有这么多可比信号，否则判无效
MIN_SIGNALS = 3


def _sig(result, cap: int) -> set[tuple[str, int]]:
    return {
        (m.mmd_type.value, m.bi.end.bar_index) for m in result.mmds if m.bi and m.bi.end.bar_index < cap
    }


def audit_one(args: tuple[str, str]) -> tuple[str, list[str], list[str], int, int]:
    """单标的审计（进程池入口）。返回 (code, 失败项, 无效项, 可比信号数, 检查点数)。"""
    code, path = args
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    df = pd.DataFrame(rows)
    df["datetime"] = pd.to_datetime(df["datetime"])

    fails: list[str] = []
    invalid: list[str] = []
    total_signals = 0
    checks = 0

    n_total = len(df)
    # 全量结果每标的只算一次（1500 根约 6s，复用可省掉 7 倍重复计算）
    r_long = ChanlunAnalyser(code=code, frequency="daily", config=ChanlunConfig()).process_klines(df)

    for frac in (0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 0.95):
        n = int(n_total * frac)
        if n < 120:
            continue
        cap = max(1, n - LOOKAHEAD_BUFFER)
        r_short = ChanlunAnalyser(
            code=code, frequency="daily", config=ChanlunConfig()
        ).process_klines(df.iloc[:n])
        s = _sig(r_short, cap)
        l = _sig(r_long, cap)
        checks += 1
        total_signals += len(s)
        if len(s) < MIN_SIGNALS:
            invalid.append(f"{code}@{n}根 可比信号仅 {len(s)} (<{MIN_SIGNALS})")
            continue
        if s != l:
            added = l - s
            removed = s - l
            fails.append(
                f"{code} 截断{n}根(cap={cap}): 短={len(s)} 长={len(l)} "
                f"新增{len(added)} 消失{len(removed)}"
                + (f"  例新增={sorted(added)[:3]}" if added else "")
                + (f"  例消失={sorted(removed)[:3]}" if removed else "")
            )
    return code, fails, invalid, total_signals, checks


def main() -> int:
    files = sorted(DATA_DIR.glob("*.json"))
    if not files:
        print(f"❌ {DATA_DIR} 无数据，先跑 scripts/audit_fetch_real_data.py")
        return 2

    jobs = [(p.stem, str(p)) for p in files]
    print(f"缠论未来函数审计 —— {len(jobs)} 只真实标的（进程池 8 并行）\n")

    all_fails: list[str] = []
    all_invalid: list[str] = []
    tot_sig = 0
    tot_checks = 0
    with Pool(processes=8) as pool:
        for code, f, inv, ns, nc in pool.imap_unordered(audit_one, jobs):
            all_fails.extend(f)
            all_invalid.extend(inv)
            tot_sig += ns
            tot_checks += nc
            status = "❌" if f else "✅"
            print(f"  {status} {code:<18} 检查点{nc:>2}  可比信号{ns:>4}  违反{len(f):>3}")

    print("\n" + "=" * 70)
    print(f"检查点总数 {tot_checks}，可比信号总数 {tot_sig}")
    print(f"❌ 未来函数违反：{len(all_fails)}")
    for d in all_fails[:30]:
        print("   " + d)
    print(f"⚠️  样本不足（未判定）：{len(all_invalid)}")
    for d in all_invalid[:10]:
        print("   " + d)
    return 1 if all_fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
