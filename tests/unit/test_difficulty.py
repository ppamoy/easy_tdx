"""web/routers/chanlun.py _filter_candidates_by_difficulty 测试（V421）。"""

from __future__ import annotations

from easy_tdx.web.routers.chanlun import _filter_candidates_by_difficulty


def _mmd(idx: int, conf: float) -> dict:
    return {
        "index": idx,
        "kind": "mmd",
        "signal": {"type": "3buy", "confidence": conf},
    }


def _fx(idx: int) -> dict:
    return {"index": idx, "kind": "fractal", "signal": None}


def _cands() -> list[dict]:
    return [
        _mmd(10, 0.9),
        _mmd(20, 0.5),
        _mmd(30, 0.85),
        _fx(40),
        _fx(50),
        _fx(60),
    ]


class TestDifficulty:
    def test_medium_unchanged(self) -> None:
        out = _filter_candidates_by_difficulty(_cands(), "medium", 0)
        assert len(out) == 6

    def test_easy_only_high_conf(self) -> None:
        out = _filter_candidates_by_difficulty(_cands(), "easy", 0)
        mmds = [c for c in out if c["kind"] == "mmd"]
        assert all(c["signal"]["confidence"] >= 0.8 for c in mmds)
        assert len(mmds) == 2  # 0.9 + 0.85

    def test_hard_only_low_conf(self) -> None:
        out = _filter_candidates_by_difficulty(_cands(), "hard", 0)
        mmds = [c for c in out if c["kind"] == "mmd"]
        assert all(c["signal"]["confidence"] < 0.75 for c in mmds)
        assert len(mmds) == 1  # 仅 0.5

    def test_seed_reproducible(self) -> None:
        a = _filter_candidates_by_difficulty(_cands(), "hard", 7)
        b = _filter_candidates_by_difficulty(_cands(), "hard", 7)
        assert a == b

    def test_invalid_difficulty_falls_back_medium(self) -> None:
        out = _filter_candidates_by_difficulty(_cands(), "nope", 0)
        assert len(out) == 6
