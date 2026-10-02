#!/usr/bin/env python3
"""缠论（P0）「未来免疫」探针：追加未来 K 线，历史买卖点不得改变。

为什么需要它
------------
F2（逐笔复盘讲解）与 F3（训练数据）都依赖一个前提：**过去某个 bar 上识别出的
买卖点是稳定可复现的**。若"后面多来一批数据"就改写了历史信号，那讲解和训练数据
都不可信。这与 P1 的 PIT 纪律是同一类要求，只是对象从财报换成了 K 线。

判定（运行时行为，不依赖代码形状）
--------------------------------
    signals(截至 N 根) == signals(截至 N+M 根)，且只看 index < cap 的早期信号

数据来源：复用 `scripts/audit_3rd_type_accuracy.py` 里**经过 ground truth 校准的
教科书案例构造器**（前跌→中枢→突破→回抽），而不是我自己拍的正弦波。

⚠️ 已踩过的坑（两轮，务必保留这条注释）
--------------------------------------
1. 第一版用「正弦」「锯齿」序列，它们**一个信号都没产生**（共有 0），却因集合相等
   而报 ✅ —— 空集自然相等，是**假通过**（与 P1 探针"检查 0 只却报通过"同类）。
   现已加**样本量自检**：可比信号 < MIN_SIGNALS 一律判为无效并单列，绝不混入通过。
2. 第二版想靠"加噪声/加趋势"让正弦波产出信号，**实测无效**：同一波形加 drift
   0.00/0.01/0.02/0.05/0.10，总信号分别为 0/0/1/0/0。诊断显示这些序列能产出
   笔与中枢，但**背驰数为 0**，所以没有买卖点 —— 不是代码 bug，是数据缺乏结构。
   正解是直接用项目里已验证过的案例构造器。

用法：  .venv/bin/python scripts/verify_chanlun_future_immunity.py
"""

from __future__ import annotations

import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import pandas as pd  # noqa: E402

from easy_tdx.chanlun.analyser import ChanlunAnalyser  # noqa: E402
from easy_tdx.chanlun.config import ChanlunConfig  # noqa: E402

from audit_3rd_type_accuracy import (  # noqa: E402
    _mk,
    _seg,
    build_3buy_case,
    build_3sell_case,
)

# 教科书案例按构造**恰好产生 1 个**指定信号（实测 3买/3卖 均在 index 47 附近），
# 所以下限取 1：仍能挡住"空集相等"的假通过（那才是真正的危害），又不误杀正常用例。
MIN_SIGNALS = 1


def _extend(bars, rng: random.Random, n_extra: int) -> list:
    """在既有走势后面追加 n_extra 根"未来"K 线（延续最后方向 + 抖动）。"""
    last_close = bars[-1][1]
    direction = 1.0 if last_close >= bars[-2][1] else -1.0
    out = list(bars)
    cur = last_close
    for _ in range(n_extra):
        step = direction * rng.uniform(0.05, 0.35) + rng.uniform(-0.12, 0.12)
        nxt = max(1.0, cur + step)
        out.append((cur, nxt, max(cur, nxt) + 0.05, min(cur, nxt) - 0.05))
        cur = nxt
    return out


def _sig(result, cap: int) -> set[tuple[str, int]]:
    return {
        (m.mmd_type.value, m.bi.end.k.k_index)
        for m in result.mmds
        if m.bi.end.k.k_index < cap
    }


def _analyze(bars):
    return ChanlunAnalyser(code="T", frequency="daily", config=ChanlunConfig()).process_klines(
        _mk(bars)
    )


def main() -> int:
    fails: list[str] = []
    invalid: list[str] = []
    print("缠论 P0 未来免疫探针（教科书案例构造器）\n")

    for case_name, builder in (("3买", build_3buy_case), ("3卖", build_3sell_case)):
        for seed in range(6):
            rng = random.Random(1000 + seed)
            bars, _gt = builder(random.Random(2000 + seed))
            # 实测：教科书案例共约 64 根，3买/3卖信号落在 index 47 附近。
            # 我第一版取 cap=len(bars)//2 (=32) 把信号整个排除在外，24 个用例
            # 全部"样本不足" —— 又是一次假通过风险。这里取 90% 覆盖信号区，
            # 同时仍远离追加的尾部数据。
            cap = max(1, int(len(bars) * 0.9))

            r_short = _analyze(bars)
            # 追加"未来"数据
            for extra in (40, 100):
                ext = _extend(bars, random.Random(3000 + seed), extra)
                r_long = _analyze(ext)
                s, l = _sig(r_short, cap), _sig(r_long, cap)
                tag = f"{case_name} seed={seed} +{extra}根"

                # 关键：以**短序列**的信号数做有效性判定，而不是用交集。
                # 若用交集，那么"未来函数把早期信号删掉"会让交集变 0 → 被误判成
                # 「样本不足」而跳过，泄漏就这样从探针眼皮底下溜过去。实测注入
                # 一个"数据变长就删掉早期信号"的假实现，旧逻辑竟然报 ✅（无牙齿）。
                if len(s) < MIN_SIGNALS:
                    print(f"  ⚠ 无效 {tag}: 短序列信号仅 {len(s)}（<{MIN_SIGNALS}）")
                    invalid.append(tag)
                    continue

                ok = s == l
                mark = "✅" if ok else "❌"
                print(
                    f"  {mark} {tag}: 短{len(s)} 长{len(l)} 共有{len(s & l)} "
                    f"仅短{len(s - l)} 仅长{len(l - s)}"
                )
                if not ok:
                    for x in sorted(s - l)[:4]:
                        print(f"       仅短有（历史信号被未来数据抹掉）: {x}")
                    for x in sorted(l - s)[:4]:
                        print(f"       仅长有（未来数据造出新信号）: {x}")
                    fails.append(tag)

    print()
    if invalid:
        print(f"⚠ {len(invalid)} 个用例样本不足、未纳入判定（不算通过）")
    if fails:
        print(f"\n结论: ❌ {len(fails)} 个用例未通过未来免疫")
        return 1
    print("结论: ✅ 缠论历史买卖点不因追加未来 K 线而改变")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
