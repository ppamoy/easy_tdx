"""真·区间套（缠论）统一实现。

缠论原文里「区间套」= **大级别背驰段，在小级别上也确认为背驰**。逐级往下套，
直到最小级别能精确定位买卖点。三个硬约束：

1. **必须有真实的低级别数据** —— 本模块的函数签名显式接受低级别结构
   （``zss_low / xds_low / bcs_low / mmds_low``）。**没有跨级别数据时返回 ``None``，
   而不是编一个分数**（这是与旧「条件205」伪区间套最关键的区别：旧实现
   ``_calc_range_set_multi_level_v68(mmd, zss, closes)`` 三个入参全是单级别，
   却叫「多级别区间套」）。
2. **逐信号确认** —— 对高级别的**每一个** ``mmd``，取其锚定笔 ``bi`` 的时间区间
   ``[bi.start.bar_index, bi.end.bar_index]``，在低级别结构里找落在该区间内的
   **同方向**背驰 / 买卖点。
3. **时间锚定（防未来函数）** —— 低级别结构必须 ``end.bar_index <= 高级别信号位置``，
   沿用 V730 的口径（信号之后才完成的结构属未来信息，不得用于评价该信号）。

支持两种低级别来源（都符合缠论「更高级别笔 = 低级别线段」的递归定义）：

- **跨周期**：日线高级别 + 30 分钟低级别（真实两份行情，已存在于
  ``/chanlun/multi-level``）。时间对齐走「日期区间重叠」。
- **同序列递归**：``recursive_levels[0]``（线段级别）作为低级别，基础 ``bis`` 作为
  高级别。端点天然锚定原始 K 线 ``bar_index``，两级别**自动对齐**，无需额外映射。

对外只暴露一个核心入口 :func:`compute_qujiantao`，以及一个方便给
``ChanlunAnalyser`` 用的 :func:`qujiantao_for_result`（基于递归级别）。
"""

from __future__ import annotations

from typing import Any

from easy_tdx.chanlun.types import BC, BI, ZS


def _line_interval(line: Any) -> tuple[int, int]:
    """取一条线（笔/线段）的 [start_bar, end_bar] 区间（含端点）。"""
    if line is None or line.start is None or line.end is None:
        return (-1, -1)
    return (line.start.bar_index, line.end.bar_index)


def _low_structures_in_window(
    hi_start: int,
    hi_end: int,
    is_buy: bool,
    *,
    bis_low: list[BI] | None = None,
    zss_low: list[ZS] | None = None,
    bcs_low: list[BC] | None = None,
    mmds_low: list[Any] | None = None,
) -> dict[str, Any]:
    """收集落在高级别笔时间窗口内的低级别结构。

    返回统计：低级别笔数、中枢数、低级别背驰（同向）、低级别买卖点（同向）等，
    供 ``compute_qujiantao`` 打分。
    """
    out: dict[str, Any] = {
        "bi_count": 0,
        "zs_count": 0,
        "bc_same_dir": None,
        "mmd_same_dir": None,
        "last_low_bc_end": -1,
    }
    if bis_low:
        out["bi_count"] = sum(
            1
            for b in bis_low
            if (s := _line_interval(b)[0]) >= 0 and s <= hi_end and _line_interval(b)[1] >= hi_start
        )
    if zss_low:
        out["zs_count"] = sum(
            1
            for z in zss_low
            if z.end is not None
            and z.end.bar_index <= hi_end
            and z.start is not None
            and z.start.bar_index >= hi_start
        )
    if bcs_low:
        same = None
        last_end = -1
        for bc in bcs_low:
            if bc.curr is None or bc.curr.end is None:
                continue
            end = bc.curr.end.bar_index
            if end < hi_start or end > hi_end:
                # 防未来函数：低级别背驰必须在信号窗口内（含端点）
                continue
            if not bc.bc:
                continue
            # 方向一致：买点→底背驰（curr 向下笔），卖点→顶背驰（curr 向上笔）
            low_is_up = bc.curr.direction.value == "up"
            direction_ok = (not low_is_up) if is_buy else low_is_up
            if not direction_ok:
                continue
            if same is None:
                same = bc
            last_end = max(last_end, end)
        out["bc_same_dir"] = same
        out["last_low_bc_end"] = last_end
    if mmds_low:
        for m in mmds_low:
            if m.bi is None:
                continue
            end = m.bi.end.bar_index
            if hi_start <= end <= hi_end:
                out["mmd_same_dir"] = m
                break
    return out


