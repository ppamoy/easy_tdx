"""web/train_store.py V424 difficulty/进度/汇总/筛选 测试。"""

from __future__ import annotations

from pathlib import Path

from easy_tdx.web.train_store import TrainScore, TrainScoreStore


def _rec(store: TrainScoreStore, player: str, cat: str, diff: str, score: float, hit: float) -> TrainScore:
    r = TrainScore(
        player_name=player,
        category=cat,
        difficulty=diff,
        score=score,
        hit_rate=hit,
        total_asked=10,
        hit_count=int(hit / 100 * 10),
    )
    return store.add(r)


class TestTrainStoreV424:
    def test_difficulty_persisted(self, tmp_path: Path) -> None:
        store = TrainScoreStore(tmp_path / "s.db")
        rec = _rec(store, "甲", "DAY", "hard", 10, 60)
        rows = store.leaderboard(difficulty="hard")
        assert len(rows) == 1
        assert rows[0].difficulty == "hard"
        assert rows[0].player_name == "甲"

    def test_leaderboard_filter(self, tmp_path: Path) -> None:
        store = TrainScoreStore(tmp_path / "s.db")
        _rec(store, "甲", "DAY", "easy", 10, 80)
        _rec(store, "乙", "DAY", "hard", 20, 50)
        _rec(store, "丙", "MIN_5", "hard", 30, 90)
        assert len(store.leaderboard(difficulty="hard")) == 2
        assert len(store.leaderboard(category="DAY", difficulty="hard")) == 1
        assert len(store.leaderboard(category="DAY")) == 2

    def test_summary(self, tmp_path: Path) -> None:
        store = TrainScoreStore(tmp_path / "s.db")
        _rec(store, "甲", "DAY", "easy", 10, 80)
        _rec(store, "乙", "DAY", "easy", 20, 60)
        s = store.summary(difficulty="easy")
        assert s["count"] == 2
        assert s["avg_hit_rate"] == 70.0
        assert s["max_score"] == 20.0

    def test_progress_matrix(self, tmp_path: Path) -> None:
        store = TrainScoreStore(tmp_path / "s.db")
        _rec(store, "甲", "DAY", "easy", 10, 80)
        _rec(store, "甲", "DAY", "hard", 20, 50)
        _rec(store, "甲", "MIN_5", "easy", 30, 90)
        _rec(store, "乙", "DAY", "easy", 40, 70)
        data = store.progress("甲")
        assert "recent" in data
        matrix = data["matrix"]
        assert "DAY" in matrix
        assert "easy" in matrix["DAY"]
        assert matrix["DAY"]["easy"]["rounds"] == 1
        assert matrix["DAY"]["hard"]["hit_rate"] == 50.0
        assert "MIN_5" in matrix

    def test_legacy_db_migration(self, tmp_path: Path) -> None:
        # 模拟旧库（无 difficulty 列），确保迁移幂等
        import sqlite3

        db = tmp_path / "legacy.db"
        conn = sqlite3.connect(db)
        conn.execute(
            "CREATE TABLE train_scores (id TEXT PRIMARY KEY, player_name TEXT, "
            "score REAL, hit_rate REAL, total_asked INTEGER, hit_count INTEGER, "
            "code TEXT, market TEXT, category TEXT, count INTEGER, created_at TEXT, extra TEXT)"
        )
        conn.commit()
        conn.close()
        store = TrainScoreStore(db)  # 迁移应补 difficulty 列
        rec = TrainScore(player_name="甲", score=1.0, hit_rate=50.0, difficulty="easy")
        store.add(rec)
        assert store.leaderboard(difficulty="easy")[0].difficulty == "easy"
