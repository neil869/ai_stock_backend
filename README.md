# AI股票后端服务

提供个股预测、全市场扫描、策略回测等服务的后端API。

## 功能特性

- 个股预测：基于AI模型预测股票未来走势
- 全市场扫描：扫描全市场股票，筛选出符合条件的股票
- 策略回测：回测AI策略的历史表现

## 技术栈

- FastAPI：高性能Web框架
- Uvicorn：ASGI服务器
- AkShare：股票数据获取
- LightGBM：机器学习模型
- SnowNLP：中文情感分析
- Baostock：备用股票数据来源

## 打包与部署

### 方法一：使用Docker容器化部署（推荐）

#### 构建Docker镜像

```bash
docker build -t ai-stock-backend .
```

#### 运行Docker容器

```bash
docker run -d -p 8001:8001 --name ai-stock-backend ai-stock-backend
```

### 方法二：使用Docker Compose部署

#### 启动服务

```bash
docker-compose up -d
```

#### 停止服务

```bash
docker-compose down
```

### 方法三：直接运行

#### 创建虚拟环境

```bash
python -m venv venv
source venv/bin/activate  # macOS/Linux
venv\Scripts\activate  # Windows
```

#### 安装依赖

```bash
pip install -r requirements.txt
```

#### 启动服务

```bash
uvicorn main:app --host 0.0.0.0 --port 8001
```

## API文档

服务启动后，可以通过以下地址访问API文档：

- Swagger UI：http://localhost:8001/docs
- ReDoc：http://localhost:8001/redoc

## 项目结构

```
ai_stock_backend/
├── main.py              # FastAPI应用入口
├── models.py            # Pydantic模型定义
├── utils.py             # 工具函数和业务逻辑
├── requirements.txt     # 项目依赖
├── Dockerfile           # Docker镜像构建文件
├── docker-compose.yml   # Docker Compose配置文件
├── stocks_cache.pkl     # 股票列表缓存文件
└── venv/                # Python虚拟环境（可选）
```

## 环境变量

- `PYTHONUNBUFFERED`: 设置为1以确保日志实时输出

## 注意事项

1. 首次启动时，系统会自动获取并缓存股票列表数据
2. 股票预测功能需要从网络获取实时数据
3. 建议使用Docker部署以确保环境一致性