# 更新日志

本文件记录 easy-tdx 的版本变更。格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/)。

## [Unreleased]

**趋势段创新低金标（V685）**：
- 新增 _is_trending 向下趋势段必须创新低的边界金标。

**走势段端点共享金标（V684）**：
- 新增 find_zsds 相邻走势段首尾相连、端点共享、方向交替的几何金标。

**走势段区间覆盖修复（V683）**：
- find_zsds 重构为同向线段组聚合，走势段区间覆盖组内所有线段极值，修复中间线段极值丢失。
- 新增多线段组极值金标。

**统计标签随级别联动（V682）**：
- ChanlunView 统计面板「笔/线段」在切换到线段级别时显示为「本级段/递归段」。

**统计面板级别标签（V681）**：
- ChanlunView 统计面板新增「级别」项，明确当前为笔级别或线段级别。

**递归空态金标补全（V680）**：
- 扩展 test_chanlun_recursive.py：不足 3 根线段时递归 zsds/qsds 也为空。

**MACD 计算边界金标（V679）**：
- 新增 tests/unit/test_chanlun_macd_edges.py：空序列、输出长度、力度区间越界回退。

**分型识别边界金标（V678）**：
- 新增 tests/unit/test_chanlun_fractal_edges.py：严格/非严格分型、十字星跳过、bar_index 回退。

**走势段独立渲染测试（V677）**：
- ChanlunChart 测试新增「仅走势段数据」场景，锁定 qsd 不误渲染。

**趋势段独立渲染测试（V676）**：
- ChanlunChart 测试新增「仅趋势段数据」场景，锁定 zsd 不误渲染。

**配置序列化字段覆盖金标（V675）**：
- 扩展 test_chanlun_config.py：锁定 to_dict 覆盖所有 dataclass 字段。

**分析器空态金标（V674）**：
- 新增 tests/unit/test_chanlun_analyser_edges.py：空 K 线输入不崩溃、返回完整 levels 空结构。

**走势段/趋势段紧凑模式线宽（V673）**：
- ChanlunChart 在 compact 模式下走势段/趋势段线宽降为 2px，减少视觉噪声。
- 前端测试锁定 compact 线宽。

**走势段/趋势段空态金标（V672）**：
- 扩展 test_chanlun_zsd.py：锁定 find_qsds 空输入/单线段返回空。

**训练页分析级别切换（V671）**：
- TrainView 新增「分析级别」切换器：笔级别 / 线段级别，训练揭示与图表同步切换。

**回测页分析级别切换（V670）**：
- BacktestView 缠论策略图新增「分析级别」切换器：笔级别 / 线段级别。

**实证复盘页分析级别切换（V669）**：
- SignalVerifyView 新增「分析级别」切换器：笔级别 / 线段级别，切换后无需重新取数。

**选股页分析级别切换（V668）**：
- ScreeningView 新增「分析级别」切换器：笔级别 / 线段级别。
- 切换后画图与择时信号同步切换，且无需重新取数。

**买卖点力度计算边界金标（V667）**：
- 新增 tests/unit/test_chanlun_mmd_edges.py：锁定 _calc_bi_force 无收盘价/端点越界/有效收盘价场景。

**走势段/趋势段空 series 优化（V666）**：
- ChanlunChart 仅在存在走势段/趋势段数据时创建对应 series，避免空图例。
- 前端测试锁定无数据时不创建空 series。

**递归层级计数金标（V665）**：
- 扩展 test_chanlun_recursive.py：锁定 levels.bi / levels.xd 的 zsd_count/qsd_count。

**递归结果内聚走势段/趋势段（V664）**：
- RecursiveLevelResult 增加 zsds/qsds，compute_recursive_level 直接返回递归走势段/趋势段。
- analyser 递归分支直接复用该结果，减少重复计算。

**多级别联立边界金标（V663）**：
- 新增 tests/unit/test_chanlun_multi_level_edges.py：空态、缺失级别、跨级别查询边界。

**层级走势段/趋势段计数（V662）**：
- levels.bi / levels.xd payload 增加 zsd_count / qsd_count。
- 金标锁定层级 payload 计数与数组一致性。

**导出与图例增强（V661）**：
- ChanlunView 导出 JSON 增加 zsds/qsds/analysis_level。
- ChanlunChart 前端测试锁定走势段/趋势段 legend 显示。

**中枢计算边界金标（V660）**：
- 新增 tests/unit/test_chanlun_zs_edges.py：锁定中枢区间有效性、重叠比例、关闭条件、质量评分等边界。

**笔计算边界金标（V659）**：
- 新增 tests/unit/test_chanlun_bi_edges.py：锁定笔规则纯函数的边界行为。
- 覆盖新/老/simple 笔 gap、弱笔阈值、端点一致性、价格方向、分型稳定性。

**ChanlunConfig 序列化补全（V658）**：
- to_dict 增加 multi_level / mmd_1st_dedup / mmd_3rd_type_technical。
- 新增配置序列化金标测试，锁定模型开关默认值与自定义值。

**走势段/趋势段统计展示（V657）**：
- to_dict 新增 zsd_count / qsd_count 顶层计数。
- ChanlunView 统计面板新增「走势段」「趋势段」数量展示。
- 金标测试锁定计数与数组一致性。

**线段级别走势段/趋势段（V656）**：
- ChanlunResult 新增 zsds_l1/qsds_l1：递归线段级别的走势段/趋势段。
- levels.xd payload 输出递归走势段/趋势段；ChanlunView 线段级别图表同步展示。
- 新增 xd_level payload 金标测试。

**走势段/趋势段接入全部缠论图表（V655）**：
- BacktestView / ScreeningView / SignalVerifyView / TrainView 均映射并展示 zsds/qsds。
- 配合 V653/V654，所有 ChanlunChart 使用页统一支持走势段（粗实线）与趋势段（粗虚线）。

**背驰边界金标与走势段 tooltip（V654）**：
- 新增 tests/unit/test_chanlun_beichi_edges.py：锁定盘整/趋势背驰的防御分支（无趋势、缺 lines、离开笔越界、未创新极值）。
- ChanlunChart tooltip 增加走势段/趋势段提示，画图交互更完整。
- 前端 ChanlunChart 测试覆盖走势段/趋势段独立 series。

**走势段/趋势段模型与画图（V653）**：
- 修复 zsd.py 趋势段判断：改用起止分型极值比较，移除对不存在的 k.h/k.l 字段的依赖。
- ChanlunAnalyser 管道新增 zsds/qsds 输出（由线段合并的走势段/趋势段），并序列化到 to_dict()。
- ChanlunChart 新增走势段（粗实线）与趋势段（粗虚线）绘制，ChanlunView 笔级别图表接入。
- 新增 tests/unit/test_chanlun_zsd.py 金标。

**缠论图表周期级别选择（V652）**：
- ScreeningView 与 SignalVerifyView 的缠论图表新增周期选择器（日线/周线/5/15/30/60分钟）。
- `/verify/signals/detail` 支持 `category` 参数：日线走预跑缓存，分钟级别走在线取数并现场分析。
- 新增 verify 路由周期契约测试。

**缠论多级别递归分析（V651）**：
- 新增 `chanlun/recursive.py`：以低级别线段（XD）作为高级别「笔」，复用线段/中枢/背驰/买卖点算法递归计算高级别线段、线段中枢、背驰与三类买卖点。
- `ChanlunResult.to_dict()` 输出 `levels.bi`（笔级别）与 `levels.xd`（线段级别）两层结构，前端按级别切换画图与择时信号。
- Web ChanlunView 新增「分析级别」切换器：笔级别 / 线段级别。
- 新增金标 `tests/unit/test_chanlun_recursive.py`：锁定人造线段序列的递归计数与几何不变量，以及真实行情两层序列化。
- 全量 tests/unit 3383 passed。

