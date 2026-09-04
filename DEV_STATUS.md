# Easy TDX 缠论模型开发状态报告

## 项目概述
**easy_tdx** 是一个基于 Python + Vue.js 的通达信 TCP 协议行情客户端，核心功能为缠论技术分析（笔/线段/中枢/买卖点/背驰）和回测验证。

## 质量加固续章十六（V399q）✅ 全部完成

- **V399q** mac/commands/unusual.py 全异动类型分支测试（+14 用例）
- **质量**：全量 pytest 2994 passed / 0 failed（1 个 sina 财报测试在全量运行下偶发失败，单独运行通过，属既有 test 隔离问题）；ruff/mypy/format 归零；覆盖率 71.88%（门槛 70）
## 质量加固续章十五（V399p）✅ 全部完成

- **V399p** mac/commands 协议编解码测试五（symbol_tick_chart/symbol_quotes/board_members_quotes，+7 用例）
- **质量**：全量 pytest 2981 passed / 0 failed；ruff/mypy/format 归零；覆盖率 71.80%（门槛 70）
## 质量加固续章十四（V399o）✅ 全部完成

- **V399o** mac/commands 协议编解码测试四（symbol_transaction/file_query，+8 用例）
- **质量**：全量 pytest 2974 passed / 0 failed；ruff/mypy/format 归零；覆盖率 71.62%（门槛 70）
## 质量加固续章十三（V399n）✅ 全部完成

- **V399n** mac/commands 协议编解码测试三（board_list/symbol_info/goods_list，+9 用例）
- **质量**：全量 pytest 2966 passed / 0 failed；ruff/mypy/format 归零；覆盖率 71.54%（门槛 70）
## 质量加固续章十二（V399m）✅ 全部完成

- **V399m** mac/commands 协议编解码测试二（symbol_capital_flow/symbol_auction/chart_sampling，+9 用例）
- **质量**：全量 pytest 2957 passed / 0 failed；ruff/mypy/format 归零；覆盖率 71.43%（门槛 70）
## 质量加固续章十一（V399k/l）✅ 全部完成

- **V399k/l** mac/commands 协议编解码测试（server_info + symbol_belong_board，+9 用例）
- **质量**：全量 pytest 2948 passed / 0 failed；ruff/mypy/format 归零；覆盖率 71.30%（门槛 70）
## 质量加固续章十（V399j）✅ 全部完成

- **V399j** web/routers/diagnosis.py 纯函数测试（_to_json_safe/_detect_divergence/_calculate_position_recommendation/_get_position_notes/_calc_volume_profile_for_diagnosis，+13 用例）
- **质量**：全量 pytest 2939 passed / 0 failed；ruff/mypy/format 归零；覆盖率 71.14%（门槛 70）
## 质量加固续章九（V399i）✅ 全部完成

- **V399i** web/routers/backtest.py 纯函数测试（_ohlcv_to_df/_filter_df_by_date/_now，+8 用例）
- **质量**：全量 pytest 2926 passed / 0 failed；ruff/mypy/format 归零；覆盖率 71.06%（门槛 70）
## 质量加固续章八（V399g/h）✅ 全部完成

- **V399g** mac/commands/unusual.py 协议编解码测试（_describe_unusual 全分支 + UnusualCmd 编解码，+9 用例）
- **V399h** cli/cmd_company.py 分块读取/板块名解析测试（_read_full_section/_resolve_filename，+6 用例）
- **质量**：全量 pytest 2912 passed / 0 failed；ruff/mypy/format 归零；覆盖率 70.98%（门槛 70）
## 质量加固续章七（V399f）✅ 全部完成

- **V399f** cli/cmd_offline.py 纯函数测试（_df_to_bars/_is_index_code/_watch_signal_row/_is_within_since_days/_fmt_opt_price/_render_watch_report/_advice_batch_one，+10 用例）
- **质量**：全量 pytest 2903 passed / 0 failed；ruff/mypy/format 归零；覆盖率 70.84%（门槛 70）
## 质量加固续章六（V399d/e）✅ 全部完成

