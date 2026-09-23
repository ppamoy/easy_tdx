# bi-type-convergence Specification

## Purpose
TBD - created by archiving change easy-tdx-chanlun-original-strict. Update Purpose after archive.
## Requirements
### Requirement: 默认笔类型为新笔（new）
默认 bi_type 保持 new（原文新笔：分型间含至少 1 根独立 K 线经典口径即 gap>=3）。old 保留。simple 不作为默认。强制（MUST）。
#### Scenario: 默认值
- **WHEN** 构造默认 ChanlunConfig()
- **THEN** bi_type 为 "new"

### Requirement: simple 显式 legacy
当 bi_type="simple" 时，find_bis/序列化/文档须标注该口径为 legacy 简化，仅在显式配置时生效，不作为推荐。强制（MUST）。
#### Scenario: legacy 标注
- **WHEN** 用户显式设置 bi_type="simple"
- **THEN** 分析与输出仍可用，但在文档/日志或配置 to_dict 中标明 legacy 简化

### Requirement: simple 不影响默认金标
默认路径下不得产生 simple 口径。既有 simple 相关测试可保留（显式开启时验证 legacy 可用），但默认规则测试不得依赖 simple。强制（MUST）。
#### Scenario: 默认不含简化口径
- **WHEN** 以默认配置运行 find_bis
- **THEN** 不进入 simple 分支，端点与分型间距满足 new 口径

