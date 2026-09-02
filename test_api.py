#!/usr/bin/env python3
"""启动开发服务器并进行基本功能测试。"""

import subprocess
import time
import sys
import os
import urllib.request
import json

def main():
    print("=" * 60)
    print("启动 easy_tdx 开发服务器测试")
    print("=" * 60)
    
    venv_python = "/home/skp/workspace/easy_tdx/.venv/bin/python"
    os.chdir("/home/skp/workspace/easy_tdx")
    
    # 1. 启动后端服务器
    print("\n[1] 启动后端服务器...")
    server_proc = subprocess.Popen(
        [venv_python, "-m", "uvicorn", "easy_tdx.web.app:app", 
         "--host", "0.0.0.0", "--port", "8765", "--log-level", "warning"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # 等待服务器启动
    time.sleep(3)
    
    # 检查服务器是否启动
    try:
        resp = urllib.request.urlopen("http://localhost:8765/api/v1/ping", timeout=5)
        print(f"  服务器已启动，ping 响应: {resp.status}")
    except Exception as e:
        print(f"  服务器启动失败: {e}")
        server_proc.terminate()
        return 1
    
    # 2. 测试缠论分析 API
    print("\n[2] 测试缠论分析 API...")
    try:
        data = json.dumps({
            "market": "SZ",
            "code": "000001",
            "category": "DAY",
            "count": 100,
            "start": 0
        }).encode()
        req = urllib.request.Request(
            "http://localhost:8765/api/v1/chanlun/analyze",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        resp = urllib.request.urlopen(req, timeout=30)
        result = json.loads(resp.read().decode())
        
        # 检查返回结构
        required_keys = ["bis", "xds", "zss", "mmds", "fractals", "bcs", "macd"]
        missing = [k for k in required_keys if k not in result]
        if missing:
            print(f"  警告: 缺少键 {missing}")
        else:
            print(f"  缠论分析成功:")
            print(f"    - K线数: {result.get('kline_count', 'N/A')}")
            print(f"    - 笔数: {len(result.get('bis', []))}")
            print(f"    - 线段数: {len(result.get('xds', []))}")
            print(f"    - 中枢数: {len(result.get('zss', []))}")
            print(f"    - 买卖点数: {len(result.get('mmds', []))}")
            print(f"    - 分型数: {len(result.get('fractals', []))}")
            print(f"    - 背驰数: {len(result.get('bcs', []))}")
            
            # 检查买卖点准确度验证
            if "signal_accuracy" in result and result["signal_accuracy"]:
                summary = result["signal_accuracy"].get("summary", "")
                print(f"    - 准确度验证: {summary[:100]}...")
    except Exception as e:
        print(f"  缠论分析测试失败: {e}")
    
    # 3. 测试多级别分析
    print("\n[3] 测试多级别缠论分析...")
    try:
        data = json.dumps({
            "market": "SZ",
            "code": "000001",
            "category": "DAY",
            "count": 200,
            "start": 0,
            "low_level": "MIN_30"
        }).encode()
        req = urllib.request.Request(
            "http://localhost:8765/api/v1/chanlun/multi-level",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        resp = urllib.request.urlopen(req, timeout=30)
        result = json.loads(resp.read().decode())
        print(f"  多级别分析成功")
        print(f"    - 高级别笔数: {len(result.get('high_level', {}).get('result', {}).get('bis', []))}")
        print(f"    - 低级别笔数: {len(result.get('low_level', {}).get('result', {}).get('bis', []))}")
        confluence = result.get("confluence", {})
        print(f"    - 一致性评分: {confluence.get('score', 'N/A')}")
    except Exception as e:
        print(f"  多级别分析测试失败: {e}")
    
    # 4. 测试推荐 API
    print("\n[4] 测试缠论推荐 API...")
    try:
        data = json.dumps({
            "market": "SZ",
            "code": "000001",
            "category": "DAY",
            "count": 200,
            "start": 0,
            "include_diagnosis": True
        }).encode()
        req = urllib.request.Request(
            "http://localhost:8765/api/v1/chanlun/recommend",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        resp = urllib.request.urlopen(req, timeout=30)
        result = json.loads(resp.read().decode())
        print(f"  推荐 API 成功:")
        print(f"    - 推荐动作: {result.get('action', 'N/A')}")
        print(f"    - 推荐标签: {result.get('action_label', 'N/A')}")
        print(f"    - 净得分: {result.get('net_score', 'N/A')}")
    except Exception as e:
        print(f"  推荐 API 测试失败: {e}")
    
    # 5. 测试前复权 K 线
    print("\n[5] 测试 K 线 API（前复权）...")
    try:
        resp = urllib.request.urlopen(
            "http://localhost:8765/api/v1/bars/SZ/000001/DAY?count=50&adjust=QFQ",
            timeout=10
        )
        result = json.loads(resp.read().decode())
        bars = result.get("bars", [])
        print(f"  K 线 API 成功: 返回 {len(bars)} 根 K 线")
        if bars:
            print(f"    - 最新日期: {bars[-1].get('date', 'N/A')}")
            print(f"    - 最新收盘: {bars[-1].get('close', 'N/A')}")
    except Exception as e:
        print(f"  K 线 API 测试失败: {e}")
    
    # 6. 测试策略列表
    print("\n[6] 测试策略列表 API...")
    try:
        resp = urllib.request.urlopen(
            "http://localhost:8765/api/v1/backtest/strategies",
            timeout=10
        )
        result = json.loads(resp.read().decode())
        strategies = result.get("strategies", [])
        print(f"  策略列表成功: {len(strategies)} 个策略")
        # 检查缠论策略
        chanlun_strategies = [s for s in strategies if "chanlun" in s.get("name", "").lower()]
        print(f"    - 缠论策略: {[s.get('name') for s in chanlun_strategies]}")
    except Exception as e:
        print(f"  策略列表 API 测试失败: {e}")
    
    # 停止服务器
    print("\n[7] 停止服务器...")
    server_proc.terminate()
    server_proc.wait(timeout=5)
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
    return 0

if __name__ == "__main__":
    sys.exit(main())
