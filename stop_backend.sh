#!/bin/bash

# 停止AI股票后端服务的脚本
APP_NAME="ai-stock-backend"

# 检查容器是否在运行
CONTAINER_ID=$(docker ps -q -f name=${APP_NAME})

if [ -z "$CONTAINER_ID" ]; then
    echo "容器 ${APP_NAME} 未在运行！"
    exit 0
fi

echo "正在停止容器 ${APP_NAME} (ID: $CONTAINER_ID)..."

# 停止容器
docker stop ${APP_NAME}

# 检查容器是否已停止
CONTAINER_ID=$(docker ps -q -f name=${APP_NAME})
if [ -z "$CONTAINER_ID" ]; then
    echo "容器 ${APP_NAME} 已成功停止！"
    exit 0
else
    # 如果停止失败，强制停止
    echo "停止失败，正在强制停止..."
    docker kill ${APP_NAME}
    
    # 再次检查
    CONTAINER_ID=$(docker ps -q -f name=${APP_NAME})
    if [ -z "$CONTAINER_ID" ]; then
        echo "容器 ${APP_NAME} 已强制停止！"
        exit 0
    else
        echo "无法停止容器 ${APP_NAME}！"
        exit 1
    fi
fi