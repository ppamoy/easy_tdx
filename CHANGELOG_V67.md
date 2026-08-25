# EasyTDX 项目更新日志 V67

## 更新时间
2026-08-28

## 背景：V67 前端集成完成
V66 完成了条件196-199的完整后端集成，V67 条件200-203 后端代码及测试已就绪，本次会话补齐前端缺失部分：TypeScript 类型定义 + Vue 组件 UI 卡片 + 多股对比表格列 + CSS 样式 + 测试，并完成构建部署。同时修复了 V66 前端卡片在后续变更中意外丢失的问题。

---

## V67 前端集成内容

### `web-ui/src/types.ts`
- 新增 `zhongshu_divergence_strength_v67` 接口（条件200）
- 新增 `multi_level_mmd_consistency_v67` 接口（条件201）
- 新增 `post_signal_trajectory_health_v67` 接口（条件202）
- 新增 `dynamic_sl_tp_recommendation_v67` 接口（条件203）

### `web-ui/src/views/DiagnosisView.vue`
- 单股诊断模式新增 V67 四个条件卡片展示：
  - 🎯 中枢背驰力度量化（条件200）
  - 🔗 多级别买卖点一致性（条件201）
  - 📊 信号后价格轨迹健康度（条件202）
  - 🛡️ 动态止损止盈推荐（条件203）
- 多股票对比表格新增 V67 条件命中列（v67_cond200-203）
- 条件命中详情区块标题更新为 V58-V67
- 新增 V67 CSS 样式类
- **修复**：恢复 V66 四个条件卡片（此前意外丢失）

### `web-ui/vite.config.ts`
- 新增生产部署域名白名单：easy.ppamoy.fun, api.ppamoy.fun, ppamoy.fun

---

## 测试结果

```
tests/unit/test_chanlun_v64_backtest.py:     55 passed（含9个V67测试）
tests/unit/test_web_api.py:                  27 passed
tests/unit/test_chanlun_v63.py:              23 passed
tests/unit/test_diagnosis_router.py:          4 passed
合计: 109 passed
```

---

## 文件变更

| 文件 | 修改内容 |
|------|----------|
| `web-ui/src/types.ts` | **新增** V67 四个 TypeScript 接口（+35行） |
| `web-ui/src/views/DiagnosisView.vue` | **新增** V67 UI卡片（+70行）+ 多股表格列（+4行）+ CSS（+4行）+ 恢复V66卡片 |
| `web-ui/vite.config.ts` | **新增** 生产域名白名单（+1行） |
| `src/easy_tdx/chanlun/mmd.py` | **已有** V67 四个计算函数（397行，上轮提交） |
| `src/easy_tdx/chanlun/types.py` | **已有** V67 四个 MMD 字段（+6行，上轮提交） |
| `src/easy_tdx/backtest/chanlun_validator.py` | **已有** V67 ConditionGroup（+4行，上轮提交） |
| `src/easy_tdx/web/routers/diagnosis.py` | **已有** V67 API 字段返回（+17行，上轮提交） |
| `tests/unit/test_chanlun_v64_backtest.py` | **新增** V67 测试类（+100行，上轮提交） |
| `pyproject.toml` | 版本更新至 1.59.0 |
| `src/easy_tdx/web/dist/` | **构建产物** 已更新 |

---

## V66→V67 核心改进对比

| 维度 | V66 | V67 | 变化 |
|------|-----|-----|------|
| 条件总数 | 199 | 203 | +4 |
| 前端覆盖 | 完整 | 完整 | 修复V66丢失+补齐V67 |
| 专项测试 | 9 | 9 | +9 |
| 版本号 | 1.58.0 | 1.59.0 | +1 |

---

## V67 条件说明

### 条件200：中枢背驰力度量化（Zhongshu Divergence Strength Quantification）
- 针对第三类买卖点，量化中枢区域的背驰强度
- 对比突破前最后一笔与突破后第一笔的MACD面积
- 面积比越小（背驰越明显），置信度调整越大
- 结合成交量变化辅助判断
- 置信度调整：+2%~+5%（背驰）/-1%（无背驰）

### 条件201：多级别买卖点一致性验证（Multi-level MMD Consistency）
- 短期（5日MA）、中期（20日MA）、长期（60日MA）三周期趋势方向
- 判断当前买卖点是否与各时间框架方向一致
- 一致度高则增强信心，分歧则降低信心
- 置信度调整：+4%（高一致）/+2%（中一致）/-3%（低一致）

### 条件202：信号后价格轨迹健康度（Post-signal Price Trajectory Health）
- 评估买卖点信号后的价格走势质量
- 统计上涨/下跌K线数量、最大回撤比例
- 趋势质量分四级：excellent/good/fair/poor
- 置信度调整：+6%（优秀）/+3%（良好）/-4%（较差）

### 条件203：动态止损止盈推荐（Dynamic SL/TP Recommendation）
- 基于ATR（14日）动态计算止损止盈位
- 止损：当前价 ± 2×ATR；止盈：当前价 ± 4×ATR
- 风险收益比评估（目标≥2:1）
- 根据风险收益比推荐仓位比例（10%~30%）
- 置信度调整：+3%（rr≥3）/+2%（rr≥2）/-2%（rr<1.5）

---

**版本**: V67
**完成日期**: 2026-08-28
**测试状态**: ✅ 109 passed（整体）
**构建状态**: ✅ web-ui 已构建并部署