**线段多义性确定性取舍金标 + Phase13 归档（V650）**：
- 新增金标：XD_TIEBREAK_EARLIEST=True（取最早确认），同一输入永远同一线段划分。
- OpenSpec tasks.md 记录 Phase 13（V634-V649 严格原文修正全清单）。
- 全量 tests/unit 3378 passed。


**线段端点极值锚定金标（V649）**：
- 多周期快照新增线段端点金标：线段端点必为特征序列分型点的极值，落在 [low, high] 区间内，且方向一致（向上终点>起点、向下终点<起点），锁定画图端点锚定。
- 全量 tests/unit 3377 passed。


**中枢进入/离开段显式建模（V648）**：
- ZS 新增 enter_bi/exit_bi 字段：缠论原文中枢 = 进入段 + 重叠段 + 离开段，find_zss 显式记录两端（进入中枢前一笔 / 离开中枢后一笔），to_dict 输出 enter_bi_index/exit_bi_index 供画图与背驰标注使用。
- 新增 enter/exit 记录金标。
- 全量 tests/unit 3373 passed。


**盘整背驰离开笔越界防御金标（V647）**：
- 新增金标：中枢最后一笔是最后一笔时，离开笔索引越界 → 不崩溃且不产出背驰，锁定 _check_pz_beichi 的边界守卫。
- 全量 tests/unit 3372 passed。


**1买/1卖 去重启发式可配置（V646）**：
- 新增 ChanlunConfig.mmd_1st_dedup（默认 True）；设为 False 时关闭「相邻间隔5笔 + 3%反弹/回落」去重，严格按缠论原文（趋势背驰点即可）生成信号。
- 新增配置默认值金标。
- 全量 tests/unit 3371 passed。


**背驰创新低对称金标（V645）**：
- 补上笔背驰「创新低」的对称金标：向下笔创新低且力度衰减 → 标背驰；未创新低不标。与已有「创新高」金标形成双向锁定。
- 全量 tests/unit 3370 passed。


**1买/1卖 结构去重启发式显式化（V644）**：
- 把 1买/1卖 的「相邻间隔5笔、3%反弹/回落」去重启发式抽取为命名常量与 _has_meaningful_rebound/_has_meaningful_pullback 辅助函数，并明确标注为工程去重启发式（非缠论原文规则），与原文背驰定义解耦。
- 新增两个启发式边界金标（3%/2%/未反弹、首次无前值）。
- 全量 tests/unit 3368 passed。


**1买/1卖 趋势强度金标（V643）**：
- 新增金标：趋势背驰需要趋势——至少两个同向中枢才趋势强度>0，不同向/单中枢为 0，锁定 1买/1卖 的原文门槛。
- 全量 tests/unit 3366 passed。


**1买/1卖 同期参考中枢无未来函数金标（V642）**：
- 新增金标：_reference_zs_for_bi 只取「笔发生前已结束」的中枢，不偷看未来中枢，锁定 1买/1卖 的 point-in-time 正确性。
- 全量 tests/unit 3365 passed。


**特征序列向下包含取低低金标（V641）**：
- 补上线段特征序列包含处理的「低低」方向金标：向下特征序列包含时 high=min、low=min，锁定缠论原文包含处理双向规则。
- 全量 tests/unit 3364 passed。


**分型严格遵循缠论原文：双维度（V640）**：
- 修复 find_fractals：缠论原文顶分型 = 中间K线高点最高 **且** 低点也最高；底分型 = 低点最低 **且** 高点也最低。旧实现只检查单一维度，会把「高点最高但低点不是最高」的K线误判为顶分型。
- 新增双维度分型金标；旧合成测试数据按双维度修正。
- 全量 tests/unit 3363 passed。


**2类买卖点技术过滤器改为增强项（V639）**：
- 2买/2卖 的成交量、MACD力度、RSI 三个非缠论原文硬门槛改为增强信息，不再一票否决；2类点核心保持「1买后回踩不创新低 / 1卖后反抽不创新高 + 时间窗口 + 去重」。
- 全量 tests/unit 3362 passed。


**中枢区间严格遵循缠论原文：延伸不改变 zg/zd（V638）**：
- 修复 find_zss：中枢区间 ZG/ZD 由「前三个连续次级别走势」的重叠确定，第4笔及以后的延伸不再改变 ZG/ZD，只更新极值 GG/DD（旧实现把延伸也纳入区间，导致 zg/zd 随延伸漂移）。
- 新增中枢延伸金标（第4笔区间略扩但 zg/zd 保持前三个值）；金标 zs_semantics 同步改为前三个走势口径。
- 全量 tests/unit 3362 passed。


**3类买卖点默认严格遵循缠论原文（V637）**：
- 新增 ChanlunConfig.mmd_3rd_type_technical（默认 False）：3买=突破中枢上沿后回踩不破、3卖=跌破下沿后反抽不破，不再叠加 RSI/KDJ/BOLL/量能/MACD零轴等技术过滤（这些非缠论原文，之前导致 3类点几乎不触发）。
- 新增 _find_third_type_mmds_original 原文实现；真实行情复测 3buy/3sell 正常触发（如 600519 日线 8 个、300750 日线 9 个）。
- 金标结构校验同步改为原文口径（3买 bi.low > zg、3卖 bi.high < zd，去掉 0.5% 缓冲）；快照 mmd 计数同步更新。
- 全量 tests/unit 3361 passed。


**3类买卖点突破三条件改为增强项（V636）**：
- 缠论原文 3买/3卖 只要求「突破中枢上沿/跌破下沿 + 回踩不破/反抽不破」；突破力度、突破站稳比例、突破量能三个技术过滤器本非原文硬门槛，现改为增强信息不再一票否决（之前导致 3类点几乎不触发）。
- 全量 tests/unit 3361 passed。


**笔严格遵循缠论原文：至少1根独立K线（V635）**：
- 修复 _can_form_bi 间距阈值：新笔从 gap>=1 修正为 gap>=3（顶底之间至少1根既不属于顶也不属于底的独立K线）、老笔 gap>=5（至少3根独立K线），旧实现过于宽松会把共享/相邻K线的分型误当笔。
- 真实行情金标快照计数同步更新（笔数显著减少，更贴近严格缠论）；新增新笔间距金标（独立K线成立/相邻拒绝）。
- 旧基础结构测试改用 bi_type=simple 保留原意，严格新笔规则由金标覆盖。
- 全量 tests/unit 3361 passed。


**线段「特征序列缺口 + 笔破坏确认」金标（V634）**：
- 新增缠论 77 课规则金标：特征序列有缺口时，第4特征元素跌破顶/底分型极值才确认线段结束（2段）；未跌破则线段继续（1段）。
- 全量 tests/unit 3363 passed。


**3类买卖点 ATR 门槛改为增强项（V633）**：
- 3买/3卖 的 ATR 支撑/阻力由硬阻断改为增强提示——缠论 3类买卖点核心是「回踩不破中枢上沿/反抽不破中枢下沿」，ATR 贴近程度只是质量加分，旧实现把它当硬门槛导致 3类点几乎从不触发。
- 全量 tests/unit 3361 passed。


**类二买卖点方向判定金标（V631）**：
- 扩展择时结论金标：2buy_s/2sell_s 按类型名中的 buy/sell 正确判为买入/卖出。
- 全量 tests/unit 3361 passed。


**择时结构计数一致性金标（V630）**：
- test_chanlun_real_golden.py 的择时输出断言锁定 structure 计数（bi27/zs3/mmd4/bc1）与快照一致。
- 全量 tests/unit 3361 passed。


**Point-in-time 取财报金标（V629）**：
- test_changying_golden.py 新增 pick_report 金标：只用披露日 <= 目标日的财报（不偷看未来）、缺失披露日用报告期近似。
- 全量 tests/unit 3361 passed。


