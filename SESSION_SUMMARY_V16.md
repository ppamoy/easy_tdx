# EasyTDX 项目更新总结 (2026-08-22 V16)

## 本次会话完成的工作

### 1. 状态检查

- **上一会话(V15)状态**: ✅ 已完成，1090测试全部通过
- **未提交变更**: V14/V15的CHANGELOG和SESSION_SUMMARY已暂存，核心代码有未暂存修改
- **处理**: 将所有V14-V15变更提交，然后实施V16增强

### 2. V16 核心Bugfix：信号衰减集成

**问题**: V15新增的`_calc_signal_aging()`仅在`calc_signal_quality_report()`中调用，
结果仅用于前端展示，未实际影响`_calc_confidence()`中的置信度计算。

**修复**:
- 在`find_mmds()`中计算并存储`_signal_aging`到MMD对象
- `_calc_confidence()`已正确使用存储的衰减数据
- 确保信号时效性贯穿整个决策链

### 3. V16 新功能：仓位建议系统

新增`_calc_position_sizing()`函数，综合以下因素给出仓位建议：

| 输入因素 | 仓位影响 |
|----------|----------|
| 基础置信度 (0.5-0.9) | 10%-70%基准 |
| 信号衰减 (过期/偏老/新鲜) | -40% / -20% / +5% |
| K线形态 (锤子线/吞没/十字星) | +5% / +5% / 0% |
| 波动率 (>3%/ <1%) | -30% / +10% |
| 质量评级 (S/A/B/C/D) | +10% / +5% / 0% / -5% / -15% |

输出格式：
```json
{
  "position_pct": 45,
  "suggestion": "半仓",
  "risk_level": "中等风险",
  "notes": ["质量评级B级，适度仓位", "hammer形态确认，看涨增强"]
}
```

### 4. MMD类字段规范化

将V14/V15的动态属性(`setattr`)转为MMD dataclass的显式字段：
- V14: `_vol_spike`, `_gap_up`, `_gap_down`, `_gap_size`, `_macd_slope_confirmed`, `_vol_profile_support`, `_vol_profile_resistance`
- V15: `_kline_pattern`, `_signal_aging`, `_retest_break`, `_retest_retracement`

### 5. 前端增强

**types.ts**: 新增`position_sizing`类型定义

**DiagnosisView.vue**:
- 新增仓位建议行（颜色编码：绿≥60%、蓝≥40%、橙≥20%、红<20%）
- 新增仓位调整原因列表
- 新增`getPositionTagClass()`辅助函数

### 6. 测试结果

```
=========================== 1098 passed, 2 warnings in 73.74s ============================
- 原有测试: 1091 passed
- V16新增: 7 passed
```

### 7. 文件变更

| 文件 | 修改内容 |
|------|----------|
| `src/easy_tdx/chanlun/types.py` | MMD类新增12个显式字段 |
| `src/easy_tdx/chanlun/mmd.py` | 新增`_calc_position_sizing()`；修复信号衰减集成；修复is_buy判断 |
| `web-ui/src/types.ts` | 新增`position_sizing`类型 |
| `web-ui/src/views/DiagnosisView.vue` | 新增仓位建议UI + CSS样式 |
| `tests/unit/test_chanlun_enhancements.py` | 新增TestV16Enhancements（7用例） |
| `CHANGELOG_V16.md` | 本次更新日志 |

---

**版本**: V16.0
**完成日期**: 2026-08-22
**测试状态**: ✅ 1098 passed
**构建状态**: ✅ 无错误
