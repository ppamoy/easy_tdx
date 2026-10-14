"""缠论分析路由。"""

from __future__ import annotations

import asyncio
import json as _json
import logging
from pathlib import Path
from typing import Any, cast

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import Field

from easy_tdx.web.deps import get_client, get_mac_client_optional
from easy_tdx.web.klines import (  # 共享 K 线取数（MAC 回退）
    fetch_bars_range,
    fetch_paged_bars,
    fetch_qfq_klines,
)
from easy_tdx.web.schemas import ChanlunRequest

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chanlun"])


# 周期白名单：前端 category → ChanlunAnalyser 的 frequency 名。
# 原先在 analyze / multi-level 两处各写一份局部字典，容易走偏（multi-level 那份
# 漏了 MONTH/YEAR）。提到模块级后，诊断路由等其它模块可复用同一份。
FREQUENCY_MAP: dict[str, str] = {
    "MIN_1": "1min",
    "MIN_5": "5min",
    "MIN_15": "15min",
    "MIN_30": "30min",
    "MIN_60": "60min",
    "DAY": "daily",
    "WEEK": "weekly",
    "MONTH": "monthly",
    "YEAR": "yearly",
}


def resolve_frequency(category: str) -> str:
    """把前端 category 转成 ChanlunAnalyser 的 frequency；未知则原样返回。"""
    return FREQUENCY_MAP.get((category or "DAY").upper(), category)


def _to_json_safe(obj: Any) -> Any:
    """递归将 numpy 类型转换为 JSON 可序列化的 Python 原生类型。"""
    import numpy as np

    if isinstance(obj, dict):
        return {k: _to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_to_json_safe(item) for item in obj]
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


def _build_signal_explanation(mmd: Any) -> str:
    """V422 错误归因「正确解读」（D4：复用 mmd.msg + V102 建议拼接）。

    从买卖点对象生成一段可读解读：信号类型 + 置信度 + V102 操作建议。
    """
    parts: list[str] = []
    parts.append(f"模型识别为 {mmd.mmd_type.value}（置信度 {mmd.confidence:.0%}）")
    _decision = getattr(mmd, "_decision_support", None) or {}
    advice = _decision.get("action_recommendation")
    if advice:
        parts.append(f"V102 建议：{advice}")
    msg = getattr(mmd, "msg", "")
    if msg:
        parts.append(str(msg))
    return "；".join(parts)


def _attach_signal_accuracy(d: dict[str, Any], result: Any) -> None:
    """给分析结果 dict 附上买卖点分类准确度（前瞻命中率 vs 随机基准）。

    V-HOTFIX: multi-level 的 fmt_result 曾漏算此字段，导致多级别联立模式下
    前端「买卖点分类准确度验证」面板永不显示（v-if 恒 false）。抽成公共
    helper 让 /chanlun/analyze 与 multi-level 共用，防止两处漂移。
    准确度验证是附加信息，失败不应阻断主分析结果。
    """
    try:
        from easy_tdx.backtest.signal_accuracy import compute_signal_accuracy_by_type

        closes = [float(k.close) for k in result.klines]
        mmd_signals = [
            {
                "type": mmd.mmd_type.value,
                "bar_index": mmd.bi.end.bar_index if mmd.bi else None,
            }
            for mmd in result.mmds
        ]
        d["signal_accuracy"] = compute_signal_accuracy_by_type(closes, mmd_signals)
    except Exception:  # noqa: BLE001
        d["signal_accuracy"] = None


def _multi_fmt_result(result: Any) -> dict[str, Any]:
    """multi-level 端点的结果序列化（模块级，可离线单测）。

    V-17: 原为端点内嵌套函数 fmt_result，无法导入测试——嵌套组装函数是
    payload 漏传 bug 的温床（train/build_train_session_payload 同例，提取
    后才纳入契约测试）。字段含 fractals/valid_fractals/signal_accuracy。
    """
    d: dict[str, Any] = result.to_dict()
    d["fractals"] = [
        {
            "fx_type": fx.fx_type.value,
            "date": result._fmt_dt(result._fx_anchor_datetime(fx)),
            "val": round(fx.val, 2),
            "index": fx.index,
            "bar_index": fx.bar_index,
        }
        for fx in result.fractals
    ]
    d["valid_fractals"] = result.valid_fractals_to_dict()
    # 买卖点分类准确度：与 /chanlun/analyze 对齐，否则多级别联立模式下
    # 前端准确度面板（读 hr.signal_accuracy）永不显示。
    _attach_signal_accuracy(d, result)
    return d