- **V399d** client.py 纯函数测试（_record_signature/_page_signature/_classify_fund_flow/_date_from_bar/缓存序列化，+9 用例）
- **V399e** mac/client.py 纯函数测试（_convert_board_code/_flatten_quote_fields/_quotes_to_df/_flatten_tick_chart/_flatten_multi_tick_chart，+8 用例）
- **质量**：全量 pytest 2893 passed / 0 failed；ruff/mypy/format 归零；覆盖率 70.80%（门槛 70）
## 质量加固续章五（V399c）✅ 全部完成

- **V399c** fundamental/pipeline 纯函数测试（_returns_at/_sina_frame/_summarize_periods，+6 用例）；修正 diagnosis 的 _calc_volume_profile 显式导入
- **质量**：全量 pytest 2876 passed / 0 failed；ruff/mypy/format 归零；覆盖率 70.67%（门槛 70）
## 质量加固续章四（V399b）✅ 全部完成

mmd.py 第五阶段拆分（V41-V65 全部迁出）：

- **V399b** V44 条件簇（13 函数）+ _calc_confidence 及共享辅助闭包（8 函数）迁入 mmd_conditions.py，mmd.py 15605→14001 行；V41-V65 版本化条件簇至此全部迁出，顶层惰性再导出保兼容
- **质量**：全量 pytest 2870 passed / 0 failed；ruff/mypy/format 归零；覆盖率 70.62%（门槛 70）
## 质量加固续章三（V399）✅ 全部完成

mmd.py 第四阶段拆分 + 纯函数测试：

- **V399** mmd.py 拆分第四步：5 个叶子辅助（_calc_atr/_calc_rsi/_calc_adx_strength/_calc_ma_slope/_calc_volume_profile）+ V41/V42/V48/V51 四个条件簇（17 个 _calc_*）迁入 mmd_conditions.py，mmd.py 17328→15607 行；另补 cmd_run_all 纯函数 + fundamental/indicators 纯函数测试（+13 用例）
- **质量**：全量 pytest 2856 passed / 0 failed；ruff/mypy/format 归零；覆盖率 70.12%（门槛 70）

## 质量加固续章二（V397-V398）✅ 全部完成

mmd.py 第三阶段拆分 + 覆盖率冲过 70%：

- **V397** mmd.py 拆分第三步：V49-V65 自包含条件簇（条件137-195，95 个 _calc_* 函数约 9500 行）迁入 mmd_conditions.py，mmd.py 26693→17328 行；mmd_conditions.py 补 ATR/KDJ/RSI/numpy/MMDType/BI/ZS 依赖，顶层惰性再导出保兼容——god-module 三阶段累计瘦身约 1.2 万行
- **V398** 低覆盖模块边界测试 +32 用例（ranker/reverify/verify_print/screen_cli/backtest_cli），覆盖率 69.57%→70.08%，首次稳定越过 70% CI 门槛
- **质量**：全量 pytest 2853 passed / 0 failed；ruff/mypy/format 归零；覆盖率 70.08%（门槛 70）

## 质量加固续章（V393-V396）✅ 全部完成

mmd.py 第二阶段拆分 + 覆盖率冲刺 70%：

