# 模型准确度验证指南（V95–V291）

> 本文档汇总 easy-tdx 自 V95 起新增的「通过历史回测验证模型/策略准确度」能力。
> 目标：让用户不只是看账户盈亏，而是能回答三件事——**信号准不准、稳健不稳健、过不过拟合**。

## 一、验证能力全景

| 版本 | 能力 | 回答的问题 | 入口 |
| --- | --- | --- | --- |
| V95 | 信号前瞻命中率 + 随机入场基准 + 买入持有基准 | 买卖点择时是否真的准 | 回测页「模型准确度验证」 |
| V96 | 缠论买卖点按类型（1买/2买/3买…）命中率 | 哪类缠论信号真的准 | 缠论分析页 / 回测页缠论策略 |
| V97 | 分段稳健性 / 过拟合检查 | 成绩是否只在一段行情里成立 | 回测页「分段稳健性检查」 |
| V98 | 选股结果前瞻收益验证 | 选股模型选的股票是否跑赢未选的 | 动态选股页「验证选股效果」 |
| V99 | 组合/多标的准确度聚合 | 策略放在多只股票上是否整体靠谱 | 组合回测页 |
| V101 | 模型可信度综合评分（0-100） | 散落验证信号汇总成一个可读分数 | 回测页「模型可信度」 |
| V103 | 组合可信度评分 | 组合整体可信度 | 组合回测页 |
| V105 | 样本外验证（训练段 + 未见过数据） | 模型在没见过的数据上是否仍准确 | 回测页「样本外验证」 |
| V106 | 回测页「验证总结」聚合卡片 | 全部验证结论一览可判 | 回测报告顶部 |
| V107 | 信号监控页自选股历史信号准确度 | 盯实时信号前先看该股历史命中率 | 信号监控页「🎯 准确度」 |
| V109 | 参数寻优结果附准确度/可信度 | 按验证过的准确度选参数，而非只看收益 | 寻优页网格点排名表 |
| V110 | 组合逐标的「可信度」列 | 同一策略在哪些标的上验证最可信 | 组合回测页逐标表 |
| V111 | 「一键寻优」全局排名补准确度/可信度列 | 跨策略挑最优点时也按验证结论比较 | 寻优页「一键寻优」策略排名 |
| V112 | 组合回测页「组合验证总结」卡片 | 组合可信度/准确度/逐标最强最弱一览 | 组合报告顶部 |
| V113 | 「一键寻优」排名支持按可信度排序 | 一键切到按模型可信度选策略 | 寻优页「按可信度」按钮 |
| V114 | 动态选股页批量策略验证 | 对筛选出的股票跑同一策略按可信度排名 | 动态选股页「批量策略验证」 |
| V115 | run-all CLI 排名补准确度/可信度列 | 命令行批量比策略时也按验证结论 | easy-tdx run-all |
| V116 | 报告导出补「样本外验证」段 | 复制报告覆盖全部验证维度 | 回测页「复制报告」 |
| V117 | CLI 模型验证报告命令 | 一条命令跑完回测+准确度+稳健性+可信度+样本外 | easy-tdx verify SZ 000001 |
| V118 | 批量验证支持「查看该股」 | 从验证排名直达单标缠论回测 | 动态选股页批量验证表 |
| V119 | CLI 批量模型验证 verify-multi | 多标的按可信度排名选股（脚本/Agent 友好） | easy-tdx verify-multi |
| V120 | 模型准确度验证指南更新 | 验证体系文档覆盖到 V119 | docs/model-accuracy-guide.md |
| V121 | 监控页主监控列表每股「历史信号准确度」 | 主监控标的也能核对历史命中率 | 信号监控页每股「🎯」 |
| V122 | 策略库快照补可信度/样本外结论 | 保存的策略即完整验证档案 | 策略库卡片 |
| V123 | 参数寻优 Walk-Forward 滚动验证 | 滚窗训练/测试验证参数是否过拟合 | 寻优页「Walk-Forward 验证」 |
| V124 | 寻优页「验证总结」聚合卡片 | 最优点可信度+命中率+Walk-Forward 一览 | 寻优结果顶部 |
| V125 | 对比页补样本外/稳健性行 | 跨任务比策略时也看是否过拟合 | 结果对比页 |
| V126 | 组合回测补样本外验证 | 组合层回答「在没见过的数据上是否仍准确」 | 组合回测页「样本外验证」 |
| V127 | 组合回测报告一键导出 | 组合绩效+验证结论汇总为 Markdown | 组合页「复制报告」 |
| V128 | 多策略组合样本外验证 | 勾选多策略跑组合也能样本外检验 | 策略库页「组合回测」 |
| V130 | 批量验证排名导出（Markdown 复制） | 验证结论可留存/分享 | 动态选股页「📋 复制排名」 |
| V131 | 批量验证结果「保存为组合策略」 | 验证选出的股票一键入策略库，载入复跑 | 动态选股页「💾 保存为组合策略」 |
| V132 | CLI verify-multi 补分段稳健性/样本外 | 批量验证每股也给出过拟合与泛化结论 | easy-tdx verify-multi --segments 3 --out-of-sample |
| V133 | 模型准确度验证指南扩展到 V132 | 文档覆盖批量验证导出/入库与 CLI 验证增强 | docs/model-accuracy-guide.md |
| V134 | 组合保存策略时把验证结论写入快照 | 组合策略同样以「验证档案」入库 | 策略库组合卡 |
| V135 | 寻优页「复制报告」 | 最优参数+Walk-Forward+网格排名导出 Markdown | 寻优页「📋 复制报告」 |
| V136 | 模型准确度验证指南扩展到 V135 | 文档覆盖组合快照验证结论与寻优报告导出 | docs/model-accuracy-guide.md |
| V137 | 单标的回测页「批量验证自选股」 | 当前策略对自选股逐个回测，按可信度排名选股 | 回测页「🗳️ 批量验证自选股」 |
| V138 | 模型准确度验证指南扩展到 V137 | 文档覆盖回测页批量验证自选股入口 | docs/model-accuracy-guide.md |
| V139 | 回测页批量验证「复制排名」 | 批量验证结论也可留存/分享 | 回测页批量验证面板「📋 复制排名」 |
| V140 | 模型准确度验证指南扩展到 V139 | 文档覆盖回测页批量验证复制排名入口 | docs/model-accuracy-guide.md |
| V141 | 回测页批量验证「保存为组合策略」 | 单标调参后的批量验证结果可入库复跑 | 回测页批量验证面板「💾 保存为组合策略」 |
| V142 | 模型准确度验证指南扩展到 V141 | 文档覆盖回测页批量验证入库入口 | docs/model-accuracy-guide.md |
| V143 | 信号监控页「批量验证监控股」 | 对已选监控标的批量回测按可信度排名选股 | 信号监控页「🧪 批量验证监控股」 |
| V144 | 模型准确度验证指南扩展到 V143 | 文档覆盖监控页批量验证入口 | docs/model-accuracy-guide.md |
| V145 | 监控页批量验证补「复制排名+保存为组合策略」 | 监控验证结论可导出/入库 | 监控页批量验证面板 |
| V146 | 模型准确度验证指南扩展到 V145 | 文档覆盖监控批量验证导出/入库入口 | docs/model-accuracy-guide.md |
| V147 | 策略库按「验证可信度」排序 | 优先看到验证过的、最可信的策略 | 策略库页「按验证可信度排序」 |
| V148 | 模型准确度验证指南扩展到 V147 | 文档覆盖策略库可信度排序入口 | docs/model-accuracy-guide.md |
| V149 | 批量验证结果支持按收益/可信度排序切换 | 批量验证既按验证可信度选股、也可按收益对比 | 回测页批量验证「按收益/按可信度」 |
| V150 | 模型准确度验证指南扩展到 V149 | 文档覆盖批量验证排序切换入口 | docs/model-accuracy-guide.md |
| V151 | 监控页批量验证支持按收益/可信度排序切换 | 与回测页 V149 对齐，跨页面一致 | 监控页批量验证「按收益/按可信度」 |
| V152 | 模型准确度验证指南扩展到 V151 | 文档覆盖监控批量验证排序切换入口 | docs/model-accuracy-guide.md |
| V153 | 回测报告「复制 JSON」 | 机器可读验证档案，Agent/脚本友好 | 回测页「⚙ 复制 JSON」 |
| V154 | 模型准确度验证指南扩展到 V153 | 文档覆盖 JSON 报告导出入口 | docs/model-accuracy-guide.md |
| V155 | run-all CLI 排名表补稳健性/样本外列 | 命令行批量比策略时也看泛化能力 | easy-tdx run-all |
| V156 | 模型准确度验证指南扩展到 V155 | 文档覆盖 run-all 稳健性/样本外列入口 | docs/model-accuracy-guide.md |
| V157 | 回测页批量验证「复制 JSON」 | 批量验证结果机器可读导出 | 回测页批量验证「⚙ 复制 JSON」 |
| V158 | 寻优页「复制 JSON」 | 寻优报告机器可读导出与回测对齐 | 寻优页「⚙ 复制 JSON」 |
| V159 | 模型准确度验证指南扩展到 V158 | 文档覆盖 JSON 导出系列入口 | docs/model-accuracy-guide.md |
| V160 | 组合回测页「批量验证候选股」 | 先验证候选股再组合，选股与组合打通 | 组合页「🧪 批量验证候选股」 |
| V161 | 模型准确度验证指南扩展到 V160 | 文档覆盖组合候选验证入口 | docs/model-accuracy-guide.md |
| V162 | 组合回测报告「复制 JSON」 | 组合验证档案机器可读导出，补齐 JSON 系列 | 组合页「⚙ 复制 JSON」 |
| V163 | 模型准确度验证指南扩展到 V162 | 文档覆盖组合 JSON 导出入口 | docs/model-accuracy-guide.md |
| V164 | 策略库卡片「验证来源」徽章 | 一眼看出策略从哪个验证流程入库 | 策略库卡片头部 |
| V165 | 模型准确度验证指南扩展到 V164 | 文档覆盖策略库来源徽章入口 | docs/model-accuracy-guide.md |
| V166 | 监控页批量验证「复制 JSON」 | 补齐 JSON 导出系列最后一处 | 监控页批量验证「⚙ 复制 JSON」 |
| V167 | 模型准确度验证指南扩展到 V166 | 文档覆盖监控批量 JSON 导出入口 | docs/model-accuracy-guide.md |
| V168 | 动态选股页批量验证「复制 JSON」 | 补齐 JSON 导出系列最后一处 | 动态选股页批量验证「⚙ 复制 JSON」 |
| V169 | 模型准确度验证指南扩展到 V168 | 文档覆盖选股批量 JSON 导出入口 | docs/model-accuracy-guide.md |
| V170 | 组合候选批量验证补「复制排名+复制 JSON」 | 组合候选验证结论可导出/留存 | 组合页候选面板「📋/⚙」 |
| V171 | 模型准确度验证指南扩展到 V170 | 文档覆盖组合候选导出入口 | docs/model-accuracy-guide.md |
| V172 | CLI verify/verify-multi 支持 --output-file | 命令行验证结论可直接落盘存档 | easy-tdx verify --output-file |
| V173 | 模型准确度验证指南扩展到 V172 | 文档覆盖 CLI 落盘入口 | docs/model-accuracy-guide.md |
| V174 | run-all CLI 支持 --output-file | 命令行批量验证结论可落盘存档 | easy-tdx run-all --output-file |
| V175 | 模型准确度验证指南扩展到 V174 | 文档覆盖 run-all 落盘入口 | docs/model-accuracy-guide.md |
| V176 | CLI 组合模型验证 verify-portfolio | 补齐 CLI 验证系列（verify/verify-multi/verify-portfolio） | easy-tdx verify-portfolio |
| V177 | 模型准确度验证指南扩展到 V176 | 文档覆盖 CLI 组合验证入口 | docs/model-accuracy-guide.md |
| V178 | 回测页批量验证「样本外」列 | 批量选股时直接看每只股票的泛化/衰减结论 | 回测页批量验证「样本外」列 |
| V179 | 模型准确度验证指南扩展到 V178 | 文档覆盖批量验证样本外列入口 | docs/model-accuracy-guide.md |
| V180 | 监控页批量验证「样本外」列 | 监控批量选股时直接看每只监控股的泛化/衰减结论 | 监控页批量验证「样本外」列 |
| V181 | 模型准确度验证指南扩展到 V180 | 文档覆盖监控批量样本外列入口 | docs/model-accuracy-guide.md |
| V182 | 动态选股页批量验证「样本外」列 | 选股批量验证直接看每只候选股的泛化/衰减结论 | 动态选股页批量验证「样本外」列 |
| V183 | 模型准确度验证指南扩展到 V182 | 文档覆盖选股批量样本外列入口 | docs/model-accuracy-guide.md |
| V184 | 组合候选批量验证「样本外」列 | 四处批量验证入口 OOS 列对齐 | 组合页候选批量验证「样本外」列 |
| V185 | 模型准确度验证指南扩展到 V184 | 文档覆盖组合候选样本外列入口 | docs/model-accuracy-guide.md |
| V186 | 批量验证「复制排名」Markdown 补「样本外」列 | 四处批量验证导出统一含 OOS 结论 | 四处批量验证「📋 复制排名」 |
| V187 | 模型准确度验证指南扩展到 V186 | 文档覆盖复制排名样本外列入口 | docs/model-accuracy-guide.md |
| V188 | 组合候选批量验证「保存为组合策略」 | 候选验证结论一键入库复跑 | 组合页候选面板「💾 保存为组合策略」 |
| V189 | 模型准确度验证指南扩展到 V188 | 文档覆盖组合候选入库入口 | docs/model-accuracy-guide.md |
| V190 | 批量验证保存组合策略快照补样本外聚合 | 策略库卡片直接看到多少只样本外稳健 | 策略库卡片「🧪 批量验证样本外」 |
| V191 | 模型准确度验证指南扩展到 V190 | 文档覆盖批量验证样本外聚合入口 | docs/model-accuracy-guide.md |
| V192 | 回测页批量验证「仅看样本外稳健」过滤 | 选股时直接筛出在未见过数据上仍稳健的股票 | 回测页批量验证「✅ 仅看样本外稳健」 |
| V193 | 监控页批量验证「仅看样本外稳健」过滤 | 与回测页 V192 对齐 | 监控页批量验证「✅ 仅看样本外稳健」 |
| V194 | 动态选股页批量验证「仅看样本外稳健」过滤 | 与回测 V192/监控 V193 对齐 | 选股页批量验证「✅ 仅看样本外稳健」 |
| V195 | 组合候选批量验证「仅看样本外稳健」过滤 | 四处批量验证入口体验对齐 | 组合页候选批量验证「✅ 仅看样本外稳健」 |
| V196 | 模型准确度验证指南扩展到 V195 | 文档覆盖四处样本外稳健过滤入口 | docs/model-accuracy-guide.md |
| V197 | 选股页保存组合策略快照补样本外聚合 | 与 V190 对齐，四处保存入口快照统一含 OOS 结论 | 选股页「💾 保存为组合策略」 |
| V198 | 模型准确度验证指南扩展到 V197 | 文档覆盖选股保存快照聚合入口 | docs/model-accuracy-guide.md |
| V199 | CLI verify-multi 支持 --only-robust | 命令行选股同样只挑样本外稳健的标的 | easy-tdx verify-multi --only-robust |
| V200 | 模型准确度验证指南扩展到 V199 | 文档覆盖 CLI --only-robust 入口 | docs/model-accuracy-guide.md |
| V201 | run-all CLI 支持 --only-robust | 命令行批量比策略只显示样本外稳健的策略 | easy-tdx run-all --only-robust |
| V202 | 模型准确度验证指南扩展到 V201 | 文档覆盖 run-all --only-robust 入口 | docs/model-accuracy-guide.md |
| V203 | 批量验证「保存为组合策略」遵循「仅看样本外稳健」过滤 | 保存动作与筛选视图一致 | 四处批量验证「💾 保存为组合策略」 |
| V204 | 模型准确度验证指南扩展到 V203 | 文档覆盖保存遵循过滤入口 | docs/model-accuracy-guide.md |
| V205 | 寻优页「批量验证自选股」 | 最优参数直接对自选股批量验证选股 | 寻优页「🗳️ 批量验证自选股」 |
| V206 | 模型准确度验证指南扩展到 V205 | 文档覆盖寻优批量验证入口 | docs/model-accuracy-guide.md |
| V207 | 策略库「验证来源」徽章补齐新来源 | 组合候选/寻优批量验证保存的策略也能溯源 | 策略库卡片「🧪 组合候选验证」「🧪 寻优批量验证」 |
| V208 | 模型准确度验证指南扩展到 V207 | 文档覆盖来源徽章新来源入口 | docs/model-accuracy-guide.md |
| V209 | 策略库「一键重验」 | 保存策略后用原标的重新回测刷新验证结论 | 策略库单标卡片「↻ 重验」 |
| V210 | 模型准确度验证指南扩展到 V209 | 文档覆盖一键重验入口 | docs/model-accuracy-guide.md |
| V211 | 策略库「一键重验」扩展到组合策略 | 组合验证结论也可一键刷新 | 策略库组合卡片「↻ 重验」 |
| V212 | 模型准确度验证指南扩展到 V211 | 文档覆盖组合重验入口 | docs/model-accuracy-guide.md |
| V213 | CLI 策略库一键重验 reverify | 命令行/脚本批量刷新已保存策略的验证结论 | easy-tdx reverify |
| V214 | 模型准确度验证指南扩展到 V213 | 文档覆盖 CLI reverify 入口 | docs/model-accuracy-guide.md |
| V215 | 策略库「按验证结论筛选」 | 只看验证过、可信且稳健的策略 | 策略库工具栏三组筛选下拉 |
| V216 | 模型准确度验证指南扩展到 V215 | 文档覆盖策略库筛选入口 | docs/model-accuracy-guide.md |
| V217 | 回测页批量验证结果持久化 | 刷新/切页后上次验证结论不丢失 | 回测页批量验证面板「🕒 上次验证时间」 |
| V218 | 模型准确度验证指南扩展到 V217 | 文档覆盖批量验证持久化入口 | docs/model-accuracy-guide.md |
| V219 | 监控页批量验证结果持久化 | 与回测页 V217 对齐，刷新/切页后监控验证结论不丢失 | 监控页批量验证「🕒 上次验证时间」 |
| V220 | 模型准确度验证指南扩展到 V219 | 文档覆盖监控批量持久化入口 | docs/model-accuracy-guide.md |
| V221 | 动态选股页批量验证结果持久化 | 与回测页 V217 / 监控页 V219 对齐 | 选股页批量验证「🕒 上次验证时间」 |
| V222 | 模型准确度验证指南扩展到 V221 | 文档覆盖选股批量持久化入口 | docs/model-accuracy-guide.md |
| V223 | 组合候选批量验证结果持久化 | 补齐四处批量验证入口持久化 | 组合页候选批量验证「🕒 上次验证时间」 |
| V224 | 模型准确度验证指南扩展到 V223 | 文档覆盖组合候选持久化入口 | docs/model-accuracy-guide.md |
| V225 | CLI verify 支持 --walk-forward | 命令行单标的验证报告补滚动窗口防过拟合维度 | easy-tdx verify --walk-forward |
| V226 | 模型准确度验证指南扩展到 V225 | 文档覆盖 CLI walk-forward 入口 | docs/model-accuracy-guide.md |
| V227 | 策略库「一键重验」扩展到多策略组合 | 三类策略全部可一键刷新验证结论 | 策略库多策略卡片「↻ 重验」 |
| V228 | 模型准确度验证指南扩展到 V227 | 文档覆盖多策略重验入口 | docs/model-accuracy-guide.md |
| V229 | CLI reverify 支持多策略组合 | 命令行三类策略全部可一键刷新验证结论 | easy-tdx reverify（kind=multi） |
| V230 | 模型准确度验证指南扩展到 V229 | 文档覆盖 CLI 多策略重验入口 | docs/model-accuracy-guide.md |
| V231 | 寻优页批量验证结果持久化 | 补齐五处批量验证入口持久化 | 寻优页批量验证「🕒 上次验证时间」 |
| V232 | 模型准确度验证指南扩展到 V231 | 文档覆盖寻优批量持久化入口 | docs/model-accuracy-guide.md |
| V233 | run-all CLI 支持 --walk-forward | 命令行批量比策略时也能看滚动窗口防过拟合判定 | easy-tdx run-all --walk-forward |
| V234 | 模型准确度验证指南扩展到 V233 | 文档覆盖 run-all walk-forward 入口 | docs/model-accuracy-guide.md |
| V235 | 策略库卡片「复制验证摘要」 | 一条 Markdown 带走全部验证结论 | 策略库卡片「📋 验证摘要」 |
| V236 | 模型准确度验证指南扩展到 V235 | 文档覆盖策略库验证摘要入口 | docs/model-accuracy-guide.md |
| V237 | 组合候选批量验证「查看该股」 | 从候选排名直达该股单标缠论回测 | 组合页候选批量验证「查看该股」 |
| V238 | 模型准确度验证指南扩展到 V237 | 文档覆盖组合候选查看该股入口 | docs/model-accuracy-guide.md |
| V239 | 监控页批量验证「查看该股」 | 从监控批量验证直达该股单标回测 | 监控页批量验证「查看该股」 |
| V240 | 模型准确度验证指南扩展到 V239 | 文档覆盖监控查看该股入口 | docs/model-accuracy-guide.md |
| V241 | CLI verify-portfolio 支持 --only-robust | 组合验证只输出样本外稳健的标的 | easy-tdx verify-portfolio --only-robust |
| V242 | 模型准确度验证指南扩展到 V241 | 文档覆盖组合 only-robust 入口 | docs/model-accuracy-guide.md |
| V243 | CLI verify-multi 支持 --walk-forward | 批量验证每只标的也输出滚动窗口防过拟合判定 | easy-tdx verify-multi --walk-forward |
| V244 | 模型准确度验证指南扩展到 V243 | 文档覆盖 verify-multi walk-forward 入口 | docs/model-accuracy-guide.md |
| V245 | CLI reverify 支持 --walk-forward | 重验快照也含滚动窗口防过拟合判定 | easy-tdx reverify --walk-forward |
| V246 | 模型准确度验证指南扩展到 V245 | 文档覆盖 reverify walk-forward 入口 | docs/model-accuracy-guide.md |
| V247 | 寻优页批量验证「查看该股」 | 从寻优批量验证直达该股单标回测 | 寻优页批量验证「查看该股」 |
| V248 | 模型准确度验证指南扩展到 V247 | 文档覆盖寻优查看该股入口 | docs/model-accuracy-guide.md |
| V249 | 策略库「全部重验」 | 一键刷新当前可见全部策略的验证结论 | 策略库页头「↻ 全部重验」 |
| V250 | 模型准确度验证指南扩展到 V249 | 文档覆盖策略库全部重验入口 | docs/model-accuracy-guide.md |
| V251 | 策略库卡片「验证 JSON」 | 单条策略完整验证档案机器可读导出 | 策略库卡片「⚙ 验证 JSON」 |
| V252 | 模型准确度验证指南扩展到 V251 | 文档覆盖策略库验证 JSON 入口 | docs/model-accuracy-guide.md |
| V253 | 回测页批量验证「导出 CSV」 | 批量验证排名 Excel 友好导出 | 回测页批量验证「📊 导出 CSV」 |
| V254 | 模型准确度验证指南扩展到 V253 | 文档覆盖批量验证 CSV 导出入口 | docs/model-accuracy-guide.md |
| V255 | 「导出 CSV」扩展到四处批量验证入口 | 五处批量验证入口统一 Excel 友好导出 | 监控/选股/组合候选/寻优「📊 导出 CSV」 |
| V256 | 模型准确度验证指南扩展到 V255 | 文档覆盖五处 CSV 导出入口 | docs/model-accuracy-guide.md |
| V257 | 寻优页网格排名「导出 CSV」 | 网格点排名 Excel 友好导出 | 寻优结果工具栏「📊 导出 CSV」 |
| V258 | 模型准确度验证指南扩展到 V257 | 文档覆盖网格排名 CSV 导出入口 | docs/model-accuracy-guide.md |
| V259 | 组合回测报告「导出 CSV」 | 组合绩效+各标的对比表 Excel 友好导出 | 组合页「📊 导出 CSV」 |
| V260 | 模型准确度验证指南扩展到 V259 | 文档覆盖组合报告 CSV 导出入口 | docs/model-accuracy-guide.md |
| V261 | 回测页「交易明细 CSV」 | 成交记录导出逐笔核对买卖点 | 回测结果工具栏「📊 交易明细 CSV」 |
| V262 | 模型准确度验证指南扩展到 V261 | 文档覆盖交易明细 CSV 导出入口 | docs/model-accuracy-guide.md |
| V263 | 监控页「信号列表导出 CSV」 | 模型发现的缠论买卖点信号 Excel 友好导出 | 监控页「🔔 新信号」面板「📊 导出 CSV」 |
| V264 | 模型准确度验证指南扩展到 V263 | 文档覆盖信号列表 CSV 导出入口 | docs/model-accuracy-guide.md |
| V265 | 一键寻优排名「导出 CSV」 | 跨策略对比表 Excel 友好导出 | 寻优页「策略排名」表「📊 导出 CSV」 |
| V266 | 模型准确度验证指南扩展到 V265 | 文档覆盖一键寻优排名 CSV 入口 | docs/model-accuracy-guide.md |
| V267 | 对比页「导出 CSV」 | 跨任务指标对比表 Excel 友好导出 | 对比页「指标对比」区「📊 导出 CSV」 |
| V268 | 模型准确度验证指南扩展到 V267 | 文档覆盖对比页 CSV 导出入口 | docs/model-accuracy-guide.md |
| V269 | 策略库「导出策略清单 CSV」 | 全库验证档案 Excel 友好归档 | 策略库页头「📊 导出策略清单」 |
| V270 | 模型准确度验证指南扩展到 V269 | 文档覆盖策略清单 CSV 导出入口 | docs/model-accuracy-guide.md |
| V271 | 监控页每股信号准确度明细「导出 CSV」 | 信号类型命中率明细可导出核对 | 监控页每股「🎯」面板「📊 导出 CSV」 |
| V272 | 模型准确度验证指南扩展到 V271 | 文档覆盖每股准确度 CSV 导出入口 | docs/model-accuracy-guide.md |
| V273 | 信号准确度面板「导出 CSV」 | 按持有根数分类的买卖信号命中率明细可导出 | 回测页信号准确度面板「📊 导出 CSV」 |
| V274 | 模型准确度验证指南扩展到 V273 | 文档覆盖信号准确度 CSV 导出入口 | docs/model-accuracy-guide.md |
| V275 | 对比页「复制 JSON」 | 跨任务对比结果机器可读导出 | 对比页「指标对比」区「⚙ 复制 JSON」 |
| V276 | 模型准确度验证指南扩展到 V275 | 文档覆盖对比 JSON 导出入口 | docs/model-accuracy-guide.md |
| V277 | 选股页「导出选股清单 CSV」 | 筛选结果明细 Excel 友好导出 | 选股页「筛选结果」面板头「📊 导出 CSV」 |
| V278 | 模型准确度验证指南扩展到 V277 | 文档覆盖选股清单 CSV 导出入口 | docs/model-accuracy-guide.md |
| V279 | CLI screen rank 补验证维度列 | 命令行选股排名也能看准确度/可信度/样本外 | easy-tdx screen rank --out-of-sample |
| V280 | 模型准确度验证指南扩展到 V279 | 文档覆盖 screen rank 验证列入口 | docs/model-accuracy-guide.md |
| V281 | 选股效果验证「导出 CSV」 | 前瞻收益对比明细 Excel 友好导出 | 选股页「选股效果验证」面板头「📊 导出 CSV」 |
| V282 | 模型准确度验证指南扩展到 V281 | 文档覆盖选股效果 CSV 导出入口 | docs/model-accuracy-guide.md |
| V283 | 信号列表/选股清单/效果验证补「复制 JSON」 | 三处 CSV 导出入口补齐 JSON 配对 | 监控页信号列表 / 选股页「⚙ 复制 JSON」 |
| V284 | 模型准确度验证指南扩展到 V283 | 文档覆盖三处 JSON 配对入口 | docs/model-accuracy-guide.md |
| V285 | 组合交易明细「导出 CSV」 | 聚合各标的成交记录逐笔核对买卖点 | 组合页报告工具栏「📊 交易明细 CSV」 |
| V286 | 模型准确度验证指南扩展到 V285 | 文档覆盖组合交易明细 CSV 入口 | docs/model-accuracy-guide.md |
| V287 | 回测页 Walk-Forward 滚动验证 | Web 单标回测补齐防过拟合维度 | 回测页「Walk-Forward 滚动验证」勾选 |
| V288 | 模型准确度验证指南扩展到 V287 | 文档覆盖回测 Walk-Forward 入口 | docs/model-accuracy-guide.md |
| V289 | WalkForwardPanel「导出 CSV」 | 滚动窗口明细 Excel 友好导出 | Walk-Forward 面板「📊 导出 CSV」 |
| V290 | 模型准确度验证指南扩展到 V289 | 文档覆盖 WF 面板 CSV 导出入口 | docs/model-accuracy-guide.md |
| V291 | 策略库「复制清单 JSON」 | 全库验证档案机器可读导出 | 策略库页头「⚙ 复制清单 JSON」 |