def _filter_candidates_by_difficulty(
    candidates: list[dict[str, Any]], difficulty: str, seed: int = 0
) -> list[dict[str, Any]]:
    """按难度过滤训练候选点（D3：难度 = f(信号置信度, 是否干扰项)）。

    - easy：仅高置信度买卖点（confidence >= 0.8）+ 少量干扰项
    - medium：全部候选点（现状，不过滤）
    - hard：低置信度买卖点（confidence < 0.75）+ 更多干扰项

    用 seed 初始化 random 做干扰项采样，保证同 (code, difficulty, seed) 出题可复现。
    """
    import random

    if difficulty not in ("easy", "medium", "hard"):
        difficulty = "medium"
    mmd_cands = [c for c in candidates if c.get("kind") == "mmd"]
    fx_cands = [c for c in candidates if c.get("kind") == "fractal"]

    if difficulty == "medium":
        return candidates

    if difficulty == "easy":
        picked_mmd = [c for c in mmd_cands if (c.get("signal") or {}).get("confidence", 0) >= 0.8]
        # 少量干扰项：mmd 数量的 1/3，seed 复现
        rng = random.Random(seed)
        n_fx = max(len(picked_mmd) // 3, 0)
        picked_fx = rng.sample(fx_cands, min(n_fx, len(fx_cands))) if fx_cands and n_fx > 0 else []
    else:  # hard
        picked_mmd = [c for c in mmd_cands if (c.get("signal") or {}).get("confidence", 0) < 0.75]
        # 更多干扰项：mmd 数量的 1/2
        rng = random.Random(seed)
        n_fx = max(len(picked_mmd) // 2, 0)
        picked_fx = rng.sample(fx_cands, min(n_fx, len(fx_cands))) if fx_cands and n_fx > 0 else []

    return sorted(picked_mmd + picked_fx, key=lambda c: c["index"])


def build_train_session_payload(
    result: Any,
    df: pd.DataFrame,
    category: str,
    difficulty: str = "medium",
    seed: int = 0,
    reveal_limit: int | None = None,
) -> dict[str, Any]:
    """把缠论分析结果组装成训练会话负载（纯函数，可单测）。

    - bars：K 线（与 /bars 同列）
    - bis/xds/zss/mmds/fractals/bcs/boll：完整结构
    - candidates：候选点（买卖点信号 + 采样分型干扰项），供逐步揭示提问
    - mmd_outcomes：每个买卖点的信号后 5/10/20 日收益（复盘验证）

    Args:
        reveal_limit: **训练防作弊闸门**（V731）。
            ``None``（默认）= 复盘模式，返回全量（F2 事后验证确实需要未来收益）。
            整数 N = 训练模式，只下发「截至第 N 根 K 线」应有的信息：
              * ``mmd_outcomes`` 置空（那是信号之后的**未来走势**）
              * 尚未揭示（index > N）的候选点，其 ``signal`` 答案置空
            前端只用 revealIndex 截断**图表渲染**，数据本身若不截断，用户
            F12 看 Network 即可读到全部答案与后续 20 日涨跌，「逐步揭示
            训练」失去意义（实测 000333 日线开局即可知 46/87/110 三个答案
            点，以及 1buy 后 20 日 +13.17%）。
    """
    # K 线（与 /bars 一致的列）
    _date_col = "date" if "date" in df.columns else "datetime"
    bars: list[dict[str, Any]] = []
    for _i, row in df.iterrows():
        dt = row[_date_col]
        bars.append(
            {
                "datetime": str(dt)[:19].replace(" ", "T"),
                "open": round(float(row["open"]), 3),
                "close": round(float(row["close"]), 3),
                "high": round(float(row["high"]), 3),
                "low": round(float(row["low"]), 3),
                "vol": float(row.get("vol", 0) or 0),
                "amount": float(row.get("amount", 0) or 0),
            }
        )

    # 结构数据（复用 analyze 的序列化）
    d = result.to_dict()
    d["fractals"] = [
        {
            "fx_type": fx.fx_type.value,
            "date": result._fmt_dt(result._fx_anchor_datetime(fx)),
            "val": round(fx.val, 2),
            "index": fx.index,
            "bar_index": fx.bar_index,
        }
        for fx in result.fractals
    ]
    d["valid_fractals"] = result.valid_fractals_to_dict()
    if result.boll:
        d["boll"] = {
            "upper": [round(x, 2) for x in result.boll.upper[-100:]],
            "mid": [round(x, 2) for x in result.boll.mid[-100:]],
            "lower": [round(x, 2) for x in result.boll.lower[-100:]],
            "width": [round(x, 2) for x in result.boll.width[-100:]],
            "percent_b": [round(x, 2) for x in result.boll.percent_b[-100:]],
            "latest_upper": round(result.boll.latest_upper, 2),
            "latest_mid": round(result.boll.latest_mid, 2),
            "latest_lower": round(result.boll.latest_lower, 2),
            "latest_percent_b": round(result.boll.latest_percent_b, 2),
            "latest_width": round(result.boll.latest_width, 4),
        }
    else:
        d["boll"] = None

    # 候选点：每个买卖点一个（kind=mmd），外加采样分型干扰项（kind=fractal）
    mmd_cands: list[dict[str, Any]] = []
    for mmd in result.mmds:
        if not mmd.bi:
            continue
        k_idx = mmd.bi.end.bar_index
        # V344: 训练教学展示 V102 决策支持（仅 3买/3卖 有建议）
        _v102_scorecard = getattr(mmd, "_signal_quality_scorecard", None) or {}
        _v102_decision = getattr(mmd, "_decision_support", None) or {}
        mmd_cands.append(
            {
                "index": k_idx,
                "date": result._fmt_dt(result._fx_anchor_datetime(mmd.bi.end)),
                "kind": "mmd",
                "fx_type": None,
                "signal": {
                    "type": mmd.mmd_type.value,
                    "confidence": round(mmd.confidence, 2),
                    "grade": getattr(getattr(mmd, "quality", None), "grade", None),
                    "v102_grade": _v102_scorecard.get("overall_grade") or None,
                    "v102_advice": _v102_decision.get("action_recommendation") or None,
                    # V422: 错误归因「正确解读」（D4：复用 mmd.msg + V102 建议）
                    "explanation": _build_signal_explanation(mmd),
                },
            }
        )
    mmd_idx_set = {c["index"] for c in mmd_cands}
    fx_cands: list[dict[str, Any]] = []
    for fx in result.fractals:
        k_idx = fx.bar_index
        if any(abs(k_idx - m) <= 3 for m in mmd_idx_set):
            continue
        fx_cands.append(
            {
                "index": k_idx,
                "date": result._fmt_dt(result._fx_anchor_datetime(fx)),
                "kind": "fractal",
                "fx_type": fx.fx_type.value,
                "signal": None,
            }
        )
    # 均匀采样干扰项：总数（信号+干扰）控制在 ~40
    target_total = 40
    distract_max = max(target_total - len(mmd_cands), 0)
    if len(fx_cands) > distract_max:
        step = len(fx_cands) / distract_max
        fx_cands = [fx_cands[int(i * step)] for i in range(distract_max)]
    candidates = sorted(mmd_cands + fx_cands, key=lambda c: c["index"])
    # V421: 难度分级过滤（D3），seed 保证出题可复现
    candidates = _filter_candidates_by_difficulty(candidates, difficulty, seed)

    # V731 防作弊闸门：训练模式（reveal_limit 非 None）下，
    # 尚未揭示到的候选点不得携带答案（signal）。注意只置空答案、保留题目
    # 本身（index/date/kind/fx_type），否则题目会凭空消失、训练没法进行。
    if reveal_limit is not None:
        for c in candidates:
            if c["index"] > reveal_limit:
                c["signal"] = None

    # 买卖点信号后 N 日收益
    closes = [k.close for k in result.klines]

    def _ret_from(idx: int, n: int) -> float | None:
        if idx is None or idx < 0 or idx >= len(closes):
            return None
        end = idx + n
        if end >= len(closes):
            return None
        base = closes[idx]
        if not base:
            return None
        return round((float(closes[end]) / float(base) - 1) * 100, 2)

    # V731 防作弊闸门：训练模式不下发未来走势。mmd_outcomes 是「信号之后
    # 5/10/20 日实际涨跌」，只有 F2 复盘模式才需要（事后验证准确率给评分用）；
    # 训练模式下它就是标准答案，必须整段置空。
    mmd_outcomes: list[dict[str, Any]] = []
    if reveal_limit is None:
        for mmd in result.mmds:
            if not mmd.bi:
                continue
            k_idx = mmd.bi.end.k.k_index
            outcomes: dict[str, Any] = {
                "type": mmd.mmd_type.value,
                "date": result._fmt_dt(mmd.bi.end.k.date),
                "price": round(result.klines[k_idx].close, 2)
                if 0 <= k_idx < len(result.klines)
                else None,
                "ret_5d": _ret_from(k_idx, 5),
                "ret_10d": _ret_from(k_idx, 10),
                "ret_20d": _ret_from(k_idx, 20),
                "max_5d": None,
                "min_5d": None,
            }
            if 0 <= k_idx < len(closes):
                base = closes[k_idx]
                if base:
                    win = closes[k_idx : k_idx + 6]
                    if win:
                        outcomes["max_5d"] = round((max(win) / base - 1) * 100, 2)
                        outcomes["min_5d"] = round((min(win) / base - 1) * 100, 2)
            mmd_outcomes.append(outcomes)

    # ── V731 防作弊闸门（第 38 轮补全）：bars 也必须截断 ──
    # 此前（含第 37 轮结构截断）bars 仍下发全量：训练模式 reveal_limit=50
    # 时 bars=160，未来 110 根 K 线（答案的原始数据源）就在响应里，前端只是
    # 不显示。用户 F12 存一次响应即得全部未来走势，无需逐题枚举。现在
    # 训练模式 bars 切到前 N+1 根 —— 做完这块，训练模式响应中不再有任何
    # 「N 之后」的信息。复盘模式不受影响。
    # 渐进揭示（作答后按需取答案 reveal_limit=index）天然兼容：每次请求
    # 返回「截至该候选点」的 bars，与前端 revealIndex 语义一致；结构截断
    # 与 bars 截断同用 keep=N+1，索引不漂移，图上对位不受影响。
    if reveal_limit is not None:
        bars = bars[: reveal_limit + 1]

    # ── V731 防作弊闸门（第 37 轮扩展 / 第 39 轮补全）：训练模式必须
    # **服务端截断**全部描述「reveal_limit 之后」的结构数据。
    #
    # 第 37 轮只截了 bis/xds/zss/fractals/valid_fractals/macd/boll，
    # 漏掉 **mmds / bcs / zsds / qsds / levels**（levels 里还整份重复了
    # 一套 bis/xds/zss/mmds/bcs/zsds/qsds）。第 39 轮实测（000333 日线
    # 160 根，reveal_limit=0，即训练开局）泄露量：
    #   mmds 3/3（含 type/date/price/confidence/grade —— 就是标准答案）
    #   bcs 1/1、zsds 2/2、qsds 2/2
    #   levels.bi.bis 10/10、levels.bi.mmds 3/3、levels.xd.bis 2/2 …
    # 也就是说：开局一次响应即可读到全部 3 个买卖点的类型/日期/价格/
    # 置信度 —— 「逐步揭示训练」名存实亡（前端 revealIndex 只是**显示层**
    # 过滤，F12 网络面板直接可读）。
    #
    # 截断口径（与第 37 轮已截数组一致，keep = N+1，索引不漂移）：
    #   * 线段类（bis/xds/zsds/qsds）：max(end_index, bar_index) < keep
    #   * 中枢（zss）：start_index < keep（中枢是区间，起点越界即未来）
    #   * 买卖点（mmds）/ 背驰（bcs）：锚点下标 < keep
    #   * macd/boll 这类与 bars 对齐的序列：切前 keep 个
    # 复盘模式（reveal_limit=None）不受影响，仍返回全量。
    if reveal_limit is not None:
        keep = reveal_limit + 1  # 含第 N 根

        def _idx(c: dict[str, Any], key: str) -> int:
            """取序列化 dict 里的 bar 下标；缺失 / 非数值按 0 计。

            V733 CI 收口：旧写法 ``max(c.get(key, 0), ...)`` 的两个操作数都是
            Any（``dict[str, Any].get`` 的返回），strict 模式下 max 的返回值无法
            判定为 int。把类型显式化的同时，也堵掉了 JSON 里出现
            ``"end_index": null`` 时 max() 拿 None 与 int 比较会抛 TypeError
            （进而 500）的隐患 —— null 按缺失处理，落到 0。
            """
            v = c.get(key)
            if isinstance(v, bool) or not isinstance(v, int | float):
                return 0
            try:
                return int(v)
            except (ValueError, OverflowError):
                return 0  # NaN / Inf 视同缺失

        def _end_le(c: dict[str, Any]) -> bool:
            return max(_idx(c, "end_index"), _idx(c, "bar_index")) < keep

        # V731 第 39 轮：结构数组的截断口径集中在这三个谓词里，新增数组
        # （或 to_dict 新增字段）只需挂到下面的 _CUT_RULES，避免再出现
        # 「清单里漏一个就漏一路未来」。
        def _anchor_le(c: dict[str, Any]) -> bool:
            """买卖点/背驰：只看锚点下标（bar_index / anchor_bar_index）。"""
            return max(_idx(c, "bar_index"), _idx(c, "anchor_bar_index")) < keep

        def _zs_start_le(c: dict[str, Any]) -> bool:
            return _idx(c, "start_index") < keep

        def _cut(items: Any, pred: Any) -> list[Any]:
            return [x for x in (items or []) if pred(x)]

        bis_t = _cut(d.get("bis"), _end_le)
        xds_t = _cut(d.get("xds"), _end_le)
        zss_t = _cut(d.get("zss"), _zs_start_le)
        fractals_t = _cut(d.get("fractals"), _end_le)
        valid_fractals_t = _cut(d.get("valid_fractals"), _end_le)
        # 买卖点 = 训练答案本体（type/date/anchor_val/confidence/grade）
        mmds_t = _cut(d.get("mmds"), _anchor_le)
        bcs_t = _cut(d.get("bcs"), _anchor_le)
        zsds_t = _cut(d.get("zsds"), _end_le)
        qsds_t = _cut(d.get("qsds"), _end_le)

        # levels：笔/线段（含递归）级别里整套重复了一遍上述结构，同样截断。
        # 只截 *_count 之外的数组键 —— count 是标量，且前端训练页不消费。
        _LEVEL_ARRAYS = {
            "bis": _end_le,
            "xds": _end_le,
            "zss": _zs_start_le,
            "mmds": _anchor_le,
            "bcs": _anchor_le,
            "zsds": _end_le,
            "qsds": _end_le,
        }

        def _cut_level(lv: Any) -> Any:
            if not isinstance(lv, dict):
                return lv
            out = dict(lv)
            for k, pred in _LEVEL_ARRAYS.items():
                if k in out:
                    out[k] = _cut(out.get(k), pred)
            # *_count 是「全量」计数（如 bi_count=10、mmd_count=3），与
            # 截断后的数组长度不一致会让前端/用户直接读出「未来还有多少
            # 结构」，同样属于泄题 —— 按截断后的数组重算，保持自洽。
            if isinstance(out.get("bi_count"), int):
                out["bi_count"] = len(out.get("bis") or [])
            if isinstance(out.get("mmd_count"), int):
                out["mmd_count"] = len(out.get("mmds") or [])
            return out

        levels_t = d.get("levels")
        if isinstance(levels_t, dict):
            levels_t = {name: _cut_level(lv) for name, lv in levels_t.items()}
        macd_t = d.get("macd")
        if isinstance(macd_t, dict) and macd_t.get("hist") is not None:
            macd_t = {k: (v[:keep] if isinstance(v, list) else v) for k, v in macd_t.items()}
        boll_t = d.get("boll")
        if isinstance(boll_t, dict):
            boll_t = {k: (v[:keep] if isinstance(v, list) else v) for k, v in boll_t.items()}
    else:
        bis_t = d.get("bis", [])
        xds_t = d.get("xds", [])
        zss_t = d.get("zss", [])
        fractals_t = d.get("fractals", [])
        valid_fractals_t = d.get("valid_fractals", [])
        mmds_t = d.get("mmds", [])
        bcs_t = d.get("bcs", [])
        zsds_t = d.get("zsds", [])
        qsds_t = d.get("qsds", [])
        levels_t = d.get("levels")
        macd_t = d.get("macd")
        boll_t = d.get("boll")

    return cast(
        dict[str, Any],
        _to_json_safe(
            {
                "code": result.code,
                "frequency": result.frequency,
                "category": category,
                "bars": bars,
                "bis": bis_t,
                "xds": xds_t,
                "zss": zss_t,
                "mmds": mmds_t,
                "fractals": fractals_t,
                # V-HOTFIX: valid_fractals 在上面 d["valid_fractals"] 已算好，
                # 但这里手工列字段时漏了它 —— 前端 train 页拿到的恒为空，
                # 图上 0 个分型（36 根窗口实测：直调 analyser=4，HTTP=0）。
                # 教训与 stock_pick._run_timing_one 的同类漏传一致：算过的
                # 字段必须在 return 处再核对一遍，别只靠手写清单。
                "valid_fractals": valid_fractals_t,
                "bcs": bcs_t,
                "boll": boll_t,
                # macd 与 valid_fractals 同批漏传：to_dict 明确给出完整序列
                # 供前端副图展示，这里手工清单却漏了 —— train 页 MACD 副图
                # 恒缺失（d.macd 恒 undefined，无 hist 就不渲染副图面板）。
                "macd": macd_t,
                # levels（笔/线段递归级别）与 zsds/qsds 同样来自 to_dict，
                # 手工清单漏了 levels 会让 train 页线段级别切换退化为空图
                # （data.levels.xd 恒 undefined，笔/分型/买卖点清空后无从恢复）。
                "levels": levels_t,
                "zsds": zsds_t,
                "qsds": qsds_t,
                "candidates": candidates,
                "mmd_outcomes": mmd_outcomes,
            }
        ),
    )


@router.post("/chanlun/analyze")
async def chanlun_analyze(
    req: ChanlunRequest,
    client: Any = Depends(get_client),
    mac_client: Any | None = Depends(get_mac_client_optional),
) -> dict[str, Any]:
    """执行缠论分析。

    自动从 TDX 服务器获取 K 线数据，运行完整缠论计算管道，
    返回笔、中枢、线段、买卖点、背驰、分型等分析结果。

    V810: 无 start_date/end_date 时优先查 SQLite 缓存（毫秒级），
    未命中则全量分析后存入缓存（版本指纹自动失效旧数据）。
    """
    from easy_tdx.chanlun import ChanlunAnalyser, ChanlunConfig
    from easy_tdx.web.chanlun_cache import ChanlunCache

    # V810: 无日期范围时查缓存（全量分析结果）
    if not req.start_date and not req.end_date:
        cache = ChanlunCache()
        cached = cache.get(req.market, req.code, req.category)
        if cached is not None:
            return cached

    # 1. Fetch kline data（QFQ 前复权，与前端 /bars 同一价格体系）
    df = await _fetch_request_klines(
        mac_client,
        client,
        req.market,
        req.code,
        req.category,
        req.start,
        req.count,
        start_date=req.start_date,
        end_date=req.end_date,
    )

    # V599: 按可选日期范围截断，让缠论分析与前端 K 线图窗口精确对齐
    # （回测页用 start_date/end_date 截取 K 线，这里用同一范围分析）。
    if req.start_date or req.end_date:
        col = "date" if "date" in df.columns else "datetime"
        ts = pd.to_datetime(df[col]).dt.normalize()
        mask = pd.Series(True, index=df.index)
        if req.start_date:
            mask &= ts >= pd.Timestamp(req.start_date)
        if req.end_date:
            mask &= ts <= pd.Timestamp(req.end_date)
        df = df[mask].reset_index(drop=True)

    # 2. Run chanlun analysis
    symbol = f"{req.market}{req.code}"
    freq = resolve_frequency(req.category)
    # V708: 多级别递归深度经前端指定（1=线段级别；标准请求不传时回落 1）。
    analyser = ChanlunAnalyser(
        code=symbol,
        frequency=freq,
        config=ChanlunConfig(recursion_depth=req.recursion_depth),
    )

    # V735 Round 9：原文第17课精确口径——用次级别线段构中枢。
    # cross_timeframe=True 时拉取次级别 K线（日线→30min），用次级别线段构中枢。
    _LOWER_TF_MAP = {"DAY": "MIN_30", "MIN_30": "MIN_5", "MIN_60": "MIN_15", "WEEK": "DAY"}
    lower_cat = _LOWER_TF_MAP.get(req.category.upper()) if req.cross_timeframe else None

    if lower_cat:
        try:
            df_lower = await _fetch_request_klines(
                mac_client, client, req.market, req.code, lower_cat, 0,
                min(req.count * 8, 8000),
            )
            if len(df_lower) >= 200:
                result = analyser.process_klines_cross_timeframe(df, df_lower)
            else:
                result = analyser.process_klines(df)
        except Exception:
            # 次级别数据拉取失败，退回默认
            result = analyser.process_klines(df)
    else:
        result = analyser.process_klines(df)

    # 3. 返回完整分析结果，包括分型数据和BOLL
    d = result.to_dict()

    # V810: 返回 bars（与分析同一 df），前端无需单独取 K 线，
    # 笔/中枢/买卖点索引与 bars 天然对齐，彻底消除索引错位。
    from easy_tdx.web.schemas import DataFrameResponse
    d["bars"] = DataFrameResponse.from_dataframe(df).data

    # 添加分型数据
    d["fractals"] = [
        {
            "fx_type": fx.fx_type.value,
            "date": result._fmt_dt(result._fx_anchor_datetime(fx)),
            "val": round(fx.val, 2),
            "index": fx.index,
            "bar_index": fx.bar_index,
        }
        for fx in result.fractals
    ]
    d["valid_fractals"] = result.valid_fractals_to_dict()

    # 添加BOLL数据
    if result.boll:
        _ = len(result.boll.upper)
        d["boll"] = {
            "upper": [round(x, 2) for x in result.boll.upper[-100:]],
            "mid": [round(x, 2) for x in result.boll.mid[-100:]],
            "lower": [round(x, 2) for x in result.boll.lower[-100:]],
            "width": [round(x, 2) for x in result.boll.width[-100:]],
            "percent_b": [round(x, 2) for x in result.boll.percent_b[-100:]],
            "latest_upper": round(result.boll.latest_upper, 2),
            "latest_mid": round(result.boll.latest_mid, 2),
            "latest_lower": round(result.boll.latest_lower, 2),
            "latest_percent_b": round(result.boll.latest_percent_b, 2),
            "latest_width": round(result.boll.latest_width, 4),
        }

    # 4. 买卖点分类准确度验证（前瞻命中率 vs 随机基准）——让用户核对
    #    「哪类缠论买卖点信号真的准」，直接服务择时交易的可信度判断。
    _attach_signal_accuracy(d, result)

    # V534: 基本面估值（PE/PB），复用诊断页的离线取数 helper（无缓存时为 None）
    try:
        from easy_tdx.web.routers.diagnosis import _fetch_diagnosis_valuation

        latest_close = float(result.klines[-1].close) if result.klines else 0.0
        d["valuation"] = _fetch_diagnosis_valuation(req.market, req.code, latest_close)
    except Exception:  # noqa: BLE001 — 估值失败不阻断缠论分析
        d["valuation"] = None

    # V810: 无日期范围的全量分析结果存入 SQLite 缓存（后续毫秒级读取）
    if not req.start_date and not req.end_date:
        try:
            cache = ChanlunCache()
            cache.put(req.market, req.code, req.category, d)
        except Exception:  # noqa: BLE001 — 缓存失败不阻断返回
            pass

    return d


class ChanlunMultiLevelRequest(ChanlunRequest):
    """多级别缠论分析请求。"""

    low_level: str = Field(default="MIN_30", description="低级别周期（如 MIN_30, MIN_5）")


# 低级别 K 线上限：见 multi-level 内「低级别 K 线截断（性能护栏）」注释
LOW_MAX_BARS = 3000

@router.post("/chanlun/multi-level")
async def chanlun_multi_level(
    req: ChanlunMultiLevelRequest,
    client: Any = Depends(get_client),
    mac_client: Any | None = Depends(get_mac_client_optional),
) -> dict[str, Any]:
    """多级别缠论分析：同时分析高级别和低级别，返回一致性评分。

    用于区间套判断：大级别背驰在小级别先确认。
    """
    from easy_tdx.chanlun import ChanlunAnalyser
    from easy_tdx.chanlun.multi_level import MultiLevelAnalyser

    # 复用模块级白名单（原先这里漏了 MONTH/YEAR，导致多级别比 analyze 少两档）
    frequency_map = FREQUENCY_MAP
    # V720: category/low_level 不在白名单时显式 400（此前静默回落 daily/30min，
    # 与 analyze 同参 400 的行为不一致，且把错别字悄悄当成日线分析）。
    if req.category.upper() not in frequency_map:
        raise HTTPException(
            status_code=400,
            detail=f"非法周期 '{req.category}'，可选值: {', '.join(frequency_map)}",
        )
    low_raw = req.low_level or "MIN_30"  # 空低级别 = 默认 30min（保留原语义）
    if low_raw.upper() not in frequency_map:
        raise HTTPException(
            status_code=400,
            detail=f"非法低级别周期 '{req.low_level}'，可选值: {', '.join(frequency_map)}",
        )
    high_freq = frequency_map[req.category.upper()]
    low_freq = frequency_map[low_raw.upper()]

    symbol = f"{req.market}{req.code}"

    # 获取高级别数据（QFQ 前复权）
    # ⚠️ 与 analyze 保持同一取数路径：给了 start_date 就走 fetch_bars_range
    #    分页直达，否则 TDX 协议取数锚定最新 bar，历史窗口会被截断成空
    #    （实测：2024 上半年窗口下本端点曾返回 low_bi_count=0 ⇒ 区间套全 false）。
    if req.start_date:
        df_high = await fetch_bars_range(
            mac_client,
            client,
            req.market,
            req.code,
            req.category,
            start_date=req.start_date,
            end_date=req.end_date,
            max_bars=8000,
        )
    else:
        df_high = await fetch_qfq_klines(
            mac_client,
            client,
            req.market,
            req.code,
            req.category,
            req.start,
            req.count,
        )
    # 获取低级别数据（需要覆盖高级别的时间范围，否则最新高级别笔的低级别走势为空）
    # 每自然日对应的低级别 K 线数（A股一天约4小时交易时段）
    _bars_per_day = {
        "MIN_1": 240,
        "MIN_5": 48,
        "MIN_15": 16,
        "MIN_30": 8,
        "MIN_60": 4,
    }
    low_bars_per_day = _bars_per_day.get(req.low_level.upper(), 8)
    try:
        if df_high is not None and len(df_high) > 0:
            # 用高级别实际时间跨度估算低级别K线数量
            _date_col = "date" if "date" in df_high.columns else "datetime"
            _first = pd.to_datetime(df_high[_date_col].iloc[0])
            _last = pd.to_datetime(df_high[_date_col].iloc[-1])
            span_days = max((_last - _first).days, 1)
            trading_days = int(span_days / 7 * 5) + 1
            low_count = int(min(trading_days * low_bars_per_day + 200, 10000))
        else:
            low_count = int(min(req.count * low_bars_per_day + 200, 10000))
    except Exception:
        low_count = int(min(req.count * low_bars_per_day + 200, 10000))
    # 低级别同理：给了日期就走范围取数，保证与高级别窗口对齐
    if req.start_date:
        df_low = await fetch_bars_range(
            mac_client,
            client,
            req.market,
            req.code,
            req.low_level,
            start_date=req.start_date,
            end_date=req.end_date,
            max_bars=8000,
        )
    else:
        df_low = await fetch_qfq_klines(
            mac_client,
            client,
            req.market,
            req.code,
            req.low_level,
            req.start,
            low_count,
        )

    # ── 低级别 K 线截断（性能护栏）──────────────────────────────────
    # ChanlunAnalyser.process_klines 实测是**超线性**的：
    #   500 根 0.6s / 3976 根 30.1s（≈ n^1.6）。而 multi-level 一次要跑
    #   high + low 两份，low 不截断时整请求 ~32s，超过浏览器 fetch 的
    #   30s 上限（Moli 实测 "curl request failed ... after 30000ms"），
    #   前端只能拿到 failed to fetch —— 区间套功能等于不可用。
    # 区间套只需低级别在**高级别信号时间窗内**的结构，窗口外的历史
    # 不参与确认，截断不影响结论正确性。保留最近 LOW_MAX_BARS 根。
    if df_low is not None and len(df_low) > LOW_MAX_BARS:
        df_low = df_low.tail(LOW_MAX_BARS).reset_index(drop=True)

    # 分别分析
    high_analyser = ChanlunAnalyser(code=symbol, frequency=high_freq)
    low_analyser = ChanlunAnalyser(code=symbol, frequency=low_freq)
    high_result = high_analyser.process_klines(df_high)
    low_result = low_analyser.process_klines(df_low)

    # 多级别一致性分析
    mla = MultiLevelAnalyser()
    mla.add_level("high", high_analyser)
    mla.add_level("low", low_analyser)

    confluence = mla.compute_confluence_score("high", "low")

    # 真·区间套：用真实低周期数据对**每个**高级别买卖点做确认（缠论原文语义）。
    # 与上面 confluence（只比「最新一对」信号）区分开：这里逐信号、按行情时间
    # 对齐、防未来函数，且只在窗口内出现同方向背驰/买卖点时才算确认。
    qujiantao: list[dict[str, Any] | None] = []
    try:
        from easy_tdx.chanlun.qujiantao import compute_qujiantao_cross_period

        qujiantao = compute_qujiantao_cross_period(
            high_result.mmds,
            bis_low=low_result.bis,
            zss_low=low_result.zss,
            bcs_low=low_result.bcs,
            mmds_low=low_result.mmds,
        )
        # 同时挂到 MMD 上，供序列化与回测复用
        for m, qt in zip(high_result.mmds, qujiantao):
            m._qujiantao = qt
    except Exception:  # noqa: BLE001
        # 区间套是增强信息，失败不影响主流程
        qujiantao = []

    # 最后一级笔的低级别走势
    low_qs: dict[str, Any] = {}
    if high_result.bis:
        last_bi = high_result.bis[-1]
        low_qs = mla.query_low_level_qs("high", "low", last_bi)

    # 格式化结果（V-17: 提取到模块级 _multi_fmt_result 以纳入离线契约测试）
    fmt_result = _multi_fmt_result

    # V541: 高级别（日线）补基本面估值，与单级别 chanlun_analyze 对齐
    high_valuation: dict[str, Any] | None = None
    try:
        from easy_tdx.web.routers.diagnosis import _fetch_diagnosis_valuation

        latest_close = float(high_result.klines[-1].close) if high_result.klines else 0.0
        high_valuation = _fetch_diagnosis_valuation(req.market, req.code, latest_close)
    except Exception:  # noqa: BLE001
        high_valuation = None

    return cast(
        dict[str, Any],
        _to_json_safe(
            {
                "high_level": {
                    "category": req.category,
                    "result": {**fmt_result(high_result), "valuation": high_valuation},
                },
                "low_level": {
                    "category": req.low_level,
                    "result": fmt_result(low_result),
                },
                "confluence": confluence,
                "low_level_qs": low_qs,
                # 真·区间套（逐信号、真实低周期确认）；与 confluence 区分
                "qujiantao": qujiantao,
                # 次级别数据覆盖边界：供前端提示「该窗口无低周期数据」。
                # 低级别 K 线取自服务端分页，覆盖范围有限（实测 30min 仅回溯到
                # 2024-09）。窗口早于该边界时区间套必然全为 false —— 这不是
                # 模型失效，是数据覆盖不到，必须让用户看见。
                "low_level_coverage": _low_coverage(df_low),
            }
        ),
    )


def _low_coverage(df: Any) -> dict[str, Any]:
    """次级别数据的实际覆盖范围（供前端判断能否做区间套）。

    返回：
        {
          "bar_count": int,        # 窗口内低级别 K 线数
          "first": str | None,     # 最早时间
          "last": str | None,      # 最晚时间
          "has_data": bool,        # 是否有实质数据
        }
    """
    try:
        n = len(df)
    except Exception:  # noqa: BLE001
        return {"bar_count": 0, "first": None, "last": None, "has_data": False}
    if not n:
        return {"bar_count": 0, "first": None, "last": None, "has_data": False}

    def _fmt(v: Any) -> str | None:
        try:
            return str(pd.Timestamp(v))[:19]
        except Exception:  # noqa: BLE001
            return None

    col = "date" if "date" in getattr(df, "columns", []) else "datetime"
    try:
        first = _fmt(df[col].iloc[0])
        last = _fmt(df[col].iloc[-1])
    except Exception:  # noqa: BLE001
        first = last = None
    return {"bar_count": int(n), "first": first, "last": last, "has_data": n > 0}


class ChanlunRecommendRequest(ChanlunRequest):
    """缠论综合推荐请求。"""

    include_diagnosis: bool = Field(default=True, description="是否同时运行技术指标诊断")


@router.post("/chanlun/recommend")
async def chanlun_recommend(
    req: ChanlunRecommendRequest,
    client: Any = Depends(get_client),
    mac_client: Any | None = Depends(get_mac_client_optional),
) -> dict[str, Any]:
    """缠论综合推荐：结合 V4 买卖点质量评级 + 技术指标诊断，给出最终操作建议。

    输出包含：
    - 最高优先级买卖点（带质量评级）
    - 多级别一致性评分
    - 技术指标诊断摘要
    - 综合推荐动作（买入/持有/卖出）及理由
    """
    from easy_tdx.chanlun import ChanlunAnalyser, ChanlunConfig
    from easy_tdx.MyTT import KDJ as MYTT_KDJ
    from easy_tdx.MyTT import MA, MACD
    from easy_tdx.MyTT import RSI as MYTT_RSI

    symbol = f"{req.market}{req.code}"
    frequency_map: dict[str, str] = {
        "MIN_5": "5min",
        "MIN_15": "15min",
        "MIN_30": "30min",
        "MIN_60": "60min",
        "DAY": "daily",
        "WEEK": "weekly",
    }
    _ = frequency_map.get(req.category.upper(), "daily")

    # ── 1. 获取日线 K 线（缠论 + 诊断共用，QFQ 前复权）────────────
    df = await fetch_qfq_klines(mac_client, client, req.market, req.code, "DAY", 0, 500)
    if df is None or len(df) < 100:
        return {"error": "数据不足", "symbol": symbol}

    closes = df["close"].tolist()
    _ = df["vol"].tolist() if "vol" in df.columns else []
    highs = df["high"].tolist()
    lows = df["low"].tolist()
    latest_close = closes[-1]
    latest_date = str(df["date"].iloc[-1])[:10] if "date" in df.columns else ""

    # ── 2. 缠论 V4 分析 ──────────────────────────────────────────────
    analyser = ChanlunAnalyser(
        code=symbol, frequency="daily", config=ChanlunConfig(recursion_depth=req.recursion_depth)
    )
    chanlun_result = analyser.process_klines(df)
    mmds = chanlun_result.mmds

    # 取最高优先级买卖点（按质量评级排序）
    def _mmd_sort_key(m: Any) -> tuple[int, float, int]:
        q = getattr(m, "quality", None)
        grade = str(getattr(q, "grade", "")) if q else ""
        grade_val = {"S": 5, "A": 4, "B": 3, "C": 2, "D": 1}.get(grade, 0)
        return (grade_val, m.confidence, m.bi.index if m.bi else 0)

    sorted_mmds = sorted(mmds, key=_mmd_sort_key, reverse=True)
    best_mmd = sorted_mmds[0] if sorted_mmds else None
    # 最新买卖点（按笔索引，用于 V79/V80 摘要）
    latest_mmd = max(mmds, key=lambda m: m.bi.index if m.bi else 0) if mmds else None

    # 买卖点摘要
    mmd_summary = []
    for m in sorted_mmds[:10]:
        q = getattr(m, "quality", None)
        mmd_summary.append(
            {
                "type": m.mmd_type.value,
                "date": chanlun_result._fmt_dt(m.bi.end.k.date) if m.bi else None,
                "confidence": round(m.confidence, 2),
                "quality": {"grade": q.grade, "score": q.score, "reasons": q.reasons}
                if q
                else None,
                # V79 缠论增强条件
                "fractal_stability": getattr(m, "_fractal_stability_validation_v79", None),
                "distance_safety": getattr(m, "_mmd_distance_safety_v79", None),
                "multi_level_consistency": getattr(
                    m, "_multi_level_structure_consistency_v79", None
                ),
                "momentum_continuity": getattr(m, "_price_momentum_continuity_v79", None),
                # V80 缠论增强条件
                "zhongshu_distance": getattr(m, "_mmd_zhongshu_distance_v80", None),
                "volume_confirmation": getattr(m, "_volume_confirmation_v80", None),
                "ma_alignment": getattr(m, "_ma_alignment_strength_v80", None),
                "risk_reward": getattr(m, "_dynamic_risk_reward_v80", None),
            }
        )

    # ── 3. 技术指标诊断（轻量版）─────────────────────────────────────
    diag: dict[str, Any] = {}
    if req.include_diagnosis and len(closes) >= 60:
        dif, dea, macd_hist = MACD(closes, 12, 26, 9)
        ma5 = MA(closes, 5)
        ma10 = MA(closes, 10)
        ma20 = MA(closes, 20)
        ma60 = MA(closes, 60)
        k, d, j = MYTT_KDJ(closes, highs, lows, 9, 3, 3)
        rsi14 = MYTT_RSI(closes, 14)

        latest_dif = dif[-1] if len(dif) > 0 else 0
        latest_dea = dea[-1] if len(dea) > 0 else 0
        golden_cross = (dif[-2] <= dea[-2] and latest_dif > latest_dea) if len(dif) > 1 else False
        dead_cross = (dif[-2] >= dea[-2] and latest_dif < latest_dea) if len(dif) > 1 else False

        # 均线排列
        ma_bull = (
            all(v > 0 for v in (ma5[-1] - ma10[-1], ma10[-1] - ma20[-1], ma20[-1] - ma60[-1]))
            if all(x > 0 for x in [ma5[-1], ma10[-1], ma20[-1], ma60[-1]])
            else False
        )

        diag = {
            "macd": {
                "dif": round(latest_dif, 4),
                "dea": round(latest_dea, 4),
                "hist": round(macd_hist[-1], 4) if len(macd_hist) > 0 else 0,
                "golden_cross": golden_cross,
                "dead_cross": dead_cross,
                "above_zero": latest_dif > 0,
            },
            "kdj": {
                "k": round(k[-1], 2) if len(k) > 0 else 0,
                "d": round(d[-1], 2) if len(d) > 0 else 0,
                "j": round(j[-1], 2) if len(j) > 0 else 0,
                "overbought": (j[-1] if len(j) > 0 else 0) > 80,
                "oversold": (j[-1] if len(j) > 0 else 0) < 20,
            },
            "rsi": {
                "value": round(rsi14[-1], 2) if len(rsi14) > 0 else 50,
                "overbought": (rsi14[-1] if len(rsi14) > 0 else 50) > 70,
                "oversold": (rsi14[-1] if len(rsi14) > 0 else 50) < 30,
            },
            "ma_bullish_arrangement": ma_bull,
            "latest_close": round(latest_close, 2),
        }

    # ── 4. 综合推荐逻辑 ──────────────────────────────────────────────
    buy_signals: float = 0.0
    sell_signals: float = 0.0
    reasons_buy: list[str] = []
    reasons_sell: list[str] = []

    # 缠论信号打分
    if best_mmd:
        q = getattr(best_mmd, "quality", None)
        grade = q.grade if q else "C"
        conf = best_mmd.confidence
        mmd_type = best_mmd.mmd_type.value

        if "buy" in mmd_type:
            buy_signals += {"S": 3, "A": 2, "B": 1}.get(grade, 0)
            buy_signals += int(conf * 2)
            reasons_buy.append(f"缠论{mmd_type}({grade}级, 置信度{conf:.0%})")
        elif "sell" in mmd_type:
            sell_signals += {"S": 3, "A": 2, "B": 1}.get(grade, 0)
            sell_signals += int(conf * 2)
            reasons_sell.append(f"缠论{mmd_type}({grade}级, 置信度{conf:.0%})")

    # 诊断指标打分
    if diag:
        if diag.get("macd", {}).get("golden_cross"):
            buy_signals += 1
            reasons_buy.append("MACD 金叉")
        if diag.get("macd", {}).get("dead_cross"):
            sell_signals += 1
            reasons_sell.append("MACD 死叉")
        if diag.get("macd", {}).get("above_zero"):
            buy_signals += 0.5
        else:
            sell_signals += 0.5
        kdj = diag.get("kdj", {})
        if kdj.get("oversold"):
            buy_signals += 1
            reasons_buy.append("KDJ 超卖")
        elif kdj.get("overbought"):
            sell_signals += 1
            reasons_sell.append("KDJ 超买")
        rsi = diag.get("rsi", {})
        if rsi.get("oversold"):
            buy_signals += 0.5
            reasons_buy.append("RSI 超卖")
        elif rsi.get("overbought"):
            sell_signals += 0.5
            reasons_sell.append("RSI 超买")
        if diag.get("ma_bullish_arrangement"):
            buy_signals += 1
            reasons_buy.append("均线多头排列")
        else:
            sell_signals += 0.5

    net_score = buy_signals - sell_signals

    if net_score >= 4:
        action = "strong_buy"
        action_label = "强烈买入"
        action_color = "#22c55e"
    elif net_score >= 2:
        action = "buy"
        action_label = "买入"
        action_color = "#4ade80"
    elif net_score <= -4:
        action = "strong_sell"
        action_label = "强烈卖出"
        action_color = "#ef4444"
    elif net_score <= -2:
        action = "sell"
        action_label = "卖出"
        action_color = "#f87171"
    else:
        action = "hold"
        action_label = "持有观望"
        action_color = "#fbbf24"

    all_reasons = reasons_buy + reasons_sell
    reason_text = "；".join(all_reasons) if all_reasons else "无明显信号"

    # V79 一致性摘要（运行时挂载字段，类型不明，先归一为 str）
    _v79_mlsc = (
        getattr(latest_mmd, "_multi_level_structure_consistency_v79", None) if latest_mmd else None
    )
    _v79_mlsc_msg = str(getattr(_v79_mlsc, "msg", "")) if _v79_mlsc else ""
    _v79_consistency = _v79_mlsc_msg.split("consistent")[0] if _v79_mlsc_msg else None

    return cast(
        dict[str, Any],
        _to_json_safe(
            {
                "symbol": symbol,
                "date": latest_date,
                "close": round(latest_close, 2),
                "action": action,
                "action_label": action_label,
                "action_color": action_color,
                "net_score": round(net_score, 1),
                "buy_signals": round(buy_signals, 1),
                "sell_signals": round(sell_signals, 1),
                "reason": reason_text,
                "best_mmd": {
                    "type": best_mmd.mmd_type.value if best_mmd else None,
                    "date": chanlun_result._fmt_dt(best_mmd.bi.end.k.date)
                    if best_mmd and best_mmd.bi
                    else None,
                    "confidence": round(best_mmd.confidence, 2) if best_mmd else None,
                    "quality": {
                        "grade": getattr(getattr(best_mmd, "quality", None), "grade", None),
                        "score": getattr(
                            getattr(getattr(best_mmd, "quality", None), "score", None),
                            "score",
                            None,
                        ),
                    }
                    if best_mmd
                    else None,
                },
                "all_mmds": mmd_summary,
                "diagnosis": diag,
                # V79 缠论四维度量摘要（基于最新买卖点）
                "v79_summary": {
                    "fractal_status": getattr(
                        getattr(latest_mmd, "_fractal_stability_validation_v79", None),
                        "fractal_status",
                        None,
                    )
                    if latest_mmd
                    else None,
                    "safety_level": getattr(
                        getattr(latest_mmd, "_mmd_distance_safety_v79", None), "safety_level", None
                    )
                    if latest_mmd
                    else None,
                    "consistency_level": _v79_consistency,
                    "momentum_level": getattr(
                        getattr(latest_mmd, "_price_momentum_continuity_v79", None),
                        "momentum_level",
                        None,
                    )
                    if latest_mmd
                    else None,
                }
                if latest_mmd
                else None,
                # V80 缠论四维度量摘要（条件252-255，基于最新买卖点）
                "v80_summary": {
                    "zs_position": getattr(
                        getattr(latest_mmd, "_mmd_zhongshu_distance_v80", None), "zs_position", None
                    )
                    if latest_mmd
                    else None,
                    "volume_confirmed": f"{'↑' if getattr(getattr(latest_mmd, '_volume_confirmation_v80', None), 'price_trend', None) == 'up' else '↓'}{'↑' if getattr(getattr(latest_mmd, '_volume_confirmation_v80', None), 'volume_trend', None) == 'up' else '↓'}"
                    if latest_mmd and getattr(latest_mmd, "_volume_confirmation_v80", None)
                    else None,
                    "ma_alignment": getattr(
                        getattr(latest_mmd, "_ma_alignment_strength_v80", None),
                        "ma_alignment",
                        None,
                    )
                    if latest_mmd
                    else None,
                    "risk_level": getattr(
                        getattr(latest_mmd, "_dynamic_risk_reward_v80", None), "risk_level", None
                    )
                    if latest_mmd
                    else None,
                }
                if latest_mmd
                else None,
                # V81 缠论四维度量摘要（条件256-259，基于最新买卖点）
                "v81_summary": {
                    "regime": getattr(
                        getattr(latest_mmd, "_volatility_regime_transition_v81", None),
                        "regime",
                        None,
                    )
                    if latest_mmd
                    else None,
                    "strength_level": getattr(
                        getattr(latest_mmd, "_support_resistance_strength_v81", None),
                        "strength_level",
                        None,
                    )
                    if latest_mmd
                    else None,
                    "energy_zone": getattr(
                        getattr(latest_mmd, "_volume_price_energy_distribution_v81", None),
                        "energy_zone",
                        None,
                    )
                    if latest_mmd
                    else None,
                    "window_quality": getattr(
                        getattr(latest_mmd, "_signal_execution_window_v81", None),
                        "window_quality",
                        None,
                    )
                    if latest_mmd
                    else None,
                }
                if latest_mmd
                else None,
                # V82 缠论四维度量摘要（条件260-263，基于最新买卖点）
                "v82_summary": {
                    "age_label": getattr(
                        getattr(latest_mmd, "_mmd_age_decay_v82", None), "age_label", None
                    )
                    if latest_mmd
                    else None,
                    "retest_quality": getattr(
                        getattr(latest_mmd, "_breakout_retest_confirm_v82", None),
                        "retest_quality",
                        None,
                    )
                    if latest_mmd
                    else None,
                    "resonance": getattr(
                        getattr(latest_mmd, "_macd_multi_tf_resonance_v82", None), "resonance", None
                    )
                    if latest_mmd
                    else None,
                    "compression_level": getattr(
                        getattr(latest_mmd, "_volatility_compression_breakout_v82", None),
                        "compression_level",
                        None,
                    )
                    if latest_mmd
                    else None,
                }
                if latest_mmd
                else None,
            }
        ),
    )


def _fetch_request_klines(
    mac_client: Any,
    client: Any,
    market: str,
    code: str,
    category: str,
    start: int,
    count: int,
    start_date: str | None = None,
    end_date: str | None = None,
) -> Any:
    """V722: 按请求取 K 线；count>800 分流到 fetch_paged_bars 循环翻页。

    QFQ 口径与列规整同 fetch_qfq_klines；start>0 时不分页（历史偏移语义
    只在单页内有效，分页路径固定从最新 bar 往回凑 lookback）。

    V723: start_date 给定时走 fetch_bars_range——TDX 协议取数锚定最新 bar，
    历史日期窗口必须由服务端翻页直达，否则旧数据只取到「最新窗口」再被
    V599 截断成空。end_date 可省略（默认到最新 bar）。
    """
    if start_date:
        return fetch_bars_range(
            mac_client,
            client,
            market,
            code,
            category,
            start_date=start_date,
            end_date=end_date,
            max_bars=8000,
        )
    if count > 800 and start == 0:
        return fetch_paged_bars(mac_client, client, market, code, category, lookback=count)
    return fetch_qfq_klines(mac_client, client, market, code, category, start, count)


@router.post("/chanlun/train/session")
async def chanlun_train_session(
    req: ChanlunRequest,
    client: Any = Depends(get_client),
    mac_client: Any | None = Depends(get_mac_client_optional),
    difficulty: str = "medium",
    seed: int = 0,
    mode: str = "train",
    reveal_limit: int | None = None,
) -> dict[str, Any]:
    """创建缠论学习训练会话（P0：逐步揭示训练 + 逐笔复盘讲解）。

    返回：
    - bars：K 线数据（与 /bars 相同格式）
    - bis/xds/zss/mmds/fractals/bcs/boll：完整缠论结构
    - candidates：训练候选点（关键分型 + 买卖点信号），供前端逐步揭示时暂停提问
      [{index, date, kind: fractal|mmd, fx_type, signal: null | {type, confidence, grade}}]
    - mmd_outcomes：每个买卖点的信号后 5/10/20 日收益（复盘验证准确率用）

    Args:
        mode: ``"train"``（默认）启用防作弊闸门；``"review"`` 复盘模式，
            返回全量（需要未来收益做事后验证）。
        reveal_limit: 训练模式下「当前揭示到第几根 K 线（含）」。``mode=train``
            且本参数为 ``None`` 时按 **0** 处理（开局，不泄露任何答案）。
    """
    from easy_tdx.chanlun import ChanlunAnalyser, ChanlunConfig

    # 1. 取行情（QFQ 前复权，与 /bars 同一价格体系）
    # V722: count>800 时走服务端循环翻页（start 仅单页协议内有效）
    # V723: start_date 给定时走 fetch_bars_range（历史区间直达）
    df = await _fetch_request_klines(
        mac_client,
        client,
        req.market,
        req.code,
        req.category,
        req.start,
        req.count,
        start_date=req.start_date,
        end_date=req.end_date,
    )
    if df is None or len(df) == 0:
        return {"error": "未取到行情数据", "bars": [], "candidates": [], "mmd_outcomes": []}

    symbol = f"{req.market}{req.code}"
    frequency_map: dict[str, str] = {
        "MIN_1": "1min",
        "MIN_5": "5min",
        "MIN_15": "15min",
        "MIN_30": "30min",
        "MIN_60": "60min",
        "DAY": "daily",
        "WEEK": "weekly",
        "MONTH": "monthly",
        "YEAR": "yearly",
    }
    freq = frequency_map.get(req.category.upper(), req.category)
    analyser = ChanlunAnalyser(
        code=symbol, frequency=freq, config=ChanlunConfig(recursion_depth=req.recursion_depth, zs_from_xd=False)
    )
    result = analyser.process_klines(df)

    # 2. 组装训练会话负载（纯函数，可单测；V421 难度分级 + seed 复现）
    # V731 防作弊闸门：训练模式按 reveal_limit 截断答案与未来收益；
    # 复盘模式（mode=review）传 None 保持全量（F2 事后验证需要）。
    if mode == "review":
        _gate: int | None = None
    else:
        _gate = 0 if reveal_limit is None else max(int(reveal_limit), 0)
    payload = build_train_session_payload(
        result, df, req.category, difficulty, seed, reveal_limit=_gate
    )
    payload["code"] = symbol
    payload["frequency"] = freq
    return payload


@router.post("/chanlun/train/score")
async def chanlun_train_score(req: dict[str, Any]) -> dict[str, Any]:
    """提交一轮「逐步揭示训练」的成绩（V90：持久化 + 排行榜）。

    请求体：
    {
      "player_name": "学员甲",
      "score": 18,
      "total_asked": 8, "hit_count": 6, "hit_rate": 75.0,
      "code": "600519", "market": "SH", "category": "DAY", "count": 400,
      "extra": {"best_streak": 3}   // 可选
    }
    """
    from easy_tdx.web.train_store import TrainScore, get_score_store

    # V720: 数值字段前置校验（此前 score="abc" 等在 int()/float() 处抛
    # ValueError → 500；松散 dict 端点形状非法一律 400）。
    def _num_field(name: str, default: float) -> float:
        raw = req.get(name, default)
        if raw is None or raw == "":
            return default
        try:
            return float(raw)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"{name} 必须是数字") from None

    _num_field("score", 0)
    _num_field("hit_rate", 0)
    for _name in ("count", "total_asked", "hit_count"):
        raw = req.get(_name)
        if raw is None or raw == "":
            continue
        try:
            int(raw)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"{_name} 必须是整数") from None
        # 浮点整型检查：count=3.5 之类也应拒绝（int() 会静默截断 float，但 str "3.5" 抛错）
        if isinstance(raw, float) and not raw.is_integer():
            raise HTTPException(status_code=400, detail=f"{_name} 必须是整数")

    def _run() -> dict[str, Any]:
        store = get_score_store()
        rec = TrainScore(
            score=float(req.get("score", 0) or 0),
            player_name=str(req.get("player_name") or "学员").strip() or "学员",
            code=str(req.get("code") or "").strip(),
            market=str(req.get("market") or "SZ").upper()[:2],
            category=str(req.get("category") or "DAY").upper(),
            difficulty=str(req.get("difficulty") or "medium").lower(),
            count=int(req.get("count", 400) or 400),
            total_asked=int(req.get("total_asked", 0) or 0),
            hit_count=int(req.get("hit_count", 0) or 0),
            hit_rate=float(req.get("hit_rate", 0) or 0),
            extra=dict(req.get("extra") or {}),
        )
        store.add(rec)
        return {"ok": True, "id": rec.id, "score": rec.to_dict()}

    try:
        return await asyncio.to_thread(_run)
    except Exception as e:  # noqa: BLE001
        logger.exception("chanlun train score 失败")
        raise HTTPException(status_code=500, detail=f"提交成绩失败: {e}") from e


