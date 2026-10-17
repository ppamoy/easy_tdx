"""探针2：验证修复方向——离开段=破中枢边沿的第一根同向笔。

对比旧版(_find_leaving_bi,第一根同向笔) vs 修复版(第一根破边沿的同向笔)，
看锚定命中+趋势背驰产出是否提升。
"""
import asyncio
from collections import Counter
from easy_tdx.chanlun import ChanlunAnalyser
from easy_tdx.chanlun.mmd_conditions import _find_leaving_bi, _calc_bi_force
from easy_tdx.mac.client import AsyncMacClient
from easy_tdx.web.klines import fetch_qfq_klines


def _find_leaving_bi_fixed(bis, zs, direction):
    """修复版：离开段=中枢之后第一根破边沿的同向笔（真离开，非中枢内震荡）。"""
    if not zs.lines:
        return -1
    start = zs.lines[-1].index + 1
    edge = zs.zd if direction == "down" else zs.zg
    for i in range(start, len(bis)):
        if bis[i].direction.value != direction:
            continue
        # 破边沿才算真离开段（向下破zd / 向上破zg）
        if direction == "down" and bis[i].low < edge:
            return i
        if direction == "up" and bis[i].high > edge:
            return i
    return -1


async def run():
    mc = AsyncMacClient.from_best_host()
    await mc.connect()
    df = await fetch_qfq_klines(mc, None, "SH", "600519", "MIN_30", 0, 600)
    res = ChanlunAnalyser(code="600519", frequency="30min").process_klines(df)
    bis, zss = res.bis, res.zss
    closes = list(df["close"])
    print(f"笔 {len(bis)} / 中枢 {len(zss)}")
    direction = "down"
    threshold = 0.8

    def count_hits(finder, label):
        anchor_match = force_hits = 0
        for bi_idx, bi in enumerate(bis):
            if bi.direction.value != direction:
                continue
            for i in range(1, len(zss)):
                prev_zs, curr_zs = zss[i - 1], zss[i]
                if not (curr_zs.zg < prev_zs.zg and curr_zs.zd < prev_zs.zd):
                    continue
                if not prev_zs.lines or not curr_zs.lines:
                    continue
                prev_exit_idx = finder(bis, prev_zs, direction)
                curr_exit_idx = finder(bis, curr_zs, direction)
                if prev_exit_idx < 0 or curr_exit_idx < 0:
                    continue
                if curr_exit_idx != bi_idx:
                    continue
                anchor_match += 1
                curr_exit, prev_exit = bis[curr_exit_idx], bis[prev_exit_idx]
                if prev_exit.direction.value != direction or curr_exit.direction.value != direction:
                    continue
                if not (curr_exit.low < prev_exit.low):
                    continue
                pf = _calc_bi_force(prev_exit, closes, prev_exit.index, True)
                cf = _calc_bi_force(curr_exit, closes, curr_exit.index, True)
                if cf < pf * threshold and cf > 0:
                    force_hits += 1
        print(f"  {label}: 锚定命中={anchor_match} 力度衰减命中(趋势背驰)={force_hits}")
        return force_hits

    print("\n对比（茅台30min, 全down笔候选）:")
    old = count_hits(_find_leaving_bi, "旧版(第一根同向笔)")
    new = count_hits(_find_leaving_bi_fixed, "修复版(第一根破边沿同向笔)")
    print(f"\n趋势背驰产出: 旧={old} 修复={new}")
    await mc.close()


asyncio.run(run())
