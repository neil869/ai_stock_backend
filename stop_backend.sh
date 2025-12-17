#!/bin/bash

# 停止AI股票后端服务的脚本

# 检查服务是否在运行
PID=$(lsof -i :8001 -t)

if [ -z "$PID" ]; then
    echo "服务未在运行！"
    exit 0
fi

echo "正在停止服务 (PID: $PID)..."

# 尝试优雅关闭
kill $PID

# 等待服务关闭
sleep 2

# 检查服务是否已关闭
PID=$(lsof -i :8001 -t)
if [ -z "$PID" ]; then
    echo "服务已成功停止！"
    exit 0
else
    # 如果优雅关闭失败，强制关闭
    echo "优雅关闭失败，正在强制停止..."
    kill -9 $PID
    
    # 再次检查
    sleep 1
    PID=$(lsof -i :8001 -t)
    if [ -z "$PID" ]; then
        echo "服务已强制停止！"
        exit 0
    else
        echo "错误：无法停止服务！"
        exit 1
    fi
fi