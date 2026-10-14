import json
from pathlib import Path

from easy_tdx.chanlun.analyser import ChanlunAnalyser
from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.web.routers.chanlun import build_train_session_payload


class _FixtureMixin:
    """真实 fixture（000333 日线 160 根）上的一次分析结果，类内共享。"""

    @classmethod
    def setup_class(cls) -> None:
        import pandas as pd

        rows = json.loads(
            (
                Path(__file__).resolve().parents[1] / "fixtures" / "chanlun_000333_daily.json"
            ).read_text(encoding="utf-8")
        )
        cls.df = pd.DataFrame(rows)
        cls.result = ChanlunAnalyser(
            code="000333", frequency="daily", config=ChanlunConfig(zs_from_xd=False)
        ).process_klines(cls.df)


class TestTrainAnticheatV731StructureTruncation(_FixtureMixin):
    """V731 第 37 轮：防作弊闸门必须截断**全部**未来结构，不只 signal。

    此前只置空 candidates[].signal 与 mmd_outcomes，但 bis/xds/zss/
    fractals/valid_fractals/macd/boll 仍携带全量未来结构。前端 revealIndex
    只是显示层过滤 —— F12 网络面板可直接读到未来：开局即知「还有 7/10 笔、
    端点价格、中枢延伸到 106/152 根、40/62 个未来分型」。实测（000333
    日线 160 根）泄露量：
        reveal_limit=30: 笔 9/10、中枢 2/2、分型 50/62
        reveal_limit=50: 笔 7/10、中枢 2/2、分型 40/62
    训练答案从此泄露渠道一键可读，逐步揭示训练名存实亡。
    """

    def _payload(self, reveal_limit):
        return build_train_session_payload(
            self.result, self.df, "daily", "medium", 0, reveal_limit=reveal_limit
        )

    def test_review_mode_still_full(self) -> None:
        """对照组：复盘模式（reveal_limit=None）必须仍是全量。"""
        p = self._payload(None)
        full_bis = len(self.result.bis)
        assert len(p["bis"]) == full_bis
        assert len(p["mmd_outcomes"]) == len(self.result.mmds)

    def test_no_structure_beyond_reveal_limit(self) -> None:
        for n in (30, 50, 80):
            p = self._payload(n)
            assert not [b for b in p["bis"] if b.get("end_index", 0) > n], f"N={n} 笔泄露"
            assert not [z for z in p["zss"] if z.get("start_index", 0) > n], f"N={n} 中枢泄露"
            assert not [f for f in p["fractals"] if f.get("bar_index", 0) > n], f"N={n} 分型泄露"
            assert not [
                f for f in (p.get("valid_fractals") or []) if (f.get("bar_index") or 0) > n
            ], f"N={n} 有效分型泄露"

    def test_aligned_series_cut_to_n_plus_one(self) -> None:
        """macd/boll 是对齐 bars 的序列，须切到前 N+1 个点。

        （V731 第 38 轮修订：bars 本身也截断为 N+1，所以这里的对齐基准
        从「全量 df」改为「截断后的 bars」—— 原断言 len(bars)==len(df)
        已不符合新的防作弊约定，按 round-38 语义更新。）
        """
        for n in (30, 50):
            p = self._payload(n)
            assert len(p["bars"]) == n + 1  # round-38: bars 截断
            macd = p.get("macd") or {}
            if isinstance(macd, dict) and macd.get("hist"):
                assert len(macd["hist"]) <= n + 1
            boll = p.get("boll") or {}
            if isinstance(boll, dict) and isinstance(boll.get("mid"), list):
                assert len(boll["mid"]) <= n + 1

    def test_signal_answers_still_blanked(self) -> None:
        p = self._payload(50)
        leaked = [c for c in p["candidates"] if c["index"] > 50 and c.get("signal")]
        assert not leaked

    # ⚠️ V733：此处原先有第二个同名 test_review_mode_still_full（复制品），
    # Python 里后者**静默遮蔽**前者 ⇒ 前一条永远不执行（ruff F811）。
    # 两条断言内容完全一致，故删掉复制品，保留 line 46 那条。

    def test_truncation_never_adds_entries(self) -> None:
        """截断只减不增：训练模式各结构数组长度 <= 复盘模式。"""
        pt = self._payload(50)
        pf = self._payload(None)
        assert len(pt["bis"]) <= len(pf["bis"])
        assert len(pt["zss"]) <= len(pf["zss"])
        assert len(pt["fractals"]) <= len(pf["fractals"])


