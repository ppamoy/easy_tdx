# 更新日志

本文件记录 easy-tdx 的版本变更。格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/)。

## [Unreleased]

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

**offline advice md 明细补列（V487）**：offline advice --output md 明细表补持有根数/MAE%/MFE% 列，与 CSV/table 格式对齐。

---

**平均持有期断言（V486）**：summarize_batch 测试补 avg_holding_bars 断言（3+2+5）/3 = 3.33。

---

**建议模拟批量加平均持有期（V485）**：simulate_advice_batch 单标的批量结果也加 avg_holding_bars（与 V484 的 summarize_batch 对齐）。

---

**建议批量汇总加平均持有期（V484）**：summarize_batch 加 avg_holding_bars（平均持有根数），与 V483 单笔 holding_bars 对齐。

---

**建议模拟持有根数（V483）**：simulate_advice_trade 单笔结果加 holding_bars（实际持有根数），便于统计平均持有期。

---

**hold-sweep 输出补中位数（V482）**：advice --hold-sweep 各持有期对比补 median_return，与单标的批量统计对齐。

---

**成交量序列测试（V481）**：execution._volume_series 纯函数补测试（vol 优先、volume 回退、缺失返回 None）。

---

**fmtPct/fmtAcc 边界测试（V480）**：前端格式函数补 NaN/Infinity 边界测试（与 fmtPf V472 一致，均返回占位符）。

---

**advice-batch 汇总补中位数（V479）**：offline advice-batch 输出补 summary_median_return，与单标的 JSON 对齐。

---

**advice table 汇总补中位/盈亏比（V478）**：advice --output table 汇总行补中位数收益与盈亏比，与 CSV/JSON 对齐。

---

**最大连续盈亏测试（V477）**：performance._compute_max_consecutive_trades 纯函数补测试（连续盈利/亏损最大次数、空序列、零盈亏打断连续）。

---

**样本外判定测试（V476）**：out_of_sample._build_oos_verdict 纯函数补测试（过拟合/泛化/无命中率文案）。

---

**分段标签/判定测试（V475）**：robustness._best_segment_label/_worst_segment_label/_build_verdict 纯函数补测试（最佳/最差段标签、过拟合/稳健判定文案、空输入）。

---

**分段命中率测试（V474）**：robustness._seg_hit_rate 纯函数补测试（优先 5 根、回退 3 根、无准确度/无买入返回 None）。

---

**总体结论盈亏比 ∞ 显示（V473）**：_build_type_summary 的「最强买点/卖点」文案盈亏比 PF>=999（仅盈利）显示 ∞，与前端 fmtPf 一致。

---

**文档与边界测试（V470-V472）**：

- **V470** simulate_advice_batch docstring 补 median_return/profit_factor/long_stats/short_stats
- **V471** summarize_batch docstring 补 median_return/avg_mae/avg_mfe
- **V472** fmtPf 补 Infinity/NaN 边界测试

---

**盈亏比 999 边界测试（V469）**：grading 补测试——profit_factor=999（仅盈利无亏损）评分应为满分 100（interpolate 取最高锚点分）。

---

**信号准确度面板加中位/盈亏比（V468）**：SignalAccuracyPanel（回测页信号准确度，buy/sell 方向）表格加中位收益与盈亏比列（复用 fmtPct/fmtPf）。

---

**多空分组测试（V467）**：simulate_advice_batch 测试补 long/short 分组正确性（2 long + 1 short → long_stats.count=2, short_stats.count=1）。

---

**advice 输出补中位数（V466）**：advice CSV/JSON 输出补 median_return，与 V461/V463 后端中位数对齐。

---

**建议模拟多空分开统计（V465）**：simulate_advice_batch 加 long_stats/short_stats（买点/卖点信号分别的笔数、胜率、平均收益），揭示模型多空不对称表现。

---

**建议模拟中位数断言（V464）**：simulate_advice_batch 测试字段循环补 median_return。

---

**建议模拟批量加中位数收益（V463）**：simulate_advice_batch 单标的批量结果也加 median_return（与 V461 的 summarize_batch 对齐），比均值稳健。

---

**中位数收益断言（V462）**：summarize_batch 测试补 median_return 断言（sorted [-2,1,3] → 1.0）。

---

**建议批量汇总加中位数收益（V461）**：summarize_batch 加 median_return（中位数收益，比均值稳健、不受极值影响）。

---

**advice 持有期敏感性 CLI（V460）**：advice 命令加 --hold-sweep 选项，对同一批建议用 3/5/10/20 根 max_hold 模拟并输出多持有期对比 JSON（各持有期的胜率/平均收益/盈亏比）。

