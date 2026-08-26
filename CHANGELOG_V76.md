# 更新日志 V76

## [V76] — 2026-08-26

**缠论模型精准度再提升 - 条件236-239集成（价格结构完整性+趋势方向对齐+波动率自适应置信度+买卖点最终有效性）**

### 新增

- **`_calc_price_structure_integrity_v76`**（`src/easy_tdx/chanlun/mmd.py`）—— 价格结构完整性验证（条件236）。检测价格在趋势中的位置（底部积累/中期反弹/突破尝试/过度延伸/顶部派发等），评估关键价位有效性，返回 `structure_score`, `trend_structure`, `key_levels_valid`, `confirm_signal`, `confidence_adjust`, `msg`。

- **`_calc_trend_alignment_validation_v76`**（`src/easy_tdx/chanlun/mmd.py`）—— 趋势方向对齐验证（条件237）。分析多周期均线（MA5/MA10/MA20/MA60）趋势方向，判断整体趋势是否与买卖点方向一致，返回 `alignment_status`, `trend_direction`, `ma_alignment`, `confirm_signal`, `confidence_adjust`, `msg`。

- **`_calc_volatility_adaptive_confidence_v76`**（`src/easy_tdx/chanlun/mmd.py`）—— 波动率自适应置信度（条件238）。基于ATR计算当前波动率等级（低/正常/高/极端），动态调整置信度，高风险环境下降低置信度，返回 `vol_level`, `atr_ratio`, `adaptive_confidence`, `confirm_signal`, `confidence_adjust`, `msg`。

- **`_calc_signal_final_validity_v76`**（`src/easy_tdx/chanlun/mmd.py`）—— 买卖点最终有效性评分（条件239）。综合V75/V76所有条件调整后的最终有效性评分，输出强/中/弱/无效四级判定及操作建议，返回 `final_validity`, `validity_score`, `recommendation`, `confirm_signal`, `msg`。

### 后端集成

- **`find_mmds_v76`** 别名新增（`src/easy_tdx/chanlun/mmd.py`）—— 与 `find_mmds_v44` 等效，完整集成条件101-239
- **诊断API增强**（`src/easy_tdx/web/routers/diagnosis.py`）：
  - 顶层新增 `v76_summary` 字段：`{structure_integrity, validity_score, recommendation}`
  - 操作建议阈值引入 V76 有效性修正：无效信号-15分、弱信号-8分、强信号+5分
  - 原因描述中加入 V76 有效性提示

### 前端集成

- **`web-ui/src/types.ts`**：`DiagnosisResult` 新增 `v76_summary` 可选字段
- **`web-ui/src/views/DiagnosisView.vue`**：
  - Hero区域新增 V76有效性标签行（带颜色编码：绿/蓝/橙/红）
  - V76四维验证卡片（条件236-239）完整渲染
  - 新增CSS样式 `.v76-summary-row`, `.v76-tag` 及四级颜色变体

### 测试

- **`tests/unit/test_chanlun_v76.py`**（21 个测试用例）：
  - `TestV76ConditionGroup`：枚举存在性、条件范围(236-239)、描述文案
  - `TestV76MMDFields`：MMD对象包含4个V76字段
  - `TestV76BacktestValidator`：单组/多组合验证、summary输出
  - `TestV76Functions`：结构完整性（买入/卖出/数据不足/量能确认）、趋势对齐（多头/空头/数据不足/MA格式）、波动率自适应（低/高/数据不足）、最终有效性（无调整/有调整/低分）
  - 综合冒烟测试：所有V76函数无异常

### 测试结果

- V75+V76联合测试：**165 passed**
- TypeScript编译：**零错误**
- Web UI构建：**built in 6.55s**

---

## 核心功能清单（更新后）

### 缠论买卖点增强（V58-V76）
| 版本 | 条件范围 | 核心能力 |
|------|----------|----------|
| V58-V59 | 172-179 | 多TF趋势+量能验证+ATR止损+自适应参数 |
| V60 | 180-183 | RSI背离+MA间距+中枢距离+KDJ确认 |
| V61 | 184-185 | MACD背离融合+综合评分 |
| V62 | 186-189 | BOLL带宽确认+动态阈值 |
| V63 | 190-191 | 中枢权重优化+多周期衰减 |
| V65 | 192-195 | 量价背离+回踩确认+波动率压缩+新鲜度 |
| V66 | 196-199 | MACD加速+量价配合+多TF共振+执行优先级 |
| V67 | 200-203 | 中枢背驰量化+多级别一致性+轨迹健康+动态止损 |
| V68 | 204-207 | 缺口趋势+区间套+资金流向+市场风格 |
| V69 | 208-211 | 量价背离二次确认+结构完整性+多指标背离+回踩深度 |
| V70 | 212-215 | 量峰检测+时间衰减+假突破过滤+置信度校准 |
| V71 | 216-219 | 均线排列强度+多周期均线共振+历史胜率+动态风险收益 |
| V72 | 220-223 | 均线收敛发散+支撑阻力距离+量价结构质量+信号衰减速度 |
| V73 | 224-227 | 买卖点位置风险+中枢突破验证+多指标一致性+波动率适配 |
| V74 | 228-231 | 量价背离二次确认+趋势动能持续+中枢重叠度+信号共振深度 |
| V75 | 232-235 | 回调深度验证+中枢回踩确认+量峰持续评分+多信号时间一致性 |
| **V76** | **236-239** | **价格结构完整性+趋势方向对齐+波动率自适应置信度+最终有效性** |

### 诊断系统
| 功能 | 状态 |
|------|------|
| MACD/KDJ/RSI/BOLL/均线/成交量/ATR分析 | ✅ |
| 综合评分+仓位建议+止损止盈 | ✅ |
| V67-V76 缠论条件卡片（共 40 张） | ✅ |
| V76 四维验证摘要（Hero区域） | ✅ |