**树粮菜同分优先级金标（V628）**：
- test_changying_golden.py 新增同分 tiebreak 金标：树/粮同 100 分时优先判树（树>粮>菜）。
- 全量 tests/unit 3359 passed。


**择时置信度阈值边界金标（V627）**：
- 锁定 _MIN_CONF=0.6 边界：置信度 0.6 给买卖建议、0.59 降级观望。
- 全量 tests/unit 3358 passed。


**to_dict 序列化金标（V626）**：
- 多周期快照新增 to_dict 序列化断言：不崩溃、含 bis/mmds/bcs，分钟级日期含时分，锁定 V623 字符串日期归一化。
- 全量 tests/unit 3357 passed。


**择时建议越界/缺触发笔加固（V625）**：
- _novice_advice 对缺触发笔的信号不再给具体价位（改为观望），并夹紧索引避免止损/目标取到错误窗口。
- 新增缺触发笔单元测试。
- 全量 tests/unit 3353 passed。


**估值 PE/PB 金标（V624）**：
- test_changying_golden.py 新增估值金标：PE/PB 计算、一季报 EPS 年化动态 PE、亏损/无价时 PE 为 None。
- 全量 tests/unit 3352 passed。


**字符串日期归一化修复 + 择时小白字段金标（V623）**：
- 修复 ChanlunAnalyser 对 JSON 载入的 DataFrame（字符串日期）调用 to_dict 时 strftime 崩溃；_df_to_klines 将字符串日期归一化为时间对象。
- 新增真实行情择时输出金标：_run_timing_one 必须返回 verdict / novice_advice / signal_quality 三个小白字段。
- 全量 tests/unit 3349 passed。


**小白风险点识别金标（V622）**：
- test_changying_golden.py 新增 novice_summary 风险点金标：亏损/高负债/负现金流都应进入 risk_flags 且 risk_level=高。
- 全量 tests/unit 3348 passed。


**择时建议三档价有序性金标（V621）**：
- test_stock_pick_router.py 新增断言：买点三档价必须 止损 < 入场 < 目标，锁定 novice_advice 输出一致性。
- 全量 tests/unit 3347 passed。


**金标快照扩到 30 分钟级别（V620）**：
- 新增 SZ000001 30 分钟真实行情金标快照（160 根，bi16/xd1/zs3/mmd0/bc1），把「多周期」覆盖从日线/周线扩展到分钟级。
- 全量 tests/unit 3347 passed。


**趋势背驰语义金标（V619）**：
- test_chanlun_golden_samples.py 新增趋势背驰单元金标：离开笔 = 中枢最后一条线之后的一笔，两段同向、创新低且力度衰减才成立，锁定 V603 修正。
- 全量 tests/unit 3337 passed。


**盘整背驰语义金标（V618）**：
- test_chanlun_golden_samples.py 新增盘整背驰单元金标：进入/离开笔同向且力度衰减才成立；方向相反不判盘整背驰，锁定 V600 修正。
- 全量 tests/unit 3336 passed。


**MACD 力度窗口精度修复（V617）**：
- _calc_bi_force 改用分型极值来源的原始 K 线索引（bar_index）而非合并 K 线最后一根索引（k.k_index），使笔力度 MACD 面积窗口精确覆盖极值区间。
- 影响：真实行情金标快照的背驰/买卖点计数微调（000001 日线 bc 0→1、600519 日线 mmd 3→2、bc 3→2），已同步更新快照。
- 全量 tests/unit 3334 passed。


**四季判断修复 + 金标（V616）**：
- 修复 season.py price_score 分支顺序 bug：旧实现把「缓跌(-1)」排在「强跌(-2)」之前，导致强跌永远只拿 -1、-2 分支不可达；修正后强跌正确得 -2。
- 新增四季金标：summer/winter/unknown + 强跌 price_score==-2。
- 全量 tests/unit 3334 passed。


**中枢计算金标（V615）**：
- test_chanlun_golden_samples.py 新增 find_zss 金标：四笔重叠成中枢、离开笔关闭，锁定 zg=min(high)/zd=max(low)/gg/dd/line_count/done。
- 全量 tests/unit 3331 passed。


**笔计算金标（V614）**：
- test_chanlun_golden_samples.py 新增 find_bis 金标：交替分型生成 4 笔（方向/端点正确）、更极端顶分型替换并延伸上一笔终点。
- 全量 tests/unit 3330 passed。


**K线包含处理金标（V613）**：
- test_chanlun_golden_samples.py 新增 merge_klines 金标：向上包含取高高、向下包含取低低，锁定合并极值与 merged_count。
- 全量 tests/unit 3328 passed。


**分型识别金标（V612）**：
- test_chanlun_golden_samples.py 新增分型识别金标：一段明显顶/底分型序列应恰好识别出 1 顶 1 底，锁定 find_fractals 的极值与 bar_index 锚定。
- 全量 tests/unit 3326 passed。


**全市场选股复合逻辑金标（V611）**：
- 新增 tests/unit/test_scan_market_golden.py：注入固定候选集，锁定 scan_market 的「盈利硬门槛 → 评分排序 → 市值门槛 → 截断 top_n」复合逻辑。
- 全量 tests/unit 3325 passed。


**选股挑20只输出路径金标（V610）**：
- 新增 tests/unit/test_selection_golden.py：锁定 stock_pick 结果行归一化（质量分正确取 scores[category]）、score 字段优先级、长盈池本地存储按分数降序。
- 全量 tests/unit 3324 passed。


**长盈选股模型金标（V609）**：
- 新增 tests/unit/test_changying_golden.py：手工标注树/粮/菜三个财报行，锁定三维打分与分类结论；并锁定市值（总股本/流通股本回退）与盈利硬门槛纯函数口径。
- 全量 tests/unit 3321 passed。


**二类买卖点结构金标（V608）**：
- 真实行情金标新增二类买卖点结构校验：2买/类2买 = 一买后回踩不创新低（存在更早、更低的一买低点）；2卖/类2卖 = 一卖后反抽不创新高。
- 全量 tests/unit 3316 passed。


**买卖点结构位置金标（V607）**：
- 真实行情金标新增三类买卖点结构校验：1买创新低(低于中枢下沿)、1卖创新高(高于中枢上沿)、3买回踩不破中枢上沿(zg×1.005)、3卖反抽不破中枢下沿(zd×0.995)。
- 全量 tests/unit 3312 passed。


**背驰金标：力度衰减 + 锚点对齐（V606）**：
- 真实行情金标新增背驰断言：每个背驰的 curr/prev 力度必须 < 前笔 80%，且背驰锚点落在触发笔端点极值上（与图上「背」标注一致）。
- 全量 tests/unit 3308 passed。


**中枢语义金标 + 文档修正（V605）**：
- 修正 zs.py 注释：zg=上沿=min(high)、zd=下沿=max(low)（旧注释把两者写反）。
- 金标新增中枢语义断言：zg==min(high)、zd==max(low)、gg==max(high)、dd==min(low)、zg>zd，锁定中枢口径。
- 全量 tests/unit 3304 passed。


**金标快照扩到多标的/多周期（V604）**：
- 新增 600519 日线、000333 日线、000001 周线三份真实行情金标快照 + test_chanlun_real_golden_multi.py，锁计数与几何不变量。
- 全量 tests/unit 3300 passed。


**真实行情金标快照 + 趋势背驰离开笔语义修正（V603）**：
- 新增 tests/fixtures/chanlun_000001_daily.json（SZ000001 真实日线 160 根）+ test_chanlun_real_golden.py，锁定笔/线段/中枢/买卖点/背驰计数与几何不变量。
- 金标暴露出趋势背驰 bug：旧实现把「中枢内部最后一条线」当「离开笔」；改为中枢最后一条线之后的那一笔，并要求两段离开笔方向都与趋势一致。该 bug 此前会误报趋势背驰。
- 全量 tests/unit 3282 passed。


