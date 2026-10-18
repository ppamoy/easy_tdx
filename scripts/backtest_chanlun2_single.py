#!/usr/bin/env python3
"""chanlun2 单股历史回测——输入股票代码，输出买卖信号+收益曲线。

用法：
  # 日线最优配置（趋势过滤+趋势持有+移动止损22%）
  .venv/bin/python scripts/backtest_chanlun2_single.py SH 600036

  # 30分钟级别
  .venv/bin/python scripts/backtest_chanlun2_single.py SZ 300750 --level 30min

  # 自定义止损率
  .venv/bin/python scripts/backtest_chanlun2_single.py SH 601318 --stop-pct 0.15

  # 基线（无优化，对比用）
  .venv/bin/python scripts/backtest_chanlun2_single.py SH 600036 --baseline

  # 显示买卖点明细
  .venv/bin/python scripts/backtest_chanlun2_single.py SZ 002415 --show-signals
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from easy_tdx.chanlun2.analyser import analyze
from easy_tdx.chanlun2.types import KLine, MMDType
from backtest_chanlun2_v3 import backtest_v3, load_klines, POSITION_TARGET


def main():
    ap = argparse.ArgumentParser(description="chanlun2 单股历史回测")
    ap.add_argument("market", choices=["SH", "SZ"], help="市场")
    ap.add_argument("code", help="股票代码，如 600036")
    ap.add_argument("--level", default="daily", choices=["daily", "30min"])
    ap.add_argument("--stop-pct", type=float, default=0.22, help="移动止损百分比(默认0.22=22pct)")
    ap.add_argument("--baseline", action="store_true", help="基线模式(无优化)")
    ap.add_argument("--show-signals", action="store_true", help="显示所有买卖点明细")
    a = ap.parse_args()

    klines = load_klines(a.market, a.code, a.level)
    if not klines:
        print(f"❌ 无数据: {a.market}{a.code} {a.level}")
        print(f"   日线数据在 audit_data/{a.market.lower()}{a.code}_daily.json")
        print(f"   30min数据在 audit_data_min/{a.market.lower()}{a.code}_30min.json")
        print(f"   如需拉取数据: .venv/bin/python scripts/fetch_minute_data.py --period 30")
        return

    if a.baseline:
        r = backtest_v3(klines)
        tag = "基线(无优化)"
    else:
        r = backtest_v3(klines, trend_filter=True, trend_hold=True,
                        trailing_stop=True, stop_pct=a.stop_pct)
        tag = f"趋势过滤+趋势持有+移动止损{a.stop_pct*100:.0f}%"

    # === 汇总 ===
    print(f"\n{'='*60}")
    print(f"  {a.market}{a.code} {a.level}级 {tag}")
    print(f"  数据: {r['bars']}根K线")
    print(f"{'='*60}")
    print(f"  策略收益:   {r['total_return']*100:>8.1f}%")
    print(f"  买入持有:   {r['buy_hold_return']*100:>8.1f}%")
    print(f"  超额收益:   {r['excess']*100:>8.1f}%")
    print(f"  最大回撤:   {r['max_drawdown']*100:>8.1f}%")
    print(f"  交易次数:   {r['trades']:>8}")
    print(f"  胜率:       {r['win_rate']*100:>7.0f}%")
    print(f"  信号总数:   {r['total_signals']:>8}")
    beaten = "✅跑赢" if r['total_return'] > r['buy_hold_return'] else "❌跑输"
    print(f"  vs买入持有: {beaten}")

    # === 买卖点明细 ===
    if a.show_signals or r['total_signals'] <= 20:
        # 重新跑一遍分析拿mmds
        norm_klines = klines
        base = klines[0].close if klines[0].close > 0 else 1.0
        nk = [KLine(i, k.dt, k.open/base, k.high/base, k.low/base, k.close/base, k.volume)
              for i, k in enumerate(klines)]
        result = analyze(nk, closes=[k.close/base for k in klines])
        mmds = sorted(result.mmds, key=lambda m: m.k_index)

        print(f"\n{'='*60}")
        print(f"  买卖点明细 ({len(mmds)}个)")
        print(f"{'='*60}")
        print(f"{'#':>3} {'类型':<14} {'日期':<18} {'价格':>10} {'方向':<6} {'说明'}")
        print("-" * 70)
        for m in mmds:
            raw_k = 0
            if 0 <= m.k_index < len(result.merged):
                rks = result.merged[m.k_index].raw_indices
                if rks: raw_k = rks[-1]
            price = klines[raw_k].close if 0 <= raw_k < len(klines) else 0
            dt = klines[raw_k].dt if 0 <= raw_k < len(klines) else "?"
            mtype = m.mmd_type.value
            direction = "↑" if m.direction.name == "UP" else "↓"
            print(f"{m.index:>3} {mtype:<14} {dt:<18} {price:>10.2f} {direction:<6} {m.note or ''}")

    # === 策略说明 ===
    if not a.baseline:
        print(f"\n{'='*60}")
        print("  策略说明")
        print(f"{'='*60}")
        print(f"  1. 趋势过滤: 只在周线MA10上行时买入（避免逆势）")
        print(f"  2. 趋势持有: 周线上行时忽略卖点信号（让利润奔跑）")
        print(f"  3. 移动止损: 跌破持仓峰值{a.stop_pct*100:.0f}%清仓（控制回撤）")
        print(f"  4. 分级仓位: 1买50%→2买80%→3买满仓；卖点分级减仓")
        print(f"\n  调参建议:")
        print(f"    --stop-pct 0.15  (更紧止损,回撤更小但可能被洗出)")
        print(f"    --stop-pct 0.25  (更宽止损,让趋势跑得更远)")
        print(f"    --baseline       (无优化对比)")
        print(f"    --show-signals   (显示买卖点明细)")


if __name__ == "__main__":
    main()
