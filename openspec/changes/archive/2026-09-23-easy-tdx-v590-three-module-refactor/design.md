# 设计（Design）— 三大模块收敛 + 缠论画图精度修复

## 架构总览（ASCII）

    浏览器 Web GUI
    ┌─────────────────────────────────────────────────────────────┐
    │ App.vue 导航（3 主导航 + 页脚齿轮）                              │
    │  [回测] [选股] [缠论测试学习]                       [⚙ 服务器]  │
    └─────────────────────────────────────────────────────────────┘
          │                │                    │
          ▼                ▼                    ▼
    BacktestView     StockPickView         LearnView（多 Tab 容器）
    /                /stock-pick            /learn
    （现状保留）      ├─ 时间/市场选择        ├─ 看图分析（ChanlunChart）
                     ├─ Step1 长盈基本面     ├─ 理论教学（TheoryLessons）
                     │   fundamental.screener│   ├─ 盘感训练（Train 复用）
                     └─ Step2 缠论择时       ├─ 买卖点实证（SignalVerify 复用）
                         ChanlunAnalyser    └─ 进度（ProgressDashboard）

    FastAPI /api/v1
    ├─ /backtest/*        回测（现状保留）
    ├─ /stock-pick/*      新增两步流（长盈基本面 → 缠论择时）
    ├─ /chanlun/analyze   缠论分析（精度修复后的序列化）
    └─ /learn/*           学习/训练/实证（复用既有端点）

## 关键决策（Decisions）

### D1：导航收敛采用「软隐藏」而非删除路由

- 决策：保留全部 15 条路由与组件，仅从 App.vue 主导航移除；服务器设置改为页脚齿轮；其余页面不显示但 URL 可直达。
- 理由：组合回测、参数寻优、策略库、诊断等仍有存量价值，且用户书签/文档可能引用；直接删除会造成破坏性变更与回归面扩大。产品上「只有三个功能」由导航信息架构体现。
- 取舍：短期保留了技术债，换取零破坏迁移；后续按用户反馈再决定是否物理删除。

### D2：选股页做成「时间选择 → 长盈基本面 → 缠论择时」两步流，且严格 point-in-time

- 决策：用户选择一个目标日期（或日期区间），第一步用 fundamental.screener 在目标日期只使用「截至当日已披露」财报，产出树粮菜分类 + 质量评分 + 评分明细；第二步对通过筛选的池内标的，取截至目标日期的前复权 K 线做 ChanlunAnalyser 分析，输出三类买卖点、背驰、中枢与择时结论。
- 理由：长盈理论是基本面选股，缠论是技术择时，两步必须时间对齐且杜绝未来函数，否则回看式选股会虚高。
- 现有资产：fundamental/screener.py 已实现 point-in-time；screening.py 已实现「选股+缠论」雏形，但标的池硬编码 30 只。本 change 复用前者，扩展后者标的池为可配置（默认热门池，可选全市场批量）。

### D3：选股标的池与超时治理

- 决策：默认使用可配置热门池（配置文件/环境变量），扫描上限、单标的超时、并发数显式化；页面提供「池范围」选择（热门池 / 全市场），全市场走分批任务 + 进度轮询，避免长连接超时。
- 理由：全市场基本面扫描耗时长，必须在「易用」与「真实覆盖」之间给用户选择权；一次性同步扫描会重蹈 30 只硬编码与超时的老问题。
- 取舍：全市场路径需要后台任务化，增加 task_runner 复用成本。

### D4：精度修复拆成「几何锚定」与「结构判定」两条线

- 几何锚定（保证端点落极值）：
  - 分型 val 取中间缠论K线的 high（顶）/low（底），bar_index 取该极值的来源原始K线索引；
  - 笔/线段端点序列化始终输出 start_val/end_val/start_index/end_index；
  - 买卖点标注价格改为触发笔终点分型的 val，而非 bars[idx].low/high 乘偏移；
  - 背驰在主图 K 线图与 MACD 副图同时给出可核对标注。
- 结构判定（保证该画的画、不该画的不画）：
  - 把 bi.py 中会静默丢弃真实转折点的过滤（弱笔、趋势一致性、分型稳定性）从「硬跳过」改为「可配置 + 质量降级标记」，不再丢极值；
  - xd.py 统一用标准特征序列转折点，收尾分支也必须与前一段共享转折点，不允许 max/min 重选端点；
  - zs.py 明确 zg/zd 是重叠区间、gg/dd 是中枢极值，序列化与前端字段一一对应；
  - mmd/beichi 标注锚定到触发笔的终点分型 bar_index。
- 理由：用户反馈「没落在最高最低点」表面是渲染问题，实际根因是算法在正确渲染之前就把极值点过滤掉了；只改前端无法根治。

### D5：建立「金标不变量」回归，覆盖多周期多形态

- 决策：在既有 tests/unit/test_chanlun_geometry.py 基础上，新增一组显式金标断言：
  1. 每支笔端点价格 == 锚定原始K线极值（顶=high，底=low）；
  2. bi[i].end 与 bi[i+1].start 共享同一根K线且价格相等；
  3. 线段方向与端点极值一致，且 xd 端点必须与某支笔端点共享分型；
  4. 中枢 zg <= gg、zd >= dd、zg > zd，且 start/end 落在构成笔范围内；
  5. 买卖点/背驰的 bar_index 必须落在触发笔终点分型上。
- 理由：这是对「画图精度」的可执行验收标准；不变量测试让精度修复可回归、可验证。

### D6：缠论测试学习页用单容器 + 子 Tab，复用既有组件

- 决策：/learn 作为唯一「缠论测试学习」入口，内含 5 个 Tab：看图分析（现有 ChanlunView 能力）、理论教学（TheoryLessons）、盘感训练（TrainView 复用）、买卖点实证（SignalVerifyView 复用）、进度（ProgressDashboard/MistakesReview）。/chanlun、/train、/verify 保留为兼容重定向或直接复用子组件。
- 理由：easy-tdx-chanlun-learning 已交付七能力，重复建设浪费；本 change 只做信息架构合并，不做能力重写。

### D7：回测页零删减

- 决策：BacktestView.vue 保持现状（含组合回测、参数寻优等子入口），仅确认新导航下可访问；不因收敛而砍功能。
- 理由：用户明确「保留目前的回测页面」，回测是既定核心资产。

## 数据流（选股两步）

    用户选择时间 T + 市场 + 池范围
      │
      ▼
    POST /api/v1/stock-pick/scan  {date:T, market, pool}
      │  1) 取池内代码列表
      │  2) 逐标的 fundamental.screener.point_in_time(T) → 树粮菜 + 评分
      │  3) 过滤/排序 → 基本面标的池（含评分明细）
      ▼
    返回池 [{symbol, category, score, detail}]
      │
      ▼（用户选择池内标的或「全部择时」）
    POST /api/v1/stock-pick/timing  {symbols, date:T}
      │  对每个 symbol：取截至 T 的 QFQ K 线 → ChanlunAnalyser
      │  输出买卖点/背驰/中枢 + 择时结论（buy/wait/sell + 建议）
      ▼
    返回 [{symbol, chanlun:{bis,xds,zss,mmds,bcs}, verdict}]
      │
      ▼
    StockPickView：左池表 + 右 ChanlunChart 详情（一次一只）

## 风险与缓解

- 全市场扫描耗时长：默认热门池；全市场走后台任务 + 进度轮询（复用 task_runner）。
- 精度修复可能改变历史信号数量：用金标不变量测试锁住几何正确性，用现有 chanlun 单测回归信号契约；如信号数量变化需在 CHANGELOG 记录原因。
- 导航收敛造成旧入口不可见：软隐藏 + 兼容重定向，文档标注直达 URL。