**线段多义性确定性取舍 + 金标样本 + 图例补背驰（V602）**：
- find_xds 明确「最早确认优先」的确定性取舍规则（XD_TIEBREAK_EARLIEST），抽 _valid_segment_end 去重，保证同数据同参数结果稳定。
- 新增 tests/unit/test_chanlun_golden_samples.py：特征序列包含/分型/线段方向/背驰创新高门槛等 8 个手工标注金标回归。
- ChanlunChart 侧边图例增加「背驰(主图)/背驰(副图 MACD)」条目，有买卖点或背驰即显示图例。
- 测试：全量 tests/unit 3275 passed；前端 vitest 61 passed、build 通过。


**线段划分补特征序列缺口 + 笔破坏确认（V601）**：
- find_xds 增加特征序列第一/第二元素「缺口」检测；有缺口时线段结束需第 4 个特征元素跌破/升破分型极值（笔破坏确认），无缺口走标准分型。
- 全量 tests/unit 3267 passed。


**盘整背驰/线段/回测窗口对齐三连修（V600）**：
- 盘整背驰改为缠论原文口径：离开中枢笔 vs 进入中枢笔（同向），力度 < 80% 才算，不再用「中枢首末同向笔」。
- 线段划分重写：特征序列先做包含处理（高高/低低合并）再判分型；SZ000001 线段数从 12 变为 6（更贴近严格缠论，段更长更少）。
- 回测页窗口对齐：/chanlun/analyze 支持 start_date/end_date，BacktestView 传入与 K 线图相同的日期范围，消除图上K线与缠论叠加层错位。
- 测试：全量 tests/unit 3267 passed；前端 vitest 61 passed、build 通过。


**背驰判定对齐缠论原文：创新高/新低门槛（V599）**：
- beichi.py 的笔背驰、趋势背驰补上「必须先创新高（向上）/新低（向下）」门槛，与 mmd._is_strong_beichi 保持一致，去掉未创新极值的误报。
- 实测 SZ000001（2025-01-12 至今）背驰标注从 12 个降到 6 个，剩余均满足创新极值。
- 测试：全量 tests/unit 3267 passed。


**选股/市值取价切到 MAC 主机 + 100亿过滤真正生效（V597）**：
- 定位：标准 TDX 行情主机对日线返回「空K线」（每只约 6s），gpcw 财报里无总股本，导致选股接口 90s 超时、100亿市值过滤名存实亡。
- 修复：pipeline 新增 _market_quote（MAC 取目标日收盘价 + 流通股本 float_shares，约 0.2s/只）；市值 = 总股本(gpcw 若可得) × 收盘价，缺总股本时回退流通股本(万股×1e4)×收盘价。
- 选股接口在线路径关闭后续表现回看、默认开启盈利硬门槛 + 100亿过滤；实测 run_screen 过滤后 21 只全部市值 ≥100亿，耗时约 12s（剩余为四季指数取数）。
- 修了在线路径质量分恒为 0 的 bug（正确取 scores[category]）。


**缠论信号真实行情验证（V596）**：
- 用真实 TDX 日线对 4 只大盘股做缠论买卖点前瞻命中率验证，新增 docs/CHANLUN_SIGNAL_VALIDATION.md。
- 结论：1buy 在 4 只样本上均跑赢随机基准（命中 56%-67%，超额 +1.5%~+19.2%，PF 1.22-2.68）；卖点避跌命中更高；二类点样本少需谨慎。
- 该证据支撑「缠论择时对新手有正向参考价值」，并提示样本局限。


**新手第一课引导层（V595）**：
- 新增 BeginnerGuide 组件：三句话讲清「先长盈选好公司 → 再缠论找买卖点 → 后看信号可信度」，附树粮菜/中枢/背驰/三类买卖点人话术语表。
- 选股页顶部 + 缠论测试学习页顶部接入，可一键隐藏（localStorage 持久化）。
- 测试：新增 BeginnerGuide 测试；前端 vitest 61 passed。


**缠论信号可信度（V594）**：
- 选股择时结果新增 signal_quality：用标的自身历史窗口内的买卖点做前瞻命中率验证，给小白一个「这类买卖点历史上准不准」的可信度提示。
- 前端择时详情卡展示「信号可信度」一句结论。
- 复用既有 compute_signal_accuracy_by_type（随机入场基准 + 盈亏比），不改算法。
- 测试：全量 tests/unit 3267 passed、前端 vitest 59 passed。


**小白保护：长盈盈利硬门槛 + 缠论低置信度降级（V593）**：
- 长盈选股/全市场扫描新增 require_profit（默认开启）：净利润非正的标的直接排除，避免把亏损股推荐给新手。
- 缠论择时新增置信度保护：信号置信度 < 60% 时结论降级为「观望」，不再给出买卖建议；novice_advice 同步改为「先观察」。
- 测试：新增低置信度降级用例；全量 tests/unit 3267 passed。


**面向小白的长盈/缠论可解释性增强（V592）**：
- 长盈选股每只标的输出 novice_summary：一句话结论（树/粮/菜什么意思）、第一步怎么看、硬风险点（亏损/高负债/负现金流）与风险等级。
- 缠论择时输出 novice_advice：把买卖点翻译成「参考入场/止损/目标 + 人话说明 + 仓位提示」，小白能照做。
- 选股页详情卡片展示入场/止损/目标三档价位与操作建议。
- 测试：test_stock_pick_router 新增 novice_advice 用例；全量 tests/unit 3266 passed、前端 vitest 59 passed。


**长盈选股离线沉淀 + 市值门槛（V591）**：
- 长盈选股增加市值硬门槛：总市值（总股本 × 目标日收盘价）< 100 亿的标的直接排除（pipeline.min_mcap_yi，默认 100）。
- 新增本地沉淀：fundamental/changying_pool.py 的 ChangyingStore（SQLite ~/.easy_tdx/changying_pool.db）+ refresh_changying_pool（凌晨用 TDX 在线数据排序检索后落盘）+ load_changying_pool（白天读取）。
- 新增 CLI easy-tdx changying-refresh（cron 0 0 * * *）+ easy-tdx serve --changying-scheduler（服务内每天 00:00 后台刷新，默认开启）。
- /stock-pick/screen 白天优先读本地沉淀池（source=local + updated_at），本地为空回退在线；前端选股页展示「本地沉淀池/在线扫描」来源。
- 财务指标框架文档 docs/CHANGYING_POOL_DESIGN.md：树粮菜三维打分 + 20 只排序规则 + 硬性门槛清单。
- 测试：test_changying_pool.py 6 passed；全量 tests/unit 3264 passed、前端 vitest 59 passed。


**网站重构：回测 / 选股 / 缠论测试学习 三大模块 + 缠论画图精度（V590）**：
- 主导航收敛为「回测 / 选股 / 缠论测试学习」三项；其余页面软隐藏（URL 直达仍可用，页面顶部给非阻断提示），服务器设置移入页脚齿轮。
- 新增选股两步流 /stock-pick：用户选时间 → 长盈基本面选股池（树粮菜 + 评分 + 明细）→ 缠论择时（买卖点/背驰/中枢 + 结论）；/api/v1/stock-pick/screen 支持热门池/自定义池/全市场，/api/v1/stock-pick/timing 输出截至目标日的前复权缠论结构。
- 缠论测试学习合并为 /learn 5 Tab：看图分析 / 理论教学 / 盘感训练 / 买卖点实证 / 进度；/chanlun、/train、/verify 重定向到对应 Tab。
- 缠论画图精度：bi_fractal_confirm 默认关闭（不再静默丢弃未确认极值转折点，弱笔/趋势过滤默认不丢点）；买卖点标注用触发笔终点分型极值 anchor_val 而非 bars 偏移；背驰增加主图标注与副图 MACD 对照；zs 序列化明确 zg/zd（重叠区间）与 gg/dd（极值）口径。
- 新增几何金标测试 test_chanlun_precision_v590.py（端点=极值、买卖点/背驰锚定）与选股路由测试、前端导航/选股两步流测试；全量门禁通过（ruff/mypy/pytest-unit 3257 通过 / vue-tsc / vite build / vitest 58 通过）。


