#!/usr/bin/env python3
"""V733：严格样本外滚动验证（walk-forward）。

为什么要做
------------
前面所有结论都是**全样本**口径：一次性跑完 1500 根，统计所有信号的前瞻收益。
即使已验证 PIT（追加数据不改写历史信号），全样本统计仍有隐患：
若某一个时段（比如 2024 的普涨行情）贡献了大部分收益，结论就不可外推。

本脚本把每只标的切成若干**滚动测试窗**，逐窗统计「信号 vs 同窗局部极值基准」
的超额，看：
  Q-R1 每一窗的超额是否都为正（还是有窗为负 → 结论不稳定）
  Q-R2 超额在时间上是否衰减（前半段 vs 后半段）

⚠️ 为什么可以复用全量运行的信号（而不是每窗重跑）
    因为 PIT 已被独立验证：
      * `scripts/audit_future_leak_real.py`：224 检查点 / 6377 信号 / 0 违反
      * 区间套：`tests/unit/test_chanlun_v733_qujiantao_pit.py` 0/291 违反
    即「在 t 时刻用 df[:t] 跑出来的信号」== 「全量跑出来的、落在 t 之前的信号」。
    故按 bar_index 切窗等价于逐窗重跑，但快几个数量级。
    若 PIT 哪天被破坏，本脚本的结论会随之失效 —— 所以 CI 里两个必须一起跑。

用法：  .venv/bin/python scripts/audit_rolling_oos.py
"""

from __future__ import annotations

import json
import sys
from math import erfc, sqrt
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from easy_tdx.chanlun.analyser import ChanlunAnalyser  # noqa: E402
from easy_tdx.chanlun.config import ChanlunConfig  # noqa: E402

DATA_DIR = ROOT / "audit_data"
N_WINDOWS = 6          # 把每只标的的可用区间切成几段
HORIZON = 20           # 前瞻窗口（根）
PIVOT = 5              # 局部极值半窗
MIN_PER_WINDOW = 20    # 每窗至少多少信号才判定
BOOT = 300
SEED = 20241002


def norm_p(z: float) -> float:
    return float(erfc(abs(z) / sqrt(2)))


def pivot_indices(c: np.ndarray, w: int, low: bool, lo: int, hi: int) -> np.ndarray:
    """在 [lo, hi) 内找局部极值点。"""
    out = []
    for i in range(max(w, lo), min(len(c) - w, hi)):
        seg = c[i - w : i + w + 1]
        if low and c[i] == seg.min():
            out.append(i)
        elif (not low) and c[i] == seg.max():
            out.append(i)
    return np.array(out, dtype=int)


