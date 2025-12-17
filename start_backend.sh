#!/bin/bash

# 启动AI股票后端服务的脚本
# 该脚本使用Docker容器启动服务

# 切换到项目目录
cd "$(dirname "$0")"

# 检查Docker是否可用
if ! command -v docker &> /dev/null; then
    echo "错误: Docker未安装或不可用！"
    echo "请先安装Docker和Docker Compose，参考DOCKER_DEPLOYMENT.md文件"
    exit 1
fi

# 检查Docker Compose是否可用
if ! command -v docker-compose &> /dev/null; then
    echo "错误: Docker Compose未安装或不可用！"
    echo "请先安装Docker Compose，参考DOCKER_DEPLOYMENT.md文件"
    exit 1
fi

APP_NAME="ai-stock-backend"

# 检查容器是否已经在运行
CONTAINER_ID=$(docker ps -q -f name=${APP_NAME})

if [ -n "$CONTAINER_ID" ]; then
    echo "容器 ${APP_NAME} 已经在运行 (ID: $CONTAINER_ID)！"
    echo "服务可访问地址: http://localhost:8001"
    echo "健康检查地址: http://localhost:8001/health"
    exit 0
fi

# 检查是否有已停止的容器
STOPPED_CONTAINER=$(docker ps -aq -f name=${APP_NAME})

if [ -n "$STOPPED_CONTAINER" ]; then
    echo "正在启动已停止的容器 ${APP_NAME}..."
    docker start ${APP_NAME}
else
    echo "正在创建并启动新容器 ${APP_NAME}..."
    docker-compose -f docker-compose.prod.yml up -d
fi

# 等待服务启动并添加重试机制
MAX_RETRIES=5
RETRY_INTERVAL=2

for i in $(seq 1 $MAX_RETRIES); do
    echo "等待服务启动... (第 $i/$MAX_RETRIES 次尝试)"
    sleep $RETRY_INTERVAL
    
    # 检查服务是否启动成功
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/health | grep -q "200"; then
        echo "容器 ${APP_NAME} 已成功启动！"
        echo "服务可访问地址: http://localhost:8001"
        echo "健康检查地址: http://localhost:8001/health"
        exit 0
    fi

done

echo "容器 ${APP_NAME} 启动失败！"
echo "请检查日志: docker logs ${APP_NAME}"
exit 1