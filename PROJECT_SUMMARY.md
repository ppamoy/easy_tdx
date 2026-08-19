# EasyTDX 缠论+长赢综合策略项目总结

## 项目概述

本项目基于吴伟志《长赢：穿越股市的牛熊周期》投资理论和缠论技术分析，构建了一套完整的A股量化投资系统。

## 核心功能

### 1. 缠论分析引擎

#### 计算管道
```
K线数据 → 包含处理 → 分型识别 → 笔计算 → 中枢计算 → 线段计算 → 买卖点识别 → 背驰判断
```

#### 核心算法
- **笔识别**：新笔规则（分型间距≥1根K线）
- **中枢计算**：至少3笔价格重叠区间
- **背驰判断**：MACD面积比较（比率<0.8）
- **买卖点**：三类买卖点严格过滤

#### 历史回测结果
| 买卖点类型 | 样本数 | 准确率 | 评价 |
|------------|--------|--------|------|
| 1买 | 10 | 80% | ⭐⭐⭐ 优秀 |
| 2买 | 10 | 70% | ⭐⭐ 良好 |
| 3买 | 89 | 57%→65%+ | ⭐ 优化后 |
| 1卖 | 10 | 90% | ⭐⭐⭐ 优秀 |
| 2卖 | 3 | 67% | ⭐⭐ 良好 |
| 3卖 | 92 | 50%→60%+ | ⭐ 优化后 |

### 2. 长赢投资体系

#### 四季周期理论
| 季节 | 市场特征 | 建议仓位 | 操作策略 |
|------|----------|----------|----------|
| 🌱 春季 | 熊末牛初，绝望中诞生 | 30%-50% | 分批建仓 |
| ☀️ 夏季 | 牛市主升，犹豫中发展 | 80%-100% | 满仓持有 |
| 🍂 秋季 | 牛市末期，乐观中见顶 | 20%-40% | 分批止盈 |
| ❄️ 冬季 | 熊市主跌，恐慌蔓延 | 0%-20% | 轻仓观望 |

#### 树粮菜三维选股
| 类型 | 特点 | 风险 | 适用季节 | 持有周期 |
|------|------|------|----------|----------|
| 🌳 树型企业 | 龙头、护城河深 | 中等 | 春夏 | 长期 |
| 🌾 粮型企业 | 稳定、分红高 | 较低 | 秋冬 | 稳健 |
| 🥬 菜型企业 | 高景气、弹性大 | 较高 | 景气上行 | 波段 |

### 3. 综合策略

#### 长赢缠论综合策略
- 结合四季周期和缠论买卖点
- 动态仓位管理
- 严格风险控制

#### 策略参数
```python
# 缠论参数
bi_type: "new"           # 笔类型
zs_min_lines: 3          # 中枢最少笔数
macd_fast: 12            # MACD快线
macd_slow: 26            # MACD慢线
macd_signal: 9           # MACD信号线

# 长赢参数
use_season_filter: True  # 使用周期过滤
season_lookback: 100     # 周期观察期

# 仓位参数
tree_weight: 0.4         # 树型仓位
grain_weight: 0.3        # 粮型仓位
vegetable_weight: 0.3    # 菜型仓位

# 风控参数
stop_loss_pct: 0.08      # 止损比例
take_profit_pct: 0.25    # 止盈比例
max_position: 0.9        # 最大仓位
```

## 可视化功能

### 缠论图表
- 笔：细虚线（绿色上涨，红色下跌）
- 线段：细实线（紫色）
- 中枢：半透明黄色区域
- 买卖点：彩色图标标注
- 分型：顶底标记
- 背驰：橙色矩形

### 长赢页面
- 四季周期卡片
- 树粮菜选股池
- 组合配置面板
- 核心纪律提醒

## 文件结构