## 二、核心概念

- **命中（hit）**：买入后 N 根收益 > 0（择时进场正确）；卖出后 N 根下跌（回避下跌正确）。
- **随机入场基准**：以相同信号数量在全部可入场 bar 上随机采样（可复现 seed，数据不足时直接用全量），作为「抛硬币择时」的下限参照。
- **超额命中率** = 模型命中率 − 随机命中率。>0 说明信号比随机择时更准。
- **模型可信度（V101 权重）**：40% 择时准确度 + 35% 稳健性 + 25% 绩效对比，融合成 0-100 分。
- **样本外验证（V105）**：把区间按时间切训练段（默认 70%）+ 样本外持有段（30%），策略参数固定，在模型从未见过的数据上重跑——检验过拟合最硬的一关。

## 三、如何启用

### 3.1 回测页（最常用）

1. 选择标的与策略，点击「开始回测」。
2. 在「资金与成本」区勾选：
   - **分段稳健性检查**：把区间切成 2~6 段逐段重跑，看各段表现是否一致。
   - **样本外验证**：训练段 + 未见过持有段对比。
3. 报告区依次展示：✅ 验证总结（V106）→ 📊 模型可信度（V101）→ 🎯 模型准确度验证（V95）→ 🧱 分段稳健性（V97）→ 🔬 样本外验证（V105）→ 🔁 Walk-Forward 滚动验证（V287，勾选后显示）；「模型准确度判定」面板（V95/V104）结论行「📊 导出 CSV」（V273）把按持有根数（1/3/5/10/20）分类的买/卖信号命中率/随机基准/前瞻收益明细导出为 Excel 友好的 CSV（组件级，各使用页面一并受益）；「Walk-Forward 滚动验证」勾选（V287）请求带 use_walk_forward，后端逐窗口回测聚合输出 windows/train_mean/test_mean/degraded/verdict，「📋 复制报告」同步补该段，「📊 导出 CSV」（V289）把判定/汇总与各窗口明细导出为 Excel 友好的 CSV——与 CLI V225 / 寻优页 V123 对齐。
4. 想留存/分享？点工具栏「📋 复制报告」导出 Markdown 摘要（V104）；「⚙ 复制 JSON」（V153）导出完整结构化的机器可读验证档案（performance/signal_accuracy/segment_robustness/model_trust/out_of_sample 等），供 Agent/脚本消费与存档；「📊 交易明细 CSV」（V261）把成交记录（时间/方向/数量/价格/手续费/已实现盈亏等）导出为 Excel 友好的 CSV，逐笔核对模型触发的买卖点。
5. 工具栏「🗳️ 批量验证自选股」（V137）：读取全局自选股（最多 12 只），用当前策略+参数逐只独立回测，按 V101 可信度降序排名；每行「查看该股」直接切换目标重新回测；面板头部「📋 复制排名」（V139）把结论导出为 Markdown 表格（含「样本外」列，V186）、「⚙ 复制 JSON」（V157）导出机器可读结果、「📊 导出 CSV」（V253）导出 Excel 友好的排名表、「💾 保存为组合策略」（V141）把验证选出的股票一键入策略库（kind=portfolio，source=batch-verify-backtest），可在组合回测页载入复跑；「按收益 / 按可信度」切换（V149）在选股与收益对比间切换排序；「样本外」列（V178）直接显示每只候选股 ✅泛化 / ⚠衰减（逐只开启 out_of_sample）；「✅ 仅看样本外稳健」过滤（V192）只保留 ✅泛化的候选股；开启过滤后「保存为组合策略」也只存筛选视图里的 ✅泛化 标的（V203）；批量验证结果持久化（V217）——上次结论存 localStorage，刷新/切页自动恢复并显示「🕒 上次验证时间」；「📊 导出 CSV」（V255）已扩展到监控/选股/组合候选/寻优四处批量验证入口——五处批量验证入口统一 Excel 友好导出（BOM+表头+排序后行数据）。

