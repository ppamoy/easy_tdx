# 更新日志 V85

## [V85] — 2026-08-30

**P1 首个模块落地：长赢基本面选股（历史时点 + 树粮菜量化 + point-in-time）**

> 承接 V84（P0 缠论学习回测已上线，需求文档见 `docs/PRODUCT_REQUIREMENTS.md`）。
> 本次把「长盈/长赢理论」从概念卡片升级为**数据驱动选股**：
> 用 gpcw 历史财报（通达信专业财务）+ 披露日截断，在任意历史日期用「当时已披露」的数据
> 对自选池做树粮菜量化打分，并回看标的自该日起的实际走势验证理论有效性。

### 新增：财务指标层 `easy_tdx/fundamental/`

| 文件 | 内容 |
| --- | --- |
| `gpcw_fields.py` | 通达信 gpcw 584 字段命名表（fields[i] ↔ 字段名），含关键索引常量 F（EPS/ROE/营收/净利/披露日等） |
| `indicators.py` | gpcw zip 下载+缓存+解析 → 具名财务记录；派生指标（毛利率/净利率/负债率/同比）；披露日 point-in-time 截断（`pick_report`） |
| `screener.py` | 树粮菜三维打分（🌳树：ROE+成长+毛利率护城河；🌾粮：盈利+低负债+现金流；🥬菜：高增长+弹性），输出可解释明细分 |
| `season.py` | 历史时点四季判断：用「截至目标日」的指数日线算趋势/均线/波动率/量能 → 春播/夏长/秋收/冬藏 |
| `pipeline.py` | 编排：自动选报告期文件 → 指标 → 分类 → 后续 N 日表现 → 四季 |

### 新增：API（`easy_tdx/web/routers/fundamental.py`，注册于 app.py）

- `GET /api/v1/fundamental/indicator/{market}/{code}?as_of=YYYY-MM-DD` — 单只股票 point-in-time 财务指标
- `POST /api/v1/fundamental/screen` — 历史时点选股：date + pool + stock_type → 树粮菜清单 + 打分明细 + 后续表现 + 四季
- `POST /api/v1/fundamental/season` — 历史日期四季判断

### 新增：前端「长赢选股」页面 `web-ui/src/views/FundamentalView.vue`

- 路由 `/fundamental` + 导航「长赢选股」
- 历史日期 + 自选池输入 + 类型过滤 → 季节卡片、统计栏、结果表（EPS/ROE/毛利率/净利率/负债率/同比/后续收益）
- 每行可展开树粮菜三张打分明细（可解释性）

### 实测验证（Playwright，浏览器控制台零报错）

- `/fundamental` 页面 2026-05-01 选股：9 只自选池全部出结果，覆盖树/粮/菜分类
- 茅台 600519 判定「🌾 粮型」：ROE 10.1%、毛利率 89.8%、净利率 50.5%、负债率 12.1%、营收/净利同比 6.3%/1.5% —— 口径为 2026-04-25 披露的一季报（point-in-time 生效，4/10 时点只有 2025 年报）
- 截图：`docs/chanlun-screenshots/fundamental_config.png / fundamental_result.png / fundamental_detail.png`

### 测试

- `tests/unit/test_fundamental_p1.py`：13 个用例 —— 字段映射、派生指标、point-in-time（含未来披露拒绝）、树粮菜打分、四季阈值，全部通过

### 数据说明（重要）

- 数据源：通达信专业财务 gpcw`*.zip`（`TdxClient.get_financial_file_list/records`），本地缓存 `~/.easy_tdx/gpcw_cache/`
- **披露日（财报公告日期字段）是 point-in-time 的法定依据**：目标日 T 只使用披露日 ≤ T 的财报，杜绝未来函数
- 已知限制：gpcw 财报从 2021Q1 起可用（历史时点选股在 2019/2020 等更早时点暂无财报覆盖，需新浪财报补充——见 P2）