def compute_qujiantao(
    mmd: Any,
    *,
    bis_low: list[BI] | None = None,
    zss_low: list[ZS] | None = None,
    bcs_low: list[BC] | None = None,
    mmds_low: list[Any] | None = None,
) -> dict[str, Any]:
    """计算一个高级别买卖点的真区间套确认。

    Args:
        mmd: 高级别买卖点（须有 ``bi`` 锚定笔）。
        bis_low / zss_low / bcs_low / mmds_low: 低级别结构。

    Returns:
        dict，字段：
        - ``nested`` (bool): 是否被低级别确认（存在同方向、时间窗口内的背驰/买卖点）。
        - ``score`` (float 0-1): 区间套强度评分。
        - ``method`` (str): "cross_period" / "recursive" / "single" / "none"。
        - ``confidence_adjust`` (float): 给 ``mmd.confidence`` 的建议调整量。
        - ``msg`` (str): 人类可读说明。
        - ``detail`` (dict): 低级别结构计数，便于调试/展示。

    **若没有任何低级别数据，返回 ``method='none'`` 且 ``nested=False``**（调用方据此
    决定不展示 / 不纳入过滤，而不是得到一个伪装的高分）。
    """
    # V-26：「提供了结构容器但为空」≠「完全没提供」。前者说明调用方走的是
    # 低级别路径（recursion / cross_period），只是窗口内没有结构——method
    # 仍应如实标注路径；后者才是真「无低级别数据」→ 'none'。
    has_low = any(seq is not None and len(seq) > 0 for seq in (bis_low, zss_low, bcs_low, mmds_low))
    any_container = any(seq is not None for seq in (bis_low, zss_low, bcs_low, mmds_low))
    if not has_low and not any_container:
        return {
            "nested": False,
            "score": 0.0,
            "method": "none",
            "confidence_adjust": 0.0,
            "msg": "无低级别数据，无法做区间套确认（返回空，不构成伪评分）",
            "detail": {},
        }

    if mmd.bi is None:
        return {
            "nested": False,
            "score": 0.0,
            "method": "none",
            "confidence_adjust": 0.0,
            "msg": "信号无锚定笔，无法做区间套确认",
            "detail": {},
        }

    hi_start, hi_end = _line_interval(mmd.bi)
    is_buy = "buy" in mmd.mmd_type.value

    low = _low_structures_in_window(
        hi_start,
        hi_end,
        is_buy,
        bis_low=bis_low,
        zss_low=zss_low,
        bcs_low=bcs_low,
        mmds_low=mmds_low,
    )

    bc = low["bc_same_dir"]  # 同方向、窗口内、确为背驰
    low_mmd = low["mmd_same_dir"]

    # 确认条件：窗口内存在同向真实背驰（最严格），或至少存在同向低级别买卖点
    confirmed = bc is not None or low_mmd is not None

    # 评分（0-1）：结构越完整、方向越一致越高
    score = 0.0
    if low["bi_count"] >= 3:
        score += 0.2
    if low["zs_count"] >= 1:
        score += 0.2
    if bc is not None:
        score += 0.4
        if low["zs_count"] >= 2:  # 有趋势结构（≥2 中枢）背驰更可信
            score += 0.2
    elif low_mmd is not None:
        score += 0.3  # 无背驰但有方向一致买卖点，次一级确认
    score = min(1.0, score)

    # 置信度建议调整：确认 +0.05，强确认（背驰+趋势结构）+0.08；不确认 -0.02
    if not confirmed:
        adj = -0.02
    elif bc is not None and low["zs_count"] >= 2:
        adj = 0.08
    else:
        adj = 0.05

    # V-26 method 语义（收敛为可区分的四值）：
    # - cross_period: mmds_low 容器被显式提供（跨周期端点四容器全传）
    # - recursive:    提供 bis_low/bcs_low（递归级别路径传笔与背驰结构）
    # - single:       只提供 zss_low（部分结构喂入，如诊断口径）
    # 此前用 ``mmds_low is not None`` 区分，而 qujiantao_for_result 恒传
    # ``mmds_low=rl.mmds``（空列表也非 None）→ 递归结果全部误标 cross_period。
    if mmds_low is not None:
        method = "cross_period"
    elif bis_low is not None or bcs_low is not None:
        method = "recursive"
    else:
        method = "single"

    dir_word = "底背驰(买)" if is_buy else "顶背驰(卖)"
    if confirmed:
        conf = f"低级别窗口内出现同方向{dir_word}确认"
    else:
        conf = "低级别窗口内无同方向背驰/买卖点确认"

    return {
        "nested": confirmed,
        "score": round(score, 3),
        "method": method,
        "confidence_adjust": round(adj, 3),
        "msg": (
            f"区间套{('确认' if confirmed else '未确认')} | {conf} | "
            f"低级别笔={low['bi_count']} 中枢={low['zs_count']}"
        ),
        "detail": {
            "low_bi_count": low["bi_count"],
            "low_zs_count": low["zs_count"],
            "low_bc_same_dir": bc.bc_type.value if bc and bc.bc_type else None,
            "low_mmd_same_dir": low_mmd.mmd_type.value if low_mmd else None,
            "hi_bar_window": [hi_start, hi_end],
        },
    }