---

**非按类型信号准确度加盈亏比（V459）**：compute_signal_accuracy（回测页信号准确度，buy/sell 方向）的统计也加 profit_factor，与 V430 的按类型版本对齐。

---

**缠论页准确度持有期切换（V458）**：缠论分析页「买卖点准确度验证」加持有期下拉（3/5/10/20 根），byTypeHorizon 按所选持有期取统计（缺则回退 5/3）。

---

**总体结论盈亏比测试（V457）**：_build_type_summary 补测试——最强买点/卖点文案附盈亏比、PF=0 时不含盈亏比。

---

**信号类型总体结论加盈亏比（V456）**：_build_type_summary 的「最强买点/卖点」文案加盈亏比（PF>0 时附），与 V432 单类型判定、V430 统计对齐。

---

**formatError 测试（V455）**：前端 formatError 纯函数补测试（fetch TypeError → 网络错误提示、Error → message、非 Error → 字符串）。

---

**选股评分重构（V454）**：抽 _latest_mmd_obj 纯函数，消除 _calc_stock_quality/_get_latest_mmd/_calc_quality_score 三处重复的「取最新买卖点」逻辑。

---

**盈亏比 ∞ 显示（V453）**：新增 fmtPf——profit_factor >= 999（仅盈利无亏损）显示 ∞，其余保留两位小数；缠论准确度面板与缠论页排名表统一使用。

---

**选股方向判断回归测试（V452）**：_get_latest_mmd 补测试——类二买 2buy_s 应取 low（回归 V429 修复）、3sell 取 high、无信号返回 None。

---

**实证复盘页列表状态指示（V451）**：买卖点实证复盘页左列表加预跑状态指示（ready=绿✓ / failed=红✗ / pending=灰…），配合 V427 在线回退，让用户一目了然哪些标的已预跑、哪些无数据。

---

**offline advice-batch 汇总补指标（V450）**：advice-batch 的 md 汇总加盈亏比，json/table/csv 输出加 summary_profit_factor/summary_avg_mae_pct/summary_avg_mfe_pct 字段。

---

**offline advice JSON 补盈亏比（V449）**：offline advice 单标的 JSON 汇总补 profit_factor，与 CSV/Markdown/table 格式对齐。

---

**选股逻辑测试覆盖（V447-V448）**：

- **V447** _calc_stock_quality 集成测试（验证 V102 评级 + 风险回报比 + 买入方向加分）
- **V448** _pass_screening 选股门槛测试（无信号/低质量不通过）

---

**advice table 输出补充指标（V446）**：advice --output table 格式汇总补 profit_factor、逐笔明细补 MAE%/MFE% 列，与 CSV/Markdown 格式对齐。

---

**信号排名加盈亏比（V445）**：compute_signal_accuracy_by_type 的 ranking 条目加 profit_factor，前端排名表直接用 rank.profit_factor（不再间接查 by_type），前后端契约自包含。

---

**多持有期敏感性分析（V444）**：新增 simulate_advice_hold_sweep，同一批建议用不同 max_hold（3/5/10/20）模拟，返回各持有期的表现对比，帮助评估建议对持有期的敏感性、选择合适止盈/到期窗口。

---

**缠论页准确度验证加盈亏比列（V443）**：缠论分析页「买卖点准确度验证」排名表加盈亏比列（复用 V430 的 profit_factor），与回测页准确度面板对齐。

---

**建议批量汇总加平均 MAE/MFE（V442）**：summarize_batch 跨标的聚合结果加 avg_mae_pct / avg_mfe_pct（平均最大不利/有利偏移），与单笔 MAE/MFE 对齐，提供跨标的风险/盈利潜力汇总。

---

**建议模拟 CLI 输出补充指标（V441）**：advice --output csv/md 输出补充 profit_factor（汇总）、mae_pct/mfe_pct（逐笔明细），与 V435/V439/V440 新增字段对齐。

---

**建议模拟单笔加最大有利偏移（V440）**：simulate_advice_trade 结果在 MAE 之外再加 mfe_pct（最大有利偏移 MFE，方向对齐后的最大浮盈百分比），与 MAE 对称——MFE 大但 return_pct 小说明止盈过早。

---

**建议模拟单笔加最大不利偏移（V439）**：simulate_advice_trade 结果加 mae_pct（最大不利偏移 MAE，方向对齐后的最大浮亏百分比），与 profit_factor（收益）互补，评估止损设置是否合理。

---

**选股页展示风险回报比（V438）**：选股结果卡片在 V102 评级与操作建议之外展示风险回报比 RR。

---