class TestTrainAnticheatV731BarsTruncation:
    """V731 第 38 轮：训练模式 bars 本身也必须截断（闸门最后一块）。

    第 37 轮截断了结构数组，但 bars 仍全量下发（reveal_limit=50 时
    bars=160）—— 未来 K 线是答案的**原始数据源**，F12 存一次响应即得
    全部未来走势，无需逐题枚举。修复后训练模式 bars = 前 N+1 根，且与
    结构截断同用 keep=N+1，索引不漂移。
    """

    def test_bars_cut_to_n_plus_one(self) -> None:
        for n in (0, 50, 87):
            p = build_train_session_payload(
                TestTrainAnticheatV731StructureTruncation.result,
                TestTrainAnticheatV731StructureTruncation.df,
                "daily",
                "medium",
                0,
                reveal_limit=n,
            )
            assert len(p["bars"]) == n + 1, f"N={n}: bars 应为 {n + 1}，实得 {len(p['bars'])}"

    def test_structure_never_exceeds_bars(self) -> None:
        """结构与 bars 同窗：任何条目索引不得越过 bars 末尾（对位不漂移）。"""
        p = build_train_session_payload(
            TestTrainAnticheatV731StructureTruncation.result,
            TestTrainAnticheatV731StructureTruncation.df,
            "daily",
            "medium",
            0,
            reveal_limit=50,
        )
        nb = len(p["bars"])
        assert not [b for b in p["bis"] if b.get("end_index", 0) >= nb]
        assert not [f for f in p["fractals"] if f.get("bar_index", 0) >= nb]
        macd = p.get("macd") or {}
        if isinstance(macd, dict) and macd.get("hist"):
            assert len(macd["hist"]) <= nb

    def test_progressive_reveal_semantics(self) -> None:
        """渐进揭示：作答后按需取答案（reveal_limit=index）返回「截至该点」。

        前端 fetchSignalFor 用 reveal_limit=index 取答案 —— 返回的 bars 必须
        恰好覆盖到该候选点（index+1 根），语义与 revealIndex 一致。
        """
        p0 = build_train_session_payload(
            TestTrainAnticheatV731StructureTruncation.result,
            TestTrainAnticheatV731StructureTruncation.df,
            "daily",
            "medium",
            0,
            reveal_limit=87,
        )
        assert len(p0["bars"]) == 88

    def test_review_mode_bars_still_full(self) -> None:
        """对照组：复盘模式 bars 全量。"""
        p = build_train_session_payload(
            TestTrainAnticheatV731StructureTruncation.result,
            TestTrainAnticheatV731StructureTruncation.df,
            "daily",
            "medium",
            0,
            reveal_limit=None,
        )
        assert len(p["bars"]) == len(TestTrainAnticheatV731StructureTruncation.df)


# ── V731 第 39 轮：mmds/bcs/zsds/qsds/levels 的泄题补全 ──────────────────
#
# 第 37/38 轮只截了 bis/xds/zss/fractals/valid_fractals/macd/boll/bars，
# **mmds / bcs / zsds / qsds / levels 五个 key 原样下发**（return 的 dict
# 里直接写 ``d.get("mmds", [])``）。其中 mmds 就是训练的标准答案本体：
# 实测 000333 日线 reveal_limit=0（训练开局）时，响应里仍有 3/3 个未来
# 买卖点，含 type / date / anchor_val / confidence / quality.grade ——
# 「逐步揭示训练」一步即全泄。
#
# 本轮测试刻意**不硬编码 key 清单**：从响应里递归派生所有结构数组并逐条
# 断言，新增结构 key 时要么被覆盖、要么显式登记，不能静默跳过。

#: 序列化的结构条目里「该条目锚定在哪根 K 线」的字段名（按优先级）。
#: 与后端截断谓词一一对应：
#:   end_index/bar_index  → 线段类（bis/xds/zsds/qsds/fractals）
#:   bar_index            → 买卖点（mmds）
#:   anchor_bar_index     → 背驰（bcs）
_N_ANCHOR_FIELDS = ("end_index", "bar_index", "anchor_bar_index")

#: 顶层里「与 bars 逐根对齐的序列」字段（长度截断，不是按锚点过滤）。
_ALIGNED_SERIES = ("macd", "boll")

#: 明确**不参与**截断断言的 key（说明理由，防止后人误以为是漏测）：
#:   code/frequency/category —— 标量与未来无关
#:   candidates —— 另有 signal 置空闸门（test_signal_answers_still_blanked）
#:   mmd_outcomes —— 训练模式整段置空（另有测试）
#:   levels.*.name / *_count —— 标量元数据
_NON_STRUCTURE_KEYS = frozenset({"code", "frequency", "category", "candidates", "mmd_outcomes"})

