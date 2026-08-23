# EasyTDX 项目更新日志 V38

## 更新时间
2026-08-23

## 本次更新内容

### 条件95：中枢结构完整性评分（ZS Structure Integrity）
**新增函数：**
- `_calc_zs_structure_integrity(mmd, zss)`

**检测逻辑：**
- 评估与当前买卖点相关的最近中枢的结构完整性
- 笔数评分：≥3笔=满分，2笔=0.7，1笔=0.4
- 完成状态加分：已完成的中枢额外+0.1
- 区间宽度评分：中枢范围占价格比例越大越清晰
- 综合评分 = 笔数分×0.5 + 完成加分 + 区间分×0.4
- 完整度高（>0.7）→ +2%；低（<0.4）→ -3%

**MMD新增字段：**
- `_zs_structure_integrity`: 中枢完整性字典

### 条件96：买卖点位置评分（MMD Position Score）
**新增函数：**
- `_calc_mmd_position_score(mmd, closes, lookback=20)`

**检测逻辑：**
- 计算当前价格在20日高低点区间中的相对位置
- 买入信号：位置<20%（底部）→ +2%；位置>80%（顶部）→ -3%
- 卖出信号：位置>80%（顶部）→ +2%；位置<20%（底部）→ -3%
- 输出位置标签：near_bottom / near_mid / near_top

**MMD新增字段：**
- `_mmd_position_score`: 位置评分字典

### 条件97：信号后收益跟踪（Post-Signal Return）
**新增函数：**
- `_calc_post_signal_return(mmd, closes, lookback=60)`

**检测逻辑：**
- 回溯历史中类似信号（局部极值点）形成后的实际收益
- 统计信号后10日和20日的平均收益
- 收益好（>3%）→ +2%；收益差（<-2%）→ -3%；不足 → 无调整
- 为决策提供历史命中率参考

**MMD新增字段：**
- `_post_signal_return`: 收益跟踪字典

### 条件98：中枢突破力度评估（Breakout Strength）
**新增函数：**
- `_calc_breakout_strength(mmd, closes, volumes)`

**检测逻辑：**
- 价格偏离度 = (当前价 - 20日均价) / 均价
- 成交量确认 = 最新成交量 / 20日均量 > 1.5
- OBV趋势：比较近10日OBV变化判断能量潮方向
- 突破强度 = min(1.0, |价格偏离|×5 + 量能确认加分)
- 强突破（>0.6且放量）→ +3%；弱突破（<0.3且无量）→ -2%

**MMD新增字段：**
- `_breakout_strength`: 突破力度字典

### 条件99：多指标偏离度综合评分（Composite Deviation）
**新增函数：**
- `_calc_composite_deviation(closes, volumes, macd_data)`

**检测逻辑：**
- RSI偏离度 = |RSI - 50| / 50（归一化）
- KDJ偏离度 = |J值 - 50| / 50
- BIAS偏离度 = |BIAS(20)| / 10（归一化）
- 综合偏离 = RSI偏离×0.4 + KDJ偏离×0.3 + BIAS偏离×0.3
- 极端偏离（>0.7）→ 对所有信号-2%
- 全局一次性计算，存储到 find_mmds._last_composite_deviation

### 条件100：信号衰减预警（Signal Decay Warning）
**新增函数：**
- `_calc_signal_decay_warning(mmd, closes, latest_idx)`

**检测逻辑：**
- 买入信号有效期：25根K线；卖出信号有效期：20根K线
- 计算已过K线数、价格漂移百分比、剩余窗口百分比
- fresh（剩余≥70%）→ 无调整
- warning（剩余30-70%）→ -1%
- expired（剩余<30%）→ -5%

**MMD新增字段：**
- `_signal_decay_warning`: 衰减预警字典

## 版本演进

