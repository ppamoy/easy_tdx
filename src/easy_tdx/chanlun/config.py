"""缠论计算配置项。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ChanlunConfig:
    """缠论计算配置。

    所有配置项均有默认值，开箱即用。
    """

    # ── 笔配置 ──────────────────────────────────────────────────────────
    # "new" 新笔（分型之间至少1根独立K线），"old" 老笔（分型之间至少3根），"simple" 简单笔
    bi_type: str = "new"
    # 是否跳过弱笔（价格变动 < 0.1% 的笔）
    bi_weak_skip: bool = False
    # 是否强制要求端点分型在后续K线得到确认后方可成笔。
    # 默认 False：即使分型暂未确认也保留真实转折点，避免静默丢弃极值导致
    # 笔/线段画不到最高/最低点（用户反馈的精度问题核心）。
    bi_fractal_confirm: bool = False

    # ── 中枢配置 ────────────────────────────────────────────────────────
    # "standard" 标准中枢，"dn" 段内中枢
    zs_type: str = "standard"
    # 中枢最少重叠线段数（标准中枢 = 3）
    zs_min_lines: int = 3
    # 中枢区间来源: "dd" 用顶底点, "ck" 用缠论K线高低, "k" 用原始K线高低
    zs_qujian: str = "dd"

    # ── 分型配置 ────────────────────────────────────────────────────────
    # 是否使用严格分型（顶底不能互相包含）
    fx_strict: bool = True

    # ── 笔区间配置 ──────────────────────────────────────────────────────
    # "dd" 用顶底点, "ck" 用缠论K线高低, "k" 用原始K线高低
    bi_qujian: str = "dd"

    # ── 线段配置 ────────────────────────────────────────────────────────
    # 是否支持笔破坏
    xd_bi_pohuai: bool = False

    # 1买/1卖 是否启用「结构去重启发式」（相邻间隔5笔 + 3%反弹/回落）。
    # 默认 True；设为 False 时严格按缠论原文（趋势背驰点即可），不去重。
    mmd_1st_dedup: bool = True

    # 3类买卖点是否启用「技术指标增强过滤」（RSI/KDJ/BOLL/量能/MACD零轴等）。
    # 默认 False：严格遵循缠论原文，3买=突破中枢上沿+回踩不破、3卖=跌破下沿+反抽不破，
    # 技术指标只作增强信息；True 时启用旧版增强过滤（信号更稀疏）。
    mmd_3rd_type_technical: bool = False

    # ── MACD 配置 ───────────────────────────────────────────────────────
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9

    def to_dict(self) -> dict[str, object]:
        return {
            "bi_type": self.bi_type,
            "bi_weak_skip": self.bi_weak_skip,
            "bi_fractal_confirm": self.bi_fractal_confirm,
            "zs_type": self.zs_type,
            "zs_min_lines": self.zs_min_lines,
            "zs_qujian": self.zs_qujian,
            "fx_strict": self.fx_strict,
            "bi_qujian": self.bi_qujian,
            "xd_bi_pohuai": self.xd_bi_pohuai,
            "macd_fast": self.macd_fast,
            "macd_slow": self.macd_slow,
            "macd_signal": self.macd_signal,
        }