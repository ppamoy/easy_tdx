# 更新日志 V83

## [V83] — 2026-08-29

**缠论核心结构精度 + 图表可视化 + 多级别联立修复**

本次围绕用户核心诉求：缠论模型准确性、K线图精准显示笔/线段/中枢/买卖点、多级别联立功能修复，以及买卖点判断精度提升。

### 缠论结构算法修复（准确性）

- **线段（XD）特征序列算法重写**（`src/easy_tdx/chanlun/xd.py`）—— 原实现用「3笔+中枢重叠」简化法，且线段方向不会交替。重写为标准特征序列法：线段方向=起始笔方向，特征序列=反向笔，出现特征分型（向上线段顶分型 / 向下线段底分型）时结束；相邻线段共享转折点，方向自然交替（up/down/up/down）。

- **中枢（ZS）形成逻辑修复**（`src/easy_tdx/chanlun/zs.py`）—— 原实现 `if len(zss) == 0 or True:` 为恒真死代码。重写为：逐笔扫描累积重叠区间，笔完全离开时才关闭中枢，≥3笔才成立，正确处理未完成中枢。

- **一类买卖点背驰判定增强**（`src/easy_tdx/chanlun/mmd.py`）—— `_is_strong_beichi` 增加「新极值确认」：趋势背驰（笔背驰、两中枢趋势背驰）要求向下笔创出新低/向上笔创出新高，避免把盘整中的普通回调误判为 1买/1卖；盘整背驰保持不要求新极值。

- **一类买卖点识别所有有效背驰点 + 信号去噪**（`src/easy_tdx/chanlun/mmd.py`）—— 原实现只取第一个背驰点；现识别各趋势段末端背驰点，同时限制相邻 1买/1卖 至少相隔 5 笔，避免信号风暴（烟雾测试 40 个→15 个）。

- **买卖点去重规则改进**（`src/easy_tdx/chanlun/mmd.py`）—— 同位置若同时出现买入与卖出候选，按方向分组各保留最高优先级信号，不再互相覆盖。

### V81/V82 条件实现（此前仅接线未实现，属真实功能缺口）

- **V81 四个函数**（`src/easy_tdx/chanlun/mmd.py`）—— 波动率状态转换检测(条件256)、关键支撑阻力强度验证(条件257)、量价能量分布验证(条件258)、信号执行窗口评估(条件259)。此前 `find_mmds_v39` 已接线调用但函数未定义，运行时 NameError 被 try/except 吞掉，条件从未生效；现已完整实现并参与置信度计算。

- **V82 四个函数**（`src/easy_tdx/chanlun/mmd.py`）—— 买卖点时间衰减验证(条件260)、中枢突破回踩确认(条件261)、多级别MACD共振验证(条件262)、波动率压缩突破确认(条件263)。同样补齐实现。

### 多级别联立功能修复

- **低级别数据覆盖范围修复**（`src/easy_tdx/web/routers/chanlun.py`）—— 原实现取 `min(high_count*6, 3000)` 根低级别K线，日线800根(约3.2年)但30分钟3000根仅约1.5年，导致查询「最新高级别笔的低级别走势」永远为空——这是多级别联立失效的根因。现根据高级别实际时间跨度 × 每分钟频率K线数动态估算低级别K线数量（上限10000），保证时间覆盖。

- **低级别走势查询窗口增强**（`src/easy_tdx/chanlun/multi_level.py`）—— 当高级别笔位于数据末端（未完成笔）时，将查询窗口延伸到低级别数据末尾；统一时间比较兼容 date/datetime 混用。

- **一致性评分逻辑重写**（`src/easy_tdx/chanlun/multi_level.py`）—— 综合买卖点类型同向、趋势方向、中枢时间重叠、信号时间接近度四维，加入反向信号降权；修复原实现的时间窗口 bug。

### 图表可视化精准显示（前端）

