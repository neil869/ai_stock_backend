# AI股票智能分析系统 - 腾讯云服务器部署指南

## 1. 腾讯云服务器准备

### 1.1 购买云服务器
1. 登录腾讯云官网：https://cloud.tencent.com/
2. 进入【云服务器 CVM】控制台，点击【新建】按钮
3. 配置服务器参数：
   - 地域：选择离您最近的地域（如广州、上海）
   - 实例规格：推荐2核4GB或以上配置
   - 镜像：选择 Ubuntu 20.04 LTS 或 CentOS 7.6
   - 存储：系统盘选择 SSD 云硬盘，建议50GB以上
   - 网络：选择默认VPC，分配公网IP
   - 安全组：创建新安全组，开放以下端口：
     - 80 (HTTP)
     - 443 (HTTPS)
     - 8001 (后端服务)
     - 22 (SSH)
4. 设置登录密码，完成购买

### 1.2 连接服务器
使用SSH客户端连接服务器：
```bash
ssh root@您的服务器公网IP
```

## 2. 环境配置

### 2.1 更新系统和安装依赖

#### Ubuntu系统：
```bash
# 更新系统
apt-get update && apt-get upgrade -y

# 安装必要依赖
apt-get install -y python3 python3-pip python3-venv git nginx certbot
```

#### CentOS系统：
```bash
# 更新系统
yum update -y

# 安装必要依赖
yum install -y python3 python3-pip git nginx certbot python3-certbot-nginx
```

### 2.2 创建项目目录和虚拟环境

```bash
# 创建项目目录
mkdir -p /var/www/ai_stock_backend
cd /var/www/ai_stock_backend

# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
source venv/bin/activate
```

## 3. 代码部署

### 3.1 获取项目代码

#### 方法1：使用Git克隆（如果代码在Git仓库）
```bash
git clone <您的代码仓库地址> .
```

#### 方法2：使用SFTP上传（如果代码在本地）
```bash
# 在本地终端执行以下命令上传代码
sftp root@您的服务器公网IP
> put -r /本地项目路径/* /var/www/ai_stock_backend/
```

### 3.2 安装项目依赖

```bash
# 确保已激活虚拟环境
pip install -r requirements.txt
```

## 4. 服务配置

### 4.1 配置Nginx反向代理

创建Nginx配置文件：
```bash
nano /etc/nginx/conf.d/ai_stock_backend.conf
```

添加以下内容（将`your_domain.com`替换为您的域名）：

```nginx
server {
    listen 80;
    server_name your_domain.com;
    root /var/www/ai_stock_backend;
    index index.html;

    location / {
        try_files $uri $uri/ =404;
    }

    # 后端API代理
    location /api/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

测试并启动Nginx：
```bash
# 测试Nginx配置
nginx -t

# 启动Nginx
nginx

# 设置Nginx开机自启
systemctl enable nginx
```

### 4.2 配置SSL证书（可选）

使用Certbot获取免费SSL证书：
```bash
certbot --nginx -d your_domain.com
```

按照提示完成证书申请和自动配置。

### 4.3 配置后端服务为系统服务

创建Systemd服务文件：
```bash
nano /etc/systemd/system/ai_stock_backend.service
```

添加以下内容：

```ini
[Unit]
Description=AI Stock Backend Service
After=network.target

[Service]
User=root
WorkingDirectory=/var/www/ai_stock_backend
ExecStart=/var/www/ai_stock_backend/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8001
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

启动后端服务并设置开机自启：
```bash
# 重新加载Systemd配置
systemctl daemon-reload

# 启动后端服务
systemctl start ai_stock_backend

# 设置开机自启
systemctl enable ai_stock_backend
```

## 5. 服务测试

### 5.1 检查服务状态

```bash
# 检查后端服务状态
systemctl status ai_stock_backend

# 检查Nginx状态
systemctl status nginx
```

### 5.2 访问应用

在浏览器中访问：
- HTTP: http://您的服务器公网IP 或 http://your_domain.com
- HTTPS: https://your_domain.com（如果配置了SSL）

## 6. 日志管理

### 6.1 查看服务日志

```bash
# 查看后端服务日志
journalctl -u ai_stock_backend -f

# 查看Nginx访问日志
tail -f /var/log/nginx/access.log

# 查看Nginx错误日志
tail -f /var/log/nginx/error.log
```

## 7. 常见问题及解决方案

### 7.1 无法访问应用
- 检查服务器安全组是否开放了80和443端口
- 检查Nginx和后端服务是否正常运行
- 检查域名解析是否正确配置

### 7.2 后端服务启动失败
- 查看服务日志：`journalctl -u ai_stock_backend -f`
- 检查端口是否被占用：`netstat -tulpn | grep 8001`
- 检查依赖是否安装完整：`pip install -r requirements.txt`

### 7.3 静态文件无法加载
- 检查Nginx配置中的root路径是否正确
- 确保index.html文件存在于项目根目录

## 8. 更新应用

```bash
# 进入项目目录
cd /var/www/ai_stock_backend

# 激活虚拟环境
source venv/bin/activate

# 获取最新代码
git pull

# 安装新依赖（如果有）
pip install -r requirements.txt

# 重启后端服务
systemctl restart ai_stock_backend

# 重启Nginx（如果需要）
systemctl restart nginx
```

---

部署完成后，您的AI股票智能分析系统就可以在腾讯云服务器上稳定运行了！如果您遇到任何问题，可以参考日志进行排查，或联系腾讯云技术支持。