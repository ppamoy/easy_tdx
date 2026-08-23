# EasyTDX 项目更新日志 V47.1

## 更新时间
2026-08-24

## 本次更新内容

### 背景：V47 核心函数已实现，但字段未集成到数据模型和 API

V47 的核心函数（`_check_post_signal_price_follow_through`, `_calc_signal_validity_window`, `_calc_confidence_v47`）已在之前版本实现，但字段未添加到 MMD 类型、诊断 API 和 Web UI。

### 集成 V47 字段到数据模型

**新增 MMD 字段（types.py）：**
- `_post_signal_price_follow_through`: 后确认价格跟随过滤结果（条件131）
- `_signal_validity_window`: 信号有效性窗口结果（条件132）
- `_confidence_v47_calibrated`: V47 校准后的置信度（条件133）

### 集成 V47 计算到 find_mmds

**在 mmd.py 中新增 V47 字段赋值：**
- 条件 131: 对 3 买/3 卖信号执行后确认价格跟随检查
- 条件 132: 对 3 买/3 卖信号计算信号有效性窗口
- 条件 133: 对 3 买/3 卖信号存储校准后的置信度

### 更新诊断 API

**在 diagnosis.py 中新增 V47 字段返回：**
```python
"post_signal_price_follow_through": ...,
"signal_validity_window": ...,
"confidence_v47_calibrated": ...,
```

### 更新 TypeScript 类型

**在 types.ts 中新增 V47 接口定义：**
- `post_signal_price_follow_through`: 后确认价格跟随过滤结果
- `signal_validity_window`: 信号有效性窗口结果
- `confidence_v47_calibrated`: 校准后的置信度

### 更新 Web UI

**在 DiagnosisView.vue 中新增 V47 诊断卡片：**
- ✅ 后确认价格跟随卡片（条件 131）
- ⏱️ 信号有效性窗口卡片（条件 132）

## 测试结果

```
============================= 582 passed, 1 warning in 4.74s ==============================
V47 专项测试: 13 passed
缠论核心测试: 全部通过
回测策略测试: 全部通过
```

## 文件变更

| 文件 | 修改内容 |
|------|----------|
| `src/easy_tdx/chanlun/types.py` | 新增 3 个 V47 字段定义 |
| `src/easy_tdx/chanlun/mmd.py` | 新增 V47 条件 131-133 字段赋值逻辑 |
| `src/easy_tdx/web/routers/diagnosis.py` | 新增 V47 字段到诊断 API 响应 |
| `web-ui/src/types.ts` | 新增 V47 TypeScript 类型定义 |
| `web-ui/src/views/DiagnosisView.vue` | 新增 V47 诊断卡片展示 |

## V47 完整功能清单

| 维度 | 状态 |
|------|------|
| 条件 131: 后确认价格跟随过滤 | ✅ 已集成 |
| 条件 132: 信号有效性窗口 | ✅ 已集成 |
| 条件 133: 置信度动态校准 | ✅ 已集成 |
| MMD 字段定义 | ✅ 已完成 |
| 诊断 API 返回 | ✅ 已完成 |
| TypeScript 类型 | ✅ 已完成 |
| Web UI 展示 | ✅ 已完成 |
| 单元测试 | ✅ 13 passed |

---
**版本**: V47.1
**完成日期**: 2026-08-24
**测试状态**: ✅ 582 passed（核心测试），13 passed（V47 专项）
**Git 状态**: 已提交