### 3.2 缠论分析页

- 分析完成后，「买卖点准确度验证」面板（V96）展示每类买卖点（1buy/2buy/3buy/各 sell）的 5 根命中率与随机基准对比。

### 3.3 动态选股页

- 扫描出符合条件的股票后，点「📈 验证选股效果」（V98）回看选股日后 5/10/20/60 日收益，对比选中组 vs 未选中池；验证面板头「📊 导出 CSV」（V281）把各持有周期的前瞻收益对比明细导出为 Excel 友好的 CSV、「⚙ 复制 JSON」（V283）导出机器可读结果。
- 「筛选结果」列表（代码/分类/质量分/1买/1卖/最新信号/操作建议）「📊 导出 CSV」（V277）把选股清单导出为 Excel 友好的 CSV、「⚙ 复制 JSON」（V283）导出机器可读结果。
- 「筛选结果」列表（代码/分类/质量分/1买/1卖/最新信号/操作建议）「📊 导出 CSV」（V277）把选股清单导出为 Excel 友好的 CSV。
- 「批量策略验证」（V114）：对前 12 只筛选股用所选策略分别回测，按 V101 可信度降序排名；每行「查看该股」（V118）；「📋 复制排名」（V130，含「样本外」列 V186）、「💾 保存为组合策略」（V131，快照含样本外聚合 V197）、「⚙ 复制 JSON」（V168）；「样本外」列（V182）直接显示每只候选股 ✅泛化 / ⚠衰减；「✅ 仅看样本外稳健」过滤（V194）只保留 ✅泛化的候选股；开启过滤后「保存为组合策略」也只存筛选视图里的 ✅泛化 标的（V203）；批量验证结果持久化（V221）——上次结论存 localStorage，刷新/切页自动恢复并显示「🕒 上次验证时间」。