**选股质量分纳入风险回报比（V437）**：选股质量分在 V102 信号质量之外，再纳入 V102 决策支持的风险回报比（RR>=2.0 加 10 分、>=1.5 加 7、>=1.0 加 3），让「交易计划质量」参与选股排序。

---

**建议批量汇总加盈亏比（V436）**：summarize_batch 跨标的聚合结果加 profit_factor（聚合所有交易的盈亏比），与单标的批量结果对齐。

---

**建议模拟与可信度展示盈亏比（V434-V435）**：

- **V434** 模型可信度面板展示盈亏比（择时准确度维度附 PF）
- **V435** 建议执行模拟批量结果加 profit_factor（平均盈利/平均亏损）

---

**模型可信度结合盈亏比（V433）**：模型可信度的择时准确度维度在超额命中率之外结合 profit_factor——PF<1（赢小亏大）时准确度分打 8 折，避免高命中率但盈亏比差被高估。

---

**信号判定结合盈亏比（V432）**：信号类型判定在命中率之外结合 profit_factor——命中率显著/略优于随机但 PF<1 时提示「盈亏比差」，避免「赢小亏大」被误判为有效信号。

---

**选股与择时完善（V428-V431）**：

- **V428** 选股质量分纳入 V102 信号质量评分卡（评级 A/B/C + 强度 + 买入方向优先）
- **V429** 修复方向判断 bug：endswith("buy") 漏判类二买（2buy_s），改用包含判断 
- **V430** 信号准确度统计加盈亏比 profit_factor（方向对齐，仅盈利取 999 避免 JSON inf）
- **V431** 缠论准确度面板展示盈亏比列

---

**买卖点实证复盘在线回退（V427）**：verify 预跑数据源离线 .day 无数据时，自动回退在线 TDX 客户端（复用 fetch_qfq_klines QFQ 前复权），保证无本地 vipdoc 数据也能预跑 20 只标的。

---

**缠论学习页面（V420-V426）—— OpenSpec change easy-tdx-chanlun-learning 七能力域落地**：

- **V420** 理论教学：6 篇缠论概念（分型/笔/线段/中枢/三类买卖点/背驰）+ LessonCard/TheoryLessons/LearnView + /learn 路由
- **V421** 难度分级 + 随机标的：训练候选点按置信度过滤（easy/medium/hard，seed 复现）+ 🎲 随机标的
- **V422** 错误归因：答错展示「正确解读」（explanation 拼接 mmd.msg + V102 建议）
- **V423** 结构时间线：已揭示分型/笔/中枢事件列表，点击跳转
- **V424** 学习进度 + 排行榜增强：train_score 加 difficulty 维度 + 掌握度矩阵 + 排行榜难度筛选/分组汇总
- **V425** 成绩趋势：progress 返回最近 N 次，前端命中率条形图
- **V426** 错题集：答错自动入集 + 学习中心错题复习列表
- **质量**：后端 pytest 3121 passed（+21）、前端 vitest 47 passed、vue-tsc + vite build、ruff/mypy/prettier 全绿

---

**买卖点实证复盘（V418-V419）—— 缠论学习页面需求与 Phase 7 落地**：

- **V418** OpenSpec 需求梳理：7 能力域（理论教学/可视化/难度分级/错误归因/进度/排行榜/实证复盘）+ 45 项任务，提交于 openspec/changes/easy-tdx-chanlun-learning/
- **V419** 买卖点实证复盘落地：后端 verify 路由（预置 20 只大市值标的池 + prerun 缓存 + list/detail + mmd.zs_index 同级别中枢关联）+ 前端 SignalVerifyView（左列表+右单标的详情，买卖点后逐根 K 线揭示，同级别中枢）
- **V419** ChanlunChart 新增 singleZsIndex prop（同级别中枢过滤）+ reveal 逐根游标复用
- **质量**：后端 pytest +7（verify 契约）、前端 vitest 43 passed、vue-tsc + vite build 通过、ruff/mypy 归零

---

**质量加固续章四十二（V416）—— backtest _optimize_one_strategy 测试**：

- **V416** web/routers/backtest.py _optimize_one_strategy 未知策略/完整寻优测试（+2 用例）。

---

**质量加固续章四十一（V415）—— backtest _run_optimize 测试**：

- **V415** web/routers/backtest.py _run_optimize 网格寻优/Walk-Forward 测试（+2 用例）。

---

**质量加固续章四十（V414）—— backtest _run_backtest 测试**：

- **V414** web/routers/backtest.py _run_backtest 未知策略/完整运行测试（+2 用例）。

---

**质量加固续章三十九（V413）—— client fund_flow/minute 编排测试**：