@router.get("/chanlun/train/leaderboard")
async def chanlun_train_leaderboard(
    limit: int = 20,
    category: str | None = None,
    difficulty: str | None = None,
) -> dict[str, Any]:
    """V90 训练排行榜：得分降序、命中率降序，可限定周期/难度。

    Query:
      limit=20   返回条数（默认 20）
      category=DAY  只返回该周期（缺省全部）
      difficulty=hard  只返回该难度（缺省全部）
    """
    from easy_tdx.web.train_store import get_score_store

    def _run() -> dict[str, Any]:
        store = get_score_store()
        rows = store.leaderboard(limit=limit, category=category, difficulty=difficulty)
        summary = store.summary(category=category, difficulty=difficulty)
        return {
            "items": [r.to_dict() for r in rows],
            "count": len(rows),
            "summary": summary,
        }

    try:
        return await asyncio.to_thread(_run)
    except Exception as e:  # noqa: BLE001
        logger.exception("chanlun train leaderboard 失败")
        raise HTTPException(status_code=500, detail=f"排行榜失败: {e}") from e


@router.get("/learn/progress")
async def learn_progress(player: str = "学员") -> dict[str, Any]:
    """V424: 学习进度聚合——按 category×difficulty 统计命中率/题数。"""
    from easy_tdx.web.train_store import get_score_store

    def _run() -> dict[str, Any]:
        store = get_score_store()
        data = store.progress(player)
        return {"player": player, "matrix": data["matrix"], "recent": data["recent"]}

    try:
        return await asyncio.to_thread(_run)
    except Exception as e:  # noqa: BLE001
        logger.exception("learn progress 失败")
        raise HTTPException(status_code=500, detail=f"学习进度失败: {e}") from e


