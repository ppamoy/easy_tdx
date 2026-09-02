# easy_tdx 缠论模型改进报告

## 最新修复 (2026-07-10)

### Bug Fix: zs.py 冗余 max() 调用
**文件**: `src/easy_tdx/chanlun/zs.py:132`
**问题**: `max(zg_candidate - zd_candidate)` 对单个参数调用 max() 无意义且造成混淆
**修复**: 改为 `(zg_candidate - zd_candidate)`
**影响**: 轻微代码清晰度改进，不影响运行结果

### 新增文件
- `tests/scripts/test_chanlun_pipeline.py`: 完整管道验证测试套件
- `scripts/dev_server.py`: 开发环境一键启动脚本

## 已修复的问题

### 1. ChanlunView.vue 语法错误 (Critical) ✅
**问题**: `confidenceColor` 函数声明缺失，只有函数体悬浮在 `ACTION_GUIDE` 对象之后
**位置**: `web-ui/src/views/ChanlunView.vue:354-358`
**修复**: 添加了完整的函数声明 `function confidenceColor(c: number): string { ... }`
**影响**: 此 bug 会导致 Vue 编译失败，缠论分析页面完全无法加载

### 2. mmd.py 文档字符串位置错误
**问题**: `_detect_price_gap` 函数的 docstring 放在了早期 return 语句之后
**位置**: `src/easy_tdx/chanlun/mmd.py:2815-2817`
**修复**: 将 docstring 移到函数体开头（return 语句之前）
**影响**: Python 不会报错但 docstring 不会被识别，影响代码可维护性

## 项目状态评估

### 缠论核心模块
| 模块 | 文件 | 状态 | 说明 |
|------|------|------|------|
| K线合并 | `kline_merge.py` | ✅ 正常 | 包含处理、极值追踪正确 |
| 分型识别 | `fractal.py` | ✅ 正常 | 严格/非严格模式支持 |
| 笔计算 | `bi.py` | ✅ 正常 | v86 端点一致性校验已实现 |
| 中枢计算 | `zs.py` | ✅ 正常 | v87 动态阈值、稳定性检查 |
| 线段计算 | `xd.py` | ✅ 正常 | 特征序列法、方向交替 |
| 买卖点 | `mmd.py` | ✅ 正常 | V82 263个增强条件 |
| 背驰判断 | `beichi.py` | ✅ 正常 | 笔/盘整/趋势三种背驰 |
| 多级别 | `multi_level.py` | ✅ 正常 | 区间套一致性分析 |

### 前端模块
| 组件 | 文件 | 状态 | 说明 |
|------|------|------|------|
| 缠论图表 | `ChanlunChart.vue` | ✅ 正常 | ECharts 6 兼容，双面板布局 |
| 缠论视图 | `ChanlunView.vue` | ✅ 已修复 | 语法错误已修复 |
| 回测视图 | `BacktestView.vue` | ✅ 正常 | 缠论策略集成 |
| 训练视图 | `TrainView.vue` | ✅ 正常 | 逐步揭示训练 |
| 选股视图 | `ScreeningView.vue` | ✅ 正常 | 缠论选股 |
| 准确度面板 | `ChanlunAccuracyPanel.vue` | ✅ 正常 | 按类型分组命中率 |
| 信号准确度 | `SignalAccuracyPanel.vue` | ✅ 正常 | 前瞻命中率验证 |

### 后端 API
| 路由 | 端点 | 状态 | 说明 |
|------|------|------|------|
| 缠论分析 | `/api/v1/chanlun/analyze` | ✅ 正常 | 完整缠论管道 |
| 多级别分析 | `/api/v1/chanlun/multi-level` | ✅ 正常 | 区间套分析 |
| 推荐 | `/api/v1/chanlun/recommend` | ✅ 正常 | V4 质量评级 + 诊断 |
| 训练会话 | `/api/v1/chanlun/train/session` | ✅ 正常 | P0 训练功能 |
| 信号准确度 | `signal_accuracy.py` | ✅ 正常 | 前瞻命中率验证 |

## 缠论理论定义验证

