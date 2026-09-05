# 设计（Design）— 缠论学习页面

## 架构总览

```
┌──────────────────────────────────────────────────────────────┐
│  /learn 学习页容器 (LearnView.vue)                            │
│  ┌──────────────┬──────────────┬───────────────────────────┐  │
│  │ 理论教学       │ 盘感训练       │ 学习中心                  │  │
│  │ TheoryLessons │  (TrainView   │  ProgressDashboard       │  │
│  │ 概念图文/视频  │  重构为子组件)  │  成绩曲线/掌握度/错误集     │  │
│  │              │ 难度分级/随机   │  Leaderboard 增强        │  │
│  └──────────────┴──────────────┴───────────────────────────┘  │
│  ChanlunChart 扩展: reveal + 高亮 + 中枢/笔构建标注             │
└──────────────────────────────────────────────────────────────┘
          │                      │
          ▼                      ▼
  /api/v1/learn/lessons    /api/v1/chanlun/train/*  (扩展)
  /api/v1/learn/progress   /api/v1/learn/mistakes
          │                      │
          ▼                      ▼
  lessons 静态内容        train_store (成绩表 + 难度维度)
  (markdown/JSON)         progress_store (掌握度/错误集)
```

## 设计决策（Decisions）

### D1：学习页采用「容器 + 子组件」而非重写 TrainView
- TrainView 的逐步揭示/复盘/排行榜逻辑已成熟（1300 行、V90 成绩持久化、V102 展示）
- 决定：新建 LearnView 容器 + /learn 路由，TrainView 的训练/复盘核心逻辑抽为 `TrainPractice.vue` 子组件，避免重写回归
- 理由：保护既有通过门禁的功能，增量演进

### D2：理论教学用「结构化 Markdown + 图例组件」而非 CMS
- 缠论概念（分型/笔/线段/中枢/买卖点/背驰）是确定性内容，不需要后台编辑
- 决定：`web-ui/src/content/lessons/*.md`（前端静态）+ `LessonCard` 渲染，图例复用 ChanlunChart 静态模式
- 理由：零后端成本、可版本管理、内容稳定

### D3：难度分级基于候选点信号特征，而非人工标注
- 出题难度 = f(信号置信度, 信号类型, 是否为干扰项)
- 决定：`train/session` 请求加 `difficulty: easy|medium|hard` + `seed`；后端按候选点特征打分排序后截取对应难度题集
- 理由：无需人工标注；seed 保证同一标的+难度出题可复现（可测试）

### D4：错误归因复用 mmd.msg + V102 决策支持，新增「正确解读」字段
- 每次答错，前端展示：模型信号、置信度、V102 建议、事后20日表现 + 一段从 msg/V102 生成的解读文案
- 决定：后端 build_train_session_payload 扩展 candidate.signal.explanation 字段（由 msg + v102_decision_support 拼接），前端错题时渲染
- 理由：不引入 LLM 依赖，讲解内容来自既有缠论引擎输出

### D5：掌握度 = 按周期×难度分组的历史命中率加权，新增 progress 端点
- 决定：`POST /learn/progress` 提交一次训练汇总 → train_store 记录；`GET /learn/progress?player=xx` 返回按 category×difficulty 聚合的命中率、总题数、趋势（最近 N 次）
- 理由：V90 排行榜表已含 player/category/count，扩展聚合查询即可，不迁移数据

### D6：排行榜筛选只加查询参数，不动存储
- 决定：`GET /chanlun/train/leaderboard?category=DAY&difficulty=hard&limit=10` 后端过滤
- 理由：成绩表已有 category，difficulty 为新增列（V418 迁移 add column 默认 easy）

## 数据模型变更

```sql
-- train_scores 扩展（V418）
ALTER TABLE train_scores ADD COLUMN difficulty TEXT NOT NULL DEFAULT 'easy';
-- 新表：学习进度汇总（按周期×难度）
CREATE TABLE IF NOT EXISTS learn_progress (
  player TEXT NOT NULL,
  category TEXT NOT NULL,
  difficulty TEXT NOT NULL,
  total_asked INT NOT NULL,
  hit_count INT NOT NULL,
  score INT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (player, category, difficulty)
);

-- 新表：错题集（供复习）
CREATE TABLE IF NOT EXISTS learn_mistakes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  player TEXT NOT NULL,
  symbol TEXT NOT NULL,
  category TEXT NOT NULL,
  difficulty TEXT NOT NULL,
  question_date TEXT,
  signal_type TEXT,
  user_choice TEXT,
  actual TEXT,
  explanation TEXT,
  created_at TEXT NOT NULL
);
```

### D7：同级别中枢 = MMD.zs 引用；单标的详情视图复用现有 analyzer 结果
- 用户要求 K 线图显示「一个同级别中枢」——即买卖点所属的中枢，而非全部中枢
- 现状：MMD 有 `zs: ZS | None` 字段直接引用所属中枢；ZS 无 level 字段；预跑固定 DAY 周期，级别即日线级别
- 决定：详情图仅渲染当前买卖点 MMD.zs 的 zg/zd 矩形 + gg/dd 边界；无 zs 则显示「无同级别中枢」；不给 ZS 加 level 字段（避免破坏现有算法）
- 理由：复用现有 MMD.zs 引用，最小改动实现「同级别中枢」；级别语义由周期参数承载，无需 schema 变更

### D8：后台预跑 20 只大市值标的 + 逐一呈现
- 不做用户选日期（全市场实时扫描计算量大）：改为后台预置 20 只市值+成交量较大标的，启动/首次访问时批量预跑缠论分析并缓存
- 前端「左列表 + 右单标的详情」一次只渲染一只；详情从缓存读取，无需实时计算
- 理由：固定 20 只标的数据量可控，预跑缓存避免用户等待；单标的详情按需读取

### D9：买卖点后逐根 K 线揭示（step-by-step）
- 用户点击某买卖点后，可从该点起逐根往后看后续 K 线（「下一根」推进一根，「快进 10 根」「跳到末尾」辅助）
- 决定：复用 reveal-index 机制——详情图有基础 K 线 + 一个 reveal 游标，游标从买卖点 index 起逐根推进，未揭示的后续 K 线淡显/隐藏
- 理由：逐根揭示让用户客观观察走势演变，而非一眼看到结果，更符合「验证模型是否精准」的实证目的

## 关键接口

```
POST /api/v1/chanlun/train/session   {market, code, category, count, difficulty?, seed?}
  → candidates 扩展 signal.explanation
POST /api/v1/chanlun/train/score     (不变，+difficulty)
GET  /api/v1/chanlun/train/leaderboard?category&difficulty&limit
GET  /api/v1/learn/lessons/{slug}    → 静态 Markdown 内容
POST /api/v1/learn/progress          {player, category, difficulty, total_asked, hit_count, score}
GET  /api/v1/learn/progress?player   → 聚合掌握度 + 最近 N 次趋势
GET  /api/v1/learn/mistakes?player&category  → 错题复习列表
POST /api/v1/verify/signals/prerun       → 后台预跑 20 只标的（触发批量分析）
GET  /api/v1/verify/signals/list          → 20 只标的清单 + 预跑状态
GET  /api/v1/verify/signals/detail       {code} → 单标的详情（买卖点 + 同级别中枢 + 基础K线 + 逐根游标）
```
