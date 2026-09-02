"""模型可信度综合评分。

把一次历史回测里散落的验证信号汇总成一个 0-100 的可信度分数，让用户一眼判断
「这个模型/策略的历史回测成绩可不可信、可不可持续」，而不是逐项看胜率/命中率/
回撤。

融合三个维度（各占权重，最终 0-100）：
1. 择时准确度（signal_accuracy）：买入信号 5 根前瞻命中率相对随机入场基准的
   超额命中率。>0 说明择时有正贡献。
2. 稳健性（segment_robustness）：分段重跑的一致性与过拟合风险。多数分段正收益、
   跑赢买入持有、不过拟合 → 高分。
3. 绩效对比（performance + benchmark）：总收益、胜率、相对买入持有的超额收益。

输出 JSON 兼容结构：score(0-100)、grade(高/中/低)、components(各维度明细)、
verdict(一句结论)。无足够数据时给出保守的低分与说明，避免过度信任。
"""

from __future__ import annotations

from typing import Any

# 各维度权重（合计 1.0）
W_ACCURACY = 0.4
W_ROBUSTNESS = 0.35
W_PERFORMANCE = 0.25


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _accuracy_score(signal_accuracy: dict[str, Any] | None) -> tuple[float, dict[str, Any]]:
    """择时准确度维度分（0-1）。

    取买入信号 5 根前瞻超额命中率（缺则回退 3/10）。超额命中率映射：
    +0.15 → 1.0（明显优于随机），0 → 0.5（与随机相当），-0.15 → 0.0。
    """
    if not signal_accuracy:
        return 0.3, {"note": "无信号准确度数据", "score": 0.3}
    buy = signal_accuracy.get("buy") or {}
    horizons = buy.get("horizons") or {}
    stats = horizons.get("5") or horizons.get("3") or horizons.get("10")
    if not stats or stats.get("count", 0) == 0:
        return 0.3, {"note": "买入信号样本不足", "score": 0.3}
    excess = float(stats.get("excess_hit_rate", 0.0))
    hit = float(stats.get("hit_rate", 0.0))
    baseline = float(stats.get("baseline_hit_rate", 0.0))
    score = _clamp(0.5 + excess / 0.15 * 0.5)
    return score, {
        "score": score,
        "hit_rate": hit,
        "baseline_hit_rate": baseline,
        "excess_hit_rate": excess,
        "n": int(stats.get("count", 0)),
    }


def _robustness_score(segment_robustness: dict[str, Any] | None) -> tuple[float, dict[str, Any]]:
    """稳健性维度分（0-1）。

    根据分段重跑的一致性：过拟合风险一票否决扣到底；否则按「正收益段占比 +
    跑赢买入持有占比」综合。
    """
    if not segment_robustness:
        return 0.5, {"note": "未做分段稳健性检查", "score": 0.5}
    overfit = bool(segment_robustness.get("overfit_likely", False))
    cons = segment_robustness.get("consistency") or {}
    pos_ratio = float(cons.get("positive_segment_ratio", 0.0))
    beat_ratio = float(cons.get("beats_buy_hold_ratio", 0.0))
    analyzed = int(cons.get("segments_analyzed", 0))
    if overfit:
        score = 0.2
    elif analyzed >= 2:
        score = _clamp(0.3 + 0.7 * (0.6 * pos_ratio + 0.4 * beat_ratio))
    else:
        score = 0.4
    return score, {
        "score": score,
        "overfit_likely": overfit,
        "positive_segment_ratio": pos_ratio,
        "beats_buy_hold_ratio": beat_ratio,
        "segments_analyzed": analyzed,
    }


def _performance_score(
    performance: dict[str, Any] | None,
    signal_accuracy: dict[str, Any] | None,
) -> tuple[float, dict[str, Any]]:
    """绩效对比维度分（0-1）。

    结合总收益、胜率、相对买入持有的 alpha（若 signal_accuracy 带 benchmark）。
    """
    if not performance:
        return 0.3, {"note": "无绩效数据", "score": 0.3}
    total_return = float(performance.get("total_return", 0.0))
    win_rate = float(performance.get("win_rate", 0.0))
    alpha = 0.0
    if signal_accuracy:
        bench = signal_accuracy.get("benchmark") or {}
        if isinstance(bench, dict):
            alpha = float(bench.get("alpha", 0.0) or 0.0)
    # 收益分：正收益给 0.5 起，alpha>0 再叠加
    ret_score = _clamp(0.5 + total_return * 2.0)
    win_score = _clamp(win_rate / 0.6)  # 胜率 60% 满分
    alpha_score = _clamp(0.5 + alpha * 2.0)
    score = _clamp(0.5 * ret_score + 0.3 * win_score + 0.2 * alpha_score)
    return score, {
        "score": score,
        "total_return": total_return,
        "win_rate": win_rate,
        "alpha": alpha,
    }