def _bi_time_span(bi: Any) -> tuple[Any, Any]:
    """取一条笔的时间跨度（start/end 分型锚定 K 线的日期）。

    跨周期对齐必须用**原始行情时间**，而不是 bar_index：日线的第 100 根
    与 30 分钟的第 100 根不是同一时刻，bar_index 直接比较是错的。
    """
    s = getattr(bi.start, "k", None) if bi.start else None
    e = getattr(bi.end, "k", None) if bi.end else None
    sd = getattr(s, "date", None) if s is not None else None
    ed = getattr(e, "date", None) if e is not None else None
    return (sd, ed)


def compute_qujiantao_cross_period(
    mmds_high: list[Any],
    *,
    bis_low: list[BI] | None = None,
    zss_low: list[ZS] | None = None,
    bcs_low: list[BC] | None = None,
    mmds_low: list[Any] | None = None,
) -> list[dict[str, Any] | None]:
    """**真·区间套**：用真实低周期数据逐信号确认（缠论原文语义）。

    与 :func:`qujiantao_for_result`（用同序列递归级别）不同，本函数要求传入
    **另一份真实行情**的低周期笔/中枢/背驰/买卖点（如日线信号 + 30 分钟结构），
    按**行情时间重叠**对齐，而不是 bar_index。

    对每个高级别 ``mmd``：
    1. 取其锚定笔的时间窗口 ``[bi_start_date, bi_end_date]``；
    2. 在低周期结构里找**落在该窗口内**（时间区间相交）的**同方向**背驰/买卖点；
    3. 防未来函数：低周期结构的结束时间不得晚于高级别信号笔结束时间。

    Returns:
        与 ``mmds_high`` 等长的列表；无低级别数据时对应项为 ``None``。
    """
    has_low = any(seq is not None and len(seq) > 0 for seq in (bis_low, zss_low, bcs_low, mmds_low))
    if not has_low:
        return [None] * len(mmds_high)

    out: list[dict[str, Any] | None] = []
    for mmd in mmds_high:
        bi = getattr(mmd, "bi", None)
        if bi is None:
            out.append(None)
            continue
        hi_s, hi_e = _bi_time_span(bi)
        if hi_s is None or hi_e is None:
            out.append(None)
            continue
        is_buy = "buy" in mmd.mmd_type.value

        # —— 低周期笔/中枢：计数落在窗口内的（时间区间相交）——
        # V-18 因果性：计数只计**结束不晚于 hi_e** 的结构。相交但结束更晚的
        # 低周期笔/中枢携带信号之后才走出的信息，实测算 19% 越界——计入
        # score 等于用未来信息给历史信号加分（bc/mmd 确认早有同款过滤）。
        bi_count = 0
        if bis_low:
            for b in bis_low:
                s, e = _bi_time_span(b)
                if s is None or e is None:
                    continue
                if e > hi_e:
                    continue
                if s <= hi_e and e >= hi_s:
                    bi_count += 1
        zs_count = 0
        if zss_low:
            for z in zss_low:
                s_l = getattr(z.start, "k", None) if z.start else None
                e_l = getattr(z.end, "k", None) if z.end else None
                sd = getattr(s_l, "date", None) if s_l is not None else None
                ed = getattr(e_l, "date", None) if e_l is not None else None
                if sd is None or ed is None:
                    continue
                if ed > hi_e:
                    continue
                if sd <= hi_e and ed >= hi_s:
                    zs_count += 1

        # —— 同方向 + 窗口内 + 防未来函数的背驰 ——
        bc_hit = None
        if bcs_low:
            for bc in bcs_low:
                if not getattr(bc, "bc", False):
                    continue
                curr = getattr(bc, "curr", None)
                if curr is None:
                    continue
                s, e = _bi_time_span(curr)
                if s is None or e is None:
                    continue
                # 防未来函数：低周期背驰结束不得晚于高级别信号笔结束
                if e > hi_e:
                    continue
                if not (s <= hi_e and e >= hi_s):
                    continue
                # 方向一致：买点→底背驰（curr 向下笔），卖点→顶背驰（curr 向上笔）
                low_is_up = curr.direction.value == "up"
                if (not low_is_up) if is_buy else low_is_up:
                    bc_hit = bc
                    break

        # —— 同方向低周期买卖点（次一级确认）——
        mmd_hit = None
        if mmds_low:
            for m in mmds_low:
                mb = getattr(m, "bi", None)
                if mb is None:
                    continue
                s, e = _bi_time_span(mb)
                if s is None or e is None:
                    continue
                if e > hi_e:  # 防未来函数
                    continue
                if s <= hi_e and e >= hi_s:
                    if ("buy" in m.mmd_type.value) == is_buy:
                        mmd_hit = m
                        break

        confirmed = bc_hit is not None or mmd_hit is not None

        score = 0.0
        if bi_count >= 3:
            score += 0.2
        if zs_count >= 1:
            score += 0.2
        if bc_hit is not None:
            score += 0.4
            if zs_count >= 2:
                score += 0.2
        elif mmd_hit is not None:
            score += 0.3
        score = min(1.0, score)

        if not confirmed:
            adj = -0.02
        elif bc_hit is not None and zs_count >= 2:
            adj = 0.08
        else:
            adj = 0.05

        dir_word = "底背驰(买)" if is_buy else "顶背驰(卖)"
        if confirmed:
            conf = f"低周期窗口内出现同方向{dir_word}确认"
        else:
            conf = "低周期窗口内无同方向背驰/买卖点确认"

        out.append(
            {
                "nested": confirmed,
                "score": round(score, 3),
                "method": "cross_period",
                "confidence_adjust": round(adj, 3),
                "msg": (
                    f"区间套{('确认' if confirmed else '未确认')} | {conf} | "
                    f"低周期笔={bi_count} 中枢={zs_count}"
                ),
                "detail": {
                    "low_bi_count": bi_count,
                    "low_zs_count": zs_count,
                    "low_bc_same_dir": (
                        bc_hit.bc_type.value if bc_hit and bc_hit.bc_type else None
                    ),
                    "low_mmd_same_dir": (mmd_hit.mmd_type.value if mmd_hit else None),
                    "hi_time_window": [str(hi_s), str(hi_e)],
                },
            }
        )
    return out


