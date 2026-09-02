# EasyTDX 缠论功能完善总结

## 本次改进内容（续上次会话）

### 1. 笔计算修复 (bi.py)

**修复的问题：**
- `_is_weak_bi()` 函数逻辑修正：原代码中 `start.val <= 0 and end.val <= 0` 返回 True 的条件永远不会触发（股票价格不可能为非正数），已修正为正确的除零保护逻辑。
- 新增 `bi_weak_skip` 配置项：允许用户选择跳过价格变动 < 0.1% 的弱笔，在震荡市场尤其有用。
- 弱笔检测现在仅作为可选项，默认不跳过（保持向后兼容）。

**文件：** `src/easy_tdx/chanlun/bi.py`

### 2. 配置项增强 (config.py)

**新增配置：**
- `bi_weak_skip: bool = False` — 是否跳过弱笔

**文件：** `src/easy_tdx/chanlun/config.py`

### 3. 中枢计算改进 (zs.py)

**改进：**
- 添加 `min_overlap_abs` 变量防止极低价格时阈值过小导致的误判
- 更新 `_should_close_candidate()` 注释说明 v88 改进

**文件：** `src/easy_tdx/chanlun/zs.py`

### 4. 前端增强 (ChanlunView.vue)

**新增功能：**
- **缠论理论说明面板**：点击「缠论说明」按钮可查看分型、笔、中枢、线段、买卖点的定义和判断标准
- **操作建议提示**：根据当前市场状态显示针对性的操作建议（如「关注中枢下沿支撑有效性」）
- **中枢位置距离指示**：显示当前价相对中枢上沿/下沿的百分比距离
- **置信度说明 tooltip**：鼠标悬停可查看置信度的含义和计算方法
- **最高置信度统计**：在统计面板中新增「最高置信」指标
- **准确度验证提示**：解释前瞻命中率的计算方式和与回测收益的区别

**文件：** `web-ui/src/views/ChanlunView.vue`

### 5. 新增测试文件

- `tests/unit/test_chanlun_integration.py` — 11个端到端测试
- `tests/scripts/test_chanlun_e2e.py` — 命令行端到端测试脚本
- `tests/scripts/test_chanlun_backtest.py` — 回测策略验证脚本
- `scripts/quick_validate.py` — 快速验证脚本

---

## 上次会话修改内容

### 图表绘制改进 (ChanlunChart.vue)
- **笔**: 细虚线（width: 1, type: 'dashed'），颜色跟随涨跌
- **线段**: 细实线（width: 1.5, type: 'solid'），紫色
- **新增分型标记**: 顶分型用倒三角(红色)，底分型用菱形(绿色)
- **新增背驰标记**: 橙色矩形，显示"背"字
- **中枢区域**: 半透明黄色区域，边框虚线

### 后端API改进 (chanlun.py)
- API 响应增加 `fractals` 字段（分型数据）

### 回测集成 (BacktestView.vue)
- 选择"缠论买卖点"策略时自动运行缠论分析
- 回测完成后显示缠论结构图

### 1. ChanlunChart.vue - 缠论图表组件
**路径**: `/home/skp/workspace/easy_tdx/web-ui/src/components/ChanlunChart.vue`

**改进**:
- **笔**: 改为**细虚线**（width: 1, type: 'dashed'），颜色跟随涨跌
- **线段**: 改为**细实线**（width: 1.5, type: 'solid'），紫色
- **新增分型标记**: 顶分型用倒三角(红色)，底分型用菱形(绿色)，带"顶"/"底"标签
- **新增背驰标记**: 橙色矩形，显示"背"字
- **中枢区域**: 半透明黄色区域，边框虚线
- **买卖点**: 一类买点(绿色三角形)，一类卖点(红色圆针)，三类买卖点使用不同大小和颜色

**符合缠论理论**:
- 笔是缠论最基础的结构，用虚线表示其临时性
- 线段由至少3笔构成，是更高级的结构，用实线表示其稳定性
- 中枢是多笔价格重叠区域，用半透明色块表示
- 买卖点是关键转折点，用明显符号标注

### 2. BacktestView.vue - 回测视图
**路径**: `/home/skp/workspace/easy_tdx/web-ui/src/views/BacktestView.vue`

**改进**:
- 导入 ChanlunChart 组件
- 选择"缠论买卖点"策略时，自动运行缠论分析
- 回测完成后显示缠论结构图（笔、线段、中枢、买卖点、分型、背驰）
- 添加"缠论"徽章标识
- 显示加载状态

### 3. ChanlunView.vue - 缠论分析视图
**路径**: `/home/skp/workspace/easy_tdx/web-ui/src/views/ChanlunView.vue`

