# EasyTDX 项目更新总结 (2026-08-22 V19)

## 本次会话完成的工作

### 1. 状态检查

- **上一会话(V18)状态**: ✅ 已完成，1116 测试通过
- **本次工作**: V19 缠论模型增强 - ATR支撑确认 + 信号新鲜度衰减

### 2. V19 增强功能

#### 条件29：ATR支撑确认

**新增函数：**
- `_calc_atr()` - 计算指定位置的ATR值（简化TR计算）
- `_check_atr_support_zone()` - 检查回踩/反抽是否在ATR支撑区域内

**逻辑：**
- 3买：回踩低点应在 `zg - 1.0×ATR ~ zg + 0.3×ATR` 范围内
- 3卖：反弹高点应在 `zd - 0.3×ATR ~ zd + 1.0×ATR` 范围内
- 超出范围则跳过信号（避免假突破）

#### 条件30：信号新鲜度衰减

**新增函数：**
- `_calc_signal_freshness()` - 计算信号衰减因子

**逻辑：**
- 信号年龄 ≤ 15根K线：无衰减（因子=1.0）
- 信号年龄 > 15根K线：每超出5根衰减10%，最低0.5
- 在 `_calc_confidence()` 中乘以衰减因子

#### 质量评分增强

**新增维度：**
- 突破力度加成（10分）：突破笔MACD面积 / 进入中枢笔MACD面积
- 信号新鲜度加成（5分）：基于衰减因子的分数

#### 置信度校准

| 类型 | V18 | V19 | 变化 |
|------|-----|-----|------|
| 3买 | 0.62 | 0.65 | +0.03 |
| 3卖 | 0.57 | 0.60 | +0.03 |

### 3. 测试验证

**V19 专项测试（8个新用例）：**
```
test_calc_atr_basic: ✅ PASS
test_check_atr_support_zone_3buy: ✅ PASS
test_check_atr_support_zone_3sell: ✅ PASS
test_calc_signal_freshness_current: ✅ PASS
test_calc_signal_freshness_aged: ✅ PASS
test_calc_breakout_force_ratio: ✅ PASS
test_v19_base_confidence_values: ✅ PASS
test_v19_all_types_still_valid: ✅ PASS
```

**全量单元测试：**
```
1125 passed, 2 warnings in 57.05s
- chanlun 核心: 通过
- 增强测试: 105 passed（含 V10-V19 各版本）
- 诊断路由: 通过
- 集成测试: 2 skipped（网络依赖）
```

**更新测试断言（V17/V18）：**
- `test_v17_confidence_calibration_3buy`: 0.58-0.65 → 0.63-0.70
- `test_v17_confidence_calibration_3sell`: 0.53-0.60 → 0.58-0.65
- `test_v18_base_confidence_values`: 更新为V19预期范围

### 4. 文件变更

| 文件 | 修改内容 |
|------|----------|
| `src/easy_tdx/chanlun/mmd.py` | 新增4个V19函数 + 条件29/30集成 + 置信度调整 + 质量评分增强 |
| `tests/unit/test_chanlun_enhancements.py` | 新增8个V19测试 + 更新V17/V18断言 |
| `pyproject.toml` | 版本 1.20.9 → 1.21.0 |
| `CHANGELOG_V19.md` | 本次更新日志 |

### 5. 预期效果

| 指标 | V18（修复前） | V19（预期） |
|------|-------------|------------|
| 1买准确率 | ~85%+ | ~85%+ |
| 1卖准确率 | ~90%+ | ~90%+ |
| 2买准确率 | ~75%+ | ~75%+ |
| 2卖准确率 | ~70%+ | ~70%+ |
| **3买准确率** | **~62%** | **~68%+** |
| **3卖准确率** | **~55%** | **~63%+** |

---

**版本**: V19.0
**完成日期**: 2026-08-22
**测试状态**: ✅ 1125 passed, 2 warnings
**构建状态**: ✅ 无错误
