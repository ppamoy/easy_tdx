"""线段级别买卖点检测。

参考 chan.py (Vespa314/chan.py) 的 CBSPointList 实现，
在**线段（走势类型）末端**检测买卖点，而非在每根笔末端。

买卖点类型对应关系：
  T1  (背驰一类)     → BUY_1 / SELL_1
  T1P (盘整背驰一类) → BUY_1 / SELL_1  (同类型，但使用盘整背驰逻辑)
  T2  (回踩二类)     → BUY_2 / SELL_2
  T2S (类二)         → BUY_2S / SELL_2S
  T3A (突破后不回)   → BUY_3 / SELL_3
  T3B (突破前)       → BUY_3 / SELL_3

核心逻辑（chan.py 对齐）：
  1. 中枢用笔构（ zs_from_xd=False 口径），但买卖点在线段末端判定
  2. 一类买卖点：线段末端，最后一个中枢的离开笔与进入笔 MACD 背驰
  3. 盘整一类：无多笔中枢时，最后两根同向笔 MACD 背驰
  4. 二类买卖点：一类后第一根反向笔，回踩幅度 ≤ max_bs2_rate
  5. 类二：二类后连续重叠的同向笔
  6. 三类买卖点(A)：下一线段首个中枢被突破后不回
  7. 三类买卖点(B)：当前线段最后一个中枢被突破
"""

from __future__ import annotations

from typing import Any

from easy_tdx.chanlun.types import (
    BI,
    XD,
    Direction,
    MMD,
    MMDType,
    ZS,
)


# ── 辅助函数 ────────────────────────────────────────────────────────────


def _bi_kindex(bi: BI | XD) -> int:
    """获取笔/线段结束分型的 k_index（DataFrame 行索引）。"""
    k = getattr(bi.end, "k", None)
    if k is not None:
        return int(getattr(k, "k_index", getattr(k, "index", 0)))
    return int(getattr(bi.end, "bar_index", 0))


def _bi_start_kindex(bi: BI | XD) -> int:
    """获取笔/线段起始分型的 k_index。"""
    k = getattr(bi.start, "k", None)
    if k is not None:
        return int(getattr(k, "k_index", getattr(k, "index", 0)))
    return int(getattr(bi.start, "bar_index", 0))


def _bi_high(bi: BI | XD) -> float:
    return bi.high


def _bi_low(bi: BI | XD) -> float:
    return bi.low


def _bi_amp(bi: BI | XD) -> float:
    """笔的振幅。"""
    h = _bi_high(bi)
    l = _bi_low(bi)
    return abs(h - l) if h > 0 and l > 0 else 0.0


def _bi_end_val(bi: BI | XD) -> float:
    """笔末端分型的值。"""
    return bi.end.val


def _has_overlap(a_low: float, a_high: float, b_low: float, b_high: float) -> bool:
    """两个区间是否重叠。"""
    return min(a_high, b_high) > max(a_low, b_low)


def _map_zs_to_seg(zss: list[ZS], xds: list[XD], bis: list[BI]) -> dict[int, list[ZS]]:
    """将中枢映射到线段：返回 {xd_index: [zs1, zs2, ...]}。

    用中枢第一根笔的 k_index 找到它在 bis 中的位置，
    再找该 bi 落在哪个线段的笔范围内。
    """
    if not xds or not bis:
        return {}

    # 为每根笔计算 start/end k_index
    bi_start = [_bi_start_kindex(bi) for bi in bis]
    bi_end = [_bi_kindex(bi) for bi in bis]

    # 线段的 k_index 范围
    seg_ranges: list[tuple[int, int]] = []
    for xd in xds:
        s = _bi_start_kindex(xd)
        e = _bi_kindex(xd)
        seg_ranges.append((s, e))

    # 构建 bi k_index → 线段 index 的映射
    # 一根笔属于哪个线段？笔的 start k_index 落在线段范围内 → 属于该线段
    bi_to_seg: dict[int, int] = {}  # bi_index → seg_index
    for bi_i, bi in enumerate(bis):
        bi_s = bi_start[bi_i]
        for si, (seg_s, seg_e) in enumerate(seg_ranges):
            if seg_s <= bi_s <= seg_e:
                bi_to_seg[bi.index] = si
                break

    result: dict[int, list[ZS]] = {i: [] for i in range(len(xds))}

    for zs in zss:
        # 用中枢第一根线（笔）来归属
        first_line = zs.lines[0] if zs.lines else None
        if first_line is None:
            continue
        seg_idx = bi_to_seg.get(first_line.index)
        if seg_idx is None:
            # fallback: 用 enter_bi
            if zs.enter_bi is not None:
                seg_idx = bi_to_seg.get(zs.enter_bi.index)
        if seg_idx is not None:
            result[seg_idx].append(zs)

    return result


