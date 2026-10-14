"""吴伟志+缠论融合交易系统 — 信号融合层。

将缠论买卖点识别（时机执行层）与吴伟志理论（方向过滤层）融合，
输出"基本面定方向，技术面定时机，制度面定约束"的最终交易信号。
"""
from .hybrid_engine import HybridEngine, HybridResult, ChanlunSignal, FilterResult, ScoreResult  # noqa: F401
