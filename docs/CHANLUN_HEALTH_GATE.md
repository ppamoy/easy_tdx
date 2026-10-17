# 缠论模型持续健康检查（chanlun_health_gate）

## 它解决什么问题

缠论的健康检查散在十几个脚本里，且**没有统一入口**：
CI 只挂了 3 个，其余（`audit_mmd_ground_truth`、`audit_3rd_type_accuracy`、
`audit_chanlun_vs_local_extreme`…）只能靠人记得手动跑 —— 忘了就不会有人发现模型退化。

`scripts/chanlun_health_gate.py` 把它们串成一个门禁，并且**自带牙齿**。

## 用法

```bash
# 牙齿自检：验证守卫真的会红（**必须先跑这个**，否则可能是在守一个恒绿的门）
.venv/bin/python scripts/chanlun_health_gate.py --selftest

# quick：限样本，分钟级。适合每次改完本地跑 / CI
.venv/bin/python scripts/chanlun_health_gate.py --quick

# full-block：全部 BLOCK 级检查全量跑（约 1 小时+）。适合定时任务
.venv/bin/python scripts/chanlun_health_gate.py --full-block --json
```

退出码：`0` = 通过（或仅 WARN/SKIP）；`1` = 有 BLOCK 失败；`2` = 牙齿自检失败。

## 三条设计纪律（都是踩过的坑）

### 1. 牙齿：守卫必须能证明自己会红

一个**从不会变红**的门禁等于没有门禁（AGENTS.md §7）。
为此给 `audit_chanlun_invariants.py` 加了 `INJECT_BROKEN=1` 注入开关：
复制末笔 → 人为制造违反 I2（同向笔）/ I3（端点不连续）/ I12（不确定性）的结构。

实测（2026-10-09）：

```
正常：            I1..I12 全 0 违反，exit=0
INJECT_BROKEN=1： ❌ I2: 2   ❌ I3: 2   ❌ I12: 2，exit=1
```

⚠️ 注入开关**默认关闭**，CI 正常跑完全不受影响。
⚠️ 另注意：验证退出码时**别用管道**（`cmd | tail` 会把退出码换成 tail 的），
我第一版就是这样看到 exit=0 差点误判"注入无效"。

### 2. 分级：环境不可用 ≠ 通过

`SKIP`（脚本缺失/超时/环境不足）与 `PASS` **严格区分**。
历史上"取到错数据还不自知"就是因为把"没执行"当成了"没问题"。

- `BLOCK`：结构/正确性被破坏（不变式、未来函数、ground truth、三类点召回率）
- `WARN`：统计口径类（样本外漂移、3卖拖累），需人看，**不阻断**
- `SKIP`：未执行，**不能当通过**

BLOCK 级失败会**早停**（后面的检查没必要跑）。

### 3. 别把慢脚本标成"快"

我第一版把 `audit_chanlun_invariants.py` 全量（286 只 ≈ 20+ 分钟）
标成了"快"，结果 `--quick` 在 CI 上跑半小时 —— 这是设计错误。

修正：给 invariants 加了 `--limit`（限样本），quick 模式默认 `--limit 3`（约 54 秒）。
只有 invariants / vs_local_extreme / pair_winrate 支持 `--limit`，
其余脚本只能全量，故不进 quick。

## 自动化

- ~~**CI**（`.github/workflows/ci.yml`）：先 `--selftest` 再 `--quick --json`，
  在 future_leak / invariants 之前跑。~~
  ⚠️ **2026-10-14 已停用**：本项目不使用 GitHub Actions，
  `.github/workflows/` 已整体删除（见 `docs/packaging.md` 与审计文档 §44）。
  健康门禁改由下面的 crontab 承担，需要时手工跑：
  `.venv/bin/python scripts/chanlun_health_gate.py --quick --json`