def _macd_area(macd_data: dict, kstart: int, kend: int) -> float:
    """计算 [kstart, kend] 区间内 MACD 柱状图面积（取绝对值之和）。"""
    hist = macd_data.get("hist", [])
    if not hist:
        return 0.0
    s = max(0, min(kstart, kend))
    e = min(len(hist), max(kstart, kend) + 1)
    return sum(abs(hist[i]) for i in range(s, e))


def _macd_peak(macd_data: dict, kstart: int, kend: int, is_up: bool) -> float:
    """计算 [kstart, kend] 区间内 MACD 柱状图峰值。
    is_up=True 取最大正值，is_up=False 取最小负值（绝对值）。"""
    hist = macd_data.get("hist", [])
    if not hist:
        return 0.0
    s = max(0, min(kstart, kend))
    e = min(len(hist), max(kstart, kend) + 1)
    vals = [hist[i] for i in range(s, e)]
    if not vals:
        return 0.0
    if is_up:
        return max(vals)
    else:
        return abs(min(vals))


# ── 一类买卖点 ──────────────────────────────────────────────────────────


def _detect_t1(
    xds: list[XD],
    bis: list[BI],
    seg_zss: dict[int, list[ZS]],
    macd_data: dict,
    config: Any,
) -> list[MMD]:
    """检测一类买卖点（含背驰一类 T1 和盘整背驰一类 T1P）。

    chan.py 逻辑：
    - 如果线段有中枢且最后一个中枢非一笔中枢：
      检查 exit_bi 与 enter_bi 的 MACD 背驰 → T1
    - 否则（盘整）：
      检查最后两根同向笔的 MACD 背驰 → T1P
    """
    mmds: list[MMD] = []
    if not xds or not bis:
        return mmds

    divergence_rate = getattr(config, "divergence_rate", 0.8)
    min_zs_cnt = getattr(config, "seg_min_zs_cnt", 1)
    bsp1_only_multibi = getattr(config, "bsp1_only_multibi_zs", True)
    bs1_peak = getattr(config, "bs1_peak", True)
    macd_algo = getattr(config, "seg_macd_algo", "peak")

    # 构建 bi.index → 在 bis 中的位置 映射
    bi_idx_map: dict[int, int] = {}
    for i, bi in enumerate(bis):
        bi_idx_map[bi.index] = i

    for si, xd in enumerate(xds):
        zs_lst = seg_zss.get(si, [])

        # 统计多笔中枢数（排除一笔中枢）
        multi_bi_zss = [z for z in zs_lst if len(z.lines) >= 2]
        zs_cnt = len(multi_bi_zss) if bsp1_only_multibi else len(zs_lst)

        # min_zs_cnt 检查
        is_target = min_zs_cnt <= 0 or zs_cnt >= min_zs_cnt

        # 找到线段末端对应的笔
        xd_end_baridx = _bi_kindex(xd)
        # 在 bis 中找到 end 对应的笔
        end_bi_pos = -1
        for i, bi in enumerate(bis):
            if _bi_kindex(bi) == xd_end_baridx:
                end_bi_pos = i
                break
        if end_bi_pos < 0:
            continue
        end_bi = bis[end_bi_pos]

        is_down = xd.direction == Direction.DOWN
        # 买点 = 下跌线段结束（向下线段最后一笔是向下，end_bi 是底分型）
        # 卖点 = 上涨线段结束

        if multi_bi_zss and multi_bi_zss[-1].exit_bi is not None:
            # ── T1: 趋势背驰 ──
            last_zs = multi_bi_zss[-1]
            enter_bi = last_zs.enter_bi
            exit_bi = last_zs.exit_bi
            if enter_bi is None or exit_bi is None:
                continue

            enter_ks = _bi_start_kindex(enter_bi)
            enter_ke = _bi_kindex(enter_bi)
            exit_ks = _bi_start_kindex(exit_bi)
            exit_ke = _bi_kindex(exit_bi)

            if macd_algo == "area":
                in_metric = _macd_area(macd_data, enter_ks, enter_ke)
                out_metric = _macd_area(macd_data, exit_ks, exit_ke)
            else:  # peak
                in_metric = _macd_peak(macd_data, enter_ks, enter_ke, not is_down)
                out_metric = _macd_peak(macd_data, exit_ks, exit_ke, not is_down)

            is_diver = out_metric <= divergence_rate * (in_metric + 1e-7)
            if not is_diver:
                is_target = False

            # bs1_peak: exit_bi 必须创新极值
            if bs1_peak:
                if is_down:
                    # 买点：exit_bi 的 low 应 <= enter_bi 的 low（创新低）
                    if exit_bi.low > enter_bi.low:
                        is_target = False
                else:
                    # 卖点：exit_bi 的 high 应 >= enter_bi 的 high（创新高）
                    if exit_bi.high < enter_bi.high:
                        is_target = False

            mmd_type = MMDType.BUY_1 if is_down else MMDType.SELL_1
            mmd = MMD(
                mmd_type=mmd_type,
                zs=last_zs,
                bi=end_bi,
                msg=f"T1 趋势背驰 diver_rate={out_metric/(in_metric+1e-7):.3f}",
                confidence=max(0.0, min(1.0, out_metric / (in_metric + 1e-7))) if in_metric > 0 else 0.5,
            )
            if is_target:
                mmds.append(mmd)
        else:
            # ── T1P: 盘整背驰 ──
            # 无多笔中枢，检查最后两根同向笔
            if end_bi_pos < 2:
                continue
            last_bi = bis[end_bi_pos]
            pre_bi = bis[end_bi_pos - 2]

            # 同向检查
            if last_bi.direction != pre_bi.direction:
                continue
            if last_bi.direction != xd.direction:
                continue

            # 创新极值检查
            if is_down:
                if last_bi.low > pre_bi.low:
                    continue
            else:
                if last_bi.high < pre_bi.high:
                    continue

            last_ks = _bi_start_kindex(last_bi)
            last_ke = _bi_kindex(last_bi)
            pre_ks = _bi_start_kindex(pre_bi)
            pre_ke = _bi_kindex(pre_bi)

            if macd_algo == "area":
                in_metric = _macd_area(macd_data, pre_ks, pre_ke)
                out_metric = _macd_area(macd_data, last_ks, last_ke)
            else:
                in_metric = _macd_peak(macd_data, pre_ks, pre_ke, not is_down)
                out_metric = _macd_peak(macd_data, last_ks, last_ke, not is_down)

            is_diver = out_metric <= divergence_rate * (in_metric + 1e-7)
            if not is_diver:
                is_target = False

            mmd_type = MMDType.BUY_1 if is_down else MMDType.SELL_1
            mmd = MMD(
                mmd_type=mmd_type,
                zs=zs_lst[-1] if zs_lst else None,
                bi=last_bi,
                msg=f"T1P 盘整背驰 diver_rate={out_metric/(in_metric+1e-7):.3f}",
                confidence=max(0.0, min(1.0, out_metric / (in_metric + 1e-7))) if in_metric > 0 else 0.5,
            )
            if is_target:
                mmds.append(mmd)

    return mmds


