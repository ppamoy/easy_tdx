# 更新日志 V91

## [V91] — 2026-08-30

**P2 在线数据补充：新浪财报指标缓存 + 全市场扫描新浪回退**

> 承接 V88（全市场扫描）、V89（SQLite 指标帧缓存）、V90（训练排行榜）。
> 本次落地路线图 P2 最后一项「在线数据补充（新浪/东财）」的**新浪部分**：
> 把新浪财报合并指标按股票代码缓存到 SQLite，并在 gpcw 未覆盖的历史时点
> （如 2019/2020）用新浪对自选池补充，全市场扫描输出可区分数据来源。

### 背景与选型

- 新浪财报接口（`sina_adapter.load_sina_rows`）每次请求三张报表 ~1.2s/只，
  历史时点选股反复回退时重复请求很浪费
- 沿用 V89 的 SQLite 方案，但维度不同：gpcw 缓存按**报告期 zip**，
  新浪缓存按**股票代码**（`~/.easy_tdx/gpcw_cache/sina_rows.db`）
- 沙箱实测新浪接口可用：600519 拉 8 期指标 1.2s，与 gpcw 口径一致

### 新增：新浪指标缓存（`easy_tdx/fundamental/sina_cache.py`）

- **`store_rows / load_rows / has_rows`** —— 按 code 缓存/读回新浪合并指标行
  （report_date / disclosure_date / indicators），幂等覆盖；
- **`cache_stats / clear_cache`** —— 统计（股票数/指标行数/库大小）与清空；
- **`FORMAT_VERSION`** —— 指标口径升级时旧缓存自动失效；
- `sina_adapter.load_sina_rows` 接入缓存：**命中直接返回（~0.005s）**，
  未命中才请求网络并写库；`use_cache=False` 可强制刷新

### 全市场扫描新浪补充（`easy_tdx/fundamental/pipeline.py`）

- **`scan_market(..., sina_pool=None)`** —— gpcw 空帧时，对自选池逐只走新浪
  财报补充并打分，结果行标注 **`data_source`**（gpcw/sina）
- gpcw 正常覆盖时全部标 `gpcw`，前端可区分数据来源

### API 与前端

- **`POST /api/v1/fundamental/scan`** 新增 `sina_pool`（可选自选代码列表）；
  响应 `results[*].data_source`（gpcw/sina）、`cache.sina_codes`
- **`GET /api/v1/fundamental/cache`** 新增 `sina` 子对象（新浪缓存统计）
- `GET /api/v1/fundamental/indicator/{market}/{code}` 新增 `data_source` 字段
- 前端 `/fundamental` 全市场扫描模式新增「新浪补充自选池」输入 + 结果表**数据源列**
  （gpcw 蓝标 / 新浪橙标）

### 实测（真实网络 + Playwright）

- **API 端到端**：2019-11-15 时点（gpcw 无覆盖）+ sina_pool 3 只 →
  全部新浪补充产出（600519 树型/000858 粮型/300750 菜型，报告期 2019-09-30，
  point-in-time 正确取三季报），写入 sina_cache 后 `cache.sina_codes=3`
- **浏览器实测**（`web-ui/scripts/fundamental-scan-sina-screenshot.mjs`）：
  扫描配置显示「新浪补充自选池」输入；结果 3 行全部为「新浪」徽章，
  明细完整展开，console/page 零错误
- 截图：`docs/chanlun-screenshots/v91_sina_fallback.png`

### 测试与质量

- 新增 `tests/unit/test_sina_cache.py` **9 例**：roundtrip、幂等覆盖、缺失返回 None、
  版本失效、stats/clear、load_sina_rows 缓存优先（不触发 HTTP）、use_cache=False 强制拉取、
  scan_market 新浪补充（data_source=sina）与 gpcw 行标注 —— 全部通过
- 全量单测 **2264 通过**；ruff 全绿；mypy（fundamental + router）0 错误；
  vue-tsc + vite 构建通过

### 下一步（P2 收尾）

- 东财数据源适配（当前新浪已覆盖核心需求）
- 全市场在线扫描（新浪逐只拉全市场较慢，当前定位自选池补充）