**估值 PE/PB 口径注释（V589）**：前端 ChanlunView 的 valuation 补注释，明确 pe 为动态市盈率（年化 EPS）、pb 为静态市净率（每股净资产 point-in-time），与 V579 动态PE 标签 / V588 后端口径注释对齐。

---

**估值 PB 口径注释（V588）**：fundamental/pipeline `_valuation` 注释明确 PB 用每股净资产（point-in-time，非累计值）不年化，与动态 PE（年化 EPS）区分。

---

**亏损/无数据标签细分（V587）**：fundamental/screener 三分类评分的「亏损/无净利润」「亏损：不满足粮条件」「亏损：需要更高增速来证明」标签拆分为「亏损」与「无净利润数据」两态（与 V584-V586 标签细分系列一致，区分「净利润为负」与「净利润数据缺失」）。

---

**粮型净利下滑/缺失标签细分（V586）**：fundamental/screener `score_grain` 的「净利大幅下滑/缺失」标签拆分为「大幅下滑」与「数据缺失」两态（与 V584/V585 标签细分一致）。

---

**菜型负增长/缺失标签细分（V585）**：fundamental/screener `score_vegetable` 的「营收负增长/缺失」「净利负增长/缺失」标签拆分为「负增长」与「数据缺失」两态（与 V584 净利率标签细分一致）。

---

**菜型净利率标签细分（V584）**：fundamental/screener `score_vegetable` 的「盈利但净利率未披露/极低」标签拆分为「未披露」与「极低」两态（原合并为一个标签，含义含糊）。

---

**indicators 双字段约定注释（V583）**：fundamental/screener `screen_stock` 的 `ind` 字典补头部注释，说明「raw + annualized」双字段约定（年初至今累计值同时透出原始/年化，前端用年化、PE 计算用原始）。

---

**衰减分析默认 lag 命名（V582）**：factor/analysis `compute_decay` 的默认最大 lag（10）抽为命名常量 `_DEFAULT_MAX_LAG`，去魔法数字（与 V567/V570/V581 一起把 analysis 模块的魔法数字全部命名）。

---

**IC 自相关 lag 命名（V581）**：factor/analysis `full_report` 的一阶自相关 lag（1）抽为命名常量 `_AUTOCORR_LAG`，去魔法数字。

---

**营收亿换算与满分上限命名（V580）**：fundamental/screener 的营收「亿」换算（1e8）与评分满分上限（100）抽为命名常量 `_YI/_MAX_SCORE`——至此 `screener.py` 评分逻辑的阈值、权重、换算、满分上限全部语义化命名，无任何魔法数字。

---

**估值 PE 明示动态口径（V579）**：前端 DiagnosisView/ChanlunView 的「PE」标签改为「动态PE」——估值用年化 EPS（V504）计算，明示「动态市盈率」避免与静态/TTM PE 混淆。

---

**树/粮档位子权重命名（V578）**：fundamental/screener `score_tree` 的 ROE/毛利率档位子权重（24/15/4、14/5）与 `score_grain` 的负债档位子权重（17/8/2）抽为命名常量——至此树/粮/菜三分类评分逻辑的阈值与权重（含全部子档）彻底语义化命名，评分函数完全无魔法数字。

---

**菜型档位子权重命名（V577）**：fundamental/screener `score_vegetable` 的各档位子权重（22/10/20/5/10）抽为命名常量 `_VEG_REV_FAST/_VEG_REV_MILD/_VEG_NP_FAST_W/_VEG_NP_POS_W/_VEG_MARGIN_POS`——至此树/粮/菜三分类评分逻辑的全部阈值与权重（含子档）语义化命名，评分函数彻底无魔法数字。

---

**回放收益率单位注释（V576）**：backtest/advice_simulator `simulate_advice_trade` 注释明确 `return_pct/mae_pct/mfe_pct` 为百分比（-5.0 = -5%）、非小数，与回测引擎 total_return（小数）单位区分，防误用。

---

**换手率跳过日期重置（V575）**：factor/analysis `compute_turnover` 在样本不足的日期重置 `prev_top`，避免下一日与「跨多日的陈旧集合」计算换手（原实现沿用上一有效日的 prev_top 会高估换手）。

---

**树型维度权重命名（V574）**：fundamental/screener `score_tree` 的盈利/营收体量（10）、ROE（30）、毛利率（20）满分抽为命名常量 `_TREE_PROFIT_WEIGHT/_TREE_REVENUE_WEIGHT/_TREE_ROE_WEIGHT/_TREE_GROSS_WEIGHT`——至此 V561-V574 把树/粮/菜三分类评分逻辑的阈值与权重全部语义化命名，`screener.py` 评分函数彻底无魔法数字。

---

**菜型维度权重命名（V573）**：fundamental/screener `score_vegetable` 的营收/净利同比满分（35）、净利率满分（20）、现金流满分（10）抽为命名常量 `_VEG_REV_FULL/_VEG_NP_FULL/_VEG_MARGIN_FULL/_VEG_OCF_WEIGHT`，去魔法数字——树/粮/菜三分类评分权重全部命名。

---

**粮型核心权重命名（V572）**：fundamental/screener `score_grain` 的盈利/现金流/每股收益三项各 20 分抽为 `_GRAIN_CORE_WEIGHT`、负债满分 25 分抽为 `_GRAIN_DEBT_WEIGHT`，去魔法数字（与 V569/V571 一起把粮型权重全部命名）。

---

**粮型净利同比权重命名（V571）**：fundamental/screener `score_grain` 的净利同比权重（15）抽为命名常量 `_GRAIN_NPYOY_WEIGHT`，去魔法数字（与 V569 树型增长权重命名对称）。

---

**换手率 top-N 下限命名（V570）**：factor/analysis `compute_turnover` 的 top-N 下限（5）抽为命名常量 `_MIN_TURNOVER_TOP`，去魔法数字并注释稳定性含义。

---

**树型增长权重命名（V569）**：fundamental/screener `score_tree` 的增长权重（15/维度）抽为命名常量 `_TREE_GROWTH_WEIGHT`，去魔法数字（与 V561-V567 一起把评分阈值/权重全部命名）。

---

**实时订阅回调泄漏修复（V568）**：realtime EventBus 新增 `unsubscribe_all`（从全局订阅列表移除回调），web 实时 WebSocket 关闭时改用它清理 `subscribe_all` 注册的全局回调——原 `unsubscribe(symbol)` 只清 per-symbol 列表，全局回调残留导致事件持续回调 + 每次连接累积泄漏；补 unsubscribe_all 回归测试。

---

**IC 样本下限命名（V567）**：factor/analysis `compute_ic` 的截面有效样本下限（5）抽为命名常量 `_MIN_IC_SAMPLES`，去魔法数字并注释统计含义。

---

**粮型净利下滑容忍阈值命名（V566）**：fundamental/screener `score_grain` 的净利同比下滑容忍阈值（-10%）抽为命名常量 `_NP_DECLINE_TOL`，去魔法数字（与 V561-V565 一起把评分阈值全部命名）。

---

**indicators 报告期转字符串（V565）**：fundamental/screener `screen_stock` 的 `indicators.report_date` 改为字符串透出（与 as_dict 外层 report_date 口径一致，避免 date 对象直接 JSON 序列化）。

---

**菜型同比阈值命名（V564）**：fundamental/screener `score_vegetable` 的营收/净利同比档位阈值（20/10、30/10）抽为命名常量 `_REV_HIGH/_REV_MED/_NP_BOOM/_NP_FAST`，去魔法数字——与 V561-V563 一起把树/粮/菜三分类评分阈值全部命名。