### 3.4 组合回测页

- 报告展示「组合准确度验证」（V99）与「组合可信度」横幅（V103）。
- 资金与成本区可勾选「样本外验证」（V126）与「训练占比」，报告区展示「🔬 组合样本外验证」面板（逐标训练/持有切分聚合）。
- 工具栏「📋 复制报告」（V127）导出组合绩效 + 可信度 + 准确度 + 样本外的 Markdown 摘要；「⚙ 复制 JSON」（V162）导出完整结构化的组合结果（total_performance/individual_results/accuracy_summary/portfolio_trust/out_of_sample 等），供 Agent/脚本消费；「📊 导出 CSV」（V259）把组合绩效块 + 各标的对比表导出为 Excel 友好的 CSV；「📊 交易明细 CSV」（V285）把各标的成交记录（标的/时间/方向/数量/价格/手续费/已实现盈亏等）聚合为一张表，逐笔核对组合级买卖点。
- 保存为组合策略（V134）时快照包含 accuracy/trust/out_of_sample 三组验证结论，策略库「组合」tab 卡片可直接展示。
- 标的列表下方「🧪 批量验证候选股」（V160）：读全局自选股（最多 12 只），用当前策略逐只独立回测并按 V101 可信度排名，支持「按收益/按可信度」切换，可单只或一键「加入组合」——先验证候选股再挑进组合，选股与组合打通；候选面板「📋 复制排名（含样本外列，V186）/ ⚙ 复制 JSON」（V170）可导出结论、「💾 保存为组合策略」（V188，source=batch-verify-cand）一键入库复跑；「样本外」列（V184）直接显示每只候选股 ✅泛化 / ⚠衰减（四处批量验证入口 OOS 列对齐）；「✅ 仅看样本外稳健」过滤（V195）只保留 ✅泛化的候选股；开启过滤后「保存为组合策略」也只存筛选视图里的 ✅泛化 标的（V203）；批量验证结果持久化（V223）——上次结论存 localStorage，刷新/切页自动恢复并显示「🕒 上次验证时间」，至此四处批量验证入口持久化全部对齐（回测 V217/监控 V219/选股 V221/组合候选 V223）；每行「查看该股」（V237）直达该股单标缠论回测。

