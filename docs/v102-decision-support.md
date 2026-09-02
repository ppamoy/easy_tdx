# V102 缠论决策支持文档

easy-tdx 的 V102 决策支持在缠论买卖点（3买/3卖）之上额外给出**可执行建议**：
入场价 / 止损 / 止盈 / 仓位 / 风险收益比 / 操作建议，并配套全站展示、回放实证、回测自动执行与批量实证能力。

## 1. 条件264-267 架构

| 条件 | 名称 | 函数 | 作用 |
|------|------|------|------|
| 264 | 多信号相关性分析 | `_calc_multi_signal_correlation` | 密集信号（≥3个/10根K线）→ -3% 置信度，避免过度交易 |
| 265 | 信号质量评分卡 | `_calc_signal_quality_scorecard` | 技术指标/量价配合/趋势对齐/波动率环境四维评分 → A/B/C/D |
| 266 | 决策支持输出 | `_calc_decision_support_enhanced` | 入场/止损/止盈/仓位/RRR/操作建议（仅 3买/3卖） |
| 267 | 历史模式匹配 | `_calc_historical_pattern_matching` | 相似形态胜率统计，胜率≥65% → +4% 置信度 |

接口：`_apply_v102_decision_confidence(mmd, scorecard, decision)` 把条件265/266 的
置信度调整真实并入 `mmd.confidence`（钳制 [0,1]）——这是 V320 的关键修复，
此前这些调整只存储字段、不参与最终置信度。

## 2. 全站入口

| 入口 | 位置 | 说明 |
|------|------|------|
| 决策卡片 | 诊断页 / 缠论分析页 | `V102DecisionCard.vue`：操作建议/入场/止损/止盈/仓位/RRR + 质量评分卡条形图 + 历史模式匹配 |
| 回放实证 | 诊断页「▶ 回放实证」按钮 | 把 3买/3卖 建议放到历史行情逐笔回放（止损/止盈/到期），输出胜率/平均收益 + CSV |
| 质量/建议摘要 | 监控页信号列表 / 选股页筛选结果 | V102 质量评级徽章（A/B/C/D）+ 操作建议摘要 |
| 买卖点列表 | 缠论分析页明细表 | V102 质量评级徽章，按信号质量快速识别 |
| 信号历史回溯 | 缠论分析页「🕰 信号历史回溯」面板 | 逐笔买卖点 V102 建议 + 5/10/20 日后表现 + 20日命中（可导出 CSV，V341/V343） |
| 引导提示 | 组合/对比/寻优页报告区 | V102 决策支持入口引导（V338/V340/V342），全站主要页面均有入口 |
| CLI | `easy-tdx advice MARKET CODE` | json/table/csv 三类输出，与 Web 共用 `collect_signal_advices` |
| 回测自动执行 | 缠论策略参数 `use_v102_advice` | 3买 首仓按 V102 建议的止损/第一止盈动态出场（盘中 high/low 触发） |
| 批量实证 | `scripts/advice_batch_validate.py` | 多标的建议回放汇总 vs 买入持有（`--md` 输出 Markdown 报告） |
| 单标实证 | `scripts/validate_v102_advice.py` | 合成行情端到端演示（`--md` 输出 Markdown 报告；V346 起 3买/3卖 多空双向回放） |

### 关键数据流

- **chanlun/analyze**：`ChanlunResult.to_dict()` 的 mmds 每项携带 v102_* 四个字段（V327）
- **诊断 quick**：latest_mmd 与 recent_signals 携带 v102_* 字段（V102 收尾）+
  `POST /diagnosis/advice-simulate` 返回回放报告（V322）
- **监控**：new_signals 携带 v102_* 字段（V328）；**选股**：latest_mmd 携带 v102_* 字段（V332）
- **回测**：ChanlunStrategy.init 信号队列携带 V102 建议（V324），按建议 SL/TP 出场

## 3. 使用示例

### 诊断页看建议 + 回放

打开 `http://localhost:3012/diagnosis` → 输入股票 → 缠论卡片下方：
1. **🎯 V102 决策支持** 卡片：操作建议 + 入场/止损/止盈/仓位/RRR
2. 点击 **「▶ 回放实证（V102建议）」** → 看每笔出场原因与收益、批量胜率 → 「📊 导出 CSV」

### 命令行建议回放

```bash
easy-tdx advice SZ 000001                # JSON
easy-tdx advice SZ 000001 --table        # 表格
easy-tdx advice SZ 000001 --output csv   # CSV 导出
easy-tdx advice SZ 000001 --output md    # Markdown 报告（V370，与离线版对齐）
```

### 回测自动止损止盈

回测页选择 **缠论买卖点** 策略 → 勾选 **「3买按V102建议止损止盈」**（use_v102_advice）：
3买 首仓按 V102 建议的止损价/第一止盈价动态出场，交易日志记录 `v102_stop_loss` / `v102_take_profit`。