#: 每个结构数组「锚定在哪根 K 线」的字段，与后端截断谓词一一对应。
#: 大多数是 max(end_index, bar_index)；中枢是**区间**，口径自第 37 轮起
#: 就是「start_index < keep」（已成形但未走完的中枢属于当前可见结构，
#: 按 end_index 判会把它整段切掉 —— 那不是泄题，是改口径）。这里必须
#: **镜像后端口径**而不是另定一套，否则测试与实现互相打架。
_ANCHOR_FIELDS_BY_KEY: dict[str, tuple[str, ...]] = {
    "zss": ("start_index",),
}
_DEFAULT_ANCHOR_FIELDS: tuple[str, ...] = _N_ANCHOR_FIELDS


def _anchor_fields_for(path: str) -> tuple[str, ...]:
    """按 key 取锚点字段（levels.bi.zss → zss 的口径）。"""
    leaf = path.rsplit(".", 1)[-1]
    return _ANCHOR_FIELDS_BY_KEY.get(leaf, _DEFAULT_ANCHOR_FIELDS)


def _anchor_of(item: dict, fields: tuple[str, ...]) -> int | None:
    """取条目锚定的 K 线下标；取不到返回 None（无法判定，交由调用方登记）。"""
    for f in fields:
        v = item.get(f)
        if isinstance(v, bool) or not isinstance(v, int | float):
            continue
        try:
            return int(v)
        except (ValueError, OverflowError):
            continue
    return None


def iter_structure_arrays(payload: dict):
    """递归产出 (路径, 数组) —— 顶层结构数组 + levels.<级>.<结构>。

    只产出 list[dict]（结构条目），标量 / 对齐序列 / 非结构 key 跳过。
    """
    for key, val in payload.items():
        if key in _NON_STRUCTURE_KEYS or key in _ALIGNED_SERIES:
            continue
        if isinstance(val, list) and all(isinstance(x, dict) for x in val):
            yield key, val
        elif key == "levels" and isinstance(val, dict):
            for lname, lv in val.items():
                if not isinstance(lv, dict):
                    continue
                for k, arr in lv.items():
                    if isinstance(arr, list) and all(isinstance(x, dict) for x in arr):
                        yield f"levels.{lname}.{k}", arr