### 3.5 信号监控页

- 「快速加入的信号」每项有「🎯 准确度」按钮（V107），点击查看该股最近 300 根日线的历史信号命中率。
- 主监控列表每股也有「🎯」按钮（V121），同样可核对历史命中率；面板「📊 导出 CSV」（V271）把该股信号类型命中率明细（类型/方向/信号数/5根命中率/超额命中率/均值/结论）导出为 Excel 友好的 CSV。
- 检测到的高置信度缠论买卖点信号（1买/1卖等）展示在「🔔 新信号」面板（V079/V263）；「📊 导出 CSV」（V263）把信号列表（类型/标的/日期/置信度/说明）导出为 Excel 友好的 CSV、「⚙ 复制 JSON」（V283）导出机器可读结果，可记录/核对模型触发过的买卖点信号。
- 股票列表下方「🧪 批量验证监控股」（V143）：选一个策略，对已选监控标的（最多 12 只）逐只独立回测（最近 500 根日线），按 V101 可信度降序排名；面板头部「📋 复制排名（含样本外列，V186）」导出 Markdown、「⚙ 复制 JSON」（V166）导出机器可读结果、「💾 保存为组合策略」（V145，source=batch-verify-monitor）一键入库复跑；「按收益 / 按可信度」切换（V151）与回测页 V149 体验一致；「样本外」列（V180）直接显示每只监控股 ✅泛化 / ⚠衰减；「✅ 仅看样本外稳健」过滤（V193）只保留 ✅泛化的监控股；开启过滤后「保存为组合策略」也只存筛选视图里的 ✅泛化 标的（V203）；批量验证结果持久化（V219）——上次结论存 localStorage，刷新/切页自动恢复并显示「🕒 上次验证时间」；每行「查看该股」（V239）直达该股单标回测。