- **V393** mmd.py 拆分第二步：V76-V82 版本化条件簇（条件236-263，28 个 _calc_* 函数约 2400 行）抽出为 mmd_conditions.py 独立模块，连同共享辅助 _calc_atr_volatility 一并迁出；mmd.py 顶层惰性再导出保兼容，并修正 advice_simulator/analyser/diagnosis 三处显式导入（消除 mypy 隐式再导出告警）——29k 行 god-module 再瘦身 2400 行
- **V394** unified.py(38%→91%) 与 screen/strength.py(44%→54%) 低覆盖模块边界测试：同步/异步统一客户端懒加载、A股→Mac/扩展→MacEx 路由、全部代理方法委托、上下文管理与关闭；strength 纯函数数值/边界/权重归一化 + 排名器序列化
- **V395** Web 路由成功路径契约补强：chanlun analyze/multi-level/recommend/train 三端点、market 8 端点、monitor create/status/check/stop/list、sina 财报；顺带修复 /monitor/list 被 /monitor/{task_id} 动态路由遮蔽的真实 bug（列表接口返回「任务不存在」）
- **V396** 覆盖率门槛 65→70（实测 69.57%，2821 passed）
- **质量**：全量 pytest tests/unit/ 2821 passed / 0 failed（V393-V396 新增 99 个用例）；ruff/mypy/format 归零；覆盖率 69.57%（门槛 70）

## 质量加固系列（V386-V392）✅ 全部完成

OpenSpec 变更 easy-tdx-v386-quality-hardening 四能力域分阶段落地，质量行从 2609 → 2722 passed：

- **V386** 15 个零覆盖内置策略参数化回归（默认/显式参数、200 根合成行情运行、短/空数据降级、信号形状）——策略层零引用盲区清零
- **V387** 11 个零覆盖 Web 路由契约测试（block/finance/board_mac/mac_data/mac_quotes/ex_market/indicator/fundamental/announcement/realtime/server）——路由层盲区清零
- **V388** 覆盖率门槛 60→65（实测 68.66%）+ .gitignore 覆盖率产物 + 根目录脚手架归档 scaffolds/
- **V389** 前端 vitest 统一测试（评级 node:test→vitest 迁移、V102DecisionCard 5 用例、format/market 纯函数 9 用例、13 视图冒烟）+ CI test 步骤
- **V390** mmd.py 死代码清理：删除零引用 find_mmds_v76，弃用 v40/v41/v42 版本化别名
- **V391** 前端 eslint/prettier 落地（eslint flat config + prettier + format/lint 脚本 + CI lint/format 门禁 + 全量格式化）
- **V392** mmd.py 拆分第一步：V102 决策支持（条件264-267，483 行）抽出为 mmd_v102.py 独立模块，mmd.py 顶层惰性再导出保兼容——29k 行 god-module 治理起步
- **质量**：全量 pytest tests/unit/ 2722 passed / 0 failed（V386-V392 新增 113 个后端用例 + 42 个前端用例）；ruff/mypy/format 归零；vue-tsc + vite build + vitest 通过；覆盖率 68.66%（门槛 65）

## 离线 V102 建议链路（V351-V360，10 个版本）✅ 全部完成