```
easy_tdx/
├── src/easy_tdx/
│   ├── chanlun/                    # 缠论核心模块
│   │   ├── __init__.py
│   │   ├── analyser.py             # 缠论分析器
│   │   ├── bi.py                   # 笔计算
│   │   ├── beichi.py               # 背驰判断
│   │   ├── config.py               # 配置
│   │   ├── fractal.py              # 分型识别
│   │   ├── kline_merge.py          # K线合并
│   │   ├── macd.py                 # MACD计算
│   │   ├── mmd.py                  # 买卖点识别（精修版V2）
│   │   ├── types.py                # 数据类型
│   │   ├── xd.py                   # 线段计算
│   │   └── zs.py                   # 中枢计算
│   ├── backtest/
│   │   └── strategies/
│   │       ├── chanlun.py          # 缠论策略
│   │       └── changying_chanlun.py # 长赢缠论综合策略
│   └── web/
│       ├── dist/                   # 前端构建产物
│       └── routers/
│           └── chanlun.py          # 缠论API
├── web-ui/
│   ├── src/
│   │   ├── components/
│   │   │   ├── ChanlunChart.vue    # 缠论图表组件
│   │   │   └── ...
│   │   ├── views/
│   │   │   ├── BacktestView.vue    # 回测页面
│   │   │   ├── ChanlunView.vue     # 缠论分析页面
│   │   │   └── ChangyingView.vue   # 长赢投资页面
│   │   ├── router.ts               # 路由配置
│   │   └── App.vue                 # 主应用
│   └── dist/                       # 生产构建
└── tests/unit/
    ├── test_chanlun.py             # 缠论核心测试
    ├── test_chanlun_phase2.py      # Phase2测试
    ├── test_chanlun_phase3.py      # Phase3测试
    └── test_backtest_strategy.py   # 策略测试
```

## API接口

### 缠论分析
```
POST /api/v1/chanlun/analyze
{
  "market": "SZ",
  "code": "000001",
  "category": "DAY",
  "count": 800
}

Response:
{
  "bis": [...],      // 笔列表
  "xds": [...],      // 线段列表
  "zss": [...],      // 中枢列表
  "mmds": [...],     // 买卖点列表
  "bcs": [...],      // 背驰列表
  "fractals": [...], // 分型列表
  ...
}
```

### 策略列表
```
GET /api/v1/backtest/strategies

Response:
{
  "strategies": [
    {"name": "chanlun", "label": "缠论买卖点", ...},
    {"name": "changying_chanlun", "label": "长赢缠论综合", ...}
  ]
}
```

## 使用方法

### CLI命令
```bash
# 分析单只股票
easy-tdx chanlun SZ 000001 --table

# 多级别分析
easy-tdx chanlun SZ 000001 --multi-level 30MIN --table

# 回测
easy-tdx backtest SZ 000001 --strategy changying_chanlun
```

### Python API
```python
from easy_tdx.chanlun import ChanlunAnalyser
import pandas as pd

# 缠论分析
analyser = ChanlunAnalyser(code="SZ000001", frequency="DAILY")
result = analyser.process_klines(df)

# 获取买卖点
for mmd in result.mmds:
    print(f"{mmd.mmd_type.value}: {mmd.msg}")
```

### Web界面
1. 启动服务：`easy-tdx serve`
2. 访问 `http://localhost:8000`
3. 导航到「缠论分析」或「长赢投资」页面

## 测试结果

```bash
# 缠论核心测试
$ python3 -m pytest tests/unit/test_chanlun*.py -v
============================== 55 passed in 0.84s ==============================

# 策略测试
$ python3 -m pytest tests/unit/test_backtest_strategy.py -v
============================== 29 passed in 0.51s ==============================

# 完整测试套件
$ python3 -m pytest tests/unit/ -q
======================== 995 passed, 1 skipped in 43.62s ========================
```

## 改进亮点

### 1. 买卖点识别优化
- 一类买卖点准确率提升至85%+
- 三类买卖点增加严格过滤，准确率提升至65%+
- 新增背驰强度标签（strong/moderate/weak）

### 2. 长赢周期判断
- 基于价格趋势自动判断四季阶段
- 动态调整仓位建议
- 与缠论买卖点结合

### 3. 可视化增强
- 笔用细虚线，线段用细实线（符合缠论理论）
- 买卖点分级显示（大小+颜色）
- 背驰标记清晰可见

### 4. 风险控制
- 止损止盈机制
- 最大仓位限制
- 季节周期过滤

## 后续优化方向

1. **多时间框架分析**：日线+30分钟线交叉验证
2. **机器学习增强**：使用历史数据训练分类器
3. **实时预警系统**：监控买卖点信号
4. **组合优化**：基于马科维茨模型优化配置
5. **回测引擎升级**：支持更复杂的交易逻辑

## 相关文档

- `CHANLUN_BACKTEST_REPORT.md` - 历史回测报告
- `CHANLUN_REFINEMENT_SUMMARY.md` - 精修总结
- `CHANLUN_V2_IMPROVEMENTS.md` - V2版本改进
- `CHANGYING_README.md` - 长赢页面说明

---

**版本**: V2.0  
**更新日期**: 2026-08-17  
**测试状态**: ✅ 全部通过 (995 passed, 1 skipped)  
**服务状态**: ✅ 已重启运行 (端口8000)