# ── 二类买卖点 ──────────────────────────────────────────────────────────


def _detect_t2(
    xds: list[XD],
    bis: list[BI],
    t1_mmds: list[MMD],
    config: Any,
) -> list[MMD]:
    """检测二类买卖点。

    chan.py 逻辑：
    - 一类买卖点后，第一根反向笔（break_bi）+ 第二根同向笔（bsp2_bi）
    - bsp2_bi 的回踩幅度 ≤ max_bs2_rate
    """
    mmds: list[MMD] = []
    if not t1_mmds or not bis:
        return mmds

    # 101课原文口径：mmd_2nd_max_pullback=None 时无门槛（总出2buy）
    mmd_2nd_max_pullback = getattr(config, "mmd_2nd_max_pullback", None)
    max_bs2_rate = getattr(config, "max_bs2_rate", 0.8)
    bsp2_follow_1 = getattr(config, "bsp2_follow_1", True)

    # bi.index → position
    bi_idx_map: dict[int, int] = {}
    for i, bi in enumerate(bis):
        bi_idx_map[bi.index] = i

    for t1 in t1_mmds:
        if t1.bi is None:
            continue
        bsp1_pos = bi_idx_map.get(t1.bi.index, -1)
        if bsp1_pos < 0 or bsp1_pos + 2 >= len(bis):
            continue

        break_bi = bis[bsp1_pos + 1]
        bsp2_bi = bis[bsp1_pos + 2]

        # bsp2_follow_1: 二类必须跟随一类
        if bsp2_follow_1 and t1.bi.index not in bi_idx_map:
            continue

        # 回踩幅度
        break_amp = _bi_amp(break_bi)
        if break_amp <= 0:
            continue
        retrace_rate = _bi_amp(bsp2_bi) / break_amp

        # 101课原文：None=无门槛（总出2buy）；有门槛时 retrace<=门槛才出
        if mmd_2nd_max_pullback is None or retrace_rate <= mmd_2nd_max_pullback:
            is_buy = t1.mmd_type == MMDType.BUY_1
            mmd_type = MMDType.BUY_2 if is_buy else MMDType.SELL_2
            mmd = MMD(
                mmd_type=mmd_type,
                zs=t1.zs,
                bi=bsp2_bi,
                msg=f"T2 回踩 retrace={retrace_rate:.3f}",
                confidence=max(0.0, 1.0 - retrace_rate),
            )
            mmds.append(mmd)

    return mmds