- **V413** client.py get_fund_flow/get_history_fund_flow/get_minute_time_data 编排测试（+4 用例）。

---

**质量加固续章三十八（V412）—— mac qfq 重算 + 逐笔分页测试**：

- **V412** mac/client.py _local_recompute_qfq 降级 + get_transactions 分页测试（+3 用例）。

---

**质量加固续章三十七（V411）—— mac get_board_change_ranking 测试**：

- **V411** mac/client.py get_board_change_ranking 非法 days/空板块/完整排行测试（+3 用例）。

---

**质量加固续章三十六（V410）—— mac K线分页编排测试**：

- **V410** mac/client.py _fetch_kline_pages 分页 + get_stock_kline/get_stock_kline_with_indicators 测试（+4 用例）。

---

**质量加固续章三十五（V409）—— mac get_board_ranking 测试**：

- **V409** mac/client.py get_board_ranking 非法 sort_by/空板块/完整聚合 + get_stock_quotes 测试（+4 用例）。

---

**质量加固续章三十四（V408）—— mac client get_* 编排路径测试三**：

- **V408** mac/client.py tick_chart/board_members/board_summary/transactions 编排路径测试（+5 用例）。

---

**质量加固续章三十三（V407）—— mac client get_* 编排路径测试二**：

- **V407** mac/client.py chart_sampling/board_list/file_meta/download_file/goods_list 编排路径测试（+7 用例）。

---

**质量加固续章三十二（V406）—— mac client get_* 编排路径测试**：

- **V406** mac/client.py get_symbol_info/belong_board/capital_flow/auction/unusual/server_info/kline_offset 编排路径测试（+7 用例）。

---

**质量加固续章三十一（V405）—— client get_* 编排路径测试二**：

- **V405** client.py get_security_quotes/get_block_info/get_report_file/get_price_limits 编排路径测试（+6 用例）。

---

**质量加固续章三十（V404）—— client get_* 编排路径测试**：

- **V404** client.py get_security_count/list/xdxr/finance/company/market_stat 编排路径测试（+8 用例）。

---

**质量加固续章二十九（V403）—— client _execute 韧性路径测试**：

- **V403** client.py TdxClient._execute 成功/无重连/重试恢复测试（+3 用例）。

---

**质量加固续章二十八（V402）—— cmd_run_all 组合边界 + cmd_reverify 多策略错误分支测试**：

- **V402** _run_combo_screen 边界 + _reverify_multi 未知市场/策略未注册/行情不足测试（+4 用例）。

---

**质量加固续章二十七（V401）—— mmd.py 第五阶段拆分（V13-V40）**：

- **V401** V13-V40 自包含条件簇（104 函数）+ MMDQuality 迁入 mmd_conditions.py，mmd.py 14000→5960 行，顶层 __all__ 惰性再导出。

---

**质量加固续章二十六（V400）—— cmd_verify 校验 + scanner 测试**：

- **V400** cli/cmd_verify.py verify-multi/verify-portfolio 校验分支 + screen/scanner.py 策略文件定位测试（+8 用例）。

---

**质量加固续章二十五（V399z）—— cmd_run_all _load_strategy_class 测试，覆盖率越过 72%**：

- **V399z** cli/cmd_run_all.py _load_strategy_class 测试（+4 用例）。

---

**质量加固续章二十四（V399y）—— unusual 截断记录边界测试**：

- **V399y** mac/commands/unusual.py 截断记录边界测试（+1 用例）。

---

**质量加固续章二十三（V399x）—— mac 零星边界测试**：

- **V399x** mac/commands 零星边界测试（kline_offset/auction/belong_board，+4 用例）。

---

**质量加固续章二十二（V399w）—— mac 最后残余路径测试**：

- **V399w** mac/commands 最后残余路径测试（+4 用例）。

---

**质量加固续章二十一（V399v）—— mac 残余边界测试**：

- **V399v** mac/commands 残余边界测试（symbol_bar 分时/非法日期 + unusual 0x0B/0x14 子分支，+4 用例）。

---

**质量加固续章二十（V399u）—— symbol_bar/tick_chart 解析测试**：

- **V399u** mac/commands/symbol_bar.py + symbol_tick_chart.py 解析测试（+3 用例）。

---

**质量加固续章十九（V399t）—— cmd_verify 校验分支测试**：

- **V399t** cli/cmd_verify.py verify 命令的 --params 非法 JSON / 未知策略分支测试（+2 用例）。

---

**质量加固续章十八（V399s）—— transport recv + tick_chart 编解码测试**：

- **V399s** ex/transport/sync _recv_exact_sock + mac/commands/symbol_tick_chart 编解码测试（+5 用例）。

---