- **V351** offline advice（本地 .day 单标建议回放）→ **V352** --file 任意路径 → **V353** advice-batch 批量实证（json/table/csv/md）→ **V354** watch 离线信号监控（新 3买/3卖 + V102 摘要）→ **V358** watch --interval 连续轮询守护 → **V360** watch --reset/--info 基线管理 → **V364** advice --output md（单标 Markdown 报告，报告能力三级统一）→ **V365** watch --out JSONL 落盘（脚本/定时任务可消费的信号管道）→ **V368** watch JSONL 行直接携带入场/止损/止盈建议（V102 决策支持，管道产出可执行建议）→ **V372** watch --since-days N（只看最近 N 天的新信号，聚焦近期信号无需重置基线）→ **V373** 测试完善（CLI 输出层 12 个单测 + --since-days 时间过滤抽纯函数并补运行时回归，V372 行为级固化）→ **V374** 测试完善（V102 四级报告 json/table/csv/md 全部输出分支 CliRunner 运行时回归 +8 用例，输出契约防线闭环）→ **V375** 测试完善（watch 状态管理 --reset/--info/互斥/损坏自愈/基线去重 8 项行为级回归，基线生命周期固化）→ **V376** 测试完善（advice 边界分支：数据不足<30 根 error JSON / 无 3买/3卖 信号 message 提示 / 离线空 .day 文件 3 项回归，CLI 行为防线闭环）→ **V377** watch --report 新信号 Markdown 报告落盘（标题/扫描时间/逐条含 V102 建议/汇总，无数据渲染 '-'；与 --out JSONL 双通道输出）→ **V378** advice-batch --workers 并行加速（ThreadPoolExecutor，默认 1 串行不变；输出按文件名稳定；单文件处理抽 _advice_batch_one 纯函数）→ **V379** watch --output md（stdout Markdown 报告，与 --report 落盘一致；watch/advice/advice-batch 四级输出统一；docs 离线章节补 V372-V378 参数）→ **V380** 测试完善（watch --interval 轮询分支运行时回归：多轮/去重/第N轮标记/Ctrl+C 优雅退出，V358 行为级固化）→ **V381** demo 升级（offline_chain_demo.py 六级→八级：--workers/--since-days/--report/--output md 全覆盖 + 真实 CLI 回归）→ **V382** 测试完善（Web 层 V102 字段契约：to_dict 四字段完整序列化 + monitor 新信号三字段 + screening latest_mmd 三字段，前端卡片不空白）→ **V383** 测试完善（Web V102 契约补全最后两个数据源：train 候选点 v102_grade/advice + 诊断页 latest_mmd/recent_signals 四字段，五个 Web 序列化点全部有契约测试）→ **V384** 测试完善（V102 实证脚本 validate/advice_batch_validate 首个 pytest 回归：默认/--md 双模式真实运行 + mock 客户端批量报告）→ **V385** 测试完善（策略执行层 use_v102_advice 边界：advice=None/禁用对照/缺字段/加仓保留/平仓重置 5 用例，实际下单环节钉住）
- **文档**：docs/v102-decision-support.md（离线三小节）、QUICKSTART 第 5 项离线实证、DEV_STATUS 落地清单全收录
- **使用流程**：sync-all 同步 → watch 监控新信号 → advice/advice-batch 单标/批量实证 → csv/md 导出 → use_v102_advice 落地策略（完全断网可用）
- **质量**：全量 pytest tests/unit/ 2609 passed / 0 failed（V373-V385 新增 63 个用例）；ruff/mypy/format 归零；vue-tsc + vite build 通过

## V102 决策支持落地清单（V320-V346，27 个版本）✅ 全部完成

**核心算法**：条件264-267（多信号相关性/质量评分卡/决策支持输出/历史模式匹配）→ V320 置信度真实并入
**Web 展示**：诊断页决策卡片+回放实证+CSV（V320/V322/V330）、缠论页卡片+买卖点徽章+信号历史回溯+CSV（V327/V336/V341/V343）、监控页信号摘要（V328）、选股页摘要（V332）、训练页复盘/教学徽章（V339/V344）
**入口引导**：回测页提示（V333）、组合/对比/寻优页引导（V338/V340/V342）
**CLI/脚本**：easy-tdx advice（json/table/csv/md，V323/V329/V370 四级报告统一）、offline advice（本地 .day 离线回放，V351；--file 指定路径，V352；advice-batch 批量实证 V353；watch 离线信号监控 V354/V358 连续轮询/V360 基线管理；--out JSONL 携带建议 V365/V368）、validate_v102_advice（V321/V334 --md / V346 3卖做空多空双向）、advice_batch_validate（V325/V335 --md）
**策略执行**：缠论策略 use_v102_advice 自动止损止盈（V324）
**文档**：QUICKSTART 指南（V326）、docs/v102-decision-support.md（V337）、CHANGELOG/DEV_STATUS 里程碑（V331/V344 等）
**质量**：全量 pytest tests/unit/ 2535+ 通过；ruff/mypy/format 归零；vue-tsc + vite build 通过

---

## 续会话收尾（2026-09）✅ 已全部完成