def _detect_t2s(
    xds: list[XD],
    bis: list[BI],
    t2_mmds: list[MMD],
    config: Any,
) -> list[MMD]:
    """检测类二买卖点（T2S）。

    chan.py 逻辑：
    - 二类后，连续同向笔与二类笔重叠
    - 每根重叠的同向笔都是类二
    """
    mmds: list[MMD] = []
    if not t2_mmds or not bis:
        return mmds

    mmd_2nd_max_pullback = getattr(config, "mmd_2nd_max_pullback", None)
    max_bs2_rate = getattr(config, "max_bs2_rate", 0.8)
    max_bsp2s_lv = getattr(config, "max_bsp2s_lv", None)

    bi_idx_map: dict[int, int] = {}
    for i, bi in enumerate(bis):
        bi_idx_map[bi.index] = i

    for t2 in t2_mmds:
        if t2.bi is None:
            continue
        bsp2_pos = bi_idx_map.get(t2.bi.index, -1)
        if bsp2_pos < 0:
            continue

        break_bi = bis[bsp2_pos - 1] if bsp2_pos >= 1 else None
        if break_bi is None:
            continue

        bias = 2
        _low, _high = None, None

        while bsp2_pos + bias < len(bis):
            bsp2s_bi = bis[bsp2_pos + bias]

            if max_bsp2s_lv is not None and bias // 2 > max_bsp2s_lv:
                break

            if bias == 2:
                if not _has_overlap(
                    _bi_low(t2.bi), _bi_high(t2.bi),
                    _bi_low(bsp2s_bi), _bi_high(bsp2s_bi),
                ):
                    break
                _low = max(_bi_low(t2.bi), _bi_low(bsp2s_bi))
                _high = min(_bi_high(t2.bi), _bi_high(bsp2s_bi))
            elif not _has_overlap(_low, _high, _bi_low(bsp2s_bi), _bi_high(bsp2s_bi)):
                break

            # 类二不能突破一类
            is_buy = t2.mmd_type == MMDType.BUY_2
            if is_buy and bsp2s_bi.low < break_bi.low:
                break
            if not is_buy and bsp2s_bi.high > break_bi.high:
                break

            retrace_rate = abs(_bi_end_val(bsp2s_bi) - _bi_end_val(break_bi)) / _bi_amp(break_bi)
            # 101课原文：None=无门槛（不因回撤 break）；有门槛时 retrace>门槛 break
            if mmd_2nd_max_pullback is not None and retrace_rate > mmd_2nd_max_pullback:
                break

            mmd_type = MMDType.BUY_2S if is_buy else MMDType.SELL_2S
            mmd = MMD(
                mmd_type=mmd_type,
                zs=t2.zs,
                bi=bsp2s_bi,
                msg=f"T2S 类二 lv={bias // 2} retrace={retrace_rate:.3f}",
                confidence=max(0.0, 1.0 - retrace_rate * 0.5),
            )
            mmds.append(mmd)
            bias += 2

    return mmds