class TestTrainAnticheatV739AllStructureKeys(_FixtureMixin):
    """V731 第 39 轮：训练模式下**任何**结构 key 都不得含 reveal_limit 之后的条目。

    与既有 test_no_structure_beyond_reveal_limit 的区别：那条是手写清单
    （bis/zss/fractals/valid_fractals），正是手写清单让 mmds 漏了三轮。
    这一条从响应**派生** key 集合，并对派生出的每个 key 逐一断言。
    """

    def _payload(self, reveal_limit):
        return build_train_session_payload(
            self.result, self.df, "daily", "medium", 0, reveal_limit=reveal_limit
        )

    def test_no_structure_key_leaks_at_strictest_setting(self) -> None:
        """reveal_limit=0（训练开局）：任一条目的锚点都不得 > 0。"""
        p = self._payload(0)
        seen: list[str] = []
        for path, arr in iter_structure_arrays(p):
            seen.append(path)
            fields = _anchor_fields_for(path)
            bad = [it for it in arr if (_anchor_of(it, fields) or 0) > 0]
            assert not bad, (
                f"{path} 在 reveal_limit=0 时泄露 {len(bad)}/{len(arr)} 条未来结构，样例={bad[0]}"
            )
        # 派生本身必须有效：真实 fixture 上至少要覆盖到这些已截断的 key，
        # 否则「零条目 → 零断言」会让本测试退化成空转。
        for must in ("bis", "zss", "mmds", "bcs", "zsds", "qsds", "fractals"):
            assert must in seen, f"派生逻辑漏了顶层 key {must}（断言面被架空）"
        assert any(x.startswith("levels.") for x in seen), "派生逻辑漏了 levels 子结构"

    def test_every_payload_key_is_classified(self) -> None:
        """守卫：payload 里**不能出现未分类的 key**。

        断言面是「从响应派生」，但如果有人新增了一个结构 key 而派生函数
        不认识它（比如不是 list[dict]，或挂在 levels 之外的嵌套 dict 里），
        它就会被静默跳过 —— 正是 mmds 漏三轮的复现路径。这里强制每个
        key 都落在「已分类」三类中：结构数组 / 对齐序列 / 显式豁免。
        """
        p = self._payload(0)
        covered = {path for path, _ in iter_structure_arrays(p)}
        for key in p:
            if key in _NON_STRUCTURE_KEYS or key in _ALIGNED_SERIES or key in covered:
                continue
            if key == "levels":
                # levels 的每个子级、每个子 key 都必须被派生或豁免
                for lname, lv in (p[key] or {}).items():
                    if not isinstance(lv, dict):
                        continue
                    for k in lv:
                        assert f"levels.{lname}.{k}" in covered or isinstance(
                            lv[k], int | float | str
                        ), f"levels.{lname}.{k} 未纳入防作弊断言面"
                continue
            val = p[key]
            assert isinstance(val, int | float | str | None) and not isinstance(val, list), (
                f"payload.key `{key}`（{type(val).__name__}）既不在结构断言面、"
                f"也不在豁免清单 —— 请登记到 _NON_STRUCTURE_KEYS 或让它可被派生"
            )

    def test_no_structure_key_leaks_at_mid_reveal(self) -> None:
        """中段揭示（30/50/80）：同样不得有任何条目越过 reveal_limit。"""
        for n in (30, 50, 80):
            p = self._payload(n)
            for path, arr in iter_structure_arrays(p):
                fields = _anchor_fields_for(path)
                bad = [it for it in arr if (_anchor_of(it, fields) or 0) > n]
                assert not bad, f"N={n}: {path} 泄露 {len(bad)}/{len(arr)} 条，样例={bad[0]}"

    def test_aligned_series_never_exceed_bars(self) -> None:
        """macd/boll 与 bars 逐根对齐，长度不得超过 bars（= N+1）。"""
        for n in (0, 30, 50, 80):
            p = self._payload(n)
            nb = len(p["bars"])
            assert nb == n + 1
            for key in _ALIGNED_SERIES:
                val = p.get(key)
                if not isinstance(val, dict):
                    continue
                for k, seq in val.items():
                    if isinstance(seq, list):
                        assert len(seq) <= nb, f"N={n}: {key}.{k} 长度 {len(seq)} > bars {nb}"

    def test_positive_control_full_reveal_has_items(self) -> None:
        """阳性对照：揭示到末尾时结构**必须**还在（修复不能是「一律清空」）。

        取 reveal_limit = len(df)-1（全量揭示）与复盘模式比对，两者结构
        条目数必须完全一致 —— 否则说明截断口径过严，把已揭示的结构也切了。
        """
        n = len(self.df) - 1
        p_full = self._payload(n)
        p_review = self._payload(None)
        assert len(p_full["bars"]) == len(self.df)
        assert p_full["mmds"], "全量揭示时 mmds 不应为空（修复过严？）"
        assert p_full["bis"], "全量揭示时 bis 不应为空（修复过严？）"
        for path, arr in iter_structure_arrays(p_full):
            if path.startswith("levels."):
                _, lname, k = path.split(".")
                other = (p_review.get("levels") or {}).get(lname, {}).get(k, [])
            else:
                other = p_review.get(path, [])
            assert len(arr) == len(other), (
                f"全量揭示（N={n}）时 {path} 有 {len(arr)} 条，"
                f"复盘模式有 {len(other)} 条 —— 截断口径过严"
            )

    def test_positive_control_review_mode_has_future_items(self) -> None:
        """阳性对照 2：复盘模式确实含「reveal_limit=0 之后」的条目。

        这是防「测试恒真」的关键：若复盘模式本身也是空的，那么训练模式的
        「无未来条目」断言毫无意义（数据本来就没内容）。
        """
        p0 = self._payload(0)
        p_review = self._payload(None)
        assert len(p_review["mmds"]) > len(p0["mmds"]), (
            "复盘模式 mmds 应多于训练开局（否则训练模式的空断言是假阳性）"
        )
        assert len(p_review["bis"]) > len(p0["bis"])
        assert len(p_review["bars"]) > len(p0["bars"])

    def test_truncation_monotonic_in_reveal_limit(self) -> None:
        """揭示越深，可见结构单调不减（渐进揭示不会「倒退」丢结构）。"""
        counts = {}
        for n in (0, 30, 50, 80, len(self.df) - 1):
            p = self._payload(n)
            counts[n] = {path: len(arr) for path, arr in iter_structure_arrays(p)}
        keys = set(counts[30]) | set(counts[50]) | set(counts[80])
        for k in keys:
            seq = [counts[n].get(k, 0) for n in (30, 50, 80)]
            assert seq == sorted(seq), f"{k} 随 reveal_limit 增长却变少: {seq}"