def compute_model_trust(
    performance: dict[str, Any] | None,
    signal_accuracy: dict[str, Any] | None,
    segment_robustness: dict[str, Any] | None,
) -> dict[str, Any]:
    """计算模型可信度综合评分。

    Args:
        performance: BacktestResult.performance（总收益/胜率等）
        signal_accuracy: V95 的 signal_accuracy 报告
        segment_robustness: V97 的 segment_robustness 报告

    Returns:
        dict：{"score": 0-100, "grade": "高"|"中"|"低",
               "components": {accuracy/robustness/performance 各维度},
               "verdict": str}
    """
    acc_score, acc_comp = _accuracy_score(signal_accuracy)
    rob_score, rob_comp = _robustness_score(segment_robustness)
    perf_score, perf_comp = _performance_score(performance, signal_accuracy)

    score01 = W_ACCURACY * acc_score + W_ROBUSTNESS * rob_score + W_PERFORMANCE * perf_score
    score100 = round(_clamp(score01) * 100, 1)

    if score100 >= 70:
        grade = "高"
    elif score100 >= 50:
        grade = "中"
    else:
        grade = "低"

    verdict = _build_verdict(score100, grade, acc_comp, rob_comp, perf_comp)

    return {
        "score": score100,
        "grade": grade,
        "components": {
            "accuracy": acc_comp,
            "robustness": rob_comp,
            "performance": perf_comp,
        },
        "verdict": verdict,
    }


def _build_verdict(
    score: float,
    grade: str,
    acc: dict[str, Any],
    rob: dict[str, Any],
    perf: dict[str, Any],
) -> str:
    """根据各维度生成一句人类可读结论。"""
    parts: list[str] = [f"综合可信度 {grade}（{score:.0f}/100）"]
    if "excess_hit_rate" in acc:
        exc = float(acc["excess_hit_rate"])
        if exc > 0.05:
            parts.append("择时命中率明显优于随机")
        elif exc > 0:
            parts.append("择时略优于随机")
        elif exc > -0.05:
            parts.append("择时与随机相当")
        else:
            parts.append("择时弱于随机")
    if "overfit_likely" in rob:
        if rob["overfit_likely"]:
            parts.append("存在过拟合/行情依赖风险")
        elif int(rob.get("segments_analyzed", 0)) >= 2:
            parts.append("分段表现较稳健")
    if "alpha" in perf:
        alpha = float(perf["alpha"])
        parts.append(f"相对买入持有超额 {alpha:+.1%}")
    return "；".join(parts) + "。"


# ── 组合/多标的可信度评分（V103）─────────────────────────────────────────────


