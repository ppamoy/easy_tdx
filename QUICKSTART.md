# easy_tdx 开发环境快速启动指南

## 环境要求
- Python 3.10+
- Node.js 18+
- npm 9+

## 一键启动

```bash
cd /home/skp/workspace/easy_tdx
source .venv/bin/activate
python scripts/dev_server.py
```

## 手动启动

### 后端 (FastAPI)
```bash
source .venv/bin/activate
easy-tdx serve --host 0.0.0.0 --port 8000
```

### 前端 (Vite)
```bash
cd web-ui
npm install  # 首次需要
npm run dev
```

## 访问地址
- 前端: http://localhost:3012
- 缠论分析: http://localhost:3012/chanlun
- API文档: http://localhost:8000/redoc
- 健康检查: http://localhost:8000/api/v1/health

## 运行测试

```bash
# 缠论管道测试
python tests/scripts/test_chanlun_pipeline.py

# 模型验证
python scripts/verify_chanlun_model.py

# 单元测试
python -m pytest tests/unit/test_chanlun_v87_comprehensive.py -xvs
python -m pytest tests/unit/test_chanlun_v86_bi_enhancements.py -xvs
python -m pytest tests/unit/test_chanlun_v87_zs_enhancements.py -xvs
python -m pytest tests/unit/test_chanlun_v87_xd_enhancements.py -xvs
python -m pytest tests/unit/test_chanlun_signal_accuracy.py -xvs
```

## 浏览器控制台检查

打开 http://localhost:3012/chanlun，按 F12 打开开发者工具：

```javascript
// 1. 检查 JavaScript 错误
// Console 标签应无红色错误

// 2. 检查缠论图表
console.log(window.__CHANLUN_CHART__)

// 3. 测试 API
fetch('/api/v1/chanlun/analyze', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({market: 'SZ', code: '000001', category: 'DAY', count: 500, start: 0})
}).then(r => r.json()).then(d => {
  console.log('笔数:', d.bi_count);
  console.log('中枢数:', d.zs_count);
  console.log('买卖点数:', d.mmd_count);
}).catch(e => console.error('API错误:', e));
```

## V102 缠论决策支持：如何用（帮你下单）

V102 在缠论买卖点（3买/3卖）上额外给出**可执行建议**（条件264-267）：
多信号相关性（避免过度交易）、信号质量评分卡（A/B/C/D）、决策支持输出（入场价/止损/止盈/仓位/风险收益比/操作建议）、历史模式匹配（胜率统计）。
条件265/266 的置信度调整已真实并入买卖点置信度。

### 1) 诊断页一键看建议 + 回放实证
- 打开 `http://localhost:3012/diagnosis`，输入股票 → 缠论卡片下方出现 **🎯 V102 决策支持** 卡片（操作建议 / 入场价 / 止损 / 止盈1 / 止盈2 / 风险收益比 / 建议仓位 + 质量评分卡 + 历史模式匹配）。
- 点击 **「▶ 回放实证（V102建议）」**：把该股最近 3买/3卖 信号的建议放到历史行情逐笔回放，输出每笔出场原因（止损/止盈/到期）与收益、批量胜率与平均收益。

### 2) 命令行建议回放
```bash
easy-tdx advice SZ 000001
easy-tdx advice SZ 000001 --max-hold 15 --table
```

### 3) 回测：缠论策略按 V102 建议自动止损止盈
- 回测页选择 **缠论买卖点** 策略，勾选参数 **「3买按V102建议止损止盈」（use_v102_advice）**：3买 首仓按 V102 建议的止损价/第一止盈价动态出场（优先于固定百分比止损）。

### 4) 批量实证（多标的汇总 vs 买入持有）
```bash
python scripts/advice_batch_validate.py SZ 000001 SH 600519
# 或用文件（每行 MARKET CODE）
python scripts/advice_batch_validate.py --file symbols.txt --max-hold 15
```
输出每只标的的建议回放结果 + 该标的「买入持有」收益对照，最后全局汇总（总建议数 / 胜率 / 平均收益 / 正收益标的占比 / 出场分布）。

### 5) 离线实证（本地 .day 行情，无需网络，V351-V353）
前置条件：本地已安装通达信并下载过日线（或已用 `easy-tdx offline sync-all` 同步）。单标与批量均可离线：

```bash
easy-tdx offline advice SZ 000001 --output csv                    # 单只（--file 可指定任意 .day 路径）
easy-tdx offline advice-batch --dir /path/to/vipdoc/sz/lday --limit 10 --output md   # 批量
easy-tdx offline watch --dir /path/to/vipdoc/sz/lday --output csv # 只报告新发现的 3买/3卖 + V102 建议摘要
easy-tdx offline watch --dir /path/to/vipdoc/sz/lday --interval 60 # 连续轮询守护（每 60 秒扫描，Ctrl+C 退出）
easy-tdx offline watch --state /tmp/watch.json --info   # 查看监控基线状态（V360）
easy-tdx offline watch --state /tmp/watch.json --reset  # 清空监控基线（V360）
```
完整用法见 [docs/v102-decision-support.md](docs/v102-decision-support.md)。