- **V102 缠论模型决策支持增强（条件264-267）**：多信号相关性分析 / 信号质量评分卡 / 决策支持输出（入场·止损·止盈·仓位·RRR）/ 历史模式匹配——总条件数 243→267
- **诊断 API 暴露 V102 字段**：diagnosis.py latest_mmd 与 recent_signals 均补 v102_multi_signal_correlation / v102_signal_quality / v102_decision_support / v102_pattern_match；types.py 补 MMD 字段声明（mypy strict 兼容）
- **算法配套收尾**：删除重复 find_mmds_v44 别名；清理 ruff 告警（重复定义/未使用变量/歧义命名/Any 导入/长行）
- **信号准确度健壮性**：空报告恒带 note 字段；前瞻收益除零保护
- **测试修复**：V102 单测 12 个全绿；修复 9 处既往失效测试；修复管道脚本 2 处 bug
- **质量门禁**：ruff check/format + mypy src/ 归零；全量 pytest tests/unit/ 2501 通过；管道脚本 7/7；web-ui vue-tsc + vite build 通过
- **提交**：3129a16 feat(chanlun): V102 缠论模型决策支持增强 + v85-v90 算法配套收尾

## V102 决策支持落地（阶段1+2，V320-V325）✅ 已全部完成

- **V320** 条件265/266 的 confidence_adjust 真实并入买卖点置信度（_apply_v102_decision_confidence，clamp [0,1]）；诊断页新增 V102DecisionCard 可执行卡片（操作建议/入场/止损/止盈/仓位/RRR + 质量评分卡 + 历史模式匹配）
- **V321** advice_simulator：V102 建议执行模拟器（long/short 方向、止损优先、到期按收盘结算）+ 实证脚本 validate_v102_advice.py
- **V322** POST /api/v1/diagnosis/advice-simulate + 诊断页「▶ 回放实证」按钮/结果表（每笔出场原因+收益、批量胜率）
- **V323** easy-tdx advice MARKET CODE CLI 命令（--table/json）；collect_signal_advices 供 Web/CLI 共用
- **V324** 缠论策略 use_v102_advice：3买 首仓按 V102 建议的止损/第一止盈动态出场（盘中 high/low 触发）
- **V325** 批量实证：summarize_batch + scripts/advice_batch_validate.py（多标的汇总 vs 买入持有）
- **质量门禁**：全量 pytest tests/unit/ 2534 通过（V320-V325 新增 33 个用例）；ruff/mypy/format 归零；vue-tsc + vite build 通过

## V102 决策支持全面落地（V323-V330）✅ 已全部完成

- **V323** easy-tdx advice MARKET CODE CLI（json/table）；**V329** 补 --output csv
- **V324** 缠论回测策略 use_v102_advice：3买 首仓按 V102 建议的止损/第一止盈动态出场
- **V325** 批量实证：summarize_batch + scripts/advice_batch_validate.py（vs 买入持有）
- **V327** 缠论分析页 /chanlun 接入 V102 决策卡片（analyser 序列化补 v102 字段）
- **V328** 监控页实时信号带 V102 质量评级徽章 + 操作建议摘要
- **V330** 诊断页「回放实证」结果「📊 导出 CSV」
- **文档**：QUICKSTART「V102 决策支持如何用」指南 + CHANGELOG/DEV_STATUS 里程碑 + [V102 决策支持完整文档](docs/v102-decision-support.md)

## V102 全站收尾（V336-V343）✅ 已全部完成

- **V336** 缠论页买卖点列表 V102 质量徽章；**V339** 训练页复盘 V102 徽章
- **V337** docs/v102-decision-support.md 完整文档；**V338/V340/V342** 组合/对比/寻优页 V102 引导提示——全站主要页面均有 V102 入口
- **V341** 缠论页「信号历史回溯」面板：逐笔买卖点 V102 建议 + 5/10/20 日后表现（DEV_STATUS 中期优化方向落地）
- **V343** 信号历史回溯面板「📊 导出 CSV」（逐笔信号 + V102 建议 + 事后表现，与全站导出系列对齐）
- **质量门禁**：全量 pytest tests/unit/ 2535 passed / 0 failed；ruff/mypy/format 归零；vue-tsc + vite build 通过