- **笔/线段连线坐标修正**（`web-ui/src/components/ChanlunChart.vue`）—— 原实现向上笔画成 [起, high]→[终, low]（方向颠倒）。现按方向精确锚点：向上笔从低点指向高点，向下笔从高点指向低点；线段同理，并按方向着色（上绿下红）。

- **单级别分析数据映射修复**（`web-ui/src/views/ChanlunView.vue`）—— 原单级别（非多级别）分支只映射 bis/xds，导致图表不显示中枢、买卖点、分型、背驰。现补齐 zss/mmds/fxs/bcs 映射。

- **分型/背驰字段对齐**（`web-ui/src/views/ChanlunView.vue`）—— 多级别分支的 fractals 引用不存在的后端私有方法；bcs 优先使用主 date 字段。

### 测试

- **V81/V82 测试全部通过**（`tests/unit/test_chanlun_v81.py` + `test_chanlun_v82.py`，40 个用例）—— 补齐实现后由 25 个失败转全绿。
- **ConditionGroup 枚举测试修复**（`tests/unit/test_chanlun_v64_backtest.py`）—— 期望集合补入 V81/V82。
- 全量测试：**2194 passed, 2 skipped**（基线含 25 个 V81/V82 失败 + 1 个 V64 枚举失败，现全部修复）。
- ruff：新增/重写文件全部通过。


### 买卖点置信度校准（精准判断核心修复）

- **信号新鲜度衰减类型感知**（`src/easy_tdx/chanlun/mmd.py`）—— 原 `_calc_signal_freshness` 按 3买/3卖 的15根K线短窗口统一惩罚所有信号，导致 1买/1卖（趋势反转、入场窗口宽达数周-数月）也被重罚（新鲜强背驰 1买 置信度被压到 0.00~0.15）。现 1买/1卖/2买/2卖 使用 120 根K线的宽松窗口，3买/3卖 保持 15 根紧窗口。

- **置信度有界收敛**（`src/easy_tdx/chanlun/mmd.py` `find_mmds_v39`）—— V39-V82 共 160+ 个条件各自做 ±0.01~±0.05 小幅调整，累计漂移会把强信号压向 0 边界。现捕获 V47 校准基线，最终置信度收敛到基线 ±0.25 内——保留条件的细化能力，同时防止过度压制。实测：真底强 1买 从 0.15 → **0.67**；下跌途中过早的 1买 保持低置信度（0.28~0.30）。

### 回测策略健壮性

- **缠论策略容错纯 OHLC 数据**（`src/easy_tdx/backtest/strategies/chanlun.py`）—— `init` 直接访问 `self.data.amount.raw`，数据缺 amount 列时 KeyError 崩溃。现 vol/amount 缺失回退 0，纯 OHLC 数据可正常运行回测。

### 验证

- 全量测试：**2194 passed, 2 skipped**；V81/V82 40 用例通过；新增代码 mypy strict 零错误；ruff 通过。
- 端到端验证：缠论回测策略完整跑通（含纯 OHLC 数据），结构产出合理（笔/中枢/线段/买卖点）。


### 买卖点识别索引一致性修复（2买/2卖/3买/3卖 准确性）

- **_find_second_type_mmds 时间窗口索引混用修复**（src/easy_tdx/chanlun/mmd.py）—— 原实现用 bi.start.k.k_index - buy_1_idx（原始K线索引 - 笔索引）比较 30/40 根 K 线窗口。两种索引尺度不同（K线索引可达数百、笔索引仅到笔数），差值恒超阈值，导致 2买/2卖 的离开笔/回调笔搜索几乎永不成立。现改为 - buy_1_bi.end.k.k_index / - sell_1_bi.end.k.k_index（同为K线索引）。

- **_find_third_type_mmds 突破笔搜索索引错位修复**（src/easy_tdx/chanlun/mmd.py）—— 原实现 bi.start.k.index > zs_end_idx 用合并K线序号与原始K线索引比较（合并后序号远小于原始索引），导致位于中枢之后的突破笔被错误过滤，3买/3卖 可能漏判。现改为 bi.start.k.k_index > zs_end_idx 同尺度比较。

