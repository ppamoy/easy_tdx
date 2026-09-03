## ADDED Requirements

### Requirement: mmd.py 子包拆分
系统 SHALL 将 chanlun/mmd.py 的指标计算簇拆分到独立子模块，同时保持顶层 find_mmds 与核心类型的导入兼容。

#### Scenario: 拆分后导入兼容
- **WHEN** 既有代码执行 from easy_tdx.chanlun.mmd import find_mmds
- **THEN** 导入成功且行为与拆分前一致

#### Scenario: 子模块边界清晰
- **WHEN** 查看拆分后的模块结构
- **THEN** 每个子模块职责单一且可独立导入与测试

### Requirement: 版本化死函数清理
系统 SHALL 清理 mmd.py 中无生产调用点的版本化旧函数，对可能存在外部引用的函数采用弃用周期。

#### Scenario: 无引用函数删除
- **WHEN** 某版本化函数（如 find_mmds_v40/v41/v76）经审计确认无任何生产调用点
- **THEN** 该函数被删除且全量测试仍通过

#### Scenario: 有引用风险函数弃用
- **WHEN** 某旧函数存在被外部用户引用的可能
- **THEN** 保留该函数一个版本周期并标注弃用，后续版本再删除

### Requirement: 拆分回归基线
系统 SHALL 在拆分过程中保持既有 2609 个单元测试全绿，作为搬移正确性的回归基线。

#### Scenario: 每步搬移全量回归
- **WHEN** 完成一个逻辑簇的搬移
- **THEN** 全量 pytest、ruff、mypy、format 门禁全部通过后才进入下一步