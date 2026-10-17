"""调试：教科书两中枢下跌+背驰为何趋势背驰不触发。"""
import sys
sys.path.insert(0, "tests/unit")
from test_chanlun_textbook_fidelity import _build, _run, _bis, _zss, _types, _1BUY_BASE, _1BUY_NS
from easy_tdx.chanlun.mmd_conditions import _find_leaving_bi, _calc_bi_force

res = _run(_build(_1BUY_BASE + [11], _1BUY_NS + [4]))
print("信号:", _types(res))
print("笔:", _bis(res))
print("中枢:", _zss(res))

bis = res.bis
zss = res.zss
closes = [k.close for k in res.klines]
direction = "down"
threshold = 0.8

print(f"\n=== 趋势背驰分支追踪（{len(zss)} 中枢）===")
for i in range(1, len(zss)):
    prev_zs, curr_zs = zss[i-1], zss[i]
    same = (curr_zs.zg < prev_zs.zg and curr_zs.zd < prev_zs.zd)
    print(f"\n对#{i}: prev_zs zg={prev_zs.zg} zd={prev_zs.zd} | curr_zs zg={curr_zs.zg} zd={curr_zs.zd} | 同向下跌={same}")
    if not same:
        continue
    prev_exit_idx = _find_leaving_bi(bis, prev_zs, direction)
    curr_exit_idx = _find_leaving_bi(bis, curr_zs, direction)
    print(f"  prev_exit_idx={prev_exit_idx} curr_exit_idx={curr_exit_idx}")
    if prev_exit_idx < 0 or curr_exit_idx < 0:
        print("  → 无离开段")
        continue
    prev_exit, curr_exit = bis[prev_exit_idx], bis[curr_exit_idx]
    print(f"  prev_exit: dir={prev_exit.direction.value} low={prev_exit.low} high={prev_exit.high}")
    print(f"  curr_exit: dir={curr_exit.direction.value} low={curr_exit.low} high={curr_exit.high}")
    print(f"  方向一致? prev={prev_exit.direction.value==direction} curr={curr_exit.direction.value==direction}")
    new_extreme = curr_exit.low < prev_exit.low
    print(f"  新极值? curr.low({curr_exit.low}) < prev.low({prev_exit.low}) = {new_extreme}")
    pf = _calc_bi_force(prev_exit, closes, prev_exit.index, False)
    cf = _calc_bi_force(curr_exit, closes, curr_exit.index, False)
    print(f"  力度: prev={pf:.4f} curr={cf:.4f} 衰减?(curr<pf*{threshold})={cf < pf*threshold} curr>0={cf>0}")
    print(f"  → 趋势背驰命中? {new_extreme and cf < pf*threshold and cf > 0}")

# 也看每个候选bi
print("\n=== 所有down笔候选 ===")
for bi_idx, bi in enumerate(bis):
    if bi.direction.value != "down":
        continue
    print(f"  bi#{bi_idx} low={bi.low} → 是某curr_zs离开段? ", end="")
    for zs in zss:
        le = _find_leaving_bi(bis, zs, direction)
        if le == bi_idx:
            print(f"是(zs#{zs.index}离开段)")
            break
    else:
        print("否")