def qujiantao_for_result(
    result: Any,
    low_level_index: int = 0,
) -> list[dict[str, Any] | None]:
    """基于递归级别，给某一级别（默认基础笔级别）的每个 MMD 算真区间套。

    ``result`` 是 ``ChanlunResult``：基础级别笔在 ``result.bis`` / ``result.mmds``，
    低级别（线段级别）在 ``result.recursive_levels[low_level_index]``
    （其 ``bis=xds``, ``zss``, ``bcs``, ``mmds``）。

    Returns:
        与 ``result.mmds`` 等长的列表，每个元素是 :func:`compute_qujiantao` 的结果，
        无低级别数据时对应项为 ``None``。
    """
    mmds = getattr(result, "mmds", None) or []
    recs = getattr(result, "recursive_levels", None) or []
    if not recs or low_level_index >= len(recs):
        # 没有低级别数据 → 全部返回 None（不编造评分）
        return [None] * len(mmds)

    rl = recs[low_level_index]
    low_bis = list(rl.xds)  # 线段级别：「笔」= 基础线段
    low_zss = rl.zss
    low_bcs = rl.bcs
    low_mmds = rl.mmds

    out: list[dict[str, Any] | None] = []
    for m in mmds:
        r = compute_qujiantao(
            m,
            bis_low=low_bis,
            zss_low=low_zss,
            bcs_low=low_bcs,
            mmds_low=low_mmds,
        )
        if r is not None:
            # V-26：递归路径的传参形态（四容器全传，mmds_low 非空列表）与
            # 跨周期端点完全一致，compute_qujiantao 内部无法区分——只有
            # 调用方知道自己的数据来源，method 必须在此显式改写。
            # compute_qujiantao_cross_period 不受影响（自己写死 cross_period）。
            r["method"] = "recursive"
        out.append(r)
    return out
