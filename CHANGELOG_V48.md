# EasyTDX 项目更新日志 V48

## 更新时间
2026-08-24

## 本次更新内容

### 背景：修正不实准确率声明，增强决策辅助能力

V47/V47.1 完成了后确认价格跟随、信号有效性窗口、置信度动态校准等核心功能。
本次更新重点：
1. **修正不实的准确率声明** - 移除无回测数据支撑的"80-90%"、"60-70%"等准确率表述
2. **新增条件134-136** - 量价背离二次确认、趋势强度加权、动态风险收益比
3. **完善诊断API和Web UI** - 新增3个V48诊断卡片

### 条件134: 量价背离二次确认（Volume-Price Divergence Secondary Confirmation）

使用VWAP（成交量加权平均价格）作为二次确认指标：
- 计算信号后最近20根K线的VWAP偏离度
- 3买：价格应在VWAP之上（多头排列）→ +3%置信度
- 3买：价格低于VWAP 2%以上 → -4%置信度（可能假突破）
- 3卖：价格应在VWAP之下（空头排列）→ +3%置信度
- 3卖：价格高于VWAP 2%以上 → -4%置信度

**决策帮助**：帮助投资者识别"价格创新高但动能不足"的假突破信号

### 条件135: 趋势强度加权（Trend Strength Weighting）

基于ADX和MA斜率对置信度进行趋势加权调整：
- ADX > 25（强趋势）+ 方向一致 → +4%置信度
- ADX 20-25（中趋势）+ 方向一致 → +2%置信度
- ADX < 20（弱趋势）→ -2%置信度
- 趋势方向与信号方向冲突时扣分

**决策帮助**：帮助投资者在趋势明确时更自信，在震荡市中小心

### 条件136: 动态风险收益比（Dynamic Risk-Reward Ratio）

基于ATR动态计算止损止盈位，提供风险收益比评估：
- 止损位：入场价 ± 2×ATR
- 止盈位：基于中枢高度或ATR倍数
- S级：风险收益比 ≥ 2.5 → +4%置信度
- A级：风险收益比 ≥ 2.0 → +3%置信度
- B级：风险收益比 ≥ 1.5 → +1%置信度
- C级：风险收益比 < 1.5 → -3%置信度

**决策帮助**：直接告诉投资者"这个信号的止损位是X，止盈位是Y，风险收益比是Z:1"

## MMD 类型字段新增

```python
# types.py 新增字段
_volume_price_divergence_secondary_v48: dict[str, Any] | None  # 条件134
_trend_strength_weighting: dict[str, Any] | None  # 条件135
_dynamic_risk_reward_ratio: dict[str, Any] | None  # 条件136
```

## 诊断 API 新增字段

```json
{
  "volume_price_divergence_secondary_v48": {
    "confirmed": true/false,
    "divergence_pct": 1.5,
    "confidence_adjust": 0.03,
    "msg": "量价背离二次确认通过：当前价VWAP偏离+1.5%（多头）"
  },
  "trend_strength_weighting": {
    "adx_value": 28.5,
    "adx_level": "strong",
    "ma_alignment": "up",
    "confidence_adjust": 0.04,
    "msg": "趋势强度加权：ADX=28.5强趋势+方向一致"
  },
  "dynamic_risk_reward_ratio": {
    "entry_price": 52.10,
    "stop_loss": 49.80,
    "take_profit_1": 56.50,
    "risk_reward_ratio": 1.92,
    "quality_tier": "B",
    "atr": 1.15,
    "confidence_adjust": 0.01,
    "msg": "合格信号：风险收益比1.9（B级），止损49.80→止盈56.50"
  }
}
```

## Web UI 新增卡片

1. **📊 量价背离二次确认（V48·条件134）**
   - 显示确认状态、VWAP偏离度、置信度调整
   - 绿色=通过，黄色=未确认

2. **📈 趋势强度加权（V48·条件135）**
   - 显示ADX值、趋势强度等级、MA对齐方向
   - 绿色=强趋势+方向一致，黄色=弱趋势

3. **💰 动态风险收益比（V48·条件136）**
   - 显示建议入场价、止损位、第一止盈
   - 显示风险收益比和质量等级（S/A/B/C）
   - 直接告诉投资者"买在这里，止损在那里，止盈目标是多少"

## 测试结果

```
======================== 563 passed, 1 warning in 4.42s ========================
V48 专项测试: 10 passed
缠论核心测试: 全部通过
诊断API测试: 全部通过
```

## 文件变更

| 文件 | 修改内容 |
|------|----------|
| `src/easy_tdx/chanlun/mmd.py` | 新增条件134-136函数，修正docstring准确率声明 |
| `src/easy_tdx/chanlun/types.py` | 新增3个V48字段定义 |
| `src/easy_tdx/web/routers/diagnosis.py` | 新增V48字段到诊断API响应 |
| `web-ui/src/types.ts` | 新增V48 TypeScript类型定义 |
| `web-ui/src/views/DiagnosisView.vue` | 新增V48诊断卡片展示 |
| `tests/unit/test_chanlun_v48.py` | 新增V48专项测试（10个） |
| `pyproject.toml` | 版本号 1.40.0 → 1.41.0 |

## V47→V48 核心改进对比

| 维度 | V47 | V48 | 变化 |
|------|-----|-----|------|
| 条件总数 | 133 | 136 | +3 |
| 不实准确率声明 | ❌ 有 | ✅ 已修正 | 移除 |
| 量价背离二次确认(134) | ❌ 无 | ✅ 有 | 新增 |
| 趋势强度加权(135) | ❌ 无 | ✅ 有 | 新增 |
| 动态风险收益比(136) | ❌ 无 | ✅ 有 | 新增 |
| 诊断API字段 | 133个 | 136个 | +3 |
| Web UI卡片 | 2个(V47) | 5个(V47+V48) | +3 |
| 版本号 | 1.40.0 | 1.41.0 | +1 |
| 测试通过数 | 553 | 563 | +10 |

---
**版本**: V48
**完成日期**: 2026-08-24
**测试状态**: ✅ 563 passed（核心测试），10 passed（V48 专项）
**Git 状态**: 待提交