- **定时任务**（crontab，每周一 05:00）：
  ```
  0 5 * * 1 .../scripts/run_bg.sh 5400 chanlun-health-weekly \
      .../chanlun_health_gate.py --full-block --json >> /tmp/chanlun_health_cron.log 2>&1
  ```
  走 `run_bg.sh` 是为了强制超时 + 同进程组回收，避免卡死占核
  （见 `docs/BG_JOB_SLowness_POSTMORTEM.md`）。

  ⚠️ **必须带 `--force`**：`run_bg.sh` 有起飞前预检，一旦当时有别的高 CPU 任务
  （本项目常态：pytest / 常驻 web / 其他 agent）就会 `exit 3` 拒绝启动。
  而 **cron 没有告警**，于是会变成"以为一直在检查、其实从没跑过"——
  这正是 AGENTS.md 案例 A 那类"改了但没生效"的静默失效。
  定时任务属计划内占用，`--force` 是合理的。
  已实测两侧：无 `--force` → exit 3 拒绝；有 `--force` → 正常执行 exit 0。

## 各检查项实测状态（2026-10-09/10 核对）

注册 8 项，逐一真实跑过（**未跑的不会写"通过"**）：

| 检查 | 等级 | 状态 | 实测证据 |
|---|---|---|---|
| `audit_chanlun_invariants` | BLOCK | ✅ | 正常 I1-I12 全 0 违反；`INJECT_BROKEN=1` → I2/I3/I12 报错 |
| `audit_future_leak_real` | BLOCK | ✅ | 224 检查点 / 6377 信号 / 0 违反 |
| `audit_mmd_ground_truth` | BLOCK | ✅ | Case1 原文期望 1buy+2buy → 实得 `1buy@12.45`、`2buy@13.95`，命中 |
| `audit_3rd_type_accuracy` | BLOCK | ✅ | 3买/3卖 召回率 **40/40 = 100%**、定位准确率 **100%** |
| `audit_rolling_oos` | WARN | ✅ | 1buy **6/6 窗为正**（中位 +0.96%）、3sell **0/6 正窗**（中位 -1.29%），与 V733 一致 |
| `audit_chanlun_vs_local_extreme` | WARN | ✅ | `--limit 3` 可跑：4/4 优于随机、**0/4** 优于局部极值（与全量一致） |
| `audit_chanlun_pair_winrate` | WARN | ✅ | `--limit 3` 可跑：胜率 50.0%、盈亏比 2.16（与全量 46.4%/1.93 同量级）。⚠️ 该脚本已改用 `ChanlunStrategy(stop_loss_pct=0, take_profit_pct=0)`（`ChanlunPairStrategy` 已废弃删除），脚本名保留仅为兼容健康门禁清单 |
| `audit_chanlun_excess_by_regime` | WARN | ✅ | 全量已跑：2025 −15.31%(t=−6.17)；熊市 +8.19%(t=+8.60) / 牛市 −9.77%(t=−6.06) |

⚠️ 后三项 WARN 中，`vs_local_extreme` / `pair_winrate` 的日常门禁跑的是 `--limit 3`
（分钟级），**全量结论来自单独跑**，不在门禁内。

⚠️ 模式选择是**安全默认**：无参数 = quick（1 项，约 1 分钟）。
我第一版把默认设成跑全部 8 项，而其中 3 项无 `--limit`、各需 1~3 小时，
无参数误跑会占满机器 —— 已修（逻辑已用单元测试验证：
默认 1 项 / `--full` 8 项 / `--full-block` 4 项）。

## 已知待办 / 已澄清

- ~~invariants 的 **I8** 与原文有偏差：`zs.py` 用前两笔冻结 ZG/ZD，
  实测 591 个中枢中 303 个（51.3%）区间被放宽，中位宽度 +30%。~~
  **【2026-10-10 已澄清：结论过时，I8 其实已修。】**
  `config.zs_zd_lines` 默认 **3**（= 缠论原文「三个连续次级别走势的重叠」），
  `zs.py:221-226` 按前 `zd_lines` 笔确定后冻结，之后只更新 GG/DD。
  重新实测 40 只标的 / **686 个中枢：区间被放宽 0 个（0.0%）** ✅。
  旧结论来自修复前的版本，文档未同步 —— 属"文档漂移"，已更正。
  教训：I8 这条**本来就该计入 BLOCK**，当时因为"常年红"而降级，
  结果错的是文档不是代码。
- ~~`bi.py` v90 注释声称实现了「反向笔过滤」，代码里搜不到~~
  **【已修】** 注释已改写为勘误说明（不擅自补实现，避免改变笔的行为）。
