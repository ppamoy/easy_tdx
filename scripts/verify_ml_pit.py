#!/usr/bin/env python3
"""多级别策略的**未来函数**检测（PIT）：截断序列后，前面的交易必须逐位一致。

## 为什么必须专门测这个
多级别策略比单周期**更容易**偷未来函数：
次级别（30min）信号是**一次性全量算好**再按时间推进消费的。
如果对齐/推进逻辑写错（比如用 bar_index 而不是 datetime 对齐，
或次级别信号用了"整段数据才确认"的笔），后面的数据会污染前面的决策。

⚠️ 更正（2026-10-10 实测，此处原说法**已被推翻**）：
   下面"次级别信号永不触发、全退化成 max_hold"是**错的**。30 只实测：
   坏对齐的出场分布 {1sell:104, max_hold:10} 与好对齐**完全一致**，
   104 笔差异全部是 exit_bar **恰好 +1 根**，**零笔**退化成 max_hold。
   真实后果是**晚一天卖出**（配对差 −2.37%，t=−2.15），不是"功能失效"。
   实测记录与更正后的牙齿见 scripts/verify_ml_sub_exit_fires.py。

⚠️ 本脚本**只做了"截断后逐位一致"这一半**，隐含假设是
   "只要有未来函数，截断结果一定会变"。这个假设**没在这里被验证**。

   我踩过一次（2026-10-10）：另一版 PIT 检查同时截断了日线和次级别数据，
   但**信号仍用全量注入**（`set_precomputed` 传全量序列）——30/30 全"一致"，
   因为信号根本没随数据截断，本来就不该变。那是**恒真的假检测**。

   ⇒ 要证明本检测不是恒真的，请跑 `scripts/verify_ml_pit_teeth.py`：
     它额外做了「注入已知未来函数必须被检出」+「截断内必须有实质配对」。
     只信本脚本的 '✅' 是不够的。

用法：  .venv/bin/python scripts/verify_ml_pit.py --limit 6
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from easy_tdx.backtest.engine import BacktestEngine  # noqa: E402
from easy_tdx.backtest.strategies.chanlun_ml import ChanlunMLStrategy  # noqa: E402

D = ROOT / "audit_data"
DM = ROOT / "audit_data_min"
SLIP = 0.002
PLAN = {"entry_types": "1buy,2buy,3buy", "exit_types": "1sell",
        "fallback_exit_types": "", "max_hold_bars": 120}


def _run(d: pd.DataFrame, s: pd.DataFrame) -> list[dict]:
    st = ChanlunMLStrategy(**PLAN)
    st.set_data(d, s)
    BacktestEngine(st, cash=100000.0, slippage=SLIP).run(d)
    return list(st.pair_log)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=6)
    ap.add_argument("--truncate", type=int, default=200, help="截断到前 N 根日线")
    a = ap.parse_args()

    codes = [p.name.split("_")[0] for p in sorted(DM.glob("*_30min.json"))]
    codes = [c for c in codes if c not in ("sh000300", "sh000001")][: a.limit]

    print(f"多级别 PIT 检测：{len(codes)} 只，截断到前 {a.truncate} 根日线\n")
    bad = 0
    for code in codes:
        d = pd.DataFrame(json.loads((D / f"{code}_daily.json").read_text()))
        d["datetime"] = pd.to_datetime(d["datetime"])
        s = pd.DataFrame(json.loads((DM / f"{code}_30min.json").read_text()))
        s["datetime"] = pd.to_datetime(s["datetime"])
        d = d[d["datetime"] >= s["datetime"].iloc[0]].reset_index(drop=True)
        if len(d) < a.truncate + 20:
            print(f"  {code}: 数据不足（{len(d)} 根），跳过")
            continue

        # 全量跑
        full = _run(d, s)
        # 截断跑
        d2 = d.iloc[: a.truncate].reset_index(drop=True)
        t_end = d2["datetime"].iloc[-1]
        s2 = s[s["datetime"] <= t_end].reset_index(drop=True)
        trunc = _run(d2, s2)

        # 只比较**截断范围内完成**的配对
        f_in = [p for p in full if p["exit_bar"] < a.truncate]
        same = (len(f_in) == len(trunc))
        if same:
            for x, y in zip(f_in, trunc):
                if (x["entry_type"], x["exit_type"], x["entry_bar"], x["exit_bar"]) != \
                   (y["entry_type"], y["exit_type"], y["entry_bar"], y["exit_bar"]):
                    same = False
                    break
        mark = "✅一致" if same else "❌不一致（有未来函数）"
        print(f"  {code}: 全量{len(full)}笔 截断内{len(f_in)}笔 vs 截断跑{len(trunc)}笔  {mark}")
        if not same:
            bad += 1
            print(f"      全量(截断内): {[(p['entry_type'], p['exit_type'], p['entry_bar'], p['exit_bar']) for p in f_in][:5]}")
            print(f"      截断跑:      {[(p['entry_type'], p['exit_type'], p['entry_bar'], p['exit_bar']) for p in trunc][:5]}")

    print()
    if bad:
        print(f"❌ {bad}/{len(codes)} 只不一致 ⇒ 多级别策略存在未来函数，结论不可信")
        return 1
    print(f"✅ 全部一致 ⇒ 未发现未来函数")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