# ── 三类买卖点 ──────────────────────────────────────────────────────────


def _detect_t3(
    xds: list[XD],
    bis: list[BI],
    seg_zss: dict[int, list[ZS]],
    t1_mmds: list[MMD],
    config: Any,
) -> list[MMD]:
    """检测三类买卖点（T3A 突破后不回 + T3B 突破前）。

    chan.py 逻辑：
    - T3A: 下一线段首个中枢被突破后不回中枢区间
    - T3B: 当前线段最后一个中枢被突破
    """
    mmds: list[MMD] = []
    if not xds or not bis:
        return mmds

    bsp3_follow_1 = getattr(config, "bsp3_follow_1", True)
    strict_bsp3 = getattr(config, "strict_bsp3", False)
    bsp3_peak = getattr(config, "bsp3_peak", False)
    bsp3a_max_zs_cnt = getattr(config, "bsp3a_max_zs_cnt", 1)

    bi_idx_map: dict[int, int] = {}
    for i, bi in enumerate(bis):
        bi_idx_map[bi.index] = i

    # T1 对应的 bi.index 集合
    t1_bi_indices = {t.bi.index for t in t1_mmds if t.bi is not None}

    for si, xd in enumerate(xds):
        zs_lst = [z for z in seg_zss.get(si, []) if len(z.lines) >= 2]
        if not zs_lst:
            continue

        is_down = xd.direction == Direction.DOWN
        # bsp1_bi = 线段末端笔
        xd_end_baridx = _bi_kindex(xd)
        bsp1_pos = -1
        for i, bi in enumerate(bis):
            if _bi_kindex(bi) == xd_end_baridx:
                bsp1_pos = i
                break
        if bsp1_pos < 0:
            continue
        bsp1_bi = bis[bsp1_pos]

        # bsp3_follow_1: 三类必须跟随一类
        if bsp3_follow_1 and bsp1_bi.index not in t1_bi_indices:
            continue

        # ── T3A: 下一线段首个中枢突破后不回 ──
        next_si = si + 1
        if next_si < len(xds):
            next_zss = [z for z in seg_zss.get(next_si, []) if len(z.lines) >= 2]
            if next_zss:
                for zs_idx, zs in enumerate(next_zss):
                    if zs_idx >= bsp3a_max_zs_cnt:
                        break
                    if zs.exit_bi is None:
                        continue
                    exit_pos = bi_idx_map.get(zs.exit_bi.index, -1)
                    if exit_pos < 0 or exit_pos + 1 >= len(bis):
                        break
                    bsp3_bi = bis[exit_pos + 1]

                    # 方向：下跌线段→1buy→T3buy（反弹不回中枢）, 上涨线段→1sell→T3sell
                    is_buy = is_down
                    if is_buy:
                        # 三买：bsp3_bi low > zs.zg（不回中枢上沿以下）
                        if bsp3_bi.low < zs.zg:
                            continue
                    else:
                        # 三卖：bsp3_bi high < zs.zd（不回中枢下沿以上）
                        if bsp3_bi.high > zs.zd:
                            continue

                    # bsp3_peak 检查
                    if bsp3_peak:
                        if is_buy and bsp3_bi.low > zs.dd:
                            continue
                        if not is_buy and bsp3_bi.high < zs.gg:
                            continue

                    mmd_type = MMDType.BUY_3 if is_buy else MMDType.SELL_3
                    mmd = MMD(
                        mmd_type=mmd_type,
                        zs=zs,
                        bi=bsp3_bi,
                        msg=f"T3A 突破后不回 zs_idx={zs_idx}",
                        confidence=0.6,
                    )
                    mmds.append(mmd)

        # ── T3B: 当前线段最后中枢突破 ──
        if not bsp3_follow_1 or bsp1_bi.index in t1_bi_indices:
            last_zs = zs_lst[-1]
            if last_zs.exit_bi is not None:
                exit_pos = bi_idx_map.get(last_zs.exit_bi.index, -1)
                if exit_pos >= 0 and exit_pos + 2 < len(bis):
                    # 在 bsp1_bi 之后找突破笔
                    for bsp3_pos in range(bsp1_pos + 2, len(bis), 2):
                        if bsp3_pos > exit_pos + 2:
                            break
                        bsp3_bi = bis[bsp3_pos]
                        # 方向：下跌线段→T3buy, 上涨线段→T3sell
                        is_buy = is_down

                        # 不能回到中枢区间
                        if is_buy:
                            if bsp3_bi.low < last_zs.zg:
                                continue
                        else:
                            if bsp3_bi.high > last_zs.zd:
                                continue

                        mmd_type = MMDType.BUY_3 if is_buy else MMDType.SELL_3
                        mmd = MMD(
                            mmd_type=mmd_type,
                            zs=last_zs,
                            bi=bsp3_bi,
                            msg="T3B 突破前中枢",
                            confidence=0.5,
                        )
                        mmds.append(mmd)
                        break

    return mmds