## 上次会话状态
- **无活跃后台任务** - 上一个 session 未留下进行中的工作
- **项目已完成大部分核心功能** - 缠论算法(V48-V84)、回测引擎、前端可视化均已实现

---

## 本次修复改进

### 1. 修复: 删除重复的 `_calc_confidence_v47` 函数定义
- **文件**: `src/easy_tdx/chanlun/mmd.py`
- **问题**: 文件中有两个 `_calc_confidence_v47` 定义（原 line 4595 和 line 16545）
  - 第一个是简单别名，直接委托给 `_calc_confidence`，绕过了 V47 的后确认/有效性窗口/类型校准逻辑
  - 第二个包含完整的 V47 校准逻辑
  - Python 使用最后定义的版本，所以功能上正确，但代码可读性差且危险
- **修复**: 删除了第一个简单别名定义，只保留正确的 V47 实现
- **影响**: 提高代码可维护性，防止未来误改

### 2. 新增测试: `tests/unit/test_chanlun_v85_core_validation.py`
覆盖以下核心验证：
- `_calc_confidence_v47` 单一定义 + 含 V47 逻辑
- `find_mmds` 调用 `_calc_confidence_v47` 而非简单别名
- 分型 bar_index 与 date 锚定一致性
- 笔端点与分型 bar_index 一致
- 中枢端点与序列化结果一致
- 买卖点 bar_index 一致性
- 笔方向严格交替
- 新笔模式 gap 要求
- 中枢最小笔数要求
- 最后一个中枢未完成情况
- 信号准确度计算结构正确性
- 上涨行情买入命中率 > 随机基准
- 下跌行情卖出命中率合理

---

## 缠论算法架构

```
K线数据 → K线合并(包含处理) → 分型识别 → 笔计算 → 中枢计算 → 线段计算 → 买卖点识别 → 背驰判断
   │                                                                          │
   └───────────────────── MACD/BOLL 指标计算 ←──────────────────────────────────┘
```

### 核心模块
| 模块 | 文件 | 功能 |
|------|------|------|
| K线合并 | `chanlun/kline_merge.py` | 处理K线包含关系，向上取高高/向下取低低 |
| 分型识别 | `chanlun/fractal.py` | 顶/底分型检测，支持严格/非严格模式 |
| 笔计算 | `chanlun/bi.py` | 新笔/老笔/简单笔三种模式，端点方向校验 |
| 中枢计算 | `chanlun/zs.py` | 重叠率动态阈值，最小宽度检查 |
| 线段计算 | `chanlun/xd.py` | 特征序列法，方向交替，共享转折点 |
| 买卖点 | `chanlun/mmd.py` | 263+增强条件，V47置信度校准 |
| 背驰判断 | `chanlun/beichi.py` | 笔背驰/盘整背驰/趋势背驰 |

### 关键改进点（V83 已修复）
- **1买/1卖趋势门控**: 必须有≥2个同向中枢才产生，纯震荡市不产生一买/一卖
- **时间窗口索引一致性**: 2买/2卖和3买/3卖使用原始K线索引(k_index)而非笔索引
- **参考中枢关联**: 笔背驰参考其发生时的同期中枢，而非数据末端最后中枢

---

## 前端功能

### 缠论分析页面 (`ChanlunView.vue`)
- 支持日线/周线/分钟线(5/15/30/60分钟)
- 多级别联立分析（高级别+低级别区间套）
- 买卖点准确度验证面板（按信号类型分组的前瞻命中率）
- 市场状态判断 + 操作建议
- BOLL辅助分析
- 缠论理论帮助面板
- 一键跳转回测验证

