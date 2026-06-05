#!/bin/bash
# start_server.sh — 启动 ProjectMgr Web 服务（自动清理旧进程）
set -e

HOST="127.0.0.1"
PORT=8000

# 1. 杀死占用端口的旧进程
OLD_PID=$(lsof -ti :"$PORT" 2>/dev/null || true)
if [ -n "$OLD_PID" ]; then
    echo "🔴 正在停止旧进程 (PID: $OLD_PID) ..."
    kill "$OLD_PID" 2>/dev/null || true
    # 等待端口释放（最多 5 秒）
    for i in $(seq 1 5); do
        if ! lsof -ti :"$PORT" >/dev/null 2>&1; then
            break
        fi
        sleep 1
    done
fi

# 2. 启动新服务
cd "$(dirname "$0")/.."
echo "🟢 启动服务 http://${HOST}:${PORT} ..."
python3 -c "
from app.server import serve
serve()
" 2>&1 &
NEW_PID=$!

# 3. 等待启动确认
sleep 3
if lsof -ti :"$PORT" >/dev/null 2>&1; then
    echo "✅ 服务已启动 (PID: $NEW_PID)"
    echo "   访问 http://${HOST}:${PORT}"
else
    echo "❌ 服务启动失败，请检查日志"
    exit 1
fi
