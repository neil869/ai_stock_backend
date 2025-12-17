# AI股票智能分析系统 - 构建与部署指南

## 1. 准备工作

在开始构建之前，请确保以下组件已正确安装和配置：

### 1.1 本地开发环境
- Python 3.8+
- Docker 和 Docker Compose
- Git

### 1.2 腾讯云服务器
- Docker 和 Docker Compose 已安装
- 已开放必要端口：8001（应用访问）、22（SSH）、8080（Jenkins，可选）
- 已创建具有Docker权限的用户（推荐使用root或添加到docker组的用户）

### 1.3 Jenkins服务器
- Jenkins 已安装（可在本地或腾讯云服务器上）
- 必要插件已安装：Docker Pipeline、Git、Pipeline、SSH Agent、GitHub Integration
- Jenkins用户已添加到docker组（允许运行Docker命令）

### 1.4 GitHub仓库
- 项目代码已推送到GitHub仓库
- 已配置SSH密钥（本地和Jenkins服务器）

## 2. 构建前配置

### 2.1 配置SSH密钥

#### 在本地机器上
```bash
# 生成SSH密钥（如果没有）
ssh-keygen -t rsa -b 4096 -C "your_email@example.com"

# 将公钥添加到GitHub
cat ~/.ssh/id_rsa.pub
# 复制内容到GitHub -> Settings -> SSH and GPG keys -> New SSH key
```

#### 在Jenkins服务器上
```bash
# 生成SSH密钥（如果没有）
ssh-keygen -t rsa -b 4096 -C "jenkins@example.com"

# 将公钥添加到GitHub
cat ~/.ssh/id_rsa.pub
# 复制内容到GitHub -> Settings -> SSH and GPG keys -> New SSH key

# 将公钥添加到腾讯云服务器
ssh-copy-id -i ~/.ssh/id_rsa.pub root@43.139.23.170
```

### 2.2 配置Jenkins凭证

1. 登录Jenkins Web界面（http://43.139.23.170:8080）
2. 进入"管理Jenkins" -> "凭证" -> "系统" -> "全局凭证" -> "添加凭证"
3. 选择"SSH Username with private key"
4. 配置：
   - Username: `git`
   - Private Key: 选择"From the Jenkins master ~/.ssh"
   - Key file: `id_rsa`
5. 点击"确定"保存凭证

## 3. Jenkins项目配置

### 3.1 创建Pipeline项目

1. 登录Jenkins，点击"新建任务"
2. 输入任务名称：`ai-stock-backend`
3. 选择"流水线"，点击"确定"

### 3.2 配置项目

在项目配置页面：

#### 3.2.1 常规设置
- 勾选"GitHub项目"，输入GitHub仓库URL：`https://github.com/neil869/ai_stock_backend.git`

#### 3.2.2 构建触发器
- 勾选"GitHub hook trigger for GITScm polling"（启用GitHub Webhook触发）
- （可选）勾选"Poll SCM"，设置定时检查：`H/30 * * * *`（每30分钟检查一次）

#### 3.2.3 流水线配置
- 选择"Pipeline script from SCM"
- SCM选择"Git"
- 输入仓库URL：`git@github.com:neil869/ai_stock_backend.git`（使用SSH URL）
- 选择之前添加的SSH凭证（git）
- 分支指定为：`*/main`（或您的主分支）
- 脚本路径保持：`Jenkinsfile`

#### 3.2.4 保存配置

点击页面底部的"保存"按钮

## 4. GitHub仓库配置

### 4.1 设置Webhook

1. 登录GitHub，进入仓库页面
2. 点击"Settings" -> "Webhooks" -> "Add webhook"
3. 配置：
   - Payload URL: `http://43.139.23.170:8080/github-webhook/`
   - Content type: `application/json`
   - Which events would you like to trigger this webhook?: 选择"Just the push event."
   - 勾选"Active"
4. 点击"Add webhook"保存

## 5. 构建流程

### 5.1 手动触发构建

1. 进入Jenkins项目页面（http://43.139.23.170:8080/job/ai-stock-backend/）
2. 点击"立即构建"
3. 在"构建历史"中点击最新的构建号，查看构建日志

### 5.2 自动触发构建

当您向GitHub仓库推送代码时，Webhook会自动触发Jenkins构建。

## 6. 构建流程详解

Jenkins会执行以下构建步骤：

### 6.1 代码检查
使用flake8检查代码质量：
```bash
pip install flake8
flake8 --max-line-length=120 main.py models.py predict.py
```