@router.post("/learn/mistakes")
async def learn_mistakes_add(req: dict[str, Any]) -> dict[str, Any]:
    """V426: 记录一道错题（供复习）。"""
    from easy_tdx.web.train_store import get_score_store

    # V720: 错题字段形状校验——question_date/signal_type/user_choice/actual/
    # explanation 会原样入库 SQLite，传数组/对象会导致存储层类型混乱，
    # 这里限制为标量（str/int/float/None），非法 400。
    _SCALAR_OK = (str, int, float, type(None))
    for _name in (
        "player",
        "symbol",
        "category",
        "difficulty",
        "question_date",
        "signal_type",
        "user_choice",
        "actual",
        "explanation",
    ):
        if _name in req and not isinstance(req[_name], _SCALAR_OK):
            raise HTTPException(status_code=400, detail=f"{_name} 必须是标量（字符串/数字）")

    def _run() -> dict[str, Any]:
        get_score_store().add_mistake(req)
        return {"ok": True}

    try:
        return await asyncio.to_thread(_run)
    except Exception as e:  # noqa: BLE001
        logger.exception("learn mistakes add 失败")
        raise HTTPException(status_code=500, detail=f"记录错题失败: {e}") from e


@router.get("/learn/mistakes")
async def learn_mistakes_list(
    player: str = "学员",
    category: str | None = None,
) -> dict[str, Any]:
    """V426: 错题复习列表（按时间倒序，可限定玩家/周期）。"""
    from easy_tdx.web.train_store import get_score_store

    def _run() -> dict[str, Any]:
        rows = get_score_store().list_mistakes(player=player, category=category)
        return {"items": rows, "count": len(rows)}

    try:
        return await asyncio.to_thread(_run)
    except Exception as e:  # noqa: BLE001
        logger.exception("learn mistakes list 失败")
        raise HTTPException(status_code=500, detail=f"错题列表失败: {e}") from e


