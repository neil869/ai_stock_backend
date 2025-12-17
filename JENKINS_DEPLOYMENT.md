# Jenkins自动化部署指南

## 1. 腾讯云服务器准备工作

### 1.1 服务器基本配置

按照之前的 `DEPLOY_TENCENT_CLOUD.md` 配置服务器：
- 操作系统：Ubuntu 20.04 LTS 或 CentOS 7/8
- 实例规格：至少 2核4G
- 安全组开放端口：
  - 22 (SSH)
  - 80 (HTTP)
  - 443 (HTTPS, 可选)
  - 8080 (Jenkins, 初始访问端口)
  - 8001 (应用服务端口)

### 1.2 系统环境配置

#### Ubuntu系统
```bash
# 更新系统软件包
sudo apt update && sudo apt upgrade -y

# 安装基本工具
sudo apt install -y git curl wget unzip
```

#### CentOS系统
```bash
# 更新系统软件包
sudo yum update -y

# 安装基本工具
sudo yum install -y git curl wget unzip
```

## 2. Docker和Docker Compose安装

按照之前的 `DOCKER_DEPLOYMENT.md` 安装Docker环境：

### Ubuntu系统
```bash
# 安装Docker
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 安装Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.3/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

### CentOS系统
```bash
# 安装Docker
sudo yum install -y yum-utils
sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
sudo yum install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

sudo systemctl start docker
sudo systemctl enable docker

# 安装Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.3/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

### 验证安装
```bash
docker --version
docker-compose --version
```

## 3. Jenkins安装和配置

### 3.1 安装Jenkins

#### Ubuntu系统
```bash
# 安装Java 11
sudo apt install -y openjdk-11-jdk

# 安装Jenkins
wget -q -O - https://pkg.jenkins.io/debian-stable/jenkins.io.key | sudo apt-key add -
sudo sh -c 'echo deb https://pkg.jenkins.io/debian-stable binary/ > /etc/apt/sources.list.d/jenkins.list'
sudo apt update
sudo apt install -y jenkins

# 启动Jenkins服务
sudo systemctl start jenkins
sudo systemctl enable jenkins
```

#### CentOS系统
```bash
# 安装Java 11
sudo yum install -y java-11-openjdk-devel

# 安装Jenkins
sudo wget -O /etc/yum.repos.d/jenkins.repo https://pkg.jenkins.io/redhat-stable/jenkins.repo
sudo rpm --import https://pkg.jenkins.io/redhat-stable/jenkins.io-2023.key
sudo yum install -y jenkins

# 启动Jenkins服务
sudo systemctl start jenkins
sudo systemctl enable jenkins
```

### 3.2 初始配置Jenkins

1. 访问Jenkins Web界面：`http://你的服务器IP:8080`
2. 获取初始管理员密码：
   ```bash
   sudo cat /var/lib/jenkins/secrets/initialAdminPassword
   ```
3. 安装推荐的插件
4. 创建管理员用户
5. 完成Jenkins配置

### 3.3 安装必要插件

在Jenkins管理界面 -> 插件管理 -> 可用插件中安装以下插件：
- Docker Pipeline
- Git
- Pipeline
- SSH Agent
- GitHub Integration

### 3.4 配置Docker权限

将Jenkins用户添加到docker组，以便Jenkins可以运行Docker命令：
```bash
sudo usermod -aG docker jenkins
sudo systemctl restart jenkins
```

## 4. 项目配置和构建

### 4.1 创建Jenkins Pipeline项目

1. 登录Jenkins，点击"新建任务"
2. 输入任务名称（如 `ai-stock-backend`）
3. 选择"流水线"，点击"确定"

### 4.2 配置Pipeline

在项目配置页面：

1. **常规设置**：
   - 勾选"GitHub项目"，输入GitHub仓库URL

2. **流水线配置**：
   - 选择"Pipeline script from SCM"
   - SCM选择"Git"
   - 输入仓库URL：`git@github.com:neil869/ai_stock_backend.git`（使用SSH URL）
   - 选择SSH凭证（如果没有，需要添加）
   - 分支指定为 `*/main`
   - 脚本路径保持 `Jenkinsfile`

3. 保存配置

### 4.3 添加SSH凭证

1. 进入Jenkins管理界面 -> 凭证 -> 系统 -> 全局凭证 -> 添加凭证
2. 选择"SSH Username with private key"
3. Username输入 `git`
4. Private Key选择"From the Jenkins master ~/.ssh"
5. Key file输入 `id_rsa`（或其他SSH私钥文件）
6. 保存凭证

## 5. 自动化部署流程

### 5.1 手动触发构建

1. 进入Jenkins项目页面
2. 点击"立即构建"
3. 查看构建日志，监控构建过程

### 5.2 配置自动构建（可选）

在项目配置页面 -> 构建触发器：

1. **GitHub hook trigger for GITScm polling**：当GitHub有push事件时自动触发构建
2. **Poll SCM**：定时检查代码更新，如 `H/30 * * * *`（每30分钟检查一次）

### 5.3 构建流程详解

Jenkins将执行以下步骤：

1. **代码检查**：使用flake8检查代码质量
2. **单元测试**：运行pytest执行单元测试
3. **构建Docker镜像**：根据项目根目录的Dockerfile构建镜像
4. **登录腾讯云服务器**：使用SSH密钥认证登录服务器
5. **部署到腾讯云Docker容器**：
   - 停止并删除旧容器
   - 传输Docker镜像到服务器
   - 运行新容器
   - 清理旧镜像
6. **部署验证**：
   - 检查容器是否正常运行
   - 测试API是否可用

## 6. 部署后管理

### 6.1 查看容器状态

```bash
docker ps
# 或
docker-compose -f docker-compose.prod.yml ps
```

### 6.2 查看应用日志

```bash
docker logs ai-stock-backend
# 或
docker-compose -f docker-compose.prod.yml logs
```

### 6.3 重启应用

```bash
docker restart ai-stock-backend
# 或
docker-compose -f docker-compose.prod.yml restart
```

### 6.4 更新应用

1. 推送代码到GitHub仓库
2. Jenkins自动触发构建和部署
3. 或手动触发Jenkins构建

## 7. 常见问题排查

### 7.1 Jenkins构建失败

- 查看构建日志，定位错误原因
- 检查Docker镜像构建是否成功
- 检查SSH连接是否正常
- 检查服务器上的Docker权限

### 7.2 应用无法访问

- 检查服务器安全组是否开放了8001端口
- 检查容器是否正常运行
- 查看应用日志，检查是否有启动错误

### 7.3 Docker容器启动失败

```bash
# 查看详细的容器启动日志
docker logs ai-stock-backend
```

## 8. 优化建议

1. **使用私有Docker镜像仓库**：如腾讯云镜像仓库，提高镜像传输速度
2. **配置HTTPS**：使用Nginx反向代理并配置SSL证书
3. **添加监控**：如Prometheus + Grafana监控应用和服务器状态
4. **配置日志收集**：如ELK Stack收集和分析应用日志
5. **自动备份**：定期备份数据库和关键配置文件

## 9. 联系方式

如有问题，请联系技术支持团队。