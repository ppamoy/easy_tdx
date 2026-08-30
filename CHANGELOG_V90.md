# 更新日志 V90

## [V90] — 2026-08-30

**P2 增强：训练成绩持久化 + 排行榜 ——「逐步揭示训练」成果落盘并可排名**

> 承接 V88（全市场扫描）、V89（财务指标缓存）。本次落地路线图 P2 最后一项中的
> 「训练成绩持久化/排行榜」：缠论「逐步揭示训练」每轮成绩持久化到 SQLite，
> 前端新增排行榜，让训练成果可沉淀、可排名、可复习。

### 新增：训练成绩存储（`easy_tdx/web/train_store.py`）

- **`TrainScore`** —— 一条训练成绩记录：学员名/得分/命中率/题数/命中数/标的/周期/参数/时间
- **`TrainScoreStore`** —— SQLite 存储（`~/.easy_tdx/train_scores.db`，受 `EASY_TDX_CONFIG_DIR` 覆盖）：
  - `add`：提交一条成绩（自动填充 id / created_at，写操作串行 + 短连接线程安全）
  - `leaderboard(limit, category)`：排行榜，得分降序、命中率降序，可限定周期
  - `list_all` / `clear`：全部成绩 / 清空
- 单例 `get_score_store()`，风格与 `strategy_store.py` 一致

### 新增：API（`easy_tdx/web/routers/chanlun.py`）

- **POST `/api/v1/chanlun/train/score`** —— 提交一轮训练成绩（学员名/得分/命中率/标的/周期）
- **GET `/api/v1/chanlun/train/leaderboard`** —— 排行榜（`?limit=&category=`）

### 前端：训练页排行榜（`web-ui/src/views/TrainView.vue`）

- 「🎯 逐步揭示训练 / 📖 复盘讲解 / 🏆 排行榜」三模式
- 训练完成卡片新增「昵称 + 💾 保存成绩」：训练结束时**自动提交一次**，也可手动改名后保存
- 排行榜 tab：得分/命中率/题数/标的/周期/时间表，前三名高亮，空态引导

### 实测（Playwright，浏览器控制台零报错）

- `/train` 排行榜 tab：2 行成绩渲染（盘感王 22分/78%、缠论新秀 18分/75%），前三名样式正常
- API 端到端：POST score → GET leaderboard 回读一致；console/page 零错误
- 截图：`docs/chanlun-screenshots/v90_train_leaderboard.png`

### 测试与质量

- 新增 `tests/unit/test_train_store.py` **5 例**：提交/读取、排行榜排序、limit/category、清空、
  extra JSON roundtrip —— 全部通过
- 全量单测 **2255 通过**；ruff（新增文件）全绿；mypy（train_store.py）0 错误；
  vue-tsc + vite 构建通过

### 下一步（P2 收尾）

- 在线数据补充（新浪/东财全量）未开始
- 排行榜可后续增强：按标的/周期筛选、分页、每轮明细快照