**质量加固续章十七（V399r）—— symbol_quotes 字段位图 + unusual 文本段测试**：

- **V399r** mac/commands/symbol_quotes.py 字段位图解析路径 + unusual.py 名称文本段测试（+2 用例）。

---

**质量加固续章十六（V399q）—— mac unusual 全类型分支测试**：

- **V399q** mac/commands/unusual.py _describe_unusual 全部异动类型分支测试（+14 用例）。

---

**质量加固续章十五（V399p）—— mac 协议编解码测试五**：

- **V399p** mac/commands/symbol_tick_chart.py + symbol_quotes.py + board_members_quotes.py 协议编解码测试（+7 用例）。

---

**质量加固续章十四（V399o）—— mac 协议编解码测试四**：

- **V399o** mac/commands/symbol_transaction.py + file_query.py 协议编解码测试（+8 用例）。

---

**质量加固续章十三（V399n）—— mac 协议编解码测试三**：

- **V399n** mac/commands/board_list.py + symbol_info.py + goods_list.py 协议编解码测试（+9 用例）。

---

**质量加固续章十二（V399m）—— mac 协议编解码测试二**：

- **V399m** mac/commands/symbol_capital_flow.py + symbol_auction.py + chart_sampling.py 协议编解码测试（+9 用例）。

---

**质量加固续章十一（V399k/l）—— mac 协议编解码测试**：

- **V399k/l** mac/commands/server_info.py + symbol_belong_board.py 协议编解码测试（+9 用例）。

---

**质量加固续章十（V399j）—— diagnosis 路由纯函数测试**：

- **V399j** web/routers/diagnosis.py 纯函数测试（_to_json_safe/_detect_divergence/_calculate_position_recommendation/_get_position_notes/_calc_volume_profile_for_diagnosis，+13 用例）。

---

**质量加固续章九（V399i）—— backtest 路由纯函数测试**：

- **V399i** web/routers/backtest.py 的 _ohlcv_to_df/_filter_df_by_date/_now 纯函数测试（+8 用例）。

---

**质量加固续章八（V399g/h）—— 协议编解码 + 板块名解析测试**：

- **V399g** mac/commands/unusual.py 协议编解码（_describe_unusual 全类型分支 + UnusualCmd，+9 用例）。
- **V399h** cli/cmd_company.py 分块读取/板块名解析（_read_full_section/_resolve_filename，+6 用例）。

---

**质量加固续章七（V399f）—— cli/cmd_offline 纯函数测试**：

- **V399f** 补 cli/cmd_offline.py 的 _df_to_bars/_is_index_code/_watch_signal_row/_is_within_since_days/_fmt_opt_price/_render_watch_report/_advice_batch_one 纯函数测试（+10 用例）。

---

**质量加固续章五（V399c）—— fundamental/pipeline 纯函数测试**：

- **V399c** 补 fundamental/pipeline.py 的 _returns_at/_sina_frame/_summarize_periods 纯函数测试（+6 用例），并修正 diagnosis 的 _calc_volume_profile 显式导入。

---

**质量加固续章四（V399b）—— mmd.py 第五阶段拆分（V41-V65 全部迁出）**：

- **V399b** mmd.py 拆分第五步：V44 条件簇（13 个 _calc_* 函数）+ _calc_confidence 及其共享辅助闭包（8 个函数）迁入 mmd_conditions.py，mmd.py 从 15605 行降到 14001 行；V41-V65 版本化条件簇至此全部迁出，mmd.py 顶层惰性再导出保持兼容。

---

**质量加固续章三（V399）—— mmd.py 第四阶段拆分**：

- **V399** mmd.py 拆分第四步：5 个叶子辅助函数（_calc_atr/_calc_rsi/_calc_adx_strength/_calc_ma_slope/_calc_volume_profile）+ V41/V42/V48/V51 四个条件簇（17 个 _calc_* 函数）迁入 mmd_conditions.py，mmd.py 17328→15607 行；另补 cmd_run_all 纯函数 + fundamental/indicators 纯函数测试（+13 用例）。

---

**质量加固续章二（V397-V398）—— mmd.py 第三阶段拆分 + 覆盖率冲过 70% 门槛**：

- **V397** mmd.py 拆分第三步：V49-V65 自包含条件簇（条件137-195 的 95 个 _calc_* 函数约 9500 行）迁入 mmd_conditions.py，mmd.py 从 26693 行降到 17328 行；mmd_conditions.py 补充 ATR/KDJ/RSI/numpy/MMDType/BI/ZS 依赖，顶层惰性再导出保兼容——29k 行 god-module 三阶段累计瘦身约 1.2 万行。