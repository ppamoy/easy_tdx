#!/usr/bin/env python3
"""V102 补丁脚本：为 diagnosis.py 添加多信号相关性、质量评分卡、决策支持和历史模式匹配字段。"""

import sys

FILE_PATH = "/home/skp/workspace/easy_tdx/src/easy_tdx/web/routers/diagnosis.py"

def apply_patch():
    with open(FILE_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # 检查是否已经应用过 V102 补丁
    if 'v102_multi_signal_correlation' in content and content.count('v102_multi_signal_correlation') >= 2:
        print("V102 补丁已经应用，跳过。")
        return True

    # 补丁 1：在 latest_mmd 部分添加 V102 字段
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
        print("补丁 1 已应用：latest_mmd 部分添加 V102 字段")
    else:
        print("警告：补丁 1 未找到匹配文本，可能已经应用或格式不同。")
        # 尝试备用匹配
        if 'v102_multi_signal_correlation' not in content:
            # 查找其他可能的模式
            import re
            pattern = r'("v82_volatility_compression": getattr\(\s*latest_mmd.*?else None,\s*\}\s*if latest_mmd\s*else None,\s*# V6)'
            match = re.search(pattern, content, re.DOTALL)
            if match:
                print(f"找到匹配模式: {match.group(0)[:100]}...")

    # 补丁 2：在 recent_signals 部分添加 V102 字段（如果还没有）
    old_text2 = '''                            "v82_volatility_compression": getattr(
                                m, "_volatility_compression_breakout_v82", None
                            ),
                        }
                        for m in sorted('''

    new_text2 = '''                            "v82_volatility_compression": getattr(
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
        print("补丁 2 已应用：recent_signals 部分添加 V102 字段")
    else:
        print("警告：补丁 2 未找到匹配文本，可能已经应用。")

    with open(FILE_PATH, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"补丁已写入: {FILE_PATH}")
    return True

if __name__ == "__main__":
    try:
        apply_patch()
        print("补丁应用完成！")
        sys.exit(0)
    except Exception as e:
        print(f"错误: {e}")
        sys.exit(1)