# ── 主入口 ──────────────────────────────────────────────────────────────


def find_mmds_seg(
    bis: list[BI],
    xds: list[XD],
    zss: list[ZS],
    closes: list[float] | None = None,
    config: Any = None,
    macd_data: dict[str, list[float]] | None = None,
) -> list[MMD]:
    """线段级别买卖点检测。

    参考 chan.py 的 CBSPointList，在**线段（走势类型）末端**检测买卖点。

    Args:
        bis: 笔列表
        xds: 线段列表
        zss: 中枢列表（笔构中枢）
        closes: 收盘价序列
        config: 缠论配置
        macd_data: MACD 数据 {"dif":[], "dea":[], "hist":[]}

    Returns:
        买卖点列表，按 bi.index 排序
    """
    if not bis or not xds:
        return []
    if macd_data is None:
        macd_data = {"dif": [], "dea": [], "hist": []}
    if config is None:
        from easy_tdx.chanlun.config import ChanlunConfig
        config = ChanlunConfig()

    # 1. 中枢映射到线段
    seg_zss = _map_zs_to_seg(zss, xds, bis)

    # 2. 检测一类买卖点
    t1_mmds = _detect_t1(xds, bis, seg_zss, macd_data, config)

    # 3. 检测二类买卖点
    t2_mmds = _detect_t2(xds, bis, t1_mmds, config)

    # 4. 检测类二买卖点
    t2s_mmds = _detect_t2s(xds, bis, t2_mmds, config)

    # 5. 检测三类买卖点
    t3_mmds = _detect_t3(xds, bis, seg_zss, t1_mmds, config)

    # 合并并排序
    all_mmds = t1_mmds + t2_mmds + t2s_mmds + t3_mmds
    all_mmds.sort(key=lambda m: m.bi.index if m.bi else 0)

    return all_mmds