### 3.6 策略库与对比页

- 保存策略时（V100）自动把准确度/稳健性结论写入快照；V122 起快照还包含模型可信度（V101）与样本外验证（V105）结论，策略库卡片直接展示。
- 页头「按验证可信度排序」（V147）：开启后按快照 trust.score 降序展示，优先看到经过历史回测验证、可信度最高的策略。
- 页头三组「按验证结论筛选」（V215）：验证来源（全部/已验证 batch-verify*/reverify/仅重验）、可信度等级（高/中/低）、样本外结论（稳健/衰减）——叠加排序即可快速定位「验证过且可信、样本外稳健」的策略。
- 卡片头部「验证来源」徽章（V164/V207）：批量验证入库的策略（source=batch-verify*）会显示对应徽章——选股/回测/监控/组合候选（V188）/寻优批量验证（V205）五种来源全覆盖，一眼看出策略从哪个验证流程入库。
- 单标卡片「↻ 重验」（V209）：用保存的策略+参数对原标的重新回测（含样本外），刷新快照中的 performance/accuracy/robustness/trust/out_of_sample 并标记 source=reverify / reverified_at——行情变化后一键更新验证结论，不必删除重存；组合策略卡片同样支持「↻ 重验」（V211）：用保存的 context.stocks 重跑组合回测（含 V126 组合样本外），刷新组合快照（accuracy_summary/portfolio_trust/out_of_sample）；多策略组合卡片也支持「↻ 重验」（V227）：用保存的 context.items 重跑多策略组合回测（含 V128 样本外），三类策略全部可一键刷新验证结论。
- 卡片操作区「📋 验证摘要」（V235）：把类型/标的/绩效/准确度/稳健性/可信度/样本外/来源（含重验时间）拼成一段 Markdown 复制到剪贴板，方便归档/分享；「⚙ 验证 JSON」（V251）把单条策略的完整验证档案（name/kind/strategy/params/context/trade_config/snapshot/tags/notes/时间戳）以 JSON 导出，机器可读。
- 页头「↻ 全部重验」（V249）：对当前可见（single/portfolio/multi）策略逐个重验并刷新验证结论（带进度提示与「成功 x、失败 y」汇总），与 CLI reverify 默认全量（V213）对齐；页头「📊 导出策略清单」（V269）：把当前可见策略的验证档案（name/kind/params/绩效/可信度/样本外/来源/标签）导出为 Excel 友好的 CSV，整库归档；「⚙ 复制清单 JSON」（V291）：把当前可见策略的完整档案（id/name/kind/strategy/params/context/trade_config/snapshot/tags/notes/时间戳）打包为结构化 JSON，机器可读。
- 卡片快照「🧪 批量验证样本外」（V190）：批量验证保存的组合策略（source=batch-verify-backtest/monitor/cand）快照含 avg_oos_degraded 与 oos_verdict（如「✅ 2/3 只样本外稳健」/「⚠ 2/2 只样本外衰减」），卡片直接展示。
- 结果对比页（V102）横向展示多个 task 的 📊 可信度 / 🎯 5根命中率 / 🎯 超额命中率；V125 起补「🔬 样本外验证」「🧱 稳健性」两行，跨任务比策略时也看是否过拟合；「指标对比」区「📊 导出 CSV」（V267）把对比表转置为 CSV（行=指标、列=对比任务），Excel 友好导出；「⚙ 复制 JSON」（V275）把所选任务的 performance/model_trust/signal_accuracy/segment_robustness/out_of_sample 打包为结构化 JSON，Agent/脚本友好。

