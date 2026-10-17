"""探针：实测趋势背驰分支为何0命中（§3 先验证再下结论）。

对茅台30min每个down笔候选，跑趋势背驰分支逻辑，记录锚定为何失败。
"""
import asyncio
from collections import Counter
from easy_tdx.chanlun import ChanlunAnalyser
from easy_tdx.chanlun.mmd_conditions import _find_leaving_bi
from easy_tdx.mac.client import AsyncMacClient
from easy_tdx.web.klines import fetch_qfq_klines


async def run():
    mc = AsyncMacClient.from_best_host()
    await mc.connect()
    df = await fetch_qfq_klines(mc, None, "SH", "600519", "MIN_30", 0, 600)
    print(f"30min K线 {len(df)} 根")
    res = ChanlunAnalyser(code="600519", frequency="30min").process_klines(df)
    bis = res.bis
    zss = res.zss
    closes = list(df["close"])
    print(f"笔 {len(bis)} / 中枢 {len(zss)}")

    direction = "down"
    fail_reasons = Counter()
    pair_examples = []
    cand_count = 0
    anchor_match = 0

    for bi_idx, bi in enumerate(bis):
        if bi.direction.value != "down":
            continue
        cand_count += 1
        if len(zss) < 2:
            continue
        for i in range(1, len(zss)):
            prev_zs, curr_zs = zss[i - 1], zss[i]
            if not (curr_zs.zg < prev_zs.zg and curr_zs.zd < prev_zs.zd):
                continue
            if not prev_zs.lines or not curr_zs.lines:
                fail_reasons["empty_lines"] += 1
                continue
            prev_exit_idx = _find_leaving_bi(bis, prev_zs, direction)
            curr_exit_idx = _find_leaving_bi(bis, curr_zs, direction)
            if prev_exit_idx < 0 or curr_exit_idx < 0:
                fail_reasons["no_leaving"] += 1
                continue
            if curr_exit_idx != bi_idx:
                fail_reasons["anchor_mismatch"] += 1
                if len(pair_examples) < 10:
                    ce = bis[curr_exit_idx]
                    pair_examples.append(
                        f"  cand#{bi_idx}(low={bi.low:.1f},破zd={bi.low<curr_zs.zd}) "
                        f"!= leaving#{curr_exit_idx}(low={ce.low:.1f},破zd={ce.low<curr_zs.zd}) "
                        f"zs#{curr_zs.index}(zd={curr_zs.zd:.1f})"
                    )
                continue
            anchor_match += 1
            curr_exit = bis[curr_exit_idx]
            prev_exit = bis[prev_exit_idx]
            if prev_exit.direction.value != direction or curr_exit.direction.value != direction:
                fail_reasons["dir_mismatch"] += 1
                continue
            new_extreme = curr_exit.low < prev_exit.low
            if not new_extreme:
                fail_reasons["no_new_extreme"] += 1
                continue
            fail_reasons["reached_force_check"] += 1

    print(f"\ndown笔候选: {cand_count}")
    print(f"锚定命中(curr_exit_idx==bi_idx): {anchor_match}")
    print(f"\n失败原因统计:")
    for r, c in fail_reasons.most_common():
        print(f"  {r}: {c}")
    print(f"\n锚定失配样例(前10)——看 leaving笔 是否破zd:")
    for e in pair_examples:
        print(e)
    await mc.close()


asyncio.run(run())
