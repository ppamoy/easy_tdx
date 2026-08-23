# EasyTDX 项目更新日志 V43

## 更新时间
2026-08-23

## 本次更新内容

### 背景：V42 API 未暴露问题修复
V42 的5个新条件（条件116-120）已在 mmd.py 中计算并影响置信度，但未在诊断 API 中返回，也未在前端 TypeScript 类型中定义。用户无法通过 API 获取这些关键信号验证数据。

### 修复1：诊断 API 暴露 V42 字段（条件116-120）
**文件：** `src/easy_tdx/web/routers/diagnosis.py`

在快速诊断 API 响应中新增以下 V42 字段：
- `post_signal_confirmation`：后确认验证结果（confirmed, bars_confirmed, direction_match, confidence_adjust）
- `break_pullback_volume_ratio`：突破-回调量比验证结果（break_vol_ratio, pullback_vol_ratio, volume_ratio_ok, confidence_adjust）
- `zhongshu_distance_validation`：中枢距离验证结果（distance_pct, distance_valid, confidence_adjust）
- `adx_trend_strength`：ADX趋势强度确认结果（adx_value, adx_level, trend_valid, confidence_adjust）
- `signal_freshness`：信号时效性衰减增强结果（bars_since_signal, decay_factor, effective_age, is_expired, confidence_adjust）

### 修复2：TypeScript 类型定义补全
**文件：** `web-ui/src/types.ts`

为 `DiagnosisResult` 接口新增 V42 五个字段的 TypeScript 类型定义，确保前端可正确访问 V42 数据。

### 修复3：版本函数别名 find_mmds_v42
**文件：** `src/easy_tdx/chanlun/mmd.py`

新增 `find_mmds_v42()` 函数，明确标识 V42 版本（集成条件101-120，共120个条件）。
同时更新 `ChanlunAnalyser` 使用 `find_mmds_v42` 作为默认版本。

### 修复4：版本号更新
**文件：** `pyproject.toml`
- 版本从 `1.35.0` 更新至 `1.36.0`

## 测试结果

```
======================== 509 passed, 1 warning in 3.84s ========================
V42专项测试: 13 passed
V41专项测试: 16 passed
V40专项测试: 21 passed
缠论核心测试: 55 passed
诊断路由测试: 4 passed
```

## 文件变更

| 文件 | 修改内容 |
|------|----------|
| `src/easy_tdx/web/routers/diagnosis.py` | 新增 V42 5个字段到诊断 API 响应 |
| `web-ui/src/types.ts` | 新增 V42 TypeScript 接口定义 |
| `src/easy_tdx/chanlun/mmd.py` | 新增 find_mmds_v42 函数 + 更新 find_mmds_v41 docstring |
| `src/easy_tdx/chanlun/analyser.py` | 切换至 find_mmds_v42 |
| `pyproject.toml` | 版本更新至 1.36.0 |

## V42→V43 核心改进对比

| 维度 | V42 | V43 | 变化 |
|------|-----|-----|------|
| API 暴露 V42 字段 | ❌ 未暴露 | ✅ 完整暴露 | 新增 |
| TypeScript 类型定义 | ❌ 缺失 | ✅ 完整定义 | 新增 |
| 版本函数别名 | 无 find_mmds_v42 | ✅ 新增 | 新增 |
| 版本号 | 1.35.0 | 1.36.0 | +1 |
| 条件总数 | 120 | 120 | 不变 |

## API 使用方式

```bash
# 快速诊断（返回 V42 字段）
GET /api/v1/diagnosis/quick?market=SZ&code=000001

# 返回的 V42 字段：
{
  "post_signal_confirmation": {
    "confirmed": true,
    "bars_confirmed": 3,
    "direction_match": "bullish",
    "confidence_adjust": 0.03
  },
  "break_pullback_volume_ratio": {
    "break_vol_ratio": 1.45,
    "pullback_vol_ratio": 0.72,
    "volume_ratio_ok": true,
    "confidence_adjust": 0.02
  },
  "zhongshu_distance_validation": {
    "distance_pct": 2.3,
    "distance_valid": true,
    "confidence_adjust": 0.01
  },
  "adx_trend_strength": {
    "adx_value": 32.5,
    "adx_level": "medium",
    "trend_valid": true,
    "confidence_adjust": 0.0
  },
  "signal_freshness": {
    "bars_since_signal": 5,
    "decay_factor": 0.94,
    "effective_age": 0.033,
    "is_expired": false,
    "confidence_adjust": 0.0
  }
}
```

---
**版本**: V43.0
**完成日期**: 2026-08-23
**测试状态**: ✅ 509 passed，1 warning，0 failures
**构建状态**: ✅ 类型定义更新完成
**Git 状态**: ⏳ 待提交