| 版本 | 日期 | 核心改进 |
|------|------|----------|
| V35 | 08-22 | 市场环境过滤+信号衰减+假信号过滤+动态SL/TP+板块轮动+多维背离 |
| V36 | 08-23 | 执行窗口+多TF一致性+风险收益+紧急度+市场综合+策略推荐 |
| V37 | 08-23 | 连续确认+动能加速度+波动率转换+时序关联+多TF动量+质量排名 |
| **V38** | **08-23** | **中枢完整性+位置评分+收益跟踪+突破力度+偏离度+衰减预警** |

## 测试结果

```
======================== 416 passed, 1 warning in 4.93s ========================
V38专项测试: 14 passed
V37专项测试: 22 passed
V36专项测试: 16 passed
缠论核心测试: 33 passed
诊断API测试: 4 passed
Web API测试: 27 passed
```

**V38 专项测试：**
```
TestV38ZSStructureIntegrity:             3 passed
TestV38PositionScore:                    3 passed
TestV38BreakoutStrength:                 2 passed
TestV38CompositeDeviation:               2 passed
TestV38SignalDecay:                      2 passed
TestV38Integration:                      3 passed
```

## 文件变更

| 文件 | 修改内容 |
|------|----------|
| `src/easy_tdx/chanlun/mmd.py` | 新增6个V38函数 + find_mmds集成（条件95-100） |
| `src/easy_tdx/chanlun/types.py` | MMD类新增6个V38字段 |
| `src/easy_tdx/web/routers/diagnosis.py` | 暴露V38 6个字段到API |
| `web-ui/src/types.ts` | 新增V38 TypeScript接口 |
| `web-ui/src/views/DiagnosisView.vue` | 新增5个V38展示卡片 + CSS |
| `tests/unit/test_chanlun_enhancements.py` | 新增14个V38测试用例 |
| `CHANGELOG_V38.md` | 本次更新日志 |

## V38 vs V37 效果预期

| 指标 | V37 | V38 | 变化 |
|------|-----|-----|------|
| 条件总数 | 94 | 100 | +6 |
| 中枢结构评估 | 无 | 结构完整性评分 | 新增 |
| 买卖点位置感知 | 无 | 区间位置评分 | 新增 |
| 历史收益参考 | 无 | 信号后收益跟踪 | 新增 |
| 突破质量评估 | 无 | 突破力度+量能确认 | 新增 |
| 极端偏离预警 | 无 | 多指标综合偏离 | 新增 |
| 信号时效管理 | V15基础衰减 | 衰减阶段预警(fresh/warning/expired) | 增强 |

## 核心设计理念

V38的核心改进思路是"**从结构到动态的全面评估**"：

1. **中枢结构完整性**：缠论的核心是中枢，中枢的质量直接决定买卖点的可靠性。V38通过笔数、完成状态、区间宽度三个维度量化中枢完整性。

2. **买卖点位置评分**：同样是一个1买信号，在区间底部出现比在区间顶部出现更可靠。V38通过20日价格区间定位，量化信号的位置优势。

3. **历史收益跟踪**：抽象的置信度不如直观的历史表现。V38回溯历史类似信号的收益表现，让用户知道"这类信号过去赚钱了吗"。

4. **突破力度评估**：突破是缠论三买的核心。V38通过价格偏离+成交量+OBV三维评估突破质量，区分真突破和假突破。

5. **多指标偏离度**：当RSI、KDJ、BIAS同时极端偏离时，市场可能处于短线极值状态，此时任何买卖信号都需谨慎。V38通过综合偏离度提供全局风险预警。

6. **信号衰减预警**：信号不是永久的。V38通过时间衰减模型，明确标注信号是"新鲜"、"衰减中"还是"已过期"，辅助用户判断行动紧迫性。

---

**版本**: V38.0
**完成日期**: 2026-08-23
**测试状态**: ✅ 416 passed（缠论专项），4 passed（诊断API），27 passed（Web API），0 failures
**构建状态**: ✅ Web UI 更新完成