- **回调缩量基准改为信号点局部均量**（src/easy_tdx/chanlun/mmd.py）—— 原 _calc_avg_volume(volumes, 20) 取数据末端 20 根均量作比较基准，历史信号的"回调缩量"会与后期放量段比较而误判。新增 _calc_local_avg_volume(volumes, anchor_idx, 20)，2买/2卖 以 1买/1卖 结束K线为锚、3买/3卖 以中枢结束K线为锚取局部均量。

### 回归测试

- **新增 tests/unit/test_chanlun_v83_index_regression.py**（6 个用例）—— 构造笔索引与K线索引刻意脱钩的数据（如 index=0 但 k_index=100），验证：2买/2卖 在 K 线窗口内可被识别、超出 40 根 K 线窗口被拒绝、3买/3卖 突破笔按 k_index 正确搜索。旧逻辑下这些用例会失败（k_index - bi_index > 30 恒真）。

### 验证

- 全量测试：2200 passed, 2 skipped（+6 新回归用例）；ruff 通过。


### 一类买卖点过度生成修复（1买/1卖 精准化）

- **1买/1卖 必须建立在真实趋势之上**（src/easy_tdx/chanlun/mmd.py）—— 原实现用单一'最后完成中枢'作全局参考，导致历史上每个跌破该中枢的底部都被标注为 1买，纯震荡市也产生 4-10 个假信号。现：
  1. **同期参考中枢** _reference_zs_for_bi：每笔参考其发生时的中枢（笔开始前最后结束的中枢），而非数据末端最后中枢；最终跌破/突破笔（恰为关闭中枢的那一笔）退而参考最后中枢。
  2. **趋势门控**：trend_strength <= 0（少于 2 个同向中枢）时直接返回空——震荡市不产生 1买/1卖。
  3. **只认趋势背驰**：_is_strong_beichi 移除'盘整背驰'分支（中枢内力度衰竭），1买/1卖 仅由笔背驰/两中枢趋势背驰（均需创出新极值）触发；盘整背驰交由 2买/类二买 处理。
- **显著效果**（400 根合成K线实测）：纯震荡市 1买/1卖 从 4-10 个降为 **0**；多波趋势市从 13-15 个降为 3-11 个（每波一个）。
- **测试数据更新**（tests/unit/test_chanlun.py）—— test_result_to_dict_with_visual_dates 与 test_print_table_with_dates 原用单中枢正弦数据（改进后正确地不产出 1买），改为确定性'多中枢下跌→反转'数据（产出 2 中枢、1买、背驰），仍覆盖日期格式化断言。

### 回归测试

- **新增 tests/unit/test_chanlun_v83_trend_gate_regression.py**（4 个用例）—— 参考中枢取同期而非末端；最终跌破笔退而参考最后中枢；盘整背驰单独不触发 1买（旧逻辑下该用例失败）；创新低+力度衰减确认为趋势背驰。mypy strict 通过。

### 验证

- 全量测试：2204 passed, 2 skipped（+4 新回归用例）；ruff/mypy 通过。


### 长赢策略季节切换计时修复

- **src/easy_tdx/backtest/strategies/changying_chanlun.py** —— 原 _update_season 用 datetime.now()（墙钟时间）判断季节切换的30天间隔：回测中所有K线在几秒内跑完，days_since 恒为 0，导致季节**永远无法切换**（回测与实盘行为断裂）。修复：改用K线自身日期计时（新增 _latest_bar_datetime，兼容 int YYYYMMDD / numpy int64 / str / Timestamp / DatetimeIndex），无法取日期时退化为按K线计数（≥30根）；_season_history 记录 (日期, 季节, bar_index)。
- 新增回归测试 tests/unit/test_chanlun_v83_changying_season.py（6 用例，含 numpy int64 解析、>30 交易日可切换、<30 日被阻断）。