def compute_portfolio_trust(accuracy_summary: dict[str, Any] | None) -> dict[str, Any]:
    """基于 V99 的组合准确度聚合结果计算组合级可信度分。

    输入为 aggregate_portfolio_accuracy 的输出（accuracy_summary）：
      {"portfolio": {symbols, avg_hit_rate, avg_excess_hit_rate, avg_win_rate,
                     avg_total_return, avg_sharpe, positive_symbols, hit_above_baseline,
                     symbols_with_accuracy}, "verdict": str, "symbols": [...]}

    与单标的 compute_model_trust 同一套权重哲学，但三个维度改用组合聚合口径：
      1. 择时准确度（0.4）：组合加权平均超额命中率（5 根 vs 随机基准）
      2. 稳健性（0.35）：跨标的一致性——命中率高于随机基准的标的比例 + 正收益标的占比
         （组合层面用「标的间一致性」代替单标的的「时间分段一致性」）
      3. 绩效对比（0.25）：组合加权平均收益/胜率

    Returns:
        dict：{"score": 0-100, "grade": 高/中/低, "components": {...}, "verdict": str}
    """
    if not accuracy_summary:
        return {
            "score": 37.0,
            "grade": "低",
            "components": {
                "accuracy": {"note": "无组合准确度数据", "score": 0.3},
                "robustness": {"note": "无组合稳健性数据", "score": 0.5},
                "performance": {"note": "无组合绩效数据", "score": 0.3},
            },
            "verdict": "综合可信度 低（37/100）；无组合准确度数据。",
        }

    portfolio = accuracy_summary.get("portfolio") or {}
    n_symbols = int(portfolio.get("symbols", 0))
    if n_symbols == 0:
        return {
            "score": 37.0,
            "grade": "低",
            "components": {
                "accuracy": {"note": "无标的", "score": 0.3},
                "robustness": {"note": "无标的", "score": 0.3},
                "performance": {"note": "无标的", "score": 0.3},
            },
            "verdict": "综合可信度 低（37/100）；组合无标的。",
        }

    # 1. 择时准确度：组合加权平均超额命中率
    avg_excess = float(portfolio.get("avg_excess_hit_rate", 0.0) or 0.0)
    with_acc = int(portfolio.get("symbols_with_accuracy", 0))
    if with_acc > 0:
        acc_score = _clamp(0.5 + avg_excess / 0.15 * 0.5)
    else:
        acc_score = 0.3
    acc_comp = {
        "score": acc_score,
        "avg_excess_hit_rate": avg_excess,
        "avg_hit_rate": float(portfolio.get("avg_hit_rate", 0.0) or 0.0),
        "symbols_with_accuracy": with_acc,
    }

    # 2. 稳健性：跨标的一致性（命中率高于基准的比例 + 正收益占比）
    hit_above = int(portfolio.get("hit_above_baseline", 0))
    positive = int(portfolio.get("positive_symbols", 0))
    above_ratio = hit_above / n_symbols if n_symbols else 0.0
    positive_ratio = positive / n_symbols if n_symbols else 0.0
    if with_acc >= 1:
        rob_score = _clamp(0.3 + 0.7 * (0.6 * positive_ratio + 0.4 * above_ratio))
    else:
        rob_score = 0.4
    rob_comp = {
        "score": rob_score,
        "hit_above_baseline": hit_above,
        "positive_symbols": positive,
        "symbols": n_symbols,
    }

    # 3. 绩效对比：组合加权平均收益/胜率
    avg_ret = float(portfolio.get("avg_total_return", 0.0) or 0.0)
    avg_win = float(portfolio.get("avg_win_rate", 0.0) or 0.0)
    ret_score = _clamp(0.5 + avg_ret * 2.0)
    win_score = _clamp(avg_win / 0.6)
    perf_score = _clamp(0.6 * ret_score + 0.4 * win_score)
    perf_comp = {"score": perf_score, "avg_total_return": avg_ret, "avg_win_rate": avg_win}

    score01 = W_ACCURACY * acc_score + W_ROBUSTNESS * rob_score + W_PERFORMANCE * perf_score
    score100 = round(_clamp(score01) * 100, 1)
    if score100 >= 70:
        grade = "高"
    elif score100 >= 50:
        grade = "中"
    else:
        grade = "低"

    verdict = _build_portfolio_verdict(score100, grade, acc_comp, rob_comp, perf_comp, n_symbols)

    return {
        "score": score100,
        "grade": grade,
        "components": {
            "accuracy": acc_comp,
            "robustness": rob_comp,
            "performance": perf_comp,
        },
        "verdict": verdict,
    }


def _build_portfolio_verdict(
    score: float,
    grade: str,
    acc: dict[str, Any],
    rob: dict[str, Any],
    perf: dict[str, Any],
    n_symbols: int,
) -> str:
    """根据组合各维度生成一句人类可读结论。"""
    parts: list[str] = [f"组合可信度 {grade}（{score:.0f}/100）"]
    exc = float(acc.get("avg_excess_hit_rate", 0.0) or 0.0)
    if int(acc.get("symbols_with_accuracy", 0)) > 0:
        if exc > 0.05:
            parts.append("组合命中率明显优于随机")
        elif exc > 0:
            parts.append("组合略优于随机")
        elif exc > -0.05:
            parts.append("组合与随机相当")
        else:
            parts.append("组合弱于随机")
    above = int(rob.get("hit_above_baseline", 0))
    pos = int(rob.get("positive_symbols", 0))
    parts.append(f"{pos}/{n_symbols} 标的正收益")
    if int(acc.get("symbols_with_accuracy", 0)) > 0:
        parts.append(f"{above}/{n_symbols} 标的命中率高于基准")
    avg_ret = float(perf.get("avg_total_return", 0.0) or 0.0)
    parts.append(f"加权平均收益 {avg_ret:+.1%}")
    return "；".join(parts) + "。"
