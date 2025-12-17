# macOS 上安装 Docker Desktop 指南

如果您在运行 `docker build` 命令时遇到 `command not found: docker` 错误，说明您的系统上尚未安装 Docker。请按照以下步骤安装 Docker Desktop：

## 安装步骤

### 1. 下载 Docker Desktop

访问 Docker 官方网站下载适用于 macOS 的 Docker Desktop 安装包：

[https://www.docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop)

**注意**：请根据您的 macOS 芯片类型选择正确的版本：
- 如果您的 Mac 使用的是 Apple Silicon 芯片（M1/M2/M3 等），选择 "Mac with Apple Silicon" 版本
- 如果您的 Mac 使用的是 Intel 芯片，选择 "Mac with Intel chip" 版本

### 2. 安装 Docker Desktop

1. 双击下载完成的 `.dmg` 文件
2. 在打开的窗口中，将 Docker 图标拖动到 Applications 文件夹中

### 3. 启动 Docker Desktop

1. 打开 Applications 文件夹
2. 找到并双击 Docker 应用图标
3. Docker Desktop 启动后，会在菜单栏显示一个 Docker 图标
4. 等待 Docker Engine 完全启动（图标变为稳定状态）

### 4. 验证安装

打开终端，运行以下命令验证 Docker 是否安装成功：

```bash
docker --version
```

如果安装成功，您应该会看到类似以下的输出：

```
Docker version 24.0.6, build ed223bc
```

同时，您也可以运行以下命令检查 Docker Compose 是否可用：

```bash
docker-compose --version
```

## 后续步骤

安装 Docker 完成后，您可以继续使用以下命令构建和运行 Docker 容器：

### 构建 Docker 镜像

```bash
docker build -t ai-stock-backend .
```

### 运行 Docker 容器

```bash
docker run -d -p 8001:8001 --name ai-stock-backend ai-stock-backend
```

### 使用 Docker Compose

```bash
docker-compose up -d
```

## 常见问题

### Q: Docker 启动后遇到权限问题怎么办？
A: 请确保您拥有足够的系统权限，并且 Docker Desktop 已经正确安装在 Applications 文件夹中。

### Q: 下载速度很慢怎么办？
A: 您可以考虑使用国内的 Docker 镜像源，或者使用 VPN 提高下载速度。

### Q: 安装完成后仍然显示 "command not found: docker"？
A: 请尝试关闭并重新打开终端窗口，或者重启您的计算机后再试。

如果您遇到其他问题，请参考 Docker 官方文档或搜索相关解决方案。