# EasyTDX 项目更新日志 V4.0

## 更新时间
2026-08-21

## 本次更新内容

### 缠论买卖点识别 V4 升级

#### 核心改进
1. **五维确认系统** - 新增趋势对齐、动量确认、成交量确认、MACD确认、力度确认
2. **严格过滤条件** - 提高突破力度阈值(1.3x)、突破幅度要求(50%)、成交量标准(1.8x)
3. **质量评级系统** - 新增 S/A/B/C/D 五级质量评级，每笔买卖点附带详细评分原因
4. **置信度提升** - 3买从55%提升至72%，3卖从50%提升至68%

#### 文件变更
- `src/easy_tdx/chanlun/mmd.py` - 核心算法升级 (+484 行)
- `src/easy_tdx/chanlun/analyser.py` - 集成质量评级输出
- `tests/unit/test_chanlun_enhancements.py` - 更新测试断言

### API 变更

#### 新增字段
```python
# MMD 对象新增 quality 字段
@dataclass
class MMD:
    mmd_type: MMDType
    zs: ZS | None = None
    bi: BI | None = None
    msg: str = ""
    confidence: float = 0.0
    quality: MMDQuality | None = None  # 新增

# MMDQuality 数据结构
@dataclass
class MMDQuality:
    grade: str              # S/A/B/C/D
    score: float            # 0-100
    factors: dict[str, float]
    reasons: list[str]
```

#### Web API 返回示例
```json
{
  "mmds": [
    {
      "type": "3buy",
      "date": "2024-01-22",
      "msg": "3买V4: 突破确认后回踩...",
      "confidence": 0.82,
      "quality": {
        "grade": "A",
        "score": 85,
        "reasons": ["类型: 3买 (22/30)", "趋势强(向上) +20", ...]
      }
    }
  ]
}
```

### 测试结果
```
============================= 1031 passed in 55.87s ==============================
```

### 版本信息
- **当前版本**: V4.0
- **测试状态**: ✅ 全部通过
- **构建状态**: ✅ 无错误