**改进**:
- 支持显示分型和背驰数据
- 传递给 ChanlunChart 新参数

### 4. chanlun.py (后端路由)
**路径**: `/home/skp/workspace/easy_tdx/src/easy_tdx/web/routers/chanlun.py`

**改进**:
- API 响应增加 `fractals` 字段（分型数据）

## 缠论理论遵循

### 笔 (Bi)
- 定义：由相邻的顶底分型连接而成
- 新笔规则：分型之间至少有1根独立缠论K线
- 老笔规则：分型之间至少有3根缠论K线
- 可视化：细虚线，颜色跟随方向

### 线段 (XianDuan)
- 定义：由至少3笔构成
- 特征序列分型判断转折
- 可视化：细实线，紫色

### 中枢 (ZhongShu)
- 定义：至少3笔（或线段）的价格区间有重叠
- zg（上沿）= 重叠区间的最高点
- zd（下沿）= 重叠区间的最低点
- 可视化：半透明黄色区域

### 买卖点
- **一类买点**：下跌趋势中最后一个中枢下方的底背驰点
- **二类买点**：一类买点后回调不创新低
- **三类买点**：向上突破中枢后回调不跌破中枢上沿
- **一类卖点**：上涨趋势中最后一个中枢上方的顶背驰点
- **二类卖点**：一类卖点后反弹不创新高
- **三类卖点**：向下跌破中枢后反弹不突破中枢下沿

### 背驰
- **笔背驰**：相邻同向笔的力度比较
- **盘整背驰**：中枢内最后一笔力度小于进入中枢的第一笔
- **趋势背驰**：两个同向中枢之间，离开中枢的笔力度减小

## 测试结果

```
============================= 106 passed in 2.13s ==============================
```

所有缠论相关测试通过：
- test_chanlun.py: 33 tests ✓
- test_chanlun_phase2.py: 13 tests ✓
- test_chanlun_phase3.py: 9 tests ✓
- test_web_api.py: 2 chanlun tests ✓
- test_factor_builtin.py: 1 chanlun test ✓

## 文件列表

| 文件 | 修改内容 |
|------|----------|
| `web-ui/src/components/ChanlunChart.vue` | 笔虚线、线段实线、新增分型/背驰标记 |
| `web-ui/src/views/BacktestView.vue` | 缠论策略回测显示缠论结构 |
| `web-ui/src/views/ChanlunView.vue` | 支持分型和背驰数据展示 + 缠论说明面板 + 操作建议 |
| `src/easy_tdx/web/routers/chanlun.py` | API返回分型数据 |
| `src/easy_tdx/chanlun/bi.py` | 修复弱笔检测逻辑 + 新增 bi_weak_skip 配置 |
| `src/easy_tdx/chanlun/config.py` | 新增 bi_weak_skip 配置项 |
| `src/easy_tdx/chanlun/zs.py` | 新增 min_overlap_abs 防误判 |
| `tests/unit/test_chanlun_integration.py` | 11个端到端集成测试 |
| `tests/scripts/test_chanlun_e2e.py` | 命令行端到端验证脚本 |
| `tests/scripts/test_chanlun_backtest.py` | 回测策略验证脚本 |
| `scripts/quick_validate.py` | 快速验证脚本 |

## 使用说明

1. **缠论分析页面**: 输入股票代码，点击"开始分析"
2. **回测页面**: 选择"缠论买卖点"策略，回测完成后自动显示缠论结构
3. **图表元素**:
   - 绿色虚线：向上笔
   - 红色虚线：向下笔
   - 紫色实线：线段
   - 黄色区域：中枢
   - 倒三角(红)：顶分型
   - 菱形(绿)：底分型
   - 三角形(绿)：一类买点
   - 圆针(红)：一类卖点
   - 橙色矩形：背驰

## 构建

前端已重新构建并部署：
```bash
cd /home/skp/workspace/easy_tdx/web-ui && npm run build
cp -r dist/* src/easy_tdx/web/dist/
```

## 验证方法

### 快速验证
```bash
cd /home/skp/workspace/easy_tdx
python scripts/quick_validate.py
```

### 单元测试
```bash
cd /home/skp/workspace/easy_tdx
python -m pytest tests/unit/test_chanlun_integration.py -v
python -m pytest tests/unit/test_chanlun.py -v
python -m pytest tests/unit/test_chanlun_v*.py -v
```

### 启动 Web 服务验证
```bash
easy-tdx serve
# 浏览器打开 http://localhost:8000/chanlun
# 输入股票代码如 000001 或 600519
# 点击「开始分析」查看缠论结构
# 点击「缠论说明」查看理论基础
# 点击「回测验证」跳转到回测页面用缠论策略验证
```