### 3.7 参数寻优页

- 单策略寻优（V109）：网格点排名表含「5根命中」「可信度」列；结果顶部新增「✅ 验证总结」卡片（V124）聚合最优点可信度/命中率/Walk-Forward 判定。
- 启用「Walk-Forward 验证」（V123）：报告区展示「🔁 Walk-Forward 滚动验证报告」——逐窗口训练/测试表现与防过拟合判定；面板「📊 导出 CSV」（V289）把判定/汇总与各窗口明细导出为 Excel 友好的 CSV（组件级，与回测页 V287 共用）。
- 结果顶部「📋 复制报告」（V135）导出 Markdown；「⚙ 复制 JSON」（V158）导出完整结构化的寻优结果（strategy/results/best/heatmap/walk_forward 等），供 Agent/脚本消费。
- 结果工具栏「🗳️ 批量验证自选股」（V205）：用寻优得到的最优策略+参数（单策略或一键寻优全局 best）对全局自选股（最多 12 只）逐只独立回测并按 V101 可信度排名，支持「按收益/按可信度」「仅看样本外稳健」过滤、「样本外」列、复制排名/JSON、保存为组合策略（source=batch-verify-optimize）——打通「寻优 → 批量验证选股」闭环；批量验证结果持久化（V231）——上次结论存 localStorage，刷新/切页自动恢复并显示「🕒 上次验证时间」，五处批量验证入口持久化全部对齐（回测 V217/监控 V219/选股 V221/组合候选 V223/寻优 V231）；每行「查看该股」（V247）直达该股单标回测。
- 结果工具栏「📊 导出 CSV」（V257）：把网格点排名（参数/总收益/夏普/回撤/交易数/胜率/5根命中/可信度）导出为 Excel 友好的 CSV，与五处批量验证 CSV 导出系列（V253/V255）对齐。
- 「一键寻优所有策略」的「策略排名」表「📊 导出 CSV」（V265）：跨策略对比（策略/参数/总收益/夏普/回撤/胜率/5根命中/可信度）Excel 友好导出，与单策略网格 V257 一致。
- 一键寻优所有策略（V111/V113）：全局排名表含准确度/可信度列，支持「按收益 / 按可信度」切换排序，按验证过的准确度挑策略。