---

**树型营收/毛利率阈值命名（V563）**：fundamental/screener `score_tree` 的营收体量阈值（100亿）与毛利率档位阈值（40/25）抽为命名常量 `_TREE_REVENUE_MIN/_GROSS_MOAT/_GROSS_MED`，去魔法数字（与 V561/V562 对称）。

---

**树型 ROE 阈值命名（V562）**：fundamental/screener `score_tree` 的 ROE 档位阈值（20/15/10）抽为命名常量 `_ROE_EXCELLENT/_ROE_GOOD/_ROE_MED`，去魔法数字（与 V561 负债率阈值命名对称）。

---

**粮型负债率阈值命名（V561）**：fundamental/screener `score_grain` 的资产负债率档位阈值（40/60/75）抽为模块级命名常量 `_DEBT_LOW/_DEBT_MED/_DEBT_HIGH`，去魔法数字。

---

**indicators 透出报告期（V560）**：fundamental/screener `screen_stock` indicators 新增 `report_date`（作为「年化」字段的取数上下文）；补报告期断言。

---

**年化净利展示 + 选股验证表修列（V559）**：前端 FundamentalView 新增「年化净利」列（V558 透出的 `net_profit_annualized` 落地）；同时修复「选股验证」期表被 V552 误加的估值单元格（该表只列后续收益，多出「年化营收」单元格导致列错位）。

---

**净利润年化透出（V558）**：fundamental/screener `screen_stock` indicators 新增 `net_profit_annualized`（净利润同为年初至今累计值，与 eps/revenue/roe 年化透出对称）；补年化字段断言。

---

**ROE 透出还原原始值（V557）**：fundamental/screener `screen_stock` 的 `indicators.roe` 还原为原始值（与 eps/revenue 一致），年化 ROE 走新字段 `roe_annualized`；前端 FundamentalView「ROE%」列改用 `roe_annualized`（显示不变，API 更一致）。

---

**树型营收偏小明示数值（V556）**：fundamental/screener `score_tree` 的「营收规模偏小」明细也给出年化营收数值，便于用户理解为何被判「偏小」（原只写「营收规模偏小」无具体值）。

---

**菜型净利正增长档位（V555）**：fundamental/screener `score_vegetable` 的净利同比新增「正增长（0~10%，5 分）」档位，区分「正增长但不够高」与「负增长」（原两者同判 0 分），与营收同比的 4 档结构对称；补正增长回归测试。

---

**异步分类报价分页末批修正（V554）**：AsyncMacClient `get_stock_quotes_list` 同步 V553 修正——分页改为循环内按剩余量取，count 非 80 整数倍不再超取。

---

**分类报价分页末批修正（V553）**：mac/client `get_stock_quotes_list` 的分页原固定 `page_size=min(count,80)`，count 非 80 整数倍时最后一批会超取（如 count=100 取到 160）；改为循环内按剩余量取 `min(count-fetched,80)`（与 get_board_list 一致）。补末批 page_size 回归测试。

---

**年化营收展示（V552）**：前端 FundamentalView 新增「年化营收」列（以亿显示，V551 透出的 `revenue_annualized` 落地），选股页补上「龙头规模」维度。

---

**营收年化透出（V551）**：fundamental/screener `screen_stock` indicators 新增 `revenue_annualized`（年化营收，与 eps_annualized 对称，一季报营收为年初至今累计值）；补年化字段回归测试。

---

**寻优跳过退化网格点（V550）**：backtest/optimizer `ParamGridOptimizer.run` 跳过「0 交易」的网格点（参数退化，如 fast==slow 的均线交叉），避免「0 交易 0 收益」被当作最优、淹没真实策略表现；补退化网格点回归测试。

---

**分类同分显式优先级（V549）**：fundamental/screener `screen_stock` 的分类裁决改为显式「树 > 粮 > 菜」同分优先级，不再依赖 dict 插入顺序（行为不变、更健壮）。

---

**因子合并透出报告期（V548）**：factor/engine `merge_fundamentals` 在追加 eps/bps 的同时透出 `report_date`（源财报报告期），便于核对 point-in-time 取数是否命中预期报告期；补报告期断言。

---

**树型 ROE 明细明示年化（V547）**：fundamental/screener `score_tree` 的 ROE 明细改为「年化ROE」（V507 年化后），与营收（V543）/EPS（V544）的年化明示口径一致；补明示断言。

---

**因子衰减守卫统一（V546）**：factor/analysis `compute_decay` 的自相关守卫统一用有效截面（dropna），与 V536/V542 口径一致。

---

**年化 EPS 透出与展示（V545）**：fundamental/screener `screen_stock` indicators 新增 `eps_annualized`（年化 EPS，保留原始 eps 供 PE 计算），前端 FundamentalView 的「EPS」列改为「年化EPS」——与年化 ROE/PE 展示口径一致，一季报不再显示被低估的单季 EPS。

---

**粮型每股收益年化展示（V544）**：fundamental/screener `score_grain` 的「每股收益」改为年化后展示（分红能力按年计，一季报单季 EPS 会低估年度分红能力），明细明示「年化」；补年化 EPS 回归测试。

---

**树型营收体量明示年化（V543）**：fundamental/screener `score_tree` 的「营收体量大」明细明示「年化」口径（V522 年化后），避免与单季营收混淆。

---

**IC 自相关守卫统一（V542）**：factor/analysis `full_report` 的 autocorr 守卫统一用有效截面（valid_ic），与 ic_mean/ic_std（V536）口径一致。

---

**多级别缠论估值（V541）**：chanlun 多级别端点 `chanlun_multi_level` 的高级别（日线）结果补 `valuation`（与单级别 chanlun_analyze 对齐），前端 ChanlunView 多级别路径同步取估值——多级别联立模式下也能看到 PE/PB。

---

**因子引擎 point-in-time 合并（V540）**：factor/engine `merge_fundamentals` 新增 `point_in_time=True` 选项——按披露日逐根取「已披露」最新一期 eps/bps（历史截面无前视偏差），默认仍为最新一期常量（V529 旧行为）；补 point-in-time 回归测试。

---

**粮型/菜型分红能力用每股口径（V539）**：fundamental/screener `score_grain`/`score_vegetable` 的「分红能力/现金流」判据改用「每股经营现金流 ocf_ps」（每股分红基础更直接），缺省回退总量口径；补每股口径回归测试。

---

**日线写入成交量溢出报错（V538）**：offline/write_daily `encode_daily_bar` 在成交量编码超出 .day 格式 uint32 上限时（高流动性标的，如平安银行日成交量 5.89 亿股）提前抛出可读 ValueError，而非隐晦的 struct.pack 'I' 报错；补溢出报错测试。

---

**年化函数更名（V537）**：fundamental/screener 的 `_annualize_pct` 更名为 `_annualize`（该函数同时用于 ROE 百分数与营收绝对值，「pct」命名有误导），保留旧名作别名兼容。

---

**IC 派生指标统一 dropna（V536）**：factor/analysis `full_report` 的 `ic_mean`/`ic_std` 原用总长度作守卫（「1 有效 + N 个 NaN」时 ic_std 被算成 NaN），统一改为 dropna 后只统计有效截面；补单有效截面回归测试。

---

**缠论页估值展示（V535）**：前端 ChanlunView 的市场状态面板补「PE」「PB」（复用 V534 后端 valuation），与诊断页估值（V526）同源同口径。

---

**缠论页估值（V534）**：chanlun 路由 `chanlun_analyze` 响应补 `valuation`（复用诊断页 `_fetch_diagnosis_valuation` 离线取缓存财报帧算 PE/PB，无缓存为 None 不阻断）。

---

**分层顶底收益丢分位修复（V533）**：factor/analysis `full_report` 的 `top_minus_bottom` 在 qcut 因重复值丢弃分位时（q{n_quantiles} 为 NaN）原返回 NaN；改为回退到实际存在的最高/最低非 NaN 分位。补丢分位回归测试。

