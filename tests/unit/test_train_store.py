"""V90 训练成绩持久化（SQLite）：提交 / 排行榜 / 全部 / 清空 单元测试。"""

from __future__ import annotations

from pathlib import Path

from easy_tdx.web.train_store import TrainScore, TrainScoreStore


def _score(**overrides) -> TrainScore:
    base = dict(
        score=18.0,
        player_name="学员甲",
        code="600519",
        market="SH",
        category="DAY",
        count=400,
        total_asked=8,
        hit_count=6,
        hit_rate=75.0,
    )
    base.update(overrides)
    return TrainScore(**base)


def _store(tmp_path: Path) -> TrainScoreStore:
    return TrainScoreStore(tmp_path / "scores.db")


class TestTrainScoreStore:
    def test_add_and_fetch(self, tmp_path):
        s = _store(tmp_path)
        rec = _score()
        s.add(rec)
        assert rec.id
        assert rec.created_at
        rows = s.list_all()
        assert len(rows) == 1
        assert rows[0].player_name == "学员甲"
        assert rows[0].score == 18.0

    def test_leaderboard_sorted_by_score(self, tmp_path):
        s = _store(tmp_path)
        s.add(_score(score=10.0, player_name="低分"))
        s.add(_score(score=30.0, player_name="高分"))
        s.add(_score(score=20.0, player_name="中分"))
        lb = s.leaderboard(limit=10)
        names = [r.player_name for r in lb]
        assert names == ["高分", "中分", "低分"]

    def test_leaderboard_limit_and_category(self, tmp_path):
        s = _store(tmp_path)
        s.add(_score(score=10.0, category="DAY"))
        s.add(_score(score=20.0, category="DAY"))
        s.add(_score(score=30.0, category="WEEK"))
        assert len(s.leaderboard(limit=2)) == 2
        week = s.leaderboard(limit=10, category="WEEK")
        assert [r.player_name for r in week] == ["学员甲"]  # WEEK 只有一条（默认 DAY→WEEK 覆盖）

    def test_clear(self, tmp_path):
        s = _store(tmp_path)
        s.add(_score())
        s.add(_score(score=5.0))
        assert s.clear() == 2
        assert s.list_all() == []

    def test_to_dict_roundtrip(self, tmp_path):
        s = _store(tmp_path)
        rec = _score(extra={"best_streak": 3})
        s.add(rec)
        d = s.list_all()[0].to_dict()
        assert d["extra"] == {"best_streak": 3}
        assert d["hit_rate"] == 75.0
