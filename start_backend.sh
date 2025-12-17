#!/bin/bash

# 启动AI股票后端服务的脚本
# 该脚本使用nohup在后台运行服务，输出日志到backend.log文件

# 切换到项目目录
cd "$(dirname "$0")"

# 检查虚拟环境是否存在
if [ ! -d "venv" ]; then
    echo "错误: 虚拟环境不存在！"
    echo "请先创建并激活虚拟环境，安装依赖："
    echo "python3 -m venv venv"
    echo "source venv/bin/activate"
    echo "pip install -r requirements.txt"
    exit 1
fi

# 激活虚拟环境
source venv/bin/activate

# 检查依赖是否安装
if ! command -v uvicorn &> /dev/null; then
    echo "错误: uvicorn未安装！"
    echo "请先安装依赖："
    echo "pip install -r requirements.txt"
    exit 1
fi

# 停止已运行的服务（如果存在）
PID=$(lsof -i :8001 -t)
if [ ! -z "$PID" ]; then
    echo "发现已运行的服务，正在停止..."
    kill -9 $PID
fi

# 使用nohup在后台运行服务（调试模式）
echo "正在启动服务..."
nohup python -m debugpy --listen 0.0.0.0:5678 -m uvicorn main:app --host 0.0.0.0 --port 8001 --log-level debug > backend.log 2>&1 &

# 等待服务启动并添加重试机制
MAX_RETRIES=5
RETRY_INTERVAL=2

for i in $(seq 1 $MAX_RETRIES); do
    echo "等待服务启动... (第 $i/$MAX_RETRIES 次尝试)"
    sleep $RETRY_INTERVAL
    
    # 检查服务是否启动成功
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/ | grep -q "200"; then
        echo "服务启动成功！"
        echo "服务地址: http://localhost:8001"
        echo "API文档: http://localhost:8001/docs"
        echo "日志文件: backend.log"
        echo ""
        echo "使用以下命令停止服务:"
        echo "kill $(lsof -i :8001 -t)"
        exit 0
    fi
done

# 所有尝试都失败
echo "服务启动失败！"
echo "请查看日志文件: backend.log"
exit 1