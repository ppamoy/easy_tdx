#!/usr/bin/env python3
"""缠论偏差A 回归守卫：GG/DD 必须只遍历与中枢方向一致的 Z走势段(Zn)。

原文（第20课 line22，逐字）：
    「把这些与中枢方向一致的次级别走势类型称为 Z走势段，按中枢中的时间顺序，
     分别记为 Zn 等，而相应的高、低点分别记为 gn、dn，定义四个指标，
     GG=max(gn), G=min(gn), D=max(dn), DD=min(dn)，n遍历中枢中所有Zn。」

第30课 line142（缠师回帖）：「一样有方向，例如从高位下来形成的，方向就是下上下」

故：
  - 中枢方向 = 首笔方向（30课L142）
  - Zn = 与中枢方向一致的同向段（A/C/E…），反向段（B/D…）不参与 GG/DD
  - GG = max(gn over Zn)，DD = min(dn over Zn)

本守卫用固定 fixture 锁定该口径。若有人回退为「遍历全部笔含反向段」，
GG 会被反向段抬高、DD 会被反向段压低，本脚本 exit 1。

历史：偏差A 曾因「破坏3+测试」被长期搁置（zs.py:334-339 旧注释）。
2026(V856) 修复：同向段过滤 + direction 字段。本守卫防止再次回退。

用法：
    python scripts/guard_chanlun_ggdd_zn_filter.py
    exit 0 = 口径正确；exit 1 = 偏差A 回归（GG/DD 又遍历了反向段）
"""
from __future__ import annotations

import sys
from datetime import datetime

from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.types import BI, CLKline, Direction, FX, FXType
from easy_tdx.chanlun.zs import find_zss


def _fx(fx_type: FXType, val: float, bar: int) -> FX:
    k = CLKline(
        k_index=bar, date=datetime(2020, 1, 1),
        open=0.0, close=0.0, high=0.0, low=0.0, amount=0.0, index=bar,
    )
    return FX(fx_type=fx_type, k=k, klines=[k], val=val, index=bar, done=True, bar_index=bar)


def _bi(index: int, direction: str, start_val: float, end_val: float,
        high: float, low: float) -> BI:
    d = Direction.UP if direction == "up" else Direction.DOWN
    s = _fx(FXType.DI if direction == "up" else FXType.DING, start_val, index * 10)
    e = _fx(FXType.DING if direction == "up" else FXType.DI, end_val, index * 10 + 5)
    return BI(start=s, end=e, direction=d, index=index, high=high, low=low)


def main() -> int:
    # fixture：与 test_chanlun_zs_extension 同构
    # bi0(A,up)[14,10] bi1(B,down)[13,11] bi2(C,up)[12,9] bi3(D,down)[15,8]
    # 中枢方向=up(首笔)；同向段 Zn = A(bi0)、C(bi2)；反向段 B(bi1)、D(bi3)
    bis = [
        _bi(0, "up", 10.0, 14.0, 14.0, 10.0),
        _bi(1, "down", 14.0, 12.0, 13.0, 11.0),
        _bi(2, "up", 12.0, 13.0, 12.0, 9.0),
        _bi(3, "down", 13.0, 10.0, 15.0, 8.0),
    ]
    zss = find_zss(bis, ChanlunConfig())
    assert len(zss) == 1, f"应产出1个中枢，实际 {len(zss)}"
    zs = zss[0]

    failures: list[str] = []

    # 1. 中枢方向 = 首笔方向 = up（30课L142）
    if zs.direction != "up":
        failures.append(
            f"direction={zs.direction!r} 应为 'up'（30课L142 中枢方向=首笔方向）"
        )

    # 2. GG = 同向段 max(gn) = max(A.high=14, C.high=12) = 14（20课L22 遍历Zn）
    #    旧偏差：遍历全笔得 15（来自反向段 D bi3），被本守卫抓出
    if zs.gg != 14.0:
        failures.append(
            f"gg={zs.gg} 应为 14.0（20课L22: GG=max(gn)只遍历同向段Zn=A,C=max(14,12)）；"
            f"若 gg=15.0 说明又遍历了反向段D(bi3.high=15)——偏差A回退！"
        )

    # 3. DD = 同向段 min(dn) = min(A.low=10, C.low=9) = 9（20课L22 遍历Zn）
    #    旧偏差：遍历全笔得 8（来自反向段 D bi3），被本守卫抓出
    if zs.dd != 9.0:
        failures.append(
            f"dd={zs.dd} 应为 9.0（20课L22: DD=min(dn)只遍历同向段Zn=A,C=min(10,9)）；"
            f"若 dd=8.0 说明又遍历了反向段D(bi3.low=8)——偏差A回退！"
        )

    # 4. 不变量仍成立（GG>=ZG, DD<=ZD）——同向段过滤不应破坏
    if not (zs.gg >= zs.zg):
        failures.append(f"不变量破坏: gg={zs.gg} < zg={zs.zg}")
    if not (zs.dd <= zs.zd):
        failures.append(f"不变量破坏: dd={zs.dd} > zd={zs.zd}")

    # 5. ZG/ZD 仍由 A/C 两段定（不受 GG/DD 改动影响）
    if zs.zg != 12.0:
        failures.append(f"zg={zs.zg} 应为 12.0（min(A.high=14,C.high=12)）")
    if zs.zd != 10.0:
        failures.append(f"zd={zs.zd} 应为 10.0（max(A.low=10,C.low=9)）")

    if failures:
        print("❌ 偏差A 回归守卫失败：GG/DD 同向段过滤被破坏！", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        print("原文依据：第20课L22「GG=max(gn)，n遍历中枢中所有Zn，"
              "Zn=与中枢方向一致的次级别走势类型」；第30课L142「一样有方向」",
              file=sys.stderr)
        return 1

    print("✅ 偏差A 回归守卫通过：GG/DD 只遍历同向段 Zn，direction 已赋值。")
    print(f"   zs: direction={zs.direction} zg={zs.zg} zd={zs.zd} "
          f"gg={zs.gg}(同向段max) dd={zs.dd}(同向段min)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