### 批量实证

```bash
python scripts/advice_batch_validate.py SZ 000001 SH 600519 --md
```
输出多标的批量实证 Markdown 报告（vs 买入持有）。

### 离线建议回放（本地 .day，无需网络，V351/V352）

前置条件：本地已安装通达信并下载过日线（或已用 `sync-all` 同步）：

```bash
easy-tdx offline advice SZ 000001            # JSON
easy-tdx offline advice SZ 000001 --output csv   # CSV 导出
easy-tdx offline advice SZ 000001 --output md    # Markdown 报告（V364）
easy-tdx offline advice SZ 000001 --count 300 --max-hold 15
easy-tdx offline advice SZ 000001 --file /path/to/sh600000.day --output csv  # 指定任意 .day 路径（V352）
```
读取本地 .day 日线 → 缠论分析 → 对 3买/3卖 信号生成 V102 建议 → 逐笔回放
（止损/止盈/到期）→ 输出汇总与每笔明细（含 symbol/bars/signals 上下文）。

### 离线批量建议实证（V353）

对自选股票池（本地 .day 目录）一键批量实证：

```bash
easy-tdx offline advice-batch --dir /path/to/vipdoc/sz/lday --limit 10 --output md
easy-tdx offline advice-batch --dir /path/to/vipdoc/sz/lday --output csv
```
扫描目录内 .day 文件（文件名推断市场/代码，如 sh600000.day → SH/600000），
逐只跑 V102 建议回放并用 summarize_batch 聚合（总建议/胜率/平均收益/正收益标的），
输出 json/table/csv/md（含每只 vs 买入持有对照）。

### 离线链路端到端联调（V366）

合成数据验证六级链路在无网络环境可完整衔接（无需真实 .day 行情）：

```bash
python scripts/offline_chain_demo.py
```
合成 .day → offline advice --file → offline advice-batch --dir → offline watch --dir --out，
输出每级退出码与结果；同时作为六命令的运行时回归（曾抓出并修复 3 个隐藏运行时 bug）。

### 离线信号监控（V354）

无网络轮询监控本地股票池的新信号（类比 Web 监控页「新信号」面板）：

```bash
easy-tdx offline watch --dir /path/to/vipdoc/sz/lday --output csv
easy-tdx offline watch --dir /path/to/vipdoc/sz/lday --state /tmp/watch.json --limit 5
easy-tdx offline watch --dir /path/to/vipdoc/sz/lday --interval 60 --output csv   # 连续轮询守护（V358）
easy-tdx offline watch --state /tmp/watch.json --info    # 查看状态（路径 + 已记录信号数，V360）
easy-tdx offline watch --state /tmp/watch.json --reset   # 清空基线重新开始（V360）
easy-tdx offline watch --dir /path/to/vipdoc/sz/lday --out /tmp/signals.jsonl   # 新信号 JSONL 落盘（V365；V368 起每行含入场/止损/止盈建议）
easy-tdx offline watch --dir /path/to/vipdoc/sz/lday --since-days 30   # 只看最近 30 天的新信号（V372）
```
状态文件（缺省 ~/.easy_tdx/offline_watch_state.json）记录已见信号
（symbol+type+date），每次只报告**新发现**的 3买/3卖 信号 + V102 质量评级
与操作建议摘要；首次运行建立基线（当前全部信号记为已见并输出）。
--interval N 开启连续轮询（每 N 秒自动扫描，Ctrl+C 退出，轻量离线监控守护）；
--info/--reset 管理监控基线（无需 .day 目录即可执行）。

## 4. 实证结果示例（合成行情回放）

`python scripts/validate_v102_advice.py --md` 输出示例：

| # | 入场 | 止损 | 止盈1 | 出场价 | 原因 | 收益% |
|---|------|------|-------|--------|------|-------|
| 1 | 49.61 | 47.59 | 52.53 | 49.38 | 到期 | -0.47 |
| 2 | 48.34 | 46.38 | 51.19 | 49.33 | 到期 | +2.04 |
| 3 | 51.25 | 49.17 | 54.27 | 52.23 | 到期 | +1.92 |

**汇总**：胜率 80% | 平均收益 +1.13% | 累计 +5.64%

> ⚠️ 合成行情仅演示回放机制；真实使用请用真实行情数据并注意交易成本/滑点。

## 5. 测试与验证

- `tests/unit/test_v102_decisionsupport.py`：条件264-267 单测 + `_apply_v102_decision_confidence` 并入/钳制
- `tests/unit/test_advice_simulator.py`：建议执行模拟器（多空/long short、止损优先、到期结算、批量汇总、CLI help）
- `tests/unit/test_chanlun_strategy.py`：use_v102_advice 止损止盈触发测试
- `tests/unit/test_diagnosis_router.py`：advice-simulate 端点测试
- 全量 `pytest tests/unit/` 通过；ruff/mypy/format 归零；vue-tsc + vite build 通过
