# scripts/ 验证脚本

本目录的脚本用于**行为级验证**——只信真实行为（网络请求、渲染结果、像素），
不信 DOM 标志或变量存在性。详见项目根 `AGENTS.md` 的编码纪律。

## 运行方式

```bash
# 推荐：直接跑（playwright 缺时会自动找可用的 python 重跑）
python3 scripts/verify_fx_pages.py

# 用项目 venv 也行（缺 playwright 时会自动切换到能用的解释器）
.venv/bin/python scripts/verify_fx_pages.py
```

playwright 若装在非当前解释器的位置（例如装在系统 python3.11 而用 .venv 的
python3.12 运行），`_pw.py` 会自动探测并用能导入的那个 python **重跑本脚本**。
也可用 `PLAYWRIGHT_PATH=/path/to/site-packages` 显式指定。

浏览器默认用系统 `/usr/bin/chromium`，可用 `CHROMIUM=/path/to/chrome` 覆盖。
地址可用 `EASY_TDX_UI`（前端，默认 :3012）、`EASY_TDX_API`（后端，默认 :8000）覆盖。

## 脚本一览

| 脚本 | 验证什么 | 锁死哪个 bug |
|---|---|---|
| `verify_fx_pages.py` | 6 个页面的分型渲染：顶底交替、不共用K线、白色 | 展示层渲染原始 `fractals` 导致「底-顶-底挤在连续三根K线」 |
| `verify_fx_independence.py` | 后端分型独立性（6 标的 × 3 笔口径 = 18 组） | `bi_type="simple"` 让 `valid_fractals` 退化成原始分型 |
| `verify_train_e2e.py` | train 页浏览器 e2e：分型/MACD 副图/线段级别切换三项数据契约（曾因 train/session 漏传全破） | 动过 train/session 返回、TrainView 级别切换、MACD 副图接线 |
| `verify_fx_tooltip.py` | 缠论图 tooltip 能同时出现「顶分型」「底分型」 | 后端字段 `fx_type` 与前端读的 `fx.type` 不匹配 |
| `verify_mmd_colors.py` | 买卖点配色跟随全局涨跌配色 | 买点色被写死，不跟随红涨绿跌/绿涨红跌切换 |
| `verify_marker_pixels.py` | canvas 上买卖点标记的实际像素颜色 | 视觉模型判色不可靠，需像素级客观裁决 |
| `verify_ui.py` | 回测页 `chanlun/analyze` 请求真的发出且 200 | 改了 `v-if` 没改触发条件 → 请求根本没发 |
| `verify_fx_contract.py` | 静态契约五则：①渲染缠论图的页面都传了 `validFxs` ②给 `fractals` 的路由都给了 `valid_fractals` ③级别切换同步分型 ④不得平移 levels 里没有的字段（死代码） ⑤手工返回清单必须覆盖 to_dict 图表字段全集（train/session 曾漏 `valid_fractals` 整页 0 分型、漏 `levels` 线段切换空图、漏 `macd` 副图缺失） | 新增页面漏传 `validFxs`；平移 `lv.valid_fractals` 死代码；算过字段却在 return 手工清单漏掉 |
| `verify_level_switch.py` | 浏览器实测四页（chanlun/backtest/screening/verify）：切到 xd 时分型同步清空、笔随级别变化、切回 bi 完整恢复 | 「xd 的笔 + bi 的分型」自相矛盾；或切回后分型永久丢失 |
| `verify_structural_invariants.py` | 缠论结构不变量 | — |
| `nesting_backtest.py` | 真区间套（nested 布尔）分组对照：确认 vs 未确认，按方向分层；走 `/chanlun/multi-level` 跨周期口径 | V-22 由 v68 伪区间套评分迁移；结论见 `docs/区间套现状说明与统一方案.md` §九 |
| `verify_nesting_threshold.py` | （已弃用）v68 伪区间套阈值扫描，保留历史基线 | 真区间套的 nested 是布尔，无阈值可扫 |
| `coverage_gaps.py` | 覆盖率差距报告：读 pytest --cov JSON，按模块列最低覆盖与低于门槛清单 | openspec 2.5「定位低覆盖模块」与 4.5 门禁复跑的沉淀机制 |
| `verify_fundamental_page.py` | 长赢选股页（/fundamental）行为级 e2e：tab 切换 / 选股请求 200 / 结果表格渲染 / 无 console 错误（Playwright+系统 chromium，需 live 8000+3012） | PRD P1 验收第 4 条「浏览器实测」的沉淀脚本 |
| `verify_all_endpoints.py` | 全端点 smoke（openapi 驱动，不手工维护清单）：路由存在 + 校验层健康 + 抽样 200；闭市/上游不可用归入 degraded 可解释降级 | V-28 首跑抓到 `/market/stat` 上游不可得时 500 误导排障 → 改 503+可读指引；V-30 又抓到 `/fundamental/screen|verify` 坏形态 pool 的 500 → 改 400+守卫 |

契约检查同时以单元测试形式存在（`tests/unit/test_chanlun_fx_display_contract.py`），
CI 每次跑 pytest 都会执行——不依赖有人记得手动跑本目录的脚本。

## 一个反复踩到的坑：别数错的度量

ChanlunChart 里**笔/线段的 series.data 恒为空**（它们画在 `markLine.data`，
中枢在 `markArea.data`）。数 `data.length` 会得到 0，从而误判成「笔没渲染」。
论坛/脚本里凡是要度量这类结构，请照 `verify_level_switch.py` 里的 JS 写。

**为什么不写死字段名**：`check_level_payload_shift` 从后端 `_level_payload` 源码
解析真实字段集，再比对前端平移的字段——后端增删字段会自动跟上，不会失修。

**级别切换数据链的审计结论（V-15）**：三页级别切换的 levels 来源各不相同——
backtest 与 screening 扩窗走 `/chanlun/analyze`（`return d` 整体返回，天然带
levels/macd/zsds/qsds）；screening 首选 `/bars`+`reanalyseWindow` 同上；verify
走 `/verify/signals/detail`（`**result` 展开，且对旧进程缓存缺 valid_fractals
时现场重算补齐）。三接口已实测字段齐全，无 train/session 式漏传。

**哪些页面不适合自动验证**（别硬凑通过率）：`TrainView`（盘感训练）出题窗口固定
在 36 根 K 线左右，只有 2 根笔，切到 xd 笔数不会变 —— 这是页面定位使然、不是缺陷，
故默认排除（`--page train` 可显式调用）。同理，数据不足时脚本报「跳过」而非「通过」。

另一处坑：回测页只有 `chanlun` 一个策略会画缠论结构图
（`CHANLUN_STRUCTURED_STRATEGIES`），`changying_chanlun` 名字里也有 "chanlun"
但**不出图**——模糊匹配会误选。（第三个缠论策略 `chanlun_pair` 已废弃删除：
它的区间套过滤用 level_synth 合成数据，是伪区间套不符合原文。）

## 前置条件

- 后端在跑（默认 `http://127.0.0.1:8000`）
- 前端 dev server 在跑（默认 `http://127.0.0.1:3012`，需 `DEV=true` 才暴露
  `window.__CHANLUN_CHART__`）
- 系统装了 chromium

## 退出码

`0` = 通过；`1` = 发现违规；`2` = 环境问题（缺依赖、连不上服务等）。