class ChanlunSignalStatsRequest(ChanlunRequest):
    """买卖点统计请求（/chanlun/signal-stats）。"""

    horizons: list[int] = Field(
        default=[5, 10, 20], description="前瞻根数列表"
    )


@router.post("/chanlun/signal-stats")
async def chanlun_signal_stats(
    req: ChanlunSignalStatsRequest,
    client: Any = Depends(get_client),
    mac_client: Any | None = Depends(get_mac_client_optional),
) -> dict[str, Any]:
    """买卖点**方向有效性**统计：胜不过随机就不算准。

    与「能不能赚钱」是两件事（行情好时模型错也能赚钱），本接口只回答
    「信号方向本身有没有信息量」：

      L1 方向对不对：买点后真涨？卖点后真跌？
      L2 胜过随机吗：与同数量随机入场对照（固定种子 ⇒ 可复现）
      L3 显著吗：配对 t 检验 + Bonferroni 多重比较校正

    统计口径复用 ``easy_tdx.backtest.signal_stats``（**唯一实现**），
    与 ``scripts/verify_chanlun_correctness.py`` 共用同一份代码，
    避免前端与审计脚本给出两个不同的数。

    ⚠️ 单标的样本量小，显著性判定会很保守（这是**特性**不是 bug）：
       想看可信结论请用脚本跑几十只票。前端应展示 sample_count 让用户
       自己判断这个数字可不可信 —— n=1 的「100% 命中率」是误导。
    """
    from easy_tdx.backtest.signal_stats import (
        bonferroni_crit,
        directional,
        is_buy_type,
        mean,
        paired_t,
        random_baseline,
    )
    from easy_tdx.chanlun import ChanlunAnalyser, ChanlunConfig

    df = await _fetch_request_klines(
        mac_client,
        client,
        req.market,
        req.code,
        req.category,
        req.start,
        req.count,
        start_date=req.start_date,
        end_date=req.end_date,
    )
    if df.empty:
        raise HTTPException(status_code=404, detail="未取到 K 线数据")

    freq = FREQUENCY_MAP.get(req.category, "daily")
    result = ChanlunAnalyser(
        code=f"{req.market}{req.code}",
        frequency=freq,
        config=ChanlunConfig(recursion_depth=req.recursion_depth),
    ).process_klines(df)

    closes = [float(k.close) for k in result.klines]
    horizons = [h for h in req.horizons if isinstance(h, int) and h > 0] or [5, 10, 20]

    by_type: dict[str, list[int]] = {}
    for m in result.mmds:
        bar = int(m.bi.end.bar_index) if m.bi else -1
        if bar >= 0:
            by_type.setdefault(str(m.mmd_type.value), []).append(bar)

    n_tests = max(len(by_type) * len(horizons), 1)
    crit = bonferroni_crit(n_tests)

    out: list[dict[str, Any]] = []
    for t, bars in sorted(by_type.items()):
        is_buy = is_buy_type(t)
        for h in horizons:
            # 前瞻收益（越界丢弃）
            fwd = []
            for b in bars:
                j = b + h
                if j < len(closes) and closes[b]:
                    fwd.append(closes[j] / closes[b] - 1.0)
            n = len(fwd)
            if n == 0:
                continue
            # 随机基准：同数量、固定种子（含类型与档位 ⇒ 可复现且互不相同）
            seed = (sum(ord(c) for c in t) * 31 + h * 7919) & 0xFFFFFFFF
            rb = random_baseline(closes, n, h, seed)
            sv = mean([directional(is_buy, x) for x in fwd])
            rv = mean([directional(is_buy, x) for x in rb]) if rb else 0.0

            # 单标的：用逐信号配对做 t 检验（同一档位下信号 vs 随机一一配对）
            k = min(len(fwd), len(rb))
            tv = 0.0
            if k >= 2:
                tv, diff = paired_t(
                    [directional(is_buy, x) for x in fwd[:k]],
                    [directional(is_buy, x) for x in rb[:k]],
                )
            else:
                diff = sv - rv

            out.append({
                "type": t,
                "horizon": h,
                "count": n,
                # ⚠️ 单位：小数（0.0388 == +3.88%），与 signal_ledger 一致
                "avg": sv,
                "rnd": rv,
                "excess": diff,
                "t": tv,
                "critical_t": crit,
                "significant": bool(tv > crit and sv > 0),
                "verdict": (
                    "✅ 方向对且显著" if (tv > crit and sv > 0)
                    else ("⚠️ 方向对但不显著" if (sv > 0 and diff > 0)
                          else "❌ 方向错/不显著")
                ),
            })

    return {
        "code": req.code,
        "market": req.market,
        "category": req.category,
        "kline_count": len(closes),
        "horizons": horizons,
        "n_tests": n_tests,
        "critical_t": crit,
        "stats": out,
        "note": (
            "单标的样本量有限，显著性判定偏保守；"
            "可信结论请用 scripts/verify_chanlun_correctness.py 跑几十只票。"
        ),
    }


