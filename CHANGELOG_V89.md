# 更新日志 V89

## [V89] — 2026-08-30

**P2 进阶：财务指标缓存（SQLite）—— 全市场扫描/选股从秒级降到亚秒级**

> 承接 V88（P2 全市场扫描）。本次落地路线图 P2 第二项「在线数据补充与财务指标缓存」
> 的缓存部分：把 gpcw 解析出的**派生指标帧**落盘 SQLite，重复扫描不再重复解压解析大 zip。

### 背景与选型

- 全市场扫描要处理 3~8 份 gpcw zip，每份解压解析 1~4s（`records_from_zip` + `build_indicator_frame`）
- 原始 584 字段 JSON 序列化 3 份 zip 约 **341MB**（太大）；只缓存**派生指标帧**（22 列）
  仅 **~4MB/3zip**，读回亚秒级
- 用标准库 `sqlite3`，零新增依赖（vs parquet 需 pyarrow）

### 新增：指标帧缓存模块（`easy_tdx/fundamental/cache.py`）

- **`store_frame / load_frame / has_frame`** —— 按报告期（zip 文件名）写入/读回指标帧，
  同 zip 先删后插幂等；日期列存 TEXT（ISO）还原为 date
- **`FORMAT_VERSION`** —— 指标口径升级时递增版本号，旧缓存自动失效重建
- **`cache_stats()`** —— 已缓存报告期/行数/库大小/格式版本（供 API 与 CLI）
- **`clear_cache()`** —— 清空全部缓存
- **`warm(filenames, client)`** —— 预生成缓存（解析缺失报告期并落盘），返回 warmed/already/failed
- 缓存库：`~/.easy_tdx/gpcw_cache/gpcw_frames.db`（可用 `EASY_TDX_GPCW_CACHE_DIR` 覆盖）

### 缓存接入（老接口零破坏）

- `indicators.py` 新增 **`frame_for_zip`** 与 **`load_all_periods_frame`**：逐份 zip 优先读 SQLite，
  未命中才解析并写库；`load_all_periods` / `build_indicator_frame` 等旧接口原样保留
- `pipeline.load_pool` / `scan_market` 改用缓存帧加载；`/fundamental/indicator` 单股端点同步接入

### API 与前端

- 新增 **GET `/api/v1/fundamental/cache`** —— 返回缓存统计（报告期清单/行数/库大小/格式版本）
- **`/api/v1/fundamental/scan`** 响应新增 `cache` 字段（命中的报告期/行数/库大小）
- 前端「全市场扫描」统计栏新增 **💾 财报缓存** 徽章（N 期 / X.XMB）

### CLI（`easy-tdx gpcw-cache`）

- `--action stats`：缓存统计（JSON 或 `--table`）
- `--action warm --date YYYY-MM-DD`：按目标日期自动选报告期预生成缓存
- `--action clear`：清空全部缓存

### 实测（真实 gpcw 数据，沙箱无外网，用本机缓存 3 份 zip）

- 冷扫描（无缓存）：3 份 zip 解析 + 打分 **11.4s**
- 热扫描（缓存命中）：**1.9s**（≈6 倍加速）；缓存库仅 4.1MB / 16490 行
- CLI：`stats` 显示 3 期 / 16490 行 / 4MB；`warm` 成功缓存 3 份（其余旧报告期本机无数据源，
  属沙箱预期，真实环境走 calc host 下载）
- 浏览器实测（端口 8000）：全市场扫描 50 行 + 统计栏 💾 财报缓存徽章（3 期 / 3.9MB）渲染正常，
  console/page 零错误（截图 `docs/chanlun-screenshots/v89_scan_cache.png`）

### 测试与质量

- 新增 `tests/unit/test_fundamental_cache.py` **9 例**：store/load roundtrip、幂等覆盖、
  格式版本失效、空帧不缓存、stats/clear、warm（含跳过已缓存）——全部通过
- 全量单测 **2250 通过**；ruff 全绿；mypy（fundamental + router + cli）0 错误

### 已知限制 / 下一步（P2 剩余）

- 缓存是「解析结果」缓存；在线数据补充（新浪/东财全量）与训练成绩持久化/排行榜仍未开始
- 沙箱无外网导致 warm 无法下载旧报告期 zip——真实环境由 calc host 提供