### 图表组件 (`ChanlunChart.vue`)
- ECharts 双面板：主图(K线+缠论结构) + 副图(MACD)
- 笔(虚线)、线段(实线)、中枢(区域)、买卖点(彩色标记)、分型(三角/菱形)、背驰(橙色标记)
- 端点精确锚定到原始K线极值
- 训练模式揭示游标

### 回测页面 (`BacktestView.vue`)
- 单标的/组合/多策略回测
- 分段稳健性检查（过拟合检测）
- 信号准确度验证
- 模型信任度评分

---

## 启动开发环境

### 后端（Python FastAPI）
```bash
cd /home/skp/workspace/easy_tdx
source .venv/bin/activate
pip install -e ".[web]"
python -m easy_tdx.cli cmd_web --host 0.0.0.0 --port 8000
```

### 前端（Vue 3 + Vite）
```bash
cd /home/skp/workspace/easy_tdx/web-ui
npm install
npm run dev
# 开发服务器运行在 http://localhost:3012
# API代理到 http://127.0.0.1:8000
```

### 浏览器访问
- 前端: http://localhost:3012
- 缠论分析: http://localhost:3012/#/chanlun
- 回测: http://localhost:3012/#/
- 诊断: http://localhost:3012/#/diagnosis

---

## 测试命令

```bash
cd /home/skp/workspace/easy_tdx
source .venv/bin/activate

# 运行所有测试
pytest tests/ -v

# 运行缠论相关测试
pytest tests/unit/test_chanlun*.py -v
pytest tests/unit/test_chanlun_enhancements.py -v

# 运行新增的V85核心验证测试
pytest tests/unit/test_chanlun_v85_core_validation.py -v

# 运行回测相关测试
pytest tests/unit/test_backtest*.py -v

# 运行前端 TypeScript 编译检查
cd web-ui && npx vue-tsc --noEmit
```

---

## 缠论模型准确性验证方法

### 1. 买卖点准确度验证（前端「买卖点准确度验证」面板）
- 显示每种信号类型（1buy/2buy/3buy/1sell/2sell/3sell）的5根前瞻命中率
- 与随机入场基准对比，超额命中率 > 0 说明信号有择时价值
- 用户可以直观看到「哪类信号真的准」

### 2. 回测验证（「去回测」/「回测验证」按钮）
- 一键跳转到回测页面，携带当前标的和周期参数
- 选择「缠论策略」跑历史回测
- 查看实际账户收益、胜率、命中率
- 分段稳健性检查验证是否过拟合

### 3. 信号准确度 API
- `GET /api/v1/diagnosis/quick?market=SH&code=000001`
- 返回完整缠论结构 + 技术指标诊断 + 综合推荐

### 4. 多级别区间套
- 勾选「多级别联立」复选框
- 观察高级别买卖点与低级别走势的一致性评分
- 高级别背驰在小级别先确认 = 更高置信度

---

## 后续优化方向

### 短期（已完成部分）
- ✅ 修复重复函数定义
- ✅ 新增核心算法验证测试
- ✅ 买卖点bar_index锚定一致性验证

### 中期
- [ ] 增加更多真实股票数据的回测验证
- [ ] 优化线段算法在极端行情下的表现
- [ ] 添加分钟线级别的缠论分析测试
- [x] 前端增加「信号历史回溯」功能（V341 落地：缠论页逐笔买卖点 V102 建议 + 事后 5/10/20 日表现 + CSV 导出 V343）

### 长期
- [ ] 引入机器学习模型对263个增强条件进行权重学习
- [ ] 添加实盘模拟交易功能
- [ ] 支持更多市场行情数据源

---

## 已知限制

1. **数据延迟**: 实时行情依赖通达信服务器，可能有几秒延迟
2. **回测精度**: 使用次日开盘价/收盘价成交，与实际滑点有差异
3. **分钟线数据**: 部分券商只支持到60分钟级别
4. **北交所股票**: 需要特殊市场识别（已在 market.ts 中处理）

---

*报告生成时间: 2025-08-28*
*版本: easy-tdx 1.59.0*