# ── 缠论选股：按日期查找买点标的 ──────────────────────────────────────────
@router.get("/chanlun/pick")
async def chanlun_pick(
    date: str,
    category: str = "MIN_30",
) -> dict[str, Any]:
    """按日期查找有缠论买点的标的。

    从预计算的30min/日线缓存中读取，返回在指定日期有买入信号(1买/2买/3买)的标的，
    包含所属中枢的ZG(压力)/ZD(支撑)/ZZ(中线)数据。
    """
    import pickle
    from pathlib import Path

    data_dir = Path.cwd() / "audit_data"

    # 根据级别选择缓存
    if category.upper() in ("MIN_30", "30MIN", "30MIN"):
        cache_file = data_dir / "hybrid_30min_cache.pkl"
    else:
        cache_file = data_dir / "hybrid_analysis_cache.pkl"

    if not cache_file.is_file():
        return {"date": date, "category": category, "results": [], "error": "缓存不存在，请先运行分析"}

    try:
        with open(cache_file, "rb") as f:
            analyses = pickle.load(f)
    except Exception as e:
        return {"date": date, "category": category, "results": [], "error": f"缓存读取失败: {e}"}

    # 筛选买点
    results = []
    for a in analyses:
        cat = a.get("category")
        if cat not in ("tree", "grain"):
            continue  # 只推荐 tree/grain
        for s in a.get("signals", []):
            if not s.get("is_buy"):
                continue
            # 兼容 dt（30min缓存，字符串）和 date（日线缓存，Timestamp）两种格式
            sig_dt = s.get("dt", "")
            if not sig_dt:
                raw_date = s.get("date", "")
                sig_dt = str(raw_date) if raw_date else ""
            if date not in sig_dt:
                continue
            results.append({
                "code": a["code"],
                "market": a.get("market", "SH"),
                "category": cat,
                "signal_type": s["type"],
                "signal_dt": sig_dt,
                "confidence": s.get("confidence", 0),
                "zg": s.get("zg"),  # 压力位
                "zd": s.get("zd"),  # 支撑位
                "zz": s.get("zz"),  # 中枢中线
            })

    # 按信号类型排序: 1买 > 2买 > 3买
    type_order = {"1buy": 0, "2buy": 1, "3buy": 2}
    results.sort(key=lambda r: (type_order.get(r["signal_type"], 9), -r.get("confidence", 0)))

    # 统计可用日期
    all_dates = set()
    for a in analyses:
        for s in a.get("signals", []):
            if s.get("is_buy"):
                d = s.get("dt", "")
                if not d:
                    d = str(s.get("date", ""))
                d = d[:10]
                if d:
                    all_dates.add(d)
    available_dates = sorted(all_dates, reverse=True)

    return {
        "date": date,
        "category": category,
        "total": len(results),
        "results": results,
        "available_dates": available_dates[:30],  # 最近30个有买点的日期
    }