---

**选股验证符号规范化统一市场推断（V532）**：web/routers/screening `_norm` 的 6 位裸代码市场推断由「6→SH 其余→请求 market」改为复用 `_market_from_code`（与前端 detectMarket / sina / gpcw 口径一致），北交所/9 开头不再被误判。

---

**因子分析分位数校验（V531）**：factor/analysis `FactorAnalyzer` 校验 `n_quantiles >= 2`（1 分位/非正数无意义，pd.qcut 会报错或退化）；补非法分位数报错测试。

---

**screen_stock ROE 年化透出（V530）**：fundamental/screener `screen_stock` 的 indicators.roe 改为报告期年化后透出（与 score_tree 打分口径一致），前端不再显示被低估的单季 ROE、与「高ROE」分类判断不再矛盾；补年化 ROE 回归测试。

---

**因子引擎与基本面打通（V529）**：factor/engine 新增 `merge_fundamentals`——把基本面指标帧的 eps/bps 合并进 OHLCV 数据（每只股票取最新一期），之后可对 `pe_ratio`/`pb_ratio` 做截面计算（V495 价值因子落地）；补合并/缺失/PE/PB 计算测试。

---

**IC 方法校验前置（V528）**：factor/analysis `compute_ic` 增加方法校验（非 spearman/pearson 显式报错，不再静默回退 pearson），scipy 可用性检查移出循环（原每截面重复 import）；补未知方法报错测试。

---

**因子引擎兼容 date 列（V527）**：factor/engine `compute_cross_section`/`compute_forward_returns` 原硬编码 `datetime` 列，喂入 get_security_bars 日线（返回 `date`）会 KeyError；改为兼容 `date` 列（与回测引擎的「date → datetime」派生一致）。补 date 列回归测试。

---

**诊断页估值展示（V526）**：前端 DiagnosisView 的 meta-info 补「PE」「PB」两项（诊断响应 V525 的 valuation 落地），types.ts 补 DiagnosisResult.valuation 字段——诊断页技术面（缠论）与基本面（估值）同框。

---

**诊断页估值（V525）**：diagnosis 路由新增 `_fetch_diagnosis_valuation`——从本地缓存 gpcw 帧取最近一期财报算 PE/PB（EPS 按报告期年化，离线优先、无缓存返回 None 不阻断），诊断响应补 `valuation` 字段；实测茅台 PE=18.9/PB=6.7、五粮液 PE=24.4/PB=3.6、宁德 PE=9.5/PB=2.2。

---

**单标财务指标估值与离线回退（V524）**：fundamental/indicator 路由新增 `price` 查询参数——提供当前价时返回 `valuation`（PE/PB，EPS 按报告期年化，与 V497/V504 口径一致）；`pick_report_zips` 网络不可用时回退本地缓存报告期（`cache_stats`），离线也可取数。实测茅台价格 1342 时 PE=15.4、PB=6.2。

---

**IC 为正占比排除 NaN（V523）**：factor/analysis `full_report` 的 `ic_positive_rate` 原用 `(ic_series > 0).mean()`，把 NaN 截面（样本不足）误当作「非正」，系统性低估 IC 为正占比；改为 `dropna()` 后只统计有效截面。补 NaN 截面回归测试。

---

**树型营收年化（V522）**：fundamental/screener `score_tree` 的「营收体量大」判据改为用报告期年化后的营收（同 V504/V507 口径），避免一季报单季营收低估龙头规模；补营收年化回归测试。

---

**gpcw 市场推断补 9 开头（V521）**：fundamental/indicators `_market_from_code` 原漏判 9 开头（900 B股被误判 SZ、920/930 北交所被误判 SZ），改为与前端 market.detectMarket / sina._build_paper_code 口径一致（北交所→BJ、沪市含 B 股→SH、其余→SZ）；补 900/920 回归测试。

---

**新浪 paperCode 北交所修复（V520）**：sina/client `_build_paper_code` 原只有「6→sh、其余→sz」，北交所（43/83/87/92/4xx/8xx）被误映射为 sz；改为与前端 market.detectMarket 口径一致（北交所→bj、沪市含 B 股→sh、其余→sz），北交所财报新浪数据源可正确取数。补 bj 前缀测试。

---

**组合报告导出补完整绩效（V519）**：前端 PortfolioView 的 Markdown/CSV 导出补「最大回撤」「夏普比率」「胜率」三行（V515/V516 完整绩效的导出落地）。

---

**因子分层收益顶底修复（V518）**：factor/analysis `full_report` 的 `top_minus_bottom` 原硬编码 `q5 - q1`，当 `n_quantiles != 5`（如 10 分位）时把中位层 q5 误当顶层；改为用最高分位 `q{n_quantiles} - q1`。补 10 分位回归测试。

---

**年化逻辑抽共享（V517）**：fundamental 的年化逻辑（按报告期月数把年初至今累计值年化，EPS/ROE 共用）抽取为 `indicators.annualize_ytd` 共享纯函数，`pipeline._annualize_eps`（V504 PE）与 `screener._annualize_pct`（V507 ROE）改为委托，消除两处重复实现。

---

**组合页完整绩效展示（V516）**：前端 PortfolioView 组合绩效摘要由「总收益/标的数/总资金」补「最大回撤」「夏普比率」「胜率」三项（V515 后端完整指标的前端落地），types.ts 补 total_performance 完整指标字段。

---

**组合绩效完整指标（V515）**：portfolio_engine `_aggregate_performance` 由「仅 total_return/annual_return/total_stocks/total_cash 4 字段」升级为与多策略引擎对齐——基于合并净值曲线 + 汇总成交喂给 PerformanceAnalyzer，得到与单标的回测同口径的完整 19 项指标（夏普/最大回撤/胜率/盈亏比等）；组合页可展示完整绩效。补完整指标回归测试。

---

**超额命中率 0 值显示修复（V514）**：前端 `fmtAccSigned` 对 0 值原显示 `+0.0%`（误导为正超额），改为中性 `0.0%`（仅正值显式加 `+`）——「与随机相当」不再被误读为优于随机；补 0 值边界测试。

---

**组合年化收益加权（V513）**：portfolio_engine `_aggregate_performance` 的 `annual_return` 原简化为直接等于 `total_return`（非年化），改为各标的年化收益资金加权——组合页年化收益不再被高估/低估；补加权年化回归测试。

---

**自选池选股同分排序优化（V512）**：fundamental/pipeline `run_screen` 排序与 scan_market（V511）对齐——同分时按三维总分（tree+grain+vegetable）作次级排序键，多维度强的标的排前，避免任取。

---

**全市场扫描同分排序优化（V511）**：fundamental/pipeline `scan_market` 排序在同分（如多只「粮型」都 100 分）时增加三维总分（tree+grain+vegetable）作次级键，让「多维度都强」的标的排前，避免仅按代码顺序任取 top_n（实测全市场扫描 top10 从任意粮型股变为中际旭创/新易盛等三维满分龙头）；补同分排序回归测试。

---

**组合净值回撤符号修复（V510）**：portfolio_engine `_build_combined_equity` 的 `drawdown` 原为 `total - peak`（负数）且 `drawdown_pct` 除以初始资金，与 PortfolioTracker 的 `peak - total`（正数、除以运行峰值）口径不一致；改为与单标的口径一致（正数 + 除以运行峰值）。补组合净值 drawdown 非负回归测试。

---

**引擎 bar 索引取位置修复（V509）**：engine `_find_bar_index` 原用 `.idxmax()` 返回 label，当 df.index 非默认 RangeIndex 时 label != position，ExecutionModel（TWAP/VWAP/Limit）路径会取错 bar；改为 `.argmax()` 返回位置索引（与 orders.py `_find_bar_index` 的既有修复一致）。补非默认 index 回归测试。

