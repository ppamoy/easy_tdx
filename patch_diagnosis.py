#!/usr/bin/env python3
"""Patch diagnosis.py to add V102 fields."""

import re

file_path = "/home/skp/workspace/easy_tdx/src/easy_tdx/web/routers/diagnosis.py"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Find and replace the first occurrence (latest_mmd section)
old_text1 = '''                        "v82_volatility_compression": getattr(
                            latest_mmd, "_volatility_compression_breakout_v82", None
                        )
                        if latest_mmd
                        else None,
                    }
                    if latest_mmd
                    else None,
                    # V6: 最近3个高质量买卖点'''

new_text1 = '''                        "v82_volatility_compression": getattr(
                            latest_mmd, "_volatility_compression_breakout_v82", None
                        )
                        if latest_mmd
                        else None,
                        # V102 缠论决策支持增强（条件264-267）
                        "v102_multi_signal_correlation": getattr(
                            latest_mmd, "_multi_signal_correlation", None
                        )
                        if latest_mmd
                        else None,
                        "v102_signal_quality": getattr(
                            latest_mmd, "_signal_quality_scorecard", None
                        )
                        if latest_mmd
                        else None,
                        "v102_decision_support": getattr(
                            latest_mmd, "_decision_support", None
                        )
                        if latest_mmd
                        else None,
                        "v102_pattern_match": getattr(
                            latest_mmd, "_historical_pattern_match", None
                        )
                        if latest_mmd
                        else None,
                    }
                    if latest_mmd
                    else None,
                    # V6: 最近3个高质量买卖点'''

if old_text1 in content:
    content = content.replace(old_text1, new_text1, 1)
    print("Patched first occurrence (latest_mmd)")
else:
    print("ERROR: First patch not found")

# Find and replace the second occurrence (recent_signals section) - already done
# Check if V102 is already in recent_signals
if 'v102_multi_signal_correlation' not in content or content.count('v102_multi_signal_correlation') < 2:
    old_text2 = '''                            # V82 缠论增强条件（条件260-263）
                            "v82_age_decay": getattr(m, "_mmd_age_decay_v82", None),
                            "v82_breakout_retest": getattr(m, "_breakout_retest_confirm_v82", None),
                            "v82_macd_resonance": getattr(m, "_macd_multi_tf_resonance_v82", None),
                            "v82_volatility_compression": getattr(
                                m, "_volatility_compression_breakout_v82", None
                            ),
                        }
                        for m in sorted('''
    
    new_text2 = '''                            # V82 缠论增强条件（条件260-263）
                            "v82_age_decay": getattr(m, "_mmd_age_decay_v82", None),
                            "v82_breakout_retest": getattr(m, "_breakout_retest_confirm_v82", None),
                            "v82_macd_resonance": getattr(m, "_macd_multi_tf_resonance_v82", None),
                            "v82_volatility_compression": getattr(
                                m, "_volatility_compression_breakout_v82", None
                            ),
                            # V102 缠论决策支持增强（条件264-267）
                            "v102_multi_signal_correlation": getattr(m, "_multi_signal_correlation", None),
                            "v102_signal_quality": getattr(m, "_signal_quality_scorecard", None),
                            "v102_decision_support": getattr(m, "_decision_support", None),
                            "v102_pattern_match": getattr(m, "_historical_pattern_match", None),
                        }
                        for m in sorted('''
    
    if old_text2 in content:
        content = content.replace(old_text2, new_text2, 1)
        print("Patched second occurrence (recent_signals)")
    else:
        print("ERROR: Second patch not found")

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Done!")