# ──────────────────────────────────────────────────────────────
# V810: 缠论分析缓存管理端点
# ──────────────────────────────────────────────────────────────


@router.delete("/chanlun/cache")
async def delete_chanlun_cache(
    market: str | None = Query(None, description="市场（留空删全部）"),
    code: str | None = Query(None, description="代码（留空删该市场全部或全部）"),
    category: str | None = Query(None, description="周期（留空删全部周期）"),
) -> dict[str, Any]:
    """删除缠论分析缓存。可按 market/code/category 精确删除，也可批量。"""
    from easy_tdx.web.chanlun_cache import ChanlunCache

    cache = ChanlunCache()
    if market and code and category:
        n = cache.delete(market, code, category)
    elif category and not market and not code:
        n = cache.delete_all(category=category)
    else:
        n = cache.delete_all()
    cache.close()
    return {"deleted": n}


@router.get("/chanlun/cache/list")
async def list_chanlun_cache(
    category: str | None = Query(None, description="按周期过滤"),
) -> dict[str, Any]:
    """列出所有缓存的缠论分析条目（含版本、创建时间）。"""
    from easy_tdx.web.chanlun_cache import ChanlunCache

    cache = ChanlunCache()
    entries = cache.list_entries(category=category)
    total = cache.count()
    cache.close()
    return {"total": total, "entries": entries}


