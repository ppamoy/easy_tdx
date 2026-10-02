

import json
from pathlib import Path

from easy_tdx.chanlun.analyser import ChanlunAnalyser
from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.web.routers.chanlun import build_train_session_payload


class TestTrainAnticheatV731StructureTruncation:
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

    @classmethod
    def setup_class(cls) -> None:
        import pandas as pd

        rows = json.loads(
            (Path(__file__).resolve().parents[1] / "fixtures" / "chanlun_000333_daily.json")
            .read_text(encoding="utf-8")
        )
        cls.df = pd.DataFrame(rows)
        cls.result = ChanlunAnalyser(
            code="000333", frequency="daily", config=ChanlunConfig()
        ).process_klines(cls.df)

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

    def test_review_mode_still_full(self) -> None:
        """对照组：复盘模式（reveal_limit=None）必须仍是全量。"""
        p = self._payload(None)
        full_bis = len(self.result.bis)
        assert len(p["bis"]) == full_bis
        assert len(p["mmd_outcomes"]) == len(self.result.mmds)

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
                "daily", "medium", 0, reveal_limit=n,
            )
            assert len(p["bars"]) == n + 1, f"N={n}: bars 应为 {n+1}，实得 {len(p['bars'])}"

    def test_structure_never_exceeds_bars(self) -> None:
        """结构与 bars 同窗：任何条目索引不得越过 bars 末尾（对位不漂移）。"""
        p = build_train_session_payload(
            TestTrainAnticheatV731StructureTruncation.result,
            TestTrainAnticheatV731StructureTruncation.df,
            "daily", "medium", 0, reveal_limit=50,
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
            "daily", "medium", 0, reveal_limit=87,
        )
        assert len(p0["bars"]) == 88

    def test_review_mode_bars_still_full(self) -> None:
        """对照组：复盘模式 bars 全量。"""
        p = build_train_session_payload(
            TestTrainAnticheatV731StructureTruncation.result,
            TestTrainAnticheatV731StructureTruncation.df,
            "daily", "medium", 0, reveal_limit=None,
        )
        assert len(p["bars"]) == len(TestTrainAnticheatV731StructureTruncation.df)
