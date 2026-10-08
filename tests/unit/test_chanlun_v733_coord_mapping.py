"""V733：逐点坐标契约所用的 ground-truth fixture（`chanlun_gt.json`）的元测试。

为什么要有这个文件
------------------
fixture 是**生成器**（`scripts/gen_chanlun_gt.py`）跑真实 `ChanlunAnalyser`
产出的，不是手写常量。这带来一个隐蔽失效模式：

> 生成器写出的 JSON 若不满足 web-ui 的 **prettier 风格**，`prettier --check`
> 会挂 CI —— 而且下次重跑生成器又会把手工修好的格式覆盖回坏的。

踩过的坑（本轮实测）：生成器用 `indent=1` 写 JSON，prettier 对 JSON 强制
`indent=2` + 末尾换行 ⇒ 23 个文件里就它一个失败。**手工改一次不够，
必须同时改生成器 + 锁住生成器**，否则必然复发。
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GEN = ROOT / "scripts" / "gen_chanlun_gt.py"
FIXTURE = ROOT / "web-ui" / "src" / "components" / "__tests__" / "__fixtures__" / "chanlun_gt.json"


class TestFixtureExists:
    def test_generator_present(self) -> None:
        assert GEN.exists(), f"缺少生成器 {GEN}"

    def test_fixture_present(self) -> None:
        assert FIXTURE.exists(), f"缺少 fixture {FIXTURE} —— 先跑 gen_chanlun_gt.py"


class TestFixtureFormatting:
    """fixture 必须满足 web-ui prettier 风格，否则 CI 挂且会自动复发。"""

    def test_generator_uses_indent_2_with_trailing_newline(self) -> None:
        s = GEN.read_text(encoding="utf-8")
        assert "indent=2" in s, "生成器必须用 indent=2（prettier 风格）"
        # 末尾换行：形如 json.dumps(...) + "\n"
        assert '+ "\\n"' in s, "生成器必须写末尾换行（prettier 要求文件以 \\n 结尾）"

    def test_fixture_ends_with_newline(self) -> None:
        raw = FIXTURE.read_text(encoding="utf-8")
        assert raw.endswith("\n"), "fixture 必须以换行结尾"

    def test_fixture_is_valid_json_and_non_empty(self) -> None:
        import json

        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        assert isinstance(data, dict) and data, "fixture 非空才可支撑逐点契约"
        total = sum(len(c["mmds"]) for c in data.values())
        assert total > 0, "没有任何买卖点 ⇒ 逐点契约测试会空转通过"


class TestFixtureSubstantive:
    """fixture 必须足够"厚"，否则逐点契约形同虚设。"""

    @pytest.fixture(scope="class")
    def gt(self) -> dict:
        import json

        return json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_multiple_cases(self, gt: dict) -> None:
        assert len(gt) >= 2, f"只有 {len(gt)} 个用例，覆盖不足"

    def test_cover_both_buy_and_sell(self, gt: dict) -> None:
        """AGENTS.md §4：改了开关要测两侧 —— 契约必须同时含买点与卖点。"""
        types = {m["type"] for c in gt.values() for m in c["mmds"]}
        buys = {t for t in types if t.endswith("buy")}
        sells = {t for t in types if t.endswith("sell")}
        assert buys, f"没有任何买点类型（见到 {sorted(types)}）"
        assert sells, f"没有任何卖点类型（见到 {sorted(types)}）"

    def test_each_case_has_bars_and_aligned_keys(self, gt: dict) -> None:
        """mmd 的 bar_index 必须落在 bars 范围内。

        \u26a0\ufe0f bars 是**位置数组**（无 bar_index 字段），bar_index 即下标；
        越界会让 findAnchorIndex() 读到 undefined \u21d2 契约比对空锚点。
        """
        for name, case in gt.items():
            assert case["bars"], f"{name}: bars 为空"
            n = len(case["bars"])
            for m in case["mmds"]:
                assert isinstance(m["bar_index"], int), f"{name}: bar_index 非整数"
                assert 0 <= m["bar_index"] < n, (
                    f"{name}: mmd bar_index={m['bar_index']} 越界（bars 只有 {n} 根）"
                )
                assert m.get("anchor_val") is not None, f"{name}: anchor_val 缺失"

    def test_daily_grade_cases_have_date_for_selfhealing(self, gt: dict) -> None:
        """日线及以上用例必须带 date —— findAnchorIndex() 的日期自愈要靠它。

        少了这个字段，上一轮实测到的"日期回退纠偏"就无从生效。
        """
        dailyish = [n for n in gt if ("daily" in n or "weekly" in n or "monthly" in n)]
        assert dailyish, f"没有任何日线及以上用例（见到 {sorted(gt)}）"
        for name in dailyish:
            for m in gt[name]["mmds"]:
                assert m.get("date"), f"{name}: 缺 date \u21d2 日期自愈无法生效"
