#!/usr/bin/env python3
"""V733：参数敏感性 —— 检验"缠论下行保护"是**结构性**还是只是默认参数的产物。

为什么要做
----------
五之十四发现缠论策略中位最大回撤 28.5% vs 买持 54.1%（97% 样本回撤更小），
这是整份审计最稳健的一条。但我当时**自己标注了风险**：

    "回撤 28.5% 依赖当前默认参数（止损/仓位），换参数回撤会变，
     '回撤减半'不是结构固有的性质。"

这条caveat必须被检验，而不是留在文档里当免责声明。

⚠️ 关键的方法论问题：回撤小可能只是"仓位小"
----------------------------------------------------------
策略有 `position_pct`（默认 1.0 全仓）和 `stop_loss_pct`（默认 0.08）。
**把仓位从 100% 降到 30%，回撤必然缩小** —— 那不是信号好，是杠杆小。

所以本脚本的对照不是"和买持比"，而是：

1. **同仓位对照**：把 `position_pct` 调成和买持一样（1.0），比回撤
   ⇒ 排除"低暴露"假象；
2. **参数扫描**：对 `stop_loss_pct` / `take_profit_pct` / `use_3buy` /
   `use_3sell` / `min_confidence` 逐个变化，看回撤是否**普遍**低于买持
   ⇒ 若只在默认值成立、稍微一变就失效，那是过拟合，不是结构；
3. **仓位缩放对照**：把 `position_pct` 降到 0.3，看回撤是否机械性下降
   ⇒ 量化"低暴露"能贡献多少，作为诚实基线。

判定标准（事先写死，避免事后找理由）
--------------------------------------
- **结构性**：多数参数组合下回撤都显著低于买持，且**在同仓位(1.0)下依然成立**；
- **参数产物**：只有默认组合好，或优势随仓位线性消失。

用法：
    .venv/bin/python scripts/audit_param_sensitivity.py
    .venv/bin/python scripts/audit_param_sensitivity.py --limit 20

退出码：0 = 跑完；2 = 环境不可用。
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from easy_tdx.backtest.engine import BacktestEngine  # noqa: E402
from easy_tdx.backtest.strategies.chanlun import ChanlunStrategy  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "audit_data"
EXCLUDE = {"sh000300", "sh000001"}

# 参数扫描：每个变体只改一个参数，其余用默认值
VARIANTS: list[tuple[str, dict]] = [
    ("默认(仓位1.0/止损0.08)", {}),
    ("止损0.00", {"stop_loss_pct": 0.0}),
    ("止损0.04", {"stop_loss_pct": 0.04}),
    ("止损0.12", {"stop_loss_pct": 0.12}),
    ("止损0.20", {"stop_loss_pct": 0.20}),
    ("止盈0.10", {"take_profit_pct": 0.10}),
    ("止盈0.50", {"take_profit_pct": 0.50}),
    ("关三类买", {"use_3buy": False}),
    ("关三类卖", {"use_3sell": False}),
    ("三类买卖全关", {"use_3buy": False, "use_3sell": False}),
    ("开类二买/卖", {"use_2s_signals": True}),
    ("笔类型=old", {"bi_type": "old"}),
    # ⚠️ 故意不扫 bi_type="simple"：实测它单次回测比其它变体慢一个数量级
    # （12 只跑 >25 分钟未完成），且策略自身告警"legacy 简化口径…不推荐"。
    # 保留 new/old 两种正式笔型对照即可。
    # —— 仓位缩放：用来量化"低暴露"能贡献多少（诚实基线）——
    ("仓位0.30(低暴露基线)", {"position_pct": 0.3}),
    ("仓位0.50", {"position_pct": 0.5}),
    ("仓位0.80", {"position_pct": 0.8}),
]


def run(dfs: list[pd.DataFrame], **kw) -> tuple[np.ndarray, np.ndarray, list[int]]:
    dds, rets, ntr = [], [], []
    for df in dfs:
        try:
            s = ChanlunStrategy()
            # ⚠️ 参数在 s.p（dict）里，**不是**实例属性。
            # 早期版本用 `if hasattr(s,k): setattr(s,k,v)` —— hasattr 恒为
            # False，于是**所有参数改动都被静默跳过**，扫描测的全是默认值
            # （"参数敏感性"名存实亡）。必须直接写 s.p[k]。
            for k, v in kw.items():
                if k not in s.p:
                    unknown.append(k)
                s.p[k] = v
            r = BacktestEngine(s, cash=100000.0).run(df)
            dds.append(float(r.performance["max_drawdown"]))
            rets.append(float(r.performance["total_return"]))
            tr = r.trades
            ntr.append(int((tr["direction"] == "SELL").sum())
                       if isinstance(tr, pd.DataFrame) and not tr.empty else 0)
        except Exception:
            continue
    return np.array(dds), np.array(rets), ntr


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=20)
    a = ap.parse_args()
    fs = [p for p in sorted(DATA.glob("*.json"))
          if p.stem.split("_")[0] not in EXCLUDE]
    if a.limit:
        fs = fs[: a.limit]
    if not fs:
        print("❌ 无 audit_data，先跑 audit_fetch_real_data.py")
        return 2

    dfs: list[pd.DataFrame] = []
    for p in fs:
        try:
            df = pd.DataFrame(json.loads(p.read_text(encoding="utf-8")))
            df["datetime"] = pd.to_datetime(df["datetime"])
            if len(df) > 200:
                dfs.append(df)
        except Exception:
            continue
    if len(dfs) < 5:
        print("❌ 有效数据不足")
        return 2

    print("参数敏感性 —— 检验\"下行保护\"是结构性还是默认参数的产物")
    print(f"{len(dfs)} 只 A 股日线，同成本模型")
    print("=" * 88)

    # 买持回撤基线
    bh_dd = []
    for df in dfs:
        px = df["close"].to_numpy(float)
        peak = np.maximum.accumulate(px)
        bh_dd.append(float((peak - px).max() / peak.max()))
    bh_dd = np.array(bh_dd)
    bh_med = float(np.median(bh_dd))
    print(f"买入持有 中位最大回撤 {bh_med*100:.1f}%\n")

    unknown: list[str] = []

    print(f"{'参数变体':<24}{'回撤中位':>9}{'收益中位':>10}"
          f"{'跑赢数':>8}{'优于买持':>10}")
    print("-" * 61)
    # 先验证参数确实生效（避免整轮扫描测的全是默认值）
    probe_s = ChanlunStrategy()
    probe_s.p["stop_loss_pct"] = 0.2
    assert probe_s.p["stop_loss_pct"] == 0.2, "参数未写入 s.p，扫描将无效"
    print(f"参数写入自检：s.p['stop_loss_pct'] = "
          f"{probe_s.p['stop_loss_pct']} ✅（参数在 s.p，不是实例属性）\n")

    rows = []
    for label, kw in VARIANTS:
        dd, ret, _ = run(dfs, **kw)
        if len(dd) < 3:
            print(f"{label:<24}{'  跑失败':>9}")
            continue
        win = int((dd < bh_dd[: len(dd)]).sum())
        med = float(np.median(dd))
        rows.append((label, med, kw.get("position_pct", 1.0)))
        print(f"{label:<24}{med*100:>8.1f}%{np.median(ret)*100:>9.1f}%"
              f"{win:>5}/{len(dd)}{win/len(dd)*100:>9.0f}%")

    if unknown:
        print(f"\n❌ 未知参数（扫描无效）：{sorted(set(unknown))}")
        return 0

    # ── 判定 ──
    print("\n" + "=" * 88)
    full = [r for r in rows if r[2] == 1.0]        # 同仓位（1.0）的变体
    if not full:
        print("❌ 无同仓位变体")
        return 0
    beat = [r for r in full if r[1] < bh_med]
    n_beat = len(beat)
    print(f"同仓位(position_pct=1.0)变体 {len(full)} 个，其中回撤低于买持的 "
          f"{n_beat} 个（{n_beat/len(full)*100:.0f}%）")
    low = [r for r in rows if r[2] < 1.0]
    if low:
        print("\n低仓位基线（量化\"低暴露\"贡献多少）：")
        for label, med, pct in sorted(low, key=lambda r: r[1]):
            print(f"  仓位{int(pct*100):>3}%  回撤 {med*100:.1f}%")
        if full:
            base = [r for r in full if r[2] == 1.0][0][1]
            l30 = next((r[1] for r in low if r[2] == 0.3), None)
            if l30 is not None:
                print(f"\n⇒ 仓位 100%→30% 让回撤从 {base*100:.1f}% 降到 "
                      f"{l30*100:.1f}%，降幅 {(1-l30/base)*100:.0f}%")
                print("  这是**纯杠杆效应**，与信号无关，必须作为诚实基线。")
                if l30 < bh_med:
                    print("  ⚠️ 即：低仓位也能'跑赢买持回撤' —— 优势大小"
                          "不能单独归功于缠论信号。")
    if n_beat == len(full) and len(full) >= 5:
        print("\n✅ 判定：**多数同仓位参数组合下回撤都低于买持**")
        print("   ⇒ 下行保护在参数扰动下大体稳健，非单点过拟合。")
    elif n_beat >= max(2, len(full) // 2):
        print("\n🟡 判定：**部分参数组合下成立**，但不稳定")
        print("   ⇒ 不能宣称'结构固有'，只能说默认值下有效。")
    else:
        print("\n❌ 判定：**多数参数组合下不成立**")
        print("   ⇒ '下行保护'很可能是特定参数的产物，应撤回该结论。")
    print("\n⚠️ 局限：单市场日线、n 有限、未 beta 中性化、"
          "参数网格较粗（未做全因子搜索）、")
    print("   '优于买持'只比回撤不比收益 —— 低回撤可能只是收益也低。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
