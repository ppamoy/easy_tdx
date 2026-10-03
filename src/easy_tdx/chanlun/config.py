"""缠论计算配置项。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ChanlunConfig:
    """缠论计算配置。

    所有配置项均有默认值，开箱即用。
    """

    # ── 笔配置 ──────────────────────────────────────────────────────────
    # "new" 新笔（分型之间至少1根独立K线，默认/推荐）、"old" 老笔（至少3根）。
    # "simple" 为 legacy 简化口径（仅显式配置时启用，不推荐；见 find_bis 告警）。
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
    # V733：ZG/ZD 由前几笔的重叠确定后冻结。
    #   3 = 缠论原文口径（第17/20/35课，**默认**）：中枢 = **三个**连续次级别
    #       走势的重叠区间，故 ZG/ZD 应由前三笔共同确定
    #       （ZG=min(g1,g2,g3)，ZD=max(d1,d2,d3)），第4笔起只更新 GG/DD。
    #   2 = 旧行为（V730 起）：ZG/ZD 由前两笔确定，第3笔起只更新 GG/DD。
    #   实测（V733，30 只日线 557 个含≥3笔的中枢）：
    #       改 3 后 52.2% 的中枢**变窄**（中位 -4.0%，均值 -19.0%），
    #       47.8% 不变，**0% 变宽**；按 3 笔规则**无**中枢变为非法。
    #       ⇒ 旧行为（2）让中枢系统性**偏宽**（高估震荡区间），
    #         3 买/3 卖 依赖 ZG/ZD 的突破/回踩阈值因此偏松。
    zs_zd_lines: int = 3

    # ── 分型配置 ────────────────────────────────────────────────────────
    # 是否使用严格分型（顶底不能互相包含）
    fx_strict: bool = True

    # ── 笔区间配置 ──────────────────────────────────────────────────────
    # "dd" 用顶底点, "ck" 用缠论K线高低, "k" 用原始K线高低
    bi_qujian: str = "dd"

    # ── 线段配置 ────────────────────────────────────────────────────────
    # 是否支持笔破坏（线段原文口径，默认开启）
    xd_bi_pohuai: bool = True

    # 是否启用多级别递归：以线段为高级别「笔」，计算高级别线段/线段中枢/背驰/
    # 三类买卖点。
    multi_level: bool = True
    # 多级别递归深度：>=1。depth=1 只递归到「线段级别」；depth>=2 会把上一级
    # 线段继续当作更高级别「笔」逐级递归（第 2 级、第 3 级…）。实际产出的级别
    # 数受数据（每级线段数量 >= 3）约束，可少于该值，默认 1 保持历史行为。
    recursion_depth: int = 1

    # 1买/1卖 是否启用「结构去重启发式」（相邻间隔5笔 + 3%反弹/回落）。
    # 默认 True；设为 False 时严格按缠论原文（趋势背驰点即可），不去重。
    mmd_1st_dedup: bool = True

    # 3类买卖点是否启用「技术指标增强过滤」（RSI/KDJ/BOLL/量能/MACD零轴等）。
    # 默认 False：严格遵循缠论原文，3买=突破中枢上沿+回踩不破、3卖=跌破下沿+反抽不破，
    # 技术指标只作增强信息；True 时启用旧版增强过滤（信号更稀疏）。
    mmd_3rd_type_technical: bool = False

    # 3类买卖点：离开笔之后允许回抽/反抽笔跨越的原始K线根数上限。
    #
    # 缠论原文对此**没有任何根数限制**——只要求「离开中枢后的次级别回抽不回到
    # 中枢区间」。此处保留窗口仅为抑制极长回抽产生的噪声信号，属工程启发式。
    # 旧的硬编码 15 根误杀严重：实测日线约 14.5%~21.5% 的笔长度 > 15 根
    # （scripts/audit_3rd_type_accuracy.py + 随机游走 1184 笔统计），
    # 周线/月线上同级别回抽对应的原始K线数放大约 5/20 倍，几乎全部失效。
    # 默认改为 0 = 不限制（纯原文口径）；设为正整数可按周期收紧。
    mmd_3rd_retest_max_bars: int = 0

    # 背驰力度是否按窗口根数归一（消除长度偏置）。
    #
    # 直接取 MACD 柱面积之和会让**长而慢**的段累积出更大的数值，与缠论
    # 「力度衰竭」相反。实测同一跌幅 2.5：8 根→1.0232、15 根→1.6724、
    # 25 根→1.9556（越慢越"有力"），导致缓慢下跌的背驰段被判为力度更大
    # 而漏掉 1买。归一后单位根力度单调下降（0.1137/0.1045/0.0752/0.0419）。
    #
    # ⚠️ 关于默认值（V731 实测修正：原先写的「建议新项目开启」并无数据支撑）：
    #    扫描「结构完全相同、只改背驰离开段行进根数」的教科书形态
    #    （均为 5 笔 down、2 个中枢、同一最低价），两者各有盲区，**不存在
    #    严格更优的一方**：
    #        两者都检出 : n = 52..80（慢跌）
    #        仅 raw    : n = 8, 12（急跌）
    #        仅 归一   : n = 20..48（缓跌 = 教科书「背驰」典型形态）
    #        两者都漏  : n = 16
    #    归一救回了教科书最典型的 20~48 根缓跌背驰，代价是在极急跌（8~12 根）
    #    上漏判。故**默认保持 False**，由调用方按交易风格（急跌 vs 缓跌）选择。
    #
    #    为什么会这样（精确比值，背驰段笔7 / 进入段笔3，阈值 0.8）：
    #        n=12 → raw 0.795 ✓  |  归一 0.918       |  振幅 0.839
    #        n=16 → raw 0.954    |  归一 0.841       |  振幅 0.839  ← 三者都不过
    #        n=20 → raw 1.044    |  归一 0.746 ✓     |  振幅 0.839
    #        n=30 → raw 1.059    |  归一 0.512 ✓     |  振幅 0.839
    #        n=40 → raw 0.949    |  归一 0.347 ✓     |  振幅 0.839
    #    可见 raw 只覆盖了最急的那一段，归一覆盖了中等以上；振幅口径对该形态
    #    恒定 0.839（>0.8），**任何 n 都判不出**——所以它不是补救方案。
    #    n=16 三者都不过，是因为这些口径在该处确实接近等价（比值 0.84~0.95），
    #    属真正的边界情形，需要更本质的力度定义（如单位时间价格变化率），
    #    而不是在这三个黄口之间二选一。见
    #    tests/unit/test_chanlun_v731_beichi_leaving_bi.py::TestBiForceNormalizeTradeoff
    bi_force_normalize: bool = False

    # 2买/2卖：回调笔（反弹笔）终点距离开笔终点的原始K线根数上限。
    #
    # 缠论原文对 2买/2卖 只要求「1买后回调不创新低（+ 幅度约束）」，
    # **无任何K线数限制**。旧的硬编码 15（2买/2卖）/ 20（类二买/类二卖）
    # 是纯工程启发式：实测静默吞掉 28% 的候选（5 个 fixture 共 46 个相邻笔
    # 间隔中 13 个 > 15 根）；且它是**绝对根数**，同一形态在周线/月线上对应
    # 的间隔只有日线的约 1/5、1/20，跨周期含义完全不同。
    # 默认 0 = 不限制（纯原文口径）；设为正整数可按周期收紧。
    mmd_2nd_span_max_bars: int = 0

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
            "zs_zd_lines": self.zs_zd_lines,
            "fx_strict": self.fx_strict,
            "bi_qujian": self.bi_qujian,
            "xd_bi_pohuai": self.xd_bi_pohuai,
            "multi_level": self.multi_level,
            "recursion_depth": self.recursion_depth,
            "mmd_1st_dedup": self.mmd_1st_dedup,
            "mmd_3rd_type_technical": self.mmd_3rd_type_technical,
            "mmd_3rd_retest_max_bars": self.mmd_3rd_retest_max_bars,
            "bi_force_normalize": self.bi_force_normalize,
            "mmd_2nd_span_max_bars": self.mmd_2nd_span_max_bars,
            "macd_fast": self.macd_fast,
            "macd_slow": self.macd_slow,
            "macd_signal": self.macd_signal,
        }
