## ADDED Requirements

### Requirement: 前端 lint 与 format
系统 SHALL 为 web-ui 引入 eslint 与 prettier，并提供与后端一致的「format check + lint check」门禁。

#### Scenario: 本地检查
- **WHEN** 开发者在 web-ui 执行 lint 与 format 脚本
- **THEN** 输出风格问题列表并可自动修复

#### Scenario: CI 门禁
- **WHEN** CI 运行 frontend job
- **THEN** lint 或 format 不通过时 job 失败

### Requirement: 仓库卫生
系统 SHALL 归档或清理项目根目录的一次性脚手架脚本，并将运行时产物目录加入 .gitignore。

#### Scenario: 脚手架脚本归档
- **WHEN** 审计根目录的未跟踪脚本
- **THEN** 确定其去留：有用的移入 scripts/ 或删除，不再散落根目录

#### Scenario: 产物忽略
- **WHEN** 生成覆盖率报告等运行时产物
- **THEN** 相关目录（如 htmlcov）被 .gitignore 覆盖，不进入版本控制