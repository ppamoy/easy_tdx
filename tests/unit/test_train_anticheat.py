

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
        """macd/boll 是对齐 bars 的序列，须切到前 N+1 个点。"""
        for n in (30, 50):
            p = self._payload(n)
            assert len(p["bars"]) == len(self.df)
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
