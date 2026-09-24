## ADDED Requirements
### Requirement: 排行榜按周期/难度筛选
排行榜接口与页面 SHALL 支持按周期（category）与难度（difficulty）筛选成绩。强制（MUST）。
- `GET /api/v1/chanlun/train/leaderboard` 接受 `category` 与 `difficulty` 查询参数
- 前端排行榜页提供周期、难度下拉筛选，默认全部
#### Scenario: 只看日线困难榜
- **WHEN** 用户选择筛选「日线 + 困难」
- **THEN** 排行榜仅显示 category=DAY 且 difficulty=hard 的成绩，按得分降序

### Requirement: 排行榜分组统计
排行榜页 SHALL 显示当前筛选条件下的总人数、平均命中率、最高分汇总行。强制（MUST）。
- 排行榜页显示当前筛选条件下的「总人数、平均命中率、最高分」汇总行
#### Scenario: 查看分组汇总
- **WHEN** 用户切换到「5分钟 + 简单」筛选
- **THEN** 顶部汇总显示该分组总人数、平均命中率、最高分，列表为该分组排名
