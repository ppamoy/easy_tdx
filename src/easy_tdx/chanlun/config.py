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
    # V735/V850 原文第33课：「中枢的延伸不能超过5段，一旦出现6段的延伸，
    # 加上形成中枢本身那三段，就构成更大级别的中枢了。」
    # ⇒ 上限 = 3 + 6 = **9 段**（总段数；第32课算术自证 + 第59/36/99课一致）。
    # 原文的"升级"需要走势类型级递归（架构级改动），代码用笔级近似。
    #
    # ⚠️ V850 更正：原注释把 True 写成"原文口径"，**是错的**。
    #   **zs_no_hard_close=True（默认）＝ 偏离原文的工程折衷**：
    #     不在9段时硬关闭中枢，让其自然延伸直到笔真正离开[ZD,ZG]。
    #     实测偏离（scripts/guard_chanlun_lesson33_zs_extension_v850.py，
    #     12 只真实日线 332 个中枢）：**81 个（24.4%）超过 9 段，最长 37 段**。
    #     收益侧实测（6 只日线）：重叠从 20→1 对（95%减少）、
    #     中枢从 100→80（20%减少，消除了人工拆分产生的假"趋势"）。
    #   zs_no_hard_close=False：9 段硬关闭（工程上限；数字贴近第33课，
    #     但仍非原文的"升级为更大级别中枢"语义）。
    #
    # V851 决策（与 zs_merge_overlap=False 配套）：
    #   原默认 True（不硬关闭）实测 24.4% 中枢超 9 段、最长 37 段。
    #   单独改成 False 不够（>9段仍有 17.8%、最长 32 段），因为硬关闭
    #   造出的相邻中枢会被 `_merge_overlapping_zss` 立刻重新拼成长中枢
    #   （合并触发对数从 3 暴涨到 77）。
    #   两项配套后（scripts/audit_g1_merge_overlap_impact.py，12 只日线 332 中枢）：
    #     >9段：81 (24.4%) → 0 (0.0%)
    #     最长：37 段 → 9 段（= 第33课上限 3+6）
    #     信号：658 → 650（-1.2%，可接受）
    #   按 AGENTS.md §4「改开关必须测两侧」：
    #     False（新默认）= 符合原文；True = 偏离原文的工程折衷，显式可开。
    zs_no_hard_close: bool = False
    # V842 重核（原判定错误，已修正）：第91课「笔是不能构成中枢的」
    #   禁的是**同级别笔**构**同级别**中枢。
    #   第83课 line 4：「我们是可以设计这样的程序，也就是用笔当成构成
    #     最小中枢的零件，但这样构造出来的系统，其稳定性极差。」
    #     ⇒ 第83课说笔**可以**构中枢，反对理由是稳定性（一笔受错单/
    #        老鼠仓等偶然因素影响大），不是逻辑不可能。
    #   第53课 line 6：「站在30分钟级别的角度，5分钟的走势都可以看成
    #     就是一个线段」⇒ **笔/线段是相对级别的**。
    #   第17课 line 20：「被至少三个连续次级别走势类型所重叠的部分」
    #     ⇒ 用次级别周期的笔构大级别中枢，那些笔就是次级别走势，
    #        原文允许。所以 find_zss(bis) 本身**不是原文偏离**。
    # 真正的缺口：第17课「次级别走势类型重叠」未精确实现
    #   （zs_cross_timeframe=True 是近似，默认 False）——
    #   这与第33课 8 段上限超限是**同一个架构缺口**（缺次级别递归）。
    zs_from_xd: bool = False
    # V851 重核（推翻 V735 的"第19课定理一"引文）：
    #
    # 原注释引「第19课定理一：前后两个中枢不能有任何重叠，否则就只是一个
    # 更大级别的盘整」——该句在 108 课原文里 **grep 不到**。已全文检索
    # 「不能有任何重叠」，唯一命中是 **第20课 line 4**：
    #   「而在趋势里，同级别的前后缠中说禅走势中枢是不能有任何重叠的……
    #     如果三个连续次级别走势类型的重叠区间虽然不和前面的走势中枢没有
    #     任何重叠，但围绕该中枢产生的波动触及前面走势中枢延续时的某个
    #     瞬间波动区间，这时候，就不能认为该走势类型是趋势，而只是产生
    #     一个更大级别的缠中说禅走势中枢。」
    # ⇒ 前后中枢重叠 ⇒ **更大级别的中枢（升级）**，不是同级别更长的中枢。
    #
    # 而 `_merge_overlapping_zss` 做的是 `prev.lines.extend(zs.lines)`：
    # 把两个**同级别**中枢的段数相加，造出同级别的超长中枢。这
    #   1) 违反第33课 line 7 的 3+6=9 段上限；
    #   2) 也不是第20课的"升级为更大级别"。
    #
    # 实测（scripts/audit_g1_merge_overlap_impact.py，12 只真实日线 332 中枢）：
    #   A 当前（无限延伸+合并开）: >9段 81 (24.4%)，最长 37 段
    #   B 硬关闭+合并开:           >9段 58 (17.8%)，最长 32 段 ← 只改开关不够
    #   C 硬关闭+合并关:           >9段 0  (0.0%)，最长  9 段 ← 符合原文
    #   注意 B 的合并触发对数从 A 的 3 暴涨到 77 —— 硬关闭造出的相邻中枢
    #   立刻被合并重新拼成长中枢，**关闭合并是 G1 的必要条件**。
    #
    # V851 决策：默认改为 False（关闭同级别合并），同时 zs_no_hard_close
    # 默认改为 False（9 段硬关闭）。两者配合使 >9 段从 24.4% 降到 0.0%，
    # 与第33课上限严格一致。信号数 658 → 650（-1.2%，可接受）。
    # 若要恢复旧行为，显式设 zs_merge_overlap=True（会重新引入超限）。
    zs_merge_overlap: bool = False
    # V853 原文第20课定理二 + 第33课：标记「升级为更大级别中枢」。
    #
    # 原文（第20课「缠中说禅走势中枢中心定理二」，逐字）：
    #   「后ZG < 前ZD 且后GG >= 前DD，或 后ZD > 前ZG 且 后DD =< 前GG，
    #     则等价于形成高级别的走势中枢。」
    # 原文（第33课，逐字）：
    #   「中枢的延伸不能超过5段，也就是一旦出现6段的延伸，加上形成中枢
    #     本身那三段，就构成更大级别的中枢了。」
    #
    # 实现口径：只做**标记**（ZS.upgraded / ZS.level / ZS.upgrade_from），
    # **不合并段数、不改 ZG/ZD/lines**。
    #   - 不合并：合并两个同级别中枢的段数正是 V851 修掉的错误
    #     （违反第33课 9 段上限，也不是原文的"升级"语义）。
    #   - 不重算区间：原文的"更大级别中枢"要换一把尺子（用更大级别的次级别
    #     走势类型重叠定义区间），需走势类型级递归，当前架构做不到。
    #     mark_upgraded_zss 的 docstring 已明确记录这个差距。
    #
    # 默认 True：纯标记 ⇒ 对既有计数（中枢数/信号数）零影响，只是把原文
    # 明确的"升级"语义显式暴露给下游。实测见
    # docs/CHANLUN_FIDELITY_AUDIT_V735.md §39。
    zs_mark_upgrade: bool = True
    # V735 Round 9：原文第17课「中枢 = 3 个连续次级别走势类型的重叠区间」。
    # 当前默认（zs_from_xd=False）用**同级别笔**构中枢，第91课说「笔不能构中枢」。
    # zs_from_xd=True 改用**同级别线段**（第91课允许），但仍非「次级别」。
    # zs_cross_timeframe=True 进一步改用**次级别（30min）线段**构中枢，
    # 是原文第17课的精确口径。需要 30min K线数据。
    # 实测（6 只日线）：中枢 56→9（84%减）、信号 138→21（15%保留）。
    # 默认 False（保持实用性），用户可显式开启获得原文精确口径。
    zs_cross_timeframe: bool = False
    # 中枢区间来源: "dd" 用顶底点, "ck" 用缠论K线高低, "k" 用原始K线高低
    zs_qujian: str = "dd"

    # ZG/ZD 按缠论原文第20课：ZG=min(g1,g2)、ZD=max(d1,d2)，只用第 1、3 笔（A、C段）。
    # 中间反向笔（B段）不参与。原文没有 g3。

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

    # V735 Round 8：第29课后置验证 → 信号可信度扣分。
    # 原文（第29课定理）：「该反弹一定触及最后一个中枢的 DD=min(dn)」。
    # 后置验证测出 _rebound_verified=False 的 1买/1卖，其 decision_score
    # 扣减此分数（默认 15 分，不改信号有无 = 不前置过滤）。
    # 设为 0 则禁用扣分（仅保留 rebound_verified 标记）。
    rebound_penalty: float = 15.0

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
    #
    # ⚠️ V734（2026-10-11 实测）：本项**曾经形同虚设** —— mmd.py 里另有一处
    # 硬编码 `if total_time > 40: break`（V8 遗留），与本项并存且不受本项控制，
    # 导致本项设 0「不限」时实际上仍被 40 根截住。现已统一由本项控制。
    #
    # 默认 40 = **刻意保持修复前的实际行为**，不是"推荐值"。
    # 25 只日线三口径实测（A/B/C 定义见 docs/CHANLUN_FIDELITY_AUDIT_V734.md §3）：
    #     类型        A 原始≤40   B 完全不限   C 只第一笔回调
    #     2buy            32          90           19
    #     2buy_s          36          54           33
    #     2sell           44          78           34
    #     2sell_s         23          41           21
    #     合计           135         263          107
    # B 会把 1买 之后**任意远**的回调笔都收进来（000333 实测：99% 回撤档位里
    #   笔4 被正确拒绝后，扫描走到笔6 误发 2buy）⇒ 搞红 V731 对称性测试 2 个。
    # C 不引入任意根数、与原文精神更合，但**比 A 严 21%**，是否更准/更赚**未验证**。
    # ⇒ 两者都**没有做收益验证**，所以默认不动，仍走 A 的行为（= 40）。
    #   想放开的自己设 0（此时**真的**不限）；想收紧设正整数。
    #
    # ⚠️ 记录两个我自己犯的错（别重蹈）：
    # 1. 第一版 A/B 只替换了「带注释的买侧那行」，卖侧那行没有注释、锚点不匹配，
    #    于是得出「卖侧 0% 被砍」的**假结论**。做字符串替换式 A/B 时，
    #    必须**先断言锚点命中数**（买卖各 1 处）。
    # 2. 复核脚本用 `ChanlunAnalyser.process_klines` 跑对照，但它内部用的是
    #    **已安装**的 mmd 模块，不是我 exec 出来的副本 ⇒ 两组其实跑的是同一份代码，
    #    得出「A 与 C 完全一致」的假结论。A/B 必须**直接调被 patch 的模块函数**。
    # V857 偏差10：默认改为 0（纯原文口径，不限根数）。
    # 第101课原文：第二类买点「第一次回拉不破前低」，无固定根数限制；
    # 原默认 40 会静默吞掉间隔 >40 根的第二类买卖点（无原文依据）。
    # mmd.py L2376 注释本就声明「默认放开(0=不限纯原文)」，但此默认值与之矛盾。
    # 想按周期收紧的可显式设非零值。
    mmd_2nd_span_max_bars: int = 0
    # V857 偏差13（subagent报告偏差2）：1买后「找离开笔」的硬编码 30 根。
    # 第101课无此限制；原硬编码会吞掉 1买后 >30 根才出现向上笔的情形。
    # 默认 0=不限（纯原文）；与 mmd_2nd_span_max_bars 同口径。
    mmd_2nd_leave_max_bars: int = 0

    # ── 线段级别买卖点配置（seg_mmd）────────────────────────────────────
    # use_seg_mmd=True: 使用线段末端买卖点检测（参考 chan.py 的 CBSPointList）
    #   一类买卖点在线段末端检测背驰（而非每根笔末端），更符合原文。
    #   False（默认）：使用 find_mmds_v44 笔级别买卖点。
    use_seg_mmd: bool = False
    # seg_mmd_hybrid=True: T1来自线段级别(更可靠), T2/T3来自笔级别(更多信号)
    seg_mmd_hybrid: bool = False
    # 背驰率阈值：exit 笔 MACD 指标 ≤ divergence_rate × enter 笔 MACD 指标
    seg_divergence_rate: float = 1.5
    # 最少中枢数：线段至少包含这么多中枢才是一类买卖点
    seg_min_zs_cnt: int = 1
    # 一类买卖点只算多笔中枢（排除一笔中枢）
    bsp1_only_multibi_zs: bool = True
    # 一类买卖点要求创新极值
    bs1_peak: bool = True
    # 二类买卖点最大回踩率（工程口径，0.8=回撤>80%抑制；仅当 mmd_2nd_max_pullback 非空时作为 fallback）
    max_bs2_rate: float = 0.8
    # 二类买卖点回撤门槛（101课原文口径）：
    # None=无门槛（纯原文：第101课「第二类买点跌破第一类买点……这是完全可以的」，总出2buy）
    # float=retrace_rate > 该值抑制2buy（工程口径，如0.5=回撤>50%抑制）
    mmd_2nd_max_pullback: float | None = None
    # 二类必须跟随一类
    bsp2_follow_1: bool = True
    # 三类买卖点必须跟随一类
    bsp3_follow_1: bool = True
    # 三类买卖点严格模式
    strict_bsp3: bool = False
    # 三类买卖点要求突破中枢极值
    bsp3_peak: bool = False
    # 三类A最多扫描几个中枢
    bsp3a_max_zs_cnt: int = 1
    # 类二买卖点最大层级
    max_bsp2s_lv: int | None = None
    # MACD 背驰算法: "peak" 取峰值, "area" 取面积
    seg_macd_algo: str = "peak"

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
            "zs_no_hard_close": self.zs_no_hard_close,
            "zs_from_xd": self.zs_from_xd,
            "zs_merge_overlap": self.zs_merge_overlap,
            # V853 原文第20课定理二 / 第33课：中枢升级标记开关
            "zs_mark_upgrade": self.zs_mark_upgrade,
            "rebound_penalty": self.rebound_penalty,
            "zs_cross_timeframe": self.zs_cross_timeframe,
            "zs_qujian": self.zs_qujian,
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
            "mmd_2nd_leave_max_bars": self.mmd_2nd_leave_max_bars,
            "macd_fast": self.macd_fast,
            "macd_slow": self.macd_slow,
            "macd_signal": self.macd_signal,
            "use_seg_mmd": self.use_seg_mmd,
            "seg_mmd_hybrid": self.seg_mmd_hybrid,
            "seg_divergence_rate": self.seg_divergence_rate,
            "seg_min_zs_cnt": self.seg_min_zs_cnt,
            "bsp1_only_multibi_zs": self.bsp1_only_multibi_zs,
            "bs1_peak": self.bs1_peak,
            "max_bs2_rate": self.max_bs2_rate,
            "mmd_2nd_max_pullback": self.mmd_2nd_max_pullback,
            "bsp2_follow_1": self.bsp2_follow_1,
            "bsp3_follow_1": self.bsp3_follow_1,
            "strict_bsp3": self.strict_bsp3,
            "bsp3_peak": self.bsp3_peak,
            "bsp3a_max_zs_cnt": self.bsp3a_max_zs_cnt,
            "max_bsp2s_lv": self.max_bsp2s_lv,
            "seg_macd_algo": self.seg_macd_algo,
        }
