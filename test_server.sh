#!/bin/bash
# 启动开发服务器并测试

set -e

cd /home/skp/workspace/easy_tdx

echo "=== 启动后端开发服务器 ==="
# 后台启动 fastapi 服务器
.venv/bin/python -m uvicorn easy_tdx.web.app:app --host 0.0.0.0 --port 8000 --reload &
SERVER_PID=$!
echo "后端 PID: $SERVER_PID"

# 等待服务器启动
sleep 3

echo ""
echo "=== 测试后端 API ==="
curl -s http://localhost:8000/api/v1/ping || echo "API 测试失败"

echo ""
echo "=== 测试缠论分析 API ==="
curl -s -X POST http://localhost:8000/api/v1/chanlun/analyze \
  -H "Content-Type: application/json" \
  -d '{"market":"SZ","code":"000001","category":"DAY","count":100,"start":0}' | head -c 500 || echo "缠论 API 测试失败"

echo ""
echo "=== 测试前端构建 ==="
cd web-ui
npm run build 2>&1 | tail -20

echo ""
echo "=== 停止服务器 ==="
kill $SERVER_PID 2>/dev/null || true

echo ""
echo "=== 测试完成 ==="
