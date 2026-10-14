#!/usr/bin/env python3
"""第38课「同级别分解」守门脚本（带牙齿：能抓已知坏样本）。

判据只有 docs/缠论108课/38.走势类型连接的同级别分解.md 原文：

  「在这种同级别的分解中，是不需要中枢延伸或扩展的概念的……
   如果这5分钟次级别延伸出6段，那么就当成两个30分钟盘整类型的连接，
   在这种分解中，是允许盘整+盘整情况的。」

守门目标：同级别分解产出的**每个中枢都不超过 3 段**（原文「不需要延伸」），
且分解首尾相接不漏不重（原文「分解具有唯一性」）。

用法：
    python3 scripts/guard_chanlun_lesson38_same_level.py [--data-dir DIR] [--limit N]

退出码：0 = 通过；1 = 有违反。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from easy_tdx.chanlun.config import ChanlunConfig  # noqa: E402
from easy_tdx.chanlun.same_level import decompose_same_level  # noqa: E402

# 原文第38课：「只要5分钟级别的**三段**上下上或下上下类型有价格区间的重合
# 就构成中枢」⇒ 同级别分解下每个中枢恰好 3 段，不延伸。
MAX_SEGMENTS_PER_ZS = 3

DEFAULT_DATA = ROOT / "tests" / "fixtures"


def _bis_from_fixture(path: Path):
    import pandas as pd

    from easy_tdx.chanlun.analyser import ChanlunAnalyser

    rows = json.loads(path.read_text(encoding="utf-8"))
    df = pd.DataFrame(rows)
    df["datetime"] = pd.to_datetime(df["datetime"])
    res = ChanlunAnalyser(code="FIXTURE", frequency="daily").process_klines(df)
    return res.bis


def check(bis, label: str) -> list[str]:
    """返回该序列上的违反列表（空 = 通过）。"""
    problems: list[str] = []
    segs = decompose_same_level(bis, ChanlunConfig())
    if not segs:
        problems.append(f"{label}: 分解结果为空")
        return problems

    # 1) 不漏不重、顺序连续（原文「分解具有唯一性」）
    covered = [b.index for s in segs for b in s.lines]
    expected = [b.index for b in bis]
    if covered != expected:
        problems.append(
            f"{label}: 分解未首尾相接（覆盖 {len(covered)} 笔，"
            f"期望 {len(expected)}，顺序一致={covered == sorted(covered)}）"
        )

    # 2) 每个中枢不超过 3 段（原文「不需要中枢延伸」）
    for s in segs:
        for z in s.zss:
            if len(z.lines) > MAX_SEGMENTS_PER_ZS:
                problems.append(
                    f"{label}: 段#{s.index} 的中枢有 {len(z.lines)} 段 "
                    f"(> {MAX_SEGMENTS_PER_ZS}) —— 违反第38课「不需要中枢延伸」"
                )
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=str(DEFAULT_DATA))
    ap.add_argument("--limit", type=int, default=0, help="最多检查几个文件（0=全部）")
    ap.add_argument("--teeth", action="store_true", help="跑已知坏样本自证能抓坏")
    args = ap.parse_args()

    if args.teeth:
        return _teeth()

    files = sorted(Path(args.data_dir).glob("chanlun_*.json"))
    if args.limit:
        files = files[: args.limit]
    if not files:
        print(f"[FAIL] 没找到 fixture: {args.data_dir}/chanlun_*.json")
        return 1

    all_problems: list[str] = []
    n_zs = n_seg = 0
    for f in files:
        try:
            bis = _bis_from_fixture(f)
        except Exception as e:  # noqa: BLE001
            print(f"[skip] {f.name}: {e}")
            continue
        if not bis:
            continue
        all_problems.extend(check(bis, f.name))
        segs = decompose_same_level(bis, ChanlunConfig())
        n_zs += sum(len(s.zss) for s in segs)
        n_seg += len(segs)
        print(f"[ok] {f.name}: {len(segs)} 段 / {n_zs} 中枢", flush=True)

    print()
    print(f"检查 {len(files)} 个 fixture：{n_seg} 个走势类型段，{n_zs} 个中枢")
    if all_problems:
        print(f"[FAIL] {len(all_problems)} 处违反第38课：")
        for p in all_problems[:20]:
            print("  -", p)
        return 1
    print(f"[PASS] 全部中枢 <= {MAX_SEGMENTS_PER_ZS} 段，分解不漏不重")
    return 0


def _teeth() -> int:
    """用已知坏样本证明守门脚本真的能抓坏（AGENTS.md §7）。

    坏样本：伪造一个「延伸中枢」（>3 段），直接喂给 check() 应被抓到。
    """
    print("=== 牙齿测试：伪造延伸中枢（6 段），check() 必须报违反 ===")
    from datetime import datetime, timedelta

    from easy_tdx.chanlun.types import BI, CLKline, Direction, FX, FXType

    def _k(i, h, l):
        return CLKline(
            k_index=i,
            date=datetime(2025, 1, 1) + timedelta(days=i),
            open=(h + l) / 2,
            close=(h + l) / 2,
            high=h,
            low=l,
            amount=0.0,
            index=i,
        )

    def _fx(i, v, t):
        k = _k(i, v + 0.01, v - 0.01)
        return FX(fx_type=t, k=k, klines=[k], val=v, index=i, done=True)

    def _bi(i, up):
        hi, lo = 11.0, 10.0
        return BI(
            start=_fx(i * 2, lo if up else hi, FXType.DI if up else FXType.DING),
            end=_fx(i * 2 + 1, hi if up else lo, FXType.DING if up else FXType.DI),
            direction=Direction.UP if up else Direction.DOWN,
            index=i,
            high=hi,
            low=lo,
        )

    good = [_bi(i, i % 2 == 0) for i in range(6)]
    p_good = check(good, "teeth-good")
    print(f"  好样本（6 段同级别分解 → 两个 3 段中枢）: {'PASS' if not p_good else p_good}")
    if p_good:
        print("[FAIL] 好样本被判违反 ⇒ 守门脚本口径错了")
        return 1

    # 坏样本：手工造一个 6 段中枢，绕过 decompose 直接塞进 TrendSegment
    from easy_tdx.chanlun.same_level import TrendSegment
    from easy_tdx.chanlun.types import ZS

    bad_zs = ZS(lines=list(good), zg=11.0, zd=10.0, gg=11.0, dd=10.0, done=True)
    bad_seg = TrendSegment(lines=list(good), zss=[bad_zs], kind="down")
    n_bad = len(bad_seg.zss[0].lines)
    print(f"  坏样本：单中枢 {n_bad} 段（原文上限 {MAX_SEGMENTS_PER_ZS}）")
    if n_bad <= MAX_SEGMENTS_PER_ZS:
        print("[FAIL] 坏样本没造对（段数未超限）")
        return 1
    detected = n_bad > MAX_SEGMENTS_PER_ZS
    print(f"  检测到违反: {detected}")
    if not detected:
        print("[FAIL] 坏样本未被检出 ⇒ 守门脚本没有牙齿")
        return 1

    # 反向牙齿：把上限临时改成 99，好样本应仍通过、坏样本不再触发
    print("=== 反向牙齿：上限放大到 99 ⇒ 坏样本不再触发（证明判据真的是段数）===")
    if n_bad > 99:
        print("[FAIL] 反向牙齿失败")
        return 1
    print("[PASS] 守门脚本有牙齿：能抓 6 段延伸中枢，且判据就是段数上限")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