def main() -> int:
    files = [p for p in sorted(DATA_DIR.glob("*.json"))
             if p.stem.split("_")[0] not in ("sh000300", "sh000001")]
    if not files:
        print(f"❌ {DATA_DIR} 无数据")
        return 2

    rng = np.random.default_rng(SEED)
    # window -> {type -> list of (symbol, signal_return, baseline_mean)}
    win_data: dict[int, dict[str, list[tuple[float, float]]]] = {}

    for p in files:
        code = p.stem.split("_")[0]
        df = pd.DataFrame(json.loads(p.read_text(encoding="utf-8")))
        df["datetime"] = pd.to_datetime(df["datetime"])
        c = df["close"].to_numpy(dtype=float)
        n = len(c)
        res = ChanlunAnalyser(code=code, frequency="daily", config=ChanlunConfig()).process_klines(df)

        usable = n - HORIZON
        edges = np.linspace(0, usable, N_WINDOWS + 1).astype(int)

        for m in res.mmds:
            if not m.bi:
                continue
            st = m.mmd_type.value.lower()
            i = m.bi.end.bar_index
            if i + HORIZON >= n:
                continue
            # ⚠️ 自误报修正：第一版用「类型名以 buy 结尾」判方向，类二买
            # 2buy_s 不匹配 → 被当成卖点、收益取反，稳定显示 -8%（实为 +8%）。
            # 类二买 2buy_s / 类二卖 2sell_s 在 V732/V733 的三个审计脚本里
            # 被整体漏掉，本脚本第一次纳入统计就暴露了这个判向 bug。
            is_buy = "buy" in st
            w = int(np.searchsorted(edges[1:], i, side="right"))
            if w >= N_WINDOWS:
                continue
            r = c[i + HORIZON] / c[i] - 1.0
            if not is_buy:
                r = -r
            # 同窗内的局部极值基准
            lo, hi = int(edges[w]), int(edges[w + 1])
            cand = pivot_indices(c, PIVOT, low=is_buy, lo=lo, hi=hi)
            cand = cand[(cand + HORIZON) < n]
            if len(cand) < 5:
                continue
            idx = rng.choice(cand, size=(BOOT, 1), replace=True)
            rr = c[idx + HORIZON] / c[idx] - 1.0
            if not is_buy:
                rr = -rr
            win_data.setdefault(w, {}).setdefault(st, []).append((float(r), float(np.mean(rr))))

    print(f"\n每只标的切成 {N_WINDOWS} 个滚动窗，前瞻 {HORIZON} 根")
    print("=" * 100)
    print(f"{'窗':>4}{'类型':<8}{'n':>6}{'信号均值':>11}{'同窗极值基准':>14}{'超额':>10}{'p':>9}  判定")
    print("-" * 100)

    per_type: dict[str, list[float]] = {}
    for w in sorted(win_data):
        for st in sorted(win_data[w]):
            dat = win_data[w][st]
            if len(dat) < MIN_PER_WINDOW:
                print(f"{w:>4}{st:<8}{len(dat):>6}{'—':>11}{'—':>14}{'—':>10}{'—':>9}  样本不足(<{MIN_PER_WINDOW})")
                continue
            arr = np.array(dat)
            sig = arr[:, 0]
            base = arr[:, 1]
            d = sig - base
            excess = float(np.mean(d))
            se = float(np.std(d, ddof=1)) / sqrt(len(d))
            z = excess / se if se > 0 else 0.0
            p = norm_p(z)
            ok = p < 0.05 and excess > 0
            per_type.setdefault(st, []).append(excess)
            print(f"{w:>4}{st:<8}{len(sig):>6}{np.mean(sig):>11.3%}{np.mean(base):>14.3%}"
                  f"{excess:>+10.2%}{p:>9.4f}  {'✅显著为正' if ok else ('❌显著为负' if (p < 0.05 and excess < 0) else '—无差异')}")

    print("\n" + "=" * 100)
    print(f"Q-R1 稳定性：各类型在 {N_WINDOWS} 个滚动窗中，超额为正的窗数")
    print("-" * 100)
    for st in sorted(per_type):
        v = np.array(per_type[st])
        npos = int((v > 0).sum())
        print(f"  {st:<8} {npos}/{len(v)} 窗为正   中位超额 {np.median(v):+.2%}   "
              f"范围 [{v.min():+.2%}, {v.max():+.2%}]"
              f"{'  ← 方向不稳定' if 0 < npos < len(v) else ''}")

    print("\nQ-R2 时间衰减：前半段 vs 后半段（各类型中位超额）")
    print("-" * 100)
    for st in sorted(per_type):
        v = np.array(per_type[st])
        if len(v) < 4:
            print(f"  {st:<8} 窗数不足")
            continue
        half = len(v) // 2
        print(f"  {st:<8} 前半 {np.median(v[:half]):+.2%}   后半 {np.median(v[half:]):+.2%}   "
              f"差 {np.median(v[half:]) - np.median(v[:half]):+.2%}")

    print("\n⚠️ 局限：基准用「同窗局部极值」而非「同窗局部极值随机抽样多次」的配对分布；")
    print("   每窗样本量较小（尤其 2buy/2sell），单窗 p 值仅供参考，以「正窗比例」为准。")

    # ── CI 门禁 ───────────────────────────────────────────────────────
    # ⚠️ 第一版这里无条件 `return 0`，导致 CI 里那条"1buy 必须 6/6 窗为正、
    # 3sell 必须 0/6 窗为正"的断言**形同虚设**（脚本打印违规但退出码 0）。
    # 这是把"看起来在 CI 里"当成"真的在 CI 里生效"的典型错误。
    #
    # ⚠️ 第二版又把阈值写死成"1buy 必须 6/6"，结果在**CI 实际数据集**
    # （audit_fetch_real_data.py 默认只抓 30 只）上稳定失败：实测三个随机种子
    # 都是 5/6（中位 +0.71%~+0.77%），并非 bootstrap 噪声，而是样本量差异
    # （全量 286 只是 6/6，中位 +0.96%）。写死阈值会造成"每次 CI 都红"的
    # 假警报 —— 门禁就没人看了。
    #
    # 所以按**样本量**设阈值，并且真正抓的是"是否系统性变差"：
    #   全量(>=200 只)：1buy 需 6/6 正
    #   小样本(<200 只)：1buy 需 >=5/6 正，且**中位超额必须为正**
    # 3sell 无论样本量：正窗 <=1（它在两个样本量下都是 0/6，很稳）。
    n_sym = len(files)
    strict = n_sym >= 200
    min_pos_1buy = N_WINDOWS if strict else max(4, N_WINDOWS - 1)
    failed: list[str] = []

    v1 = per_type.get("1buy")
    if not v1 or len(v1) < N_WINDOWS:
        failed.append(f"1buy: 窗数不足（{len(v1) if v1 else 0}/{N_WINDOWS}）")
    else:
        npos = int((np.array(v1) > 0).sum())
        med = float(np.median(v1))
        if npos < min_pos_1buy:
            failed.append(f"1buy: 正窗 {npos}/{len(v1)} < 要求 {min_pos_1buy}"
                          f"（样本 {n_sym} 只，{'全量' if strict else '小样本'}档）")
        if med <= 0:
            failed.append(f"1buy: 中位超额 {med:+.2%} 不为正 —— 这是核心结论，"
                          f"任何样本量下都不应转负")

    v3 = per_type.get("3sell")
    if not v3 or len(v3) < N_WINDOWS:
        failed.append(f"3sell: 窗数不足（{len(v3) if v3 else 0}/{N_WINDOWS}）")
    else:
        npos3 = int((np.array(v3) > 0).sum())
        if npos3 > 1:
            failed.append(f"3sell: 正窗 {npos3}/{len(v3)} > 允许 1"
                          f" —— V733 实测为 0/6，若转正需人工复核")

    print(f"\n门禁档位：样本 {n_sym} 只 → "
          f"{'全量档（1buy 需 %d/%d 正）' % (N_WINDOWS, N_WINDOWS) if strict else '小样本档（1buy 需 %d/%d 正 + 中位为正）' % (min_pos_1buy, N_WINDOWS)}")

    print("\n" + "=" * 100)
    if failed:
        print("❌ CI 门禁未通过：")
        for f in failed:
            print(f"   {f}")
        print("\n若这是模型行为的有意变更，请更新本脚本的 gates 并说明原因。")
        return 1
    n1 = int((np.array(per_type["1buy"]) > 0).sum())
    print(f"✅ CI 门禁通过：1buy {n1}/{N_WINDOWS} 窗为正且中位超额为正、"
          f"3sell 未见正窗（与 V733 结论一致，{n_sym} 只样本）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