# ──────────────────────────────────────────────────────────────
# V810: 图表数据端点 — 从 JSON K 线缓存读取（与选股缓存同源），
# 保证图表信号与选股结果一致。分析结果存 SQLite 缓存。
# ──────────────────────────────────────────────────────────────

_KLINE_DIR_30M = Path("audit_data") / "kline_30min"
_KLINE_DIR_DAY = Path("audit_data")


def _read_kline_json(market: str, code: str, category: str) -> pd.DataFrame | None:
    """从 JSON 缓存文件读取 K 线（与选股缓存同源）。"""
    if category.upper() == "MIN_30":
        fp = _KLINE_DIR_30M / f"{market.lower()}{code}_30min.json"
    elif category.upper() == "DAY":
        fp = _KLINE_DIR_DAY / f"{market.lower()}{code}_daily.json"
    else:
        return None
    if not fp.is_file():
        return None
    rows = _json.loads(fp.read_text("utf-8"))
    df = pd.DataFrame(rows)
    dt_col = "datetime" if "datetime" in df.columns else "date"
    df["datetime"] = pd.to_datetime(df[dt_col])
    df = df.sort_values("datetime").reset_index(drop=True)
    return df


@router.get("/chanlun/chart-data")
async def chanlun_chart_data(
    request: Request,
    market: str = Query(..., description="市场: SH, SZ"),
    code: str = Query(..., description="股票代码"),
    category: str = Query("MIN_30", description="周期: MIN_30, DAY"),
) -> dict[str, Any]:
    """获取图表数据：K线 + 完整缠论分析。

    从 JSON K 线缓存读取（与选股缓存同源），运行缠论分析，
    结果存入 SQLite 缓存（后续毫秒级读取）。
    保证图表信号与选股结果一致。

    在缓存分析的基础上，追加 TDX 最新 K 线（实时数据），
    让用户能看到信号之后的最新走势。
    """
    from easy_tdx.chanlun import ChanlunAnalyser, ChanlunConfig
    from easy_tdx.web.chanlun_cache import ChanlunCache
    from easy_tdx.web.schemas import DataFrameResponse

    # TDX 客户端（用于追加实时 K 线）
    tdx_client = getattr(request.app.state, "tdx_client", None)
    mac_client = getattr(request.app.state, "mac_client", None)

    cache = ChanlunCache()
    cached = cache.get(market, code, category)
    if cached is not None:
        cache.close()
        # 追加 TDX 最新 K 线
        cached["bars"] = await _append_tdx_bars(
            cached.get("bars", []), tdx_client, mac_client, market, code, category
        )
        cached["cached"] = True
        return cached

    # 读 K 线缓存
    df = _read_kline_json(market, code, category)
    if df is None or len(df) < 60:
        cache.close()
        raise HTTPException(404, f"无 K 线缓存: {market}{code} {category}")

    # 运行缠论分析（与选股缓存脚本同参数）
    freq = "30min" if category.upper() == "MIN_30" else "daily"
    cfg = ChanlunConfig(zs_from_xd=False)  # 笔构中枢，按原文
    analyser = ChanlunAnalyser(code=f"{market}{code}", frequency=freq, config=cfg)
    result = analyser.process_klines(df)

    d = result.to_dict()

    # 添加 bars（与分析同一 df）
    d["bars"] = DataFrameResponse.from_dataframe(df).data

    # 添加分型
    d["fractals"] = [
        {
            "fx_type": fx.fx_type.value,
            "date": result._fmt_dt(result._fx_anchor_datetime(fx)),
            "val": round(fx.val, 2),
            "index": fx.index,
            "bar_index": fx.bar_index,
        }
        for fx in result.fractals
    ]
    d["valid_fractals"] = result.valid_fractals_to_dict()

    # 信号准确度
    _attach_signal_accuracy(d, result)

    # 存入缓存（存 JSON 缓存原始 bars，不含 TDX 追加部分）
    try:
        cache.put(market, code, category, d)
    except Exception:  # noqa: BLE001
        pass
    cache.close()

    # 追加 TDX 最新 K 线
    d["bars"] = await _append_tdx_bars(
        d.get("bars", []), tdx_client, mac_client, market, code, category
    )
    d["cached"] = False
    return d


async def _append_tdx_bars(
    base_bars: list[dict],
    tdx_client: Any | None,
    mac_client: Any | None,
    market: str,
    code: str,
    category: str,
) -> list[dict]:
    """在 JSON 缓存 K 线末尾追加 TDX 实时 K 线（较新部分）。

    分析（笔/中枢/买卖点）基于 JSON 缓存，bar_index 不变；
    追加的 TDX bars 在末尾，无分析覆盖，但用户能看到最新走势。
    """
    if not base_bars:
        return base_bars
    if mac_client is None and tdx_client is None:
        return base_bars
    try:
        import asyncio as _asyncio
        from easy_tdx.web.convert import (
            adjust_from_str,
            category_from_str,
            market_from_str,
            market_value_from_str,
            period_times_from_category,
        )

        cat = category_from_str(category)
        if mac_client is not None:
            # MAC 客户端（与 /bars 端点一致），支持 QFQ 复权
            period, times = period_times_from_category(cat)
            tdx_df = await _asyncio.wait_for(
                mac_client.get_stock_kline(
                    market_value_from_str(market),
                    code,
                    period,
                    0,
                    800,
                    times,
                    adjust=adjust_from_str("QFQ"),
                    bar_time="start",
                ),
                timeout=5.0,
            )
            # 列规整：日线及以上 datetime→date
            from easy_tdx.models.enums import KlineCategory
            daily_plus = int(cat) >= int(KlineCategory.DAY)
            if tdx_df is not None and not tdx_df.empty:
                if "float_shares" in tdx_df.columns:
                    tdx_df = tdx_df.drop(columns=["float_shares"])
                if "datetime" in tdx_df.columns and daily_plus:
                    tdx_df["datetime"] = pd.to_datetime(tdx_df["datetime"]).dt.normalize()
                    tdx_df = tdx_df.rename(columns={"datetime": "date"})
        else:
            # 回退标准 TdxClient（无复权）
            tdx_df = await _asyncio.wait_for(
                tdx_client.get_security_bars(
                    market_from_str(market), code, cat, 0, 800
                ),
                timeout=5.0,
            )
        if tdx_df is None or len(tdx_df) == 0:
            return base_bars

        # JSON 缓存最后一根 K 线的 datetime
        last_dt = base_bars[-1].get("datetime") or base_bars[-1].get("date")
        if last_dt:
            last_dt = str(last_dt).replace("T", " ")[:16]

        # 筛选比 JSON 缓存更新的 TDX bars
        new_rows = []
        for _, row in tdx_df.iterrows():
            row_dt = str(row.get("datetime", "")).replace("T", " ")[:16]
            if row_dt > last_dt:
                new_rows.append({
                    "datetime": str(row["datetime"]),
                    "open": round(float(row["open"]), 2),
                    "high": round(float(row["high"]), 2),
                    "low": round(float(row["low"]), 2),
                    "close": round(float(row["close"]), 2),
                    "vol": float(row.get("vol", 0)),
                    "amount": float(row.get("amount", 0)),
                })

        if new_rows:
            return base_bars + new_rows
    except Exception:  # noqa: BLE001
        pass

    return base_bars
