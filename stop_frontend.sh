#!/bin/bash

PORT=8080

# 检查是否有进程占用端口
PID=$(lsof -i :$PORT -t)
if [ -z "$PID" ]; then
    echo "前端服务器未在运行"
    exit 0
fi

echo "正在停止前端服务器 (PID: $PID)..."
kill $PID

# 检查是否成功停止
sleep 2
PID=$(lsof -i :$PORT -t)
if [ -z "$PID" ]; then
    echo "前端服务器已成功停止！"
else
    echo "无法停止服务器，正在尝试强制关闭..."
    kill -9 $PID
    sleep 1
    PID=$(lsof -i :$PORT -t)
    if [ -z "$PID" ]; then
        echo "前端服务器已成功停止！"
    else
        echo "服务器停止失败，请手动终止进程"
        exit 1
    fi
fi