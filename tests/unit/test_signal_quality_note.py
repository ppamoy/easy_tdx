"""V733「信号质量实测说明」的契约测试。

背景
----
审计实测：3买/3卖 相对"同窗随机极值入场"为负
（1buy +0.79% vs 3buy −1.12%，差 +1.90%，t=+3.06，p=0.0022），
但 UI 把 3买/3卖 与 1买/1卖 一视同仁，还对 3买/3卖 给出
入场/止损/止盈建议 ⇒ **会误导用户把三买/三卖当更强的确认信号**。
本轮在 `ChanlunView.vue` 加了 `signal-quality-note` 如实说明。

⚠️ 这条提示的价值完全取决于"数字是不是真的"，
   所以测试要锁住：**它引用的是实测数字，不是编出来的措辞**。
"""

from pathlib import Path

VIEW = Path(__file__).resolve().parents[2] / "web-ui" / "src" / "views" / "ChanlunView.vue"
E2E = Path(__file__).resolve().parents[2] / "scripts" / "e2e_signal_quality_note.py"


def _vue() -> str:
    return VIEW.read_text(encoding="utf-8")


class TestNoteExists:
    def test_component_edited(self) -> None:
        assert VIEW.exists()

    def test_has_note_class(self) -> None:
        assert "signal-quality-note" in _vue()

    def test_note_is_conditional(self) -> None:
        """必须**按需**显示：没有 3买/3卖 时不该弹这个。"""
        assert 'v-if="hasWeakSignals"' in _vue()

    def test_condition_uses_real_mmd_type(self) -> None:
        """⚠️ 字段名是 `type` 不是 `mmd_type` —— 我第一版写错过，
        vue-tsc 直接报错（TS2339）。"""
        s = _vue()
        assert "WEAK_SIGNAL_TYPES.has(m.type)" in s
        assert "mmd_type.value" not in s

    def test_weak_types_are_3buy_3sell(self) -> None:
        assert "new Set(['3buy', '3sell'])" in _vue()


class TestNumbersAreReal:
    """⚠️ 提示里的数字必须与审计结论一致，不能是随口写的。"""

    def test_states_1buy_positive(self) -> None:
        assert "+0.79%" in _vue()

    def test_states_3buy_negative(self) -> None:
        assert "−1.12%" in _vue() or "-1.12%" in _vue()

    def test_states_the_significance(self) -> None:
        """必须给出 t 与 p，否则"为负"只是断言没有证据。"""
        s = _vue()
        assert "t=+3.06" in s
        assert "p=0.0022" in s

    def test_mentions_cross_market_and_period(self) -> None:
        s = _vue()
        assert "跨周期" in s
        assert "跨市场" in s


class TestHonestCaveat:
    """⚠️ 反向解读必须克制，否则就是另一种误导。"""

    def test_says_not_necessarily_losing(self) -> None:
        """⚠️ 必须断言**用户能看见的那句话**，不能只断言某处出现过"不等于"。
        我第一版写 `... or "不等于" in s` —— 结果第435行的**代码注释**里
        也有"不等于"三个字，测试就算把界面改成"就是三买三卖必亏"也照样绿。
        这正是 AGENTS.md §7 说的"先验证脚本确实能抓到"。
        现在锁死模板里那句原文。"""
        s = _vue()
        assert "不等于<b>" not in s  # 防止把免责语气改掉
        assert '不等于"三买三卖必亏"' in s, "模板里必须有给用户看的免责措辞（不能只存在于代码注释）"

    def test_says_not_proving_chanlun_invalid(self) -> None:
        assert "不代表缠论整体无效" in _vue()

    def test_states_sample_limitation(self) -> None:
        s = _vue()
        assert "n=60" in s or "样本" in s

    def test_avoids_vague_boilerplate(self) -> None:
        """不能又写回"仅供参考"那种套话——那正是要改的东西。"""
        assert "信号质量的实测说明" in _vue()


class TestE2EScript:
    """⚠️ 这个脚本自己也踩了两次坑，必须锁住。"""

    def test_exists(self) -> None:
        assert E2E.exists()

    def test_waits_for_render_not_just_response(self) -> None:
        """⚠️ 第一版只等接口有响应就读 note，那刻 Vue 还没渲染，
        读到 present:0，差点误判'功能没生效'（案例 A 翻版）。"""
        s = E2E.read_text(encoding="utf-8")
        assert ".stats-bar" in s

    def test_collects_mmds_recursively(self) -> None:
        """⚠️ analyze 是**多级别**结构（levels[].mmds），
        只找顶层 r.mmds 会拿到空数组。"""
        s = E2E.read_text(encoding="utf-8")
        assert "Array.isArray(o.mmds)" in s
        assert "walk" in s

    def test_membership_check_uses_list(self) -> None:
        """⚠️ ev() 已把 JSON 解析成 list，我却拿 '"3buy"' 子串去 in，
        恒为 False ⇒ "有没有三买"永远判成没有。"""
        s = E2E.read_text(encoding="utf-8")
        assert 'any(t in ("3buy", "3sell") for t in types)' in s
        assert "'\"3buy\"' in" not in s

    def test_checks_visibility_not_just_presence(self) -> None:
        """AGENTS.md §1：元素存在 ≠ 生效。必须查 getBoundingClientRect + 可见性。"""
        s = E2E.read_text(encoding="utf-8")
        assert "getBoundingClientRect" in s
        assert "visibility" in s
        assert "opacity" in s

    def test_tests_both_sides(self) -> None:
        """AGENTS.md §4：改开关必须测两侧。"""
        s = E2E.read_text(encoding="utf-8")
        assert "不应出现" in s
        assert "说明块可见" in s


class TestPreExistingBuildErrorsFixed:
    """⚠️ 这两个 TS 错误在我改之前就存在（commit 56b619b），
    但会让 `npm run build` 失败 ⇒ 我的 e2e 根本跑不起来。
    用 git worktree 在 56b619b 上复现确认过是**既有失败**。"""

    def test_dead_function_removed(self) -> None:
        tv = (VIEW.parent / "TrainView.vue").read_text(encoding="utf-8")
        assert "function clearSavedSession" not in tv, "残留死代码会让 vue-tsc 报 TS6133 而构建失败"

    def test_rollup_input_is_typed(self) -> None:
        """三元里 mmdE2e 可能不存在，TS 推成 {mmdE2e?:undefined}
        与 rollup 的 InputOption 重载不匹配 ⇒ TS2769。"""
        cfg = (VIEW.parents[2] / "vite.config.ts").read_text(encoding="utf-8")
        assert "const rollupInput: Record<string, string>" in cfg