---

**在线 advice table 补平均持有（V508）**：online advice --output table 汇总行补「平均持有 N 根」，与 CSV（V500）、md 明细及离线输出对齐。

---

**树型 ROE 年化（V507）**：fundamental/screener `score_tree` 的 ROE 按报告期月数年化（同 V504 的 EPS 口径：一季报 *4、中报 *2、三季报 *4/3、年报 *1），避免一季报单期 ROE 系统性低估「高ROE」龙头——实测贵州茅台 2026Q1 ROE 10.06% 年化 40.2% 后由「粮型」正确改判「树型」；补 ROE 年化打分 + `_annualize_pct` 测试。

---

**最大回撤持续时间修复（V506）**：performance 的 `_compute_max_dd_duration` 原从谷底往前找第一个 `total[i] > total[谷底]` 作回撤起点，把「跌破谷底水位线」误判为起点，严重低估持续时间（峰值后一路阴跌 4 根被算成 1 根）；改为取谷底之前最近一次达到历史峰值处作回撤起点。补峰值→谷底 + 多峰值回归测试。

---

**因子去极值 MAD 退化修复（V505）**：factor/transform `winsorize` 的 MAD 法在「超过半数取值相同 → MAD=0」时原会把上下界都定在中位数、把所有值（含真实离群点）误裁到中位数；改为 MAD=0 时回退标准差法（std=0 则跳过裁剪）。补 MAD 退化回退回归测试。

---

**PE 动态年化（V504）**：fundamental/pipeline `_valuation` 的 PE 改用「动态市盈率」——EPS 按报告期月数年化（一季报 *4、中报 *2、三季报 *4/3、年报 *1），避免用一季报单期 EPS 直接算 PE 系统性高估（实测贵州茅台 2026Q1 EPS 21.76 由 PE 66.6 修正为 16.7）；补四期年化 + 无法解析报告期测试。

---

**卖点基准方向对齐（按类型路径 V503）**：signal_accuracy 的 `compute_signal_accuracy_by_type`（缠论买卖点按类型分组准确度）卖出类信号随机基准同 V502 一样误用 P(up)，改为对齐下跌方向（基准命中率 = 1-P(up)、基准收益取反）——缠论页「买卖点准确度验证」面板的卖点（1卖/2卖/3卖）超额命中率与结论随之一并修正；补下跌市卖点类型基准回归测试。

---

**卖点基准方向对齐（V502）**：signal_accuracy 的 `compute_signal_accuracy` 卖出信号随机基准原误用「上涨概率 P(up)」作命中基准，在单边市里高估/低估卖点择时价值；改为对齐下跌方向——卖出基准命中率 = 1 - P(up)、基准收益 = -随机买入平均收益。补下跌市卖出基准回归测试（超额应 ≈ 0 而非旧实现 1.0）。

---

**基本面页补每股指标与估值列（V501）**：FundamentalView 的选股结果表与全市场扫描表统一补「每股净资产(bps)」「每股现金流(ocf_ps)」两列；扫描表在「附带后续表现」时同步补「PE」「PB」两列（与选股表 V497 对齐），把后端 V497/V499 透出的每股指标与估值完整呈现在前端。

---

**在线 advice CSV 补持有期列（V500）**：online advice --output csv 汇总行补 `avg_holding_bars`、逐笔明细补 `holding_bars`，与 table/md 明细及离线 CSV 对齐（V483-V485 落 simulator 后在线 CSV 漏同步）。

---

**基本面数据透出补全（V499）**：单标财务指标 API（/fundamental/indicator）字段补 `bps`（每股净资产，此前 indicator_values 已算但路由未透出），并抽为 `_INDICATOR_COLS` 常量便于维护；`screen_stock` indicators 补 `ocf_ps`（每股经营现金流，分红能力代理，此前同样被丢弃）。补 cols 契约 + bps/ocf_ps 输出测试。

---

**建议回放跳空成交（V498）**：advice_simulator 的 `simulate_advice_trade`/`simulate_advice_batch`/`simulate_advice_hold_sweep` 新增可选 `opens` 参数——提供开盘价时启用跳空成交：开盘价已越过止损/止盈则按开盘价成交（止损跳空更保守、止盈跳空更真实），否则仍按盘中 high/low 触发；CLI（online/offline advice、advice-batch、hold-sweep）与 Web advice-simulate 全链路透传 opens；补跳空多/空、未跳空回归测试。

---

**基本面选股估值（PE/PB）落地（V497）**：fundamental 管线补齐估值输出——`screen_stock` indicators 补 `bps`（每股净资产），pipeline 新增 `_valuation`（用目标日收盘价 as_of_close + eps/bps 计算 PE/PB，亏损/无净资产/无价格置 None），`run_screen`/`scan_market` 在附带表现时输出 `valuation` 字段；前端 FundamentalView 结果表补「PE」「PB」两列（两位小数）。补 bps 输出 + PE/PB 计算/亏损/无价格/缺失 bps 测试。

---

**量价相关性因子（V496）**：factor/builtin/volume.py 新增 `vol_price_corr`（20 日收益率与成交量滚动相关系数，正值=上涨放量/下跌缩量的健康量价配合），补齐 A 股选股「量价背离」监测维度；补注册 + 有界性 + 同向趋势方向性测试。

---

**价值类因子落地（V495）**：factor/builtin/value.py 的 `pe_ratio`/`pb_ratio` 由死占位（恒 NaN）改为真实可算——df 携带 `eps`/`bps` 基本面列时按 `close/eps`、`close/bps` 计算，非正分母（亏损/无净资产）置 NaN，未携带列时返回全 NaN（数据缺失语义）；补 PE/PB 计算/缺失/负 eps 测试。

---

**V102 决策支持 ATR 窗口修复（V494）**：mmd_v102.py `_calc_decision_support_enhanced` 的止损 ATR 原误取 K 线窗口「最前 14 根」（历史早期波动），改为「最近 14 根」——止损宽度现在反映当前波动率（ATR 止损的本意）；补 ATR 窗口回归测试（前静后烈场景止损应取近期宽幅）。

---

**树型选股变量命名修正（V493）**：fundamental/screener.py `score_tree` 中取营收的变量由误导性命名 `assets` 改为 `revenue`，与「营收体量大」打分语义一致（纯重构，行为不变）。

---

**强势股趋势一致性指标（V492）**：screen/strength.py 新增 `_trend_quality`（60 日对数价线性回归 R²，1=完美线性趋势，0=无序），`compute_strength_metrics` 返回 `trend_quality`，`StrengthResult`/`to_json`/`to_table` 同步输出「趋势」列——补充波动率惩罚只能量「幅度」、无法量「路径平滑度」的短板，直接服务 steady 预设「稳着涨」定位。

---

**选股技术因子补 KDJ（V491）**：factor/builtin/technical.py 新增 `kdj_j` 因子（KDJ J 值归一化到 [-1,1]，正值超买/负值超卖），补齐 A 股选股常用的技术指标因子，与 RSI14/BollPosition 归一化口径一致；补注册与上涨/下跌趋势方向性测试。

---

**选股热门股票池去重（V490）**：web/routers/screening.py `_get_stock_list` SH 池重复代码 601398 去重并补 600887；补「股票池无重复代码」回归测试。

---

**回放空结果契约对齐（V489）**：advice_simulator 的 `simulate_advice_batch` 与 `summarize_batch` 在「无有效交易」时空结果补齐全部统计键（median_return/profit_factor/long_stats/short_stats/avg_holding_bars/stop/tp/expire/avg_mae/avg_mfe 等），与正常结果键一致，下游可依赖稳定 schema 避免 KeyError；补空结果 schema parity 回归测试。

---

**advice table 明细补持有（V488）**：advice --output table 明细表补持有根数列，与 V487 md 明细对齐。

---