### 二/三类买卖点量能校准（3买/3卖 检测率验证与改进）

- **验证发现**：3买/3卖 的成交量确认（突破≥1.8x、回调<0.6x）以"笔均量"度量时几乎无法满足——突破笔均量被笔内多根K线稀释，实测 99.2% 候选被量能条件拦截，3买/3卖 系统性失效；2买/2卖 受索引混用+缩量过严双重压制也极少触发。
- **修复**（src/easy_tdx/chanlun/mmd.py）：
  1. 新增 _calc_zs_avg_volume：突破/跌破量能基线改为**中枢自身盘整期均量**（盘整 vs 突破对比），而非数据末端/中枢末端窗口均量；并钳制越界索引。
  2. 突破放量倍数 1.8→1.3（高波动 1.15、低波动 1.5）；回调/反弹缩量倍数 0.6→0.85（2买/2卖 同步从 0.7→0.85）。
- **效果**：2买 在真实量价结构数据上恢复触发（此前几乎永不触发）；3买 仍保持保守（约 15 个 AND 过滤器的刻意设计），但量能门槛已回到可达到区间。
- 新增回归测试（test_chanlun_v83_trend_gate_regression.py 追加 3 用例）：中枢盘整均量计算、空数据、越界钳制。

### 验证

- 全量测试：2213 passed, 2 skipped（+9 新回归用例）；新增测试 mypy strict 通过。



### 图表可视化浏览器实测修复（Playwright 截图验证）

使用 Playwright 打开 /chanlun 实测（000001/600519 × 日线/60分钟/多级别联立），发现并修复两个导致「缠论叠加层显示不正确」的根因：

- **ECharts 按需注册缺失：分型/买卖点/背驰完全不可见，中枢 markArea 区域静默不渲染**（web-ui/src/echarts-setup.ts）—— 图表用 scatter 系列渲染分型（268 个）、买卖点（17 个）、背驰（35 个），用 markArea 渲染中枢（16 个），但按需引入清单只有 candlestick/line/bar/heatmap，未注册 ScatterChart 与 MarkAreaComponent。浏览器 console 实测报错 [ECharts] Series scatter is used but not imported + 图例告警「分型/买卖点/背驰 series not exists」；markArea 不注册时不报错，但对照实验截图实测中枢黄色区域完全不渲染。补注册 ScatterChart + MarkAreaComponent 后 console 零错误、中枢/分型/买卖点/背驰全部正常渲染。

- **K 线窗口与分析窗口不一致：叠加层被压缩到最右侧 10%**（web-ui/src/api.ts + web-ui/src/views/ChanlunView.vue）—— fetchBars 默认翻页取满 8000 根（10 页 × 800），而缠论分析 /chanlun/analyze 只分析最新 count（默认 800）根，导致图表显示 8000 根历史但笔/线段/中枢/买卖点只覆盖最近 800 根，叠加层全部挤在右端。新增 fetchBars(..., maxCount?) 可选参数，缠论页只取最新 count 根，与分析窗口严格对齐（实测统计栏 K线 8000 → 800）。

- **调试钩子**（web-ui/src/components/ChanlunChart.vue）—— DEV 模式向 window.__CHANLUN_CHART__ 暴露 echarts 实例，供 Playwright 校验内部 markLine/markArea/scatter 数量与坐标。
- 新增浏览器测试脚本 web-ui/scripts/chanlun-screenshot.mjs：自动打开页面 → 设置代码/周期 → 等待分析 → 读取图表内部系列计数、坐标合法性、console/网络错误 → 缩放截图。

**验证结果**（000001 日线 800 根）：笔 133/133 markLine、线段 15/15、中枢 16/16、分型 268、买卖点 17、背驰 35，全部与后端 API 计数一致；买卖点坐标 0 个越界；console/page 零错误。500 根茅台日线、600 根 60 分钟线、多级别联立同样全绿；生产构建（dist 经 FastAPI 托管）复测通过。