### 3.8 动态选股页（批量验证）

- 扫描出股票后，「批量策略验证」（V114）对前 12 只筛选股用所选策略分别回测，按模型可信度降序排名；每行「查看该股」（V118）直达该股的单标缠论回测视图。
- 结果区「📋 复制排名」（V130）把按可信度排名的结论导出为 Markdown 表格、「⚙ 复制 JSON」（V168）导出机器可读结果；「💾 保存为组合策略」（V131）把验证选出的股票一键存入策略库（kind=portfolio，带 source=batch-verify 快照），可在「策略库 → 组合」tab 载入后在组合回测页复跑。
- 策略库页勾选多个单标的策略可做「组合回测」；勾选「样本外验证」（V128）后组合结果区展示多策略组合级样本外验证面板。

### 3.9 命令行（CLI）

- `easy-tdx verify SZ 000001 --strategy ma_cross --segments 3 --out-of-sample`（V117）：单标的完整验证报告 JSON，verdict 汇总全部结论；加 `--output-file 路径`（V172）把报告写入文件；加 `--walk-forward`（V225）输出滚动窗口防过拟合判定（与 Web 寻优页 V123 对齐）。
- `easy-tdx screen scan --strategy strategies/rsi_reversal.py | easy-tdx screen rank --from - --table`（V279）：策略选股扫描 + 回测排名；rank 每条结果带 accuracy（V99 命中率）/trust（V101 可信度）/oos（V105 样本外，加 `--out-of-sample` 开启）三组验证维度——命令行选股排名也能按验证结论比较。
- `easy-tdx verify-multi "SZ 000001,SH 600519" --strategy ma_cross`（V119）：多标的批量验证，按可信度降序排名选股，适合脚本/Agent；加 `--segments 3 --out-of-sample`（V132）可让每只标的额外输出 overfit_likely/oos_degraded/train_return/test_return；加 `--only-robust`（V199，需同时 --out-of-sample）可只输出样本外 ✅泛化 的标的；加 `--walk-forward`（V243）对每只标的输出滚动窗口防过拟合判定（wf_degraded/wf_verdict）。
- `easy-tdx verify-portfolio "SZ 000001,SZ 000002" --strategy ma_cross --out-of-sample`（V176）：组合模型验证，输出组合绩效 + accuracy_summary（V99）+ portfolio_trust（V103）+ 组合样本外（V126）+ verdict，补齐 CLI 验证系列；加 `--only-robust`（V241，需同时 --out-of-sample）只输出组合中样本外 ✅泛化 的标的（individual_results/equity_allocation 收敛到稳健子集）。
- `easy-tdx reverify --ids <id,...>`（V213）：策略库一键重验——逐条对单标/组合策略用原标的重新回测（含样本外与分段稳健性），刷新快照 performance/accuracy/robustness/trust/out_of_sample 并标记 source=reverify / reverified_at；支持多策略组合（V229）：对 context.items 各策略在原标的上重跑 MultiStrategyEngine 组合回测（含 V128 逐槽样本外），三类策略全部可一键刷新验证结论；加 `--walk-forward`（V245）单标重验时快照也含滚动窗口防过拟合判定。
- `easy-tdx run-all SZ 300308`（V115/V155）：run-all 排名表补「5根命中」「超额命中」「可信度」列（V115），并按需追加「稳健性」「样本外」列（V155）——每策略额外计算分段稳健性（V97）与样本外（V105）结论；加 `--output-file`（V174）把排名结果 JSON 写入文件；加 `--only-robust`（V201）只显示样本外 ✅泛化（未衰减）的策略；加 `--walk-forward`（V233）对每个策略输出滚动窗口防过拟合判定（排名表「滚动验证」列）。

## 四、如何解读

- **命中率高于随机基准（超额 > 0）**：择时有正贡献，值得参考。
- **命中率与随机相当**：择时贡献有限，收益可能来自行情本身。
- **分段稳健性显示过拟合 / 样本外衰减**：历史成绩可能不可持续，需谨慎对待。
- **模型可信度 70+ 高 / 50~69 中 / <50 低**：综合信号准确度、稳健性、绩效对比的加权结论。

## 五、代码接口

```python
from easy_tdx.backtest.signal_accuracy import compute_signal_accuracy, compute_signal_accuracy_by_type
from easy_tdx.backtest.model_trust import compute_model_trust, compute_portfolio_trust
from easy_tdx.backtest.robustness import compute_segment_robustness
from easy_tdx.backtest.screening_verify import compute_screening_verify
from easy_tdx.backtest.out_of_sample import compute_out_of_sample

from easy_tdx.backtest import BacktestEngine

engine = BacktestEngine(MyStrategy, cash=1_000_000)
result = engine.run(df)

# 信号前瞻命中率 vs 随机基准（V95）
acc = result.signal_accuracy

# 分段稳健性（V97）
rob = compute_segment_robustness(df, lambda: MyStrategy())

# 模型可信度（V101）
trust = compute_model_trust(result.performance, acc, rob)

# 样本外验证（V105）
oos = compute_out_of_sample(df, lambda: MyStrategy())
```

## 六、测试

对应单元测试：`tests/unit/test_backtest_signal_accuracy.py`、`test_backtest_model_trust.py`、
`test_backtest_robustness.py`、`test_backtest_screening_verify.py`、`test_backtest_portfolio_accuracy.py`、
`test_backtest_portfolio_trust.py`、`test_backtest_out_of_sample.py`、`test_backtest_cli.py`（verify / verify-multi）。