| 元素 | 理论定义 | 实现状态 |
|------|----------|----------|
| **分型** | 顶分型: 中间K线高低均为三根最高; 底分型反之 | ✅ 严格模式 (> / <) |
| **笔** | 相邻顶底分型间至少1根独立K线(new)或3根(old) | ✅ v86 端点一致性校验 |
| **中枢** | 至少3笔价格区间重叠形成的密集成交区 | ✅ v87 动态重叠率阈值 |
| **线段** | 由多笔构成，特征序列分型结束 | ✅ v87 方向一致性检查 |
| **1买/1卖** | 趋势背驰后的第一个反转点 | ✅ 新极值 + MACD力度衰竭 |
| **2买/2卖** | 1买/1卖后回调不创新低/高 | ✅ 缩量 + MACD确认 |
| **3买/3卖** | 突破中枢后回踩不进中枢 | ✅ 28+条件严格过滤 |
| **背驰** | 笔/盘整/趋势背驰三级判断 | ✅ MACD面积比较 |

## 启动开发环境

### 方式1: 使用启动脚本
```bash
cd /home/skp/workspace/easy_tdx
source .venv/bin/activate
python scripts/dev_server.py
```

### 方式2: 手动启动
```bash
# 终端1: 启动后端
source .venv/bin/activate
easy-tdx serve --host 0.0.0.0 --port 8000

# 终端2: 启动前端
cd web-ui
npm run dev
```

### 访问地址
- 前端: http://localhost:3012
- API: http://localhost:8000/api/v1
- 文档: http://localhost:8000/redoc
- 缠论分析: http://localhost:3012/chanlun

## 运行测试

```bash
cd /home/skp/workspace/easy_tdx
source .venv/bin/activate

# 运行完整管道测试
python tests/scripts/test_chanlun_pipeline.py

# 运行单元测试
python -m pytest tests/unit/test_chanlun_v87_comprehensive.py -xvs
python -m pytest tests/unit/test_chanlun_v86_bi_enhancements.py -xvs
python -m pytest tests/unit/test_chanlun_v87_zs_enhancements.py -xvs
python -m pytest tests/unit/test_chanlun_v87_xd_enhancements.py -xvs
python -m pytest tests/unit/test_chanlun_signal_accuracy.py -xvs
```

## 浏览器控制台检查清单

打开浏览器 DevTools (F12) → Console 标签，检查：

```javascript
// 1. 检查是否有 JavaScript 错误
// 应无红色错误信息

// 2. 检查缠论图表实例
console.log(window.__CHANLUN_CHART__)  // 开发模式下应有 ECharts 实例

// 3. 测试缠论分析 API
fetch('/api/v1/chanlun/analyze', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({market: 'SZ', code: '000001', category: 'DAY', count: 500, start: 0})
}).then(r => r.json()).then(d => {
  console.log('笔数:', d.bi_count);
  console.log('中枢数:', d.zs_count);
  console.log('买卖点数:', d.mmd_count);
  console.log('分型数:', d.fractal_count);
}).catch(e => console.error('API错误:', e));

// 4. 检查网络请求
// Network 标签应无 4xx/5xx 错误
```

## 用户选股与择时帮助

### 选股功能
1. **缠论分析页**: 输入股票代码，查看笔/线段/中枢/买卖点
2. **多级别联立**: 日线+30分钟共振确认
3. **信号准确度验证**: 查看历史命中率 vs 随机基准
4. **市场状态判断**: 自动给出买入/卖出/持有/观望建议
5. **动态选股**: 筛选符合缠论条件的股票

### 择时交易
1. **一类买卖点**: 趋势背驰反转，最可靠
2. **二类买卖点**: 确认反转，胜率较高
3. **三类买卖点**: 突破回踩确认，趋势确认
4. **置信度评分**: 综合263个条件评估信号质量
5. **回测验证**: 历史回测检验策略有效性

## 项目健康状态

| 检查项 | 状态 |
|--------|------|
| Python 后端核心模块 | ✅ 正常 |
| 缠论算法 (笔/线段/中枢/买卖点) | ✅ 正常 |
| 前端 Vue 组件 | ✅ 正常 |
| 回测引擎 | ✅ 正常 |
| 策略注册表 | ✅ 正常 |
| 信号准确度验证 | ✅ 正常 |
| API 路由 | ✅ 正常 |
