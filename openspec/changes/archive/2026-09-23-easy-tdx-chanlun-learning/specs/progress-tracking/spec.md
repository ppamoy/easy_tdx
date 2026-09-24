## ADDED Requirements
### Requirement: 学习进度聚合
学习页 SHALL 聚合展示用户的训练进度（按周期/难度/日期统计的练习量与正确率）。强制（MUST）。
- `POST /api/v1/learn/progress` 提交一次训练汇总（player/category/difficulty/total_asked/hit_count/score）
- `GET /api/v1/learn/progress?player=xx` 返回按 category×difficulty 聚合的命中率、总题数、总分
#### Scenario: 查看掌握度矩阵
- **WHEN** 用户在「学习中心」查看自己的进度
- **THEN** 显示表格：行=周期（DAY/5MIN/…），列=难度（easy/medium/hard），单元格=命中率+题数，可点击展开最近记录

### Requirement: 成绩趋势曲线
学习页 SHALL 以曲线展示用户历史成绩趋势。强制（MUST）。
- 学习中心展示「最近 20 次训练命中率」折线图（前端 ECharts 或轻量 SVG）
- 每条训练记录含时间/标的/周期/难度/命中率
#### Scenario: 观察进步趋势
- **WHEN** 用户完成 3 次以上训练后打开学习中心
- **THEN** 折线图按时间显示每次命中率，标注平均线，供用户观察是否进步
