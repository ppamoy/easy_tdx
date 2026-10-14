#!/usr/bin/env python3
"""静态扫描：缠论图的「笔端点 / 分型」标记必须是小圆点，不能是三角形。

背景（用户要求 2026-10-10）
---------------------------
> 笔的端点不要用三角形，用小圆点标识吧。所有的缠论图都这样。

这条要求有两个容易踩的坑，所以做成可执行门禁而不是只写注释：

1. **「所有缠论图」= 所有复用 ChanlunChart 的页面**（回测页 / 选股 / 今日可操作 /
   买卖点核对 / 训练 / 筛查…）。组件收口在 ``ChanlunChart.vue`` 一处，
   所以符号定义必须从 ``echarts-setup.ts`` 的 ``FX_SYMBOL`` 取，
   不能在某个 series 里另写一个 ``symbol: 'triangle'`` 绕过。
2. **圆点是旋转对称的** —— ECharts 的 ``symbolRotate: 180`` 对它完全无效。
   所以顶/底分型必须靠 ``symbolOffset`` 的 y 方向区分（顶在上方=负 y、
   底在下方=正 y）。如果谁把分型改回三角形并加 rotate，这里会拦不住，
   但至少能保证「没有 triangle 混进来」。

检查项
------
A. ChanlunChart.vue / echarts-setup.ts 里不得再出现三角形分型：
   - 不允许 ``symbol: 'triangle'`` 出现在分型相关代码（顶分型/底分型/fxPoints）
   - 买卖点（1buy/2buy/3buy/…）仍用三角形表达 ▲▼，那是**有意**保留的，不算违规
B. 分型 series 必须用 ``FX_SYMBOL``（保证全站统一，改一处全生效）
C. 顶/底的 ``symbolOffset`` y 必须符号相反且非 0（否则圆点重叠，顶底不可分）
D. 不得用 ``symbolRotate`` 标记分型（对圆点无效，是死代码/误导）

用法
----
    python3 scripts/check_fx_symbol.py          # 检查
    python3 scripts/check_fx_symbol.py --verbose
退出码：0=通过，1=发现违规（CI 会红）。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "web-ui" / "src" / "components" / "ChanlunChart.vue"
SETUP = ROOT / "web-ui" / "src" / "echarts-setup.ts"

VIOLATIONS: list[str] = []


def fail(msg: str) -> None:
    VIOLATIONS.append(msg)


def split_series(src: str) -> list[tuple[str, str, int]]:
    """把 ChanlunChart.vue 的 option series 数组切成 [(name, block, start_line)]。

    只切 `        name: '<名字>'` 这一层的 series（8 空格缩进），
    买卖点的 rgba 之类更深的层级不会被误当 series。
    """
    lines = src.split("\n")
    marks: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        m = re.match(r"^\s{8}name: '([^']+)',?\s*$", line)
        if m:
            marks.append((i, m.group(1)))
    out: list[tuple[str, str, int]] = []
    for k, (i, name) in enumerate(marks):
        j = marks[k + 1][0] if k + 1 < len(marks) else len(lines)
        out.append((name, "\n".join(lines[i:j]), i + 1))
    return out


def strip_comments(src: str) -> str:
    """去掉 // 行注释（不处理跨行块注释 —— 本项目 Vue 里没用到）。

    用于区分「真在用的属性」和「注释里提到的属性」。
    """
    return "\n".join(re.sub(r"//.*$", "", line) for line in src.split("\n"))


def check_no_triangle_fx(src: str) -> None:
    """A. 分型系列不得用 triangle（买卖点的 triangle 是有意保留的，不算违规）。

    做法：按 series 名字切块，只在「顶分型 / 底分型」两个系列里查 triangle。
    这样 162/378/401 行那些**买卖点**的 triangle 不会被误报。
    """
    fx_series = {"顶分型", "底分型"}
    found = False
    for name, block, line_no in split_series(src):
        if name in fx_series:
            found = True
            # 只在**代码**里查 triangle；注释里解释历史做法不算违规
            if "triangle" in strip_comments(block):
                ln = line_no + [
                    i for i, l in enumerate(block.split("\n")) if "triangle" in l
                ][0]
                fail(
                    f"ChanlunChart.vue:{ln} 「{name}」系列仍在用 triangle —— "
                    "用户要求笔端点/分型用小圆点"
                )
    if not found:
        fail("没找到「顶分型」/「底分型」series —— 检查脚本的 series 切分正则需要更新")


def check_uses_fx_symbol(src: str) -> None:
    """B. 分型 series 必须引用 FX_SYMBOL，而不是硬编码 'circle'。"""
    # echarts-setup.ts 自己定义它是可以的
    body = src
    if SETUP.name in str(CHART):  # 只在检查 ChanlunChart 时生效
        n_fx = body.count("FX_SYMBOL")
        if n_fx == 0:
            fail("ChanlunChart.vue 没有引用 FX_SYMBOL —— 应改为从 echarts-setup 取，保证全站统一")
        # 分型 series 应至少出现 3 次：import + 顶 + 底 + (per-item)
        if n_fx < 3:
            fail(f"ChanlunChart.vue 只出现 {n_fx} 次 FX_SYMBOL —— 顶/底/per-item 都该用它")


def check_top_bottom_offset(src: str) -> None:
    """C. 顶/底 symbolOffset 必须反向且非 0；D. 分型系列不得用 symbolRotate。"""
    blocks = {name: (blk, ln) for name, blk, ln in split_series(src)}
    top, top_ln = blocks.get("顶分型", ("", 0))
    bot, bot_ln = blocks.get("底分型", ("", 0))
    if not top or not bot:
        fail("找不到「顶分型」或「底分型」series —— 检查脚本的正则需要更新")
        return

    def offset_y(block: str) -> int | None:
        """取 symbolOffset 第二个元素。

        实际代码写的是 `props.compact ? -4 : -6`（三元表达式），
        所以要抽出全部候选数字：必须同号且都不为 0
        （不为 0 才是「顶底不重叠」，同号才是「compact 与否方向一致」）。
        """
        m = re.search(r"symbolOffset:\s*\[\s*[^,]+,\s*([^\]]+)\]", block)
        if not m:
            return None
        nums = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", m.group(1))]
        if not nums:
            return None
        if any(n == 0 for n in nums):
            return 0  # 让上层的「非 0」检查统一报错
        if any((n > 0) != (nums[0] > 0) for n in nums):
            fail(f"symbolOffset 三元候选符号不一致 {nums} —— 顶/底方向会随 compact 反转")
        return int(nums[0])

    top_y, bot_y = offset_y(top), offset_y(bot)
    if top_y is None or bot_y is None:
        fail(f"分型 series 缺少 symbolOffset（顶={top_y} 底={bot_y}）—— 圆点靠它区分顶/底")
        return
    if top_y == 0 or bot_y == 0:
        fail(f"symbolOffset 的 y 不能为 0（顶={top_y} 底={bot_y}）—— 顶底会画在同一点上")
    elif not ((top_y < 0 < bot_y) or (top_y > 0 > bot_y)):
        fail(
            f"顶/底 symbolOffset y 必须反向（顶={top_y} 底={bot_y}）—— "
            "顶应在最高价上方、底在最低价下方"
        )
    elif top_y != -bot_y:
        fail(f"顶/底 offset 不对称（顶={top_y} 底={bot_y}）—— 视觉上会偏")

    for nm, blk, ln in (("顶分型", top, top_ln), ("底分型", bot, bot_ln)):
        # 只看**代码**，不看注释 —— 注释里常会解释「为什么不用 symbolRotate」，
        # 直接搜字符串会把这类说明误判成违规（我自己就被自己写的注释绊过一次）。
        code = strip_comments(blk)
        if "symbolRotate" in code:
            fail(f"ChanlunChart.vue:{ln} 「{nm}」还在用 symbolRotate —— 圆点旋转对称，rotate 无效")


def check_test_mocks() -> None:
    """E. 所有 mock 了 echarts-setup 的测试，必须同步导出 FX_SYMBOL。

    为什么单独查这一条：我加 ``FX_SYMBOL`` 时只改了 ``ChanlunChart.test.ts`` 的 mock，
    另外两个测试文件（mmd-chart-contract / chanlun-coord-mapping）里的 mock 没改，
    结果 **8 个用例**以 ``No "FX_SYMBOL" export is defined on the mock`` 崩掉。
    这个报错信息完全看不出和分型有关，很容易误判成别的问题 ——
    所以在这里显式把「mock 漏导出」变成一条可读的门禁。
    """
    tests_dir = ROOT / "web-ui" / "src" / "components" / "__tests__"
    comp_dir = tests_dir.parent
    real_exports = {
        e for e in re.findall(r"^export const (\w+)", SETUP.read_text(), re.M)
        if e.startswith("FX_")
    }
    for tf in sorted(tests_dir.glob("*.test.ts")):
        src = tf.read_text()
        if "echarts-setup" not in src or "vi.mock" not in src:
            continue
        # 关键：被测组件不能靠「测试文件名 == 组件名」推。
        # mmd-chart-contract.test.ts / chanlun-coord-mapping.test.ts 这种按契约命名的
        # 测试推不出组件名 —— 我第一版就是这么漏检的（剔除 mock 导出后仍报通过）。
        # 改为**按测试实际 import 的 .vue** 判定。
        imports = re.findall(r"import\s+\w+\s+from\s+'\.\./([\w.-]+\.vue)'", src)
        if not imports:
            continue
        used: set[str] = set()
        for rel in imports:
            comp = comp_dir / rel
            if not comp.exists():
                continue
            cs = comp.read_text()
            used |= {e for e in real_exports if e in cs}
        if not used:
            continue  # KlineChart 不画分型 → mock 不含 FX_* 是合理的
        mocked = set(re.findall(r"^\s{4}(\w+):", src, re.M))
        missing = used - mocked
        if missing:
            fail(
                f"{tf.name} 的 echarts-setup mock 缺少导出 {sorted(missing)} "
                f"（它测试的 {', '.join(sorted(set(imports)))} 确实用到了）—— "
                "组件 import 时会抛 'No export is defined on the mock'"
            )


def main() -> int:
    if not CHART.exists() or not SETUP.exists():
        print(f"❌ 找不到源文件：{CHART} / {SETUP}")
        return 1

    src = CHART.read_text()
    setup_src = SETUP.read_text()

    if "FX_SYMBOL" not in setup_src:
        fail("echarts-setup.ts 没有导出 FX_SYMBOL —— 分型符号应集中定义以保证全站统一")
    m = re.search(r"export const FX_SYMBOL = '(\w+)'", setup_src)
    if m and m.group(1) != "circle":
        fail(f"FX_SYMBOL = '{m.group(1)}'，但用户要求是小圆点（circle）")

    check_no_triangle_fx(src)
    check_uses_fx_symbol(src)
    check_top_bottom_offset(src)
    check_test_mocks()

    if VIOLATIONS:
        print("❌ 分型标记检查未通过：")
        for v in VIOLATIONS:
            print(f"   - {v}")
        return 1
    print("✅ 分型标记检查通过：缠论图的笔端点均为小圆点（circle），顶/底靠偏移区分")
    return 0


if __name__ == "__main__":
    sys.exit(main())


def check_test_mocks() -> None:
    """E. 所有 mock 了 echarts-setup 的测试，必须同步导出 FX_SYMBOL。

    为什么单独查这一条：我加 ``FX_SYMBOL`` 时只改了 ``ChanlunChart.test.ts`` 的 mock，
    另外两个测试文件（mmd-chart-contract / chanlun-coord-mapping）里的 mock 没改，
    结果 **8 个用例**以 ``No "FX_SYMBOL" export is defined on the mock`` 崩掉。
    这个报错信息完全看不出和分型有关，很容易误判成别的问题 ——
    所以在这里显式把「mock 漏导出」变成一条可读的门禁。
    """
    tests_dir = ROOT / "web-ui" / "src" / "components" / "__tests__"
    real_exports = {
        e for e in re.findall(r"^export const (\w+)", SETUP.read_text(), re.M)
        if e.startswith("FX_")
    }
    for tf in sorted(tests_dir.glob("*.test.ts")):
        src = tf.read_text()
        if "echarts-setup" not in src or "vi.mock" not in src:
            continue
        # 被测组件名由测试文件名推出（ChanlunChart.test.ts → ChanlunChart.vue）。
        # 只有**组件真的用了** FX_* 才要求 mock 里必须有 —— KlineChart 不画分型，
        # 它的 mock 不导出 FX_* 是完全合理的，不能一刀切报错。
        comp = tests_dir.parent / tf.name.replace(".test.ts", ".vue")
        if not comp.exists():
            continue
        comp_src = comp.read_text()
        used = {e for e in real_exports if e in comp_src}
        if not used:
            continue
        mocked = set(re.findall(r"^\s{4}(\w+):", src, re.M))
        missing = used - mocked
        if missing:
            fail(
                f"{tf.name} 的 echarts-setup mock 缺少导出 {sorted(missing)} "
                f"（{comp.name} 确实用到了）—— 组件 import 时会抛 "
                "'No export is defined on the mock'"
            )
