# AI股票智能分析系统 - Docker容器部署指南

## 1. 系统要求

- Docker 20.10+ 
- Docker Compose 1.29+
- 至少2GB可用内存
- 至少10GB可用磁盘空间

## 2. Docker环境安装

### 2.1 Ubuntu系统安装Docker

```bash
# 更新系统
apt-get update && apt-get upgrade -y

# 安装依赖
apt-get install -y apt-transport-https ca-certificates curl gnupg-agent software-properties-common

# 添加Docker官方GPG密钥
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | apt-key add -

# 添加Docker官方仓库
add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"

# 安装Docker和Docker Compose
apt-get update && apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose

# 启动Docker服务
systemctl start docker

# 设置Docker开机自启
systemctl enable docker

# 验证安装
docker --version
docker-compose --version
```

### 2.2 CentOS系统安装Docker

```bash
# 更新系统
yum update -y

# 安装依赖
yum install -y yum-utils device-mapper-persistent-data lvm2

# 添加Docker官方仓库
yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo

# 安装Docker和Docker Compose
yum install -y docker-ce docker-ce-cli containerd.io docker-compose

# 启动Docker服务
systemctl start docker

# 设置Docker开机自启
systemctl enable docker

# 验证安装
docker --version
docker-compose --version
```

### 2.3 Windows系统安装Docker

1. 下载Docker Desktop for Windows: https://www.docker.com/products/docker-desktop
2. 运行安装程序，按照提示完成安装
3. 启动Docker Desktop
4. 验证安装：在命令提示符或PowerShell中执行
   ```bash
   docker --version
   docker-compose --version
   ```

### 2.4 macOS系统安装Docker

1. 下载Docker Desktop for Mac: https://www.docker.com/products/docker-desktop
2. 运行安装程序，按照提示完成安装
3. 启动Docker Desktop
4. 验证安装：在终端中执行
   ```bash
   docker --version
   docker-compose --version
   ```

## 3. 部署步骤

### 3.1 获取项目代码

```bash
# 克隆代码仓库（如果代码在Git仓库）
git clone <您的代码仓库地址> ai_stock_backend
cd ai_stock_backend

# 或者直接进入已有的项目目录
cd /path/to/ai_stock_backend
```

### 3.2 构建Docker镜像

```bash
# 使用Docker Compose构建镜像
docker-compose build

# 或者使用Docker命令直接构建
docker build -t ai-stock-backend .
```

### 3.3 启动Docker容器

#### 方法1：使用Docker Compose（推荐）

```bash
# 启动容器（后台运行）
docker-compose up -d

# 查看容器状态
docker-compose ps

# 查看日志
docker-compose logs -f
```

#### 方法2：使用Docker命令直接启动

```bash
# 启动容器（后台运行）
docker run -d \
  --name ai-stock-backend \
  -p 8001:8001 \
  -v $(pwd)/stocks_cache.pkl:/app/stocks_cache.pkl \
  -v $(pwd)/predict_cache.pkl:/app/predict_cache.pkl \
  -e PYTHONUNBUFFERED=1 \
  --restart unless-stopped \
  ai-stock-backend

# 查看容器状态
docker ps

# 查看日志
docker logs -f ai-stock-backend
```

### 3.4 访问应用

在浏览器中访问：
- 后端API: http://localhost:8001
- API文档: http://localhost:8001/docs
- 前端应用: http://localhost:8001/static/index.html

## 4. 容器管理命令

### 4.1 停止容器

```bash
# 使用Docker Compose
docker-compose down

# 使用Docker命令
docker stop ai-stock-backend
```

### 4.2 重启容器

```bash
# 使用Docker Compose
docker-compose restart

# 使用Docker命令
docker restart ai-stock-backend
```

### 4.3 进入容器

```bash
# 使用Docker Compose
docker-compose exec ai-stock-backend bash

# 使用Docker命令
docker exec -it ai-stock-backend bash
```

### 4.4 查看容器资源使用情况

```bash
docker stats ai-stock-backend
```

## 5. 数据持久化

当前配置已挂载以下文件用于数据持久化：

- `stocks_cache.pkl`: 股票数据缓存文件
- `predict_cache.pkl`: 预测结果缓存文件（可选，需在docker-compose.yml中添加）

如需添加更多持久化文件，可在docker-compose.yml中添加相应的volume配置：

```yaml
volumes:
  - ./stocks_cache.pkl:/app/stocks_cache.pkl
  - ./predict_cache.pkl:/app/predict_cache.pkl
  - ./your_file:/app/your_file
```

## 6. 配置修改

### 6.1 修改端口映射

如果需要使用不同的端口，可以修改docker-compose.yml文件中的ports配置：

```yaml
ports:
  - "8080:8001"  # 将容器的8001端口映射到主机的8080端口
```

### 6.2 添加环境变量

如需添加环境变量，可以在docker-compose.yml文件中添加相应的配置：

```yaml
environment:
  - PYTHONUNBUFFERED=1
  - YOUR_ENV_VAR=your_value
```

## 7. 常见问题及解决方案

### 7.1 端口被占用

如果8001端口已被占用，可以修改docker-compose.yml文件中的端口映射：

```yaml
ports:
  - "8080:8001"  # 使用8080端口替代8001端口
```

### 7.2 镜像构建失败

- 检查网络连接是否正常
- 检查requirements.txt文件是否存在且格式正确
- 检查Dockerfile是否存在语法错误

### 7.3 容器启动失败

- 查看日志获取详细错误信息：`docker-compose logs -f`
- 检查端口是否被占用
- 检查挂载的文件或目录权限是否正确

### 7.4 无法访问应用

- 检查容器是否正常运行：`docker-compose ps`
- 检查防火墙是否开放了相应端口
- 检查主机IP和端口是否正确

## 8. 升级应用

```bash
# 停止并删除旧容器
docker-compose down

# 更新代码
git pull

# 重新构建镜像
docker-compose build

# 启动新容器
docker-compose up -d
```

## 9. Docker Compose配置详解

```yaml
version: '3.8'  # Docker Compose版本

services:  # 定义服务
  ai-stock-backend:  # 服务名称
    build: .  # 使用当前目录的Dockerfile构建镜像
    container_name: ai-stock-backend  # 容器名称
    ports:  # 端口映射
      - "8001:8001"  # 主机端口:容器端口
    volumes:  # 数据卷挂载
      - ./stocks_cache.pkl:/app/stocks_cache.pkl  # 主机文件:容器文件
    environment:  # 环境变量
      - PYTHONUNBUFFERED=1  # 确保Python输出实时显示
    restart: unless-stopped  # 重启策略：除非手动停止，否则自动重启
```

---

Docker容器部署完成后，您的AI股票智能分析系统就可以在Docker环境中稳定运行了！如果您遇到任何问题，可以参考日志信息进行排查，或查阅Docker官方文档获取更多帮助。