### 6.2 单元测试
运行pytest执行单元测试：
```bash
pip install pytest
python -m pytest tests/ -v
```

### 6.3 构建Docker镜像
根据Dockerfile构建Docker镜像：
```bash
docker build -t ai_stock_backend:${BUILD_ID} .
docker tag ai_stock_backend:${BUILD_ID} ai_stock_backend:latest
```

### 6.4 登录腾讯云服务器
使用SSH密钥登录腾讯云服务器：
```bash
ssh -p 22 root@43.139.23.170 'echo 登录成功'
```

### 6.5 部署到腾讯云Docker容器
```bash
# 停止并删除旧容器
ssh -p 22 root@43.139.23.170 'docker stop ai-stock-backend || true'
ssh -p 22 root@43.139.23.170 'docker rm ai-stock-backend || true'

# 传输Docker镜像到腾讯云服务器
docker save ai_stock_backend:${BUILD_ID} | ssh -p 22 root@43.139.23.170 'docker load'

# 运行新容器
ssh -p 22 root@43.139.23.170 'docker run -d --name ai-stock-backend -p 8001:8001 ai_stock_backend:${BUILD_ID}'

# 清理旧镜像
ssh -p 22 root@43.139.23.170 'docker image prune -f'
```

### 6.6 部署验证
```bash
# 等待容器启动
sleep 10

# 检查容器是否运行
ssh -p 22 root@43.139.23.170 'docker ps -f name=ai-stock-backend'

# 测试API是否可用
curl -s -o /dev/null -w '%{http_code}' http://43.139.23.170:8001/health
```

## 7. 验证部署结果

### 7.1 检查应用状态

#### 查看容器状态
```bash
ssh root@43.139.23.170 'docker ps -f name=ai-stock-backend'
```

#### 查看应用日志
```bash
ssh root@43.139.23.170 'docker logs ai-stock-backend'
```

### 7.2 访问应用

应用已部署到：`http://43.139.23.170:8001`

可以通过以下方式访问：
- 浏览器访问：`http://43.139.23.170:8001`
- API测试：`curl http://43.139.23.170:8001/health`（应该返回200状态码）

## 8. 常见问题排查

### 8.1 Jenkins构建失败

#### 问题：无法连接到GitHub仓库
- 检查SSH凭证是否正确
- 确保Jenkins服务器的公钥已添加到GitHub
- 检查网络连接

#### 问题：Docker命令执行失败
- 确保Jenkins用户已添加到docker组
- 检查Docker服务是否运行

#### 问题：无法连接到腾讯云服务器
- 检查腾讯云服务器的IP地址和端口是否正确
- 确保SSH密钥已添加到腾讯云服务器
- 检查防火墙和安全组设置

### 8.2 应用部署失败

#### 问题：容器无法启动
- 查看容器日志：`docker logs ai-stock-backend`
- 检查端口是否被占用：`lsof -i :8001`

#### 问题：API无法访问
- 检查容器是否正在运行：`docker ps`
- 检查端口映射是否正确：`docker port ai-stock-backend`
- 检查应用日志中的错误信息

## 9. 维护与更新

### 9.1 更新应用

1. 修改本地代码
2. 推送到GitHub仓库
3. Jenkins自动触发构建和部署（如果配置了Webhook）
4. 或手动触发Jenkins构建

### 9.2 重启应用
```bash
ssh root@43.139.23.170 'docker restart ai-stock-backend'
```

### 9.3 停止应用
```bash
ssh root@43.139.23.170 'docker stop ai-stock-backend'
```

## 10. 高级配置（可选）

### 10.1 使用私有Docker镜像仓库

1. 修改Jenkinsfile中的DOCKER_REGISTRY配置
2. 在Jenkins服务器上登录镜像仓库
3. 更新构建脚本以推送和拉取镜像

### 10.2 配置环境变量

可以在Jenkinsfile中添加或修改环境变量来配置应用行为：

```groovy
environment {
    // 添加或修改环境变量
    PRODUCTION = 'true'
    LOG_LEVEL = 'INFO'
    DATABASE_URL = 'sqlite:///stocks.db'
}
```

### 10.3 配置通知

可以在Jenkinsfile的post部分添加通知，如邮件、Slack等：

```groovy
post {
    success {
        emailext body: '构建成功！', subject: 'Jenkins构建成功', to: 'your_email@example.com'
    }
    failure {
        emailext body: '构建失败！', subject: 'Jenkins构建失败', to: 'your_email@example.com'
    }
}
```

## 11. 联系信息

如有问题，请随时联系技术支持团队。