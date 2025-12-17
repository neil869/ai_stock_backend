# main.py
import logging
import os
from typing import Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from models import PredictRequest, PredictResponse, ScanRequest, BacktestRequest, BacktestResponse, HistoryPredictRequest, HistoryPredictListResponse, UserRegisterRequest, UserLoginRequest, UserResponse, AuthResponse
from predict import predict_signal
from stock_utils import get_all_stocks, get_market_board
from backtest import backtest_ai_strategy_cached
from scheduler import start_scheduled_tasks
from data_fetch import _logout_baostock
from db import query_predict_results, init_db, get_db, create_user, authenticate_user, User

# 配置logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('stock_backend.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI Stock Screener API",
    description="提供个股预测、全市场扫描、策略回测等服务",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# 设置静态文件目录（挂载到/static子路径）
app.mount("/static", StaticFiles(directory="."), name="static")

# CORS（开发用，生产请限制 origin）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    # 初始化数据库
    init_db()
    # 启动定时更新任务
    start_scheduled_tasks()

@app.on_event("shutdown")
def shutdown_event():
    from utils import _logout_baostock
    _logout_baostock()

# 健康检查接口
@app.get("/health", summary="检查API状态", description="简单检查API服务器是否正常运行")
async def health_check():
    return {"message": "AI Stock Screener API is running"}

# 根路径提供H5页面
@app.get("/")
async def read_root():
    with open("index.html", "r", encoding="utf-8") as f:
        html_content = f.read()
    return Response(content=html_content, media_type="text/html")

# 同时支持直接访问index.html
@app.get("/index.html")
async def read_index():
    with open("index.html", "r", encoding="utf-8") as f:
        html_content = f.read()
    return Response(content=html_content, media_type="text/html")

# 用户注册接口
@app.post("/register", response_model=AuthResponse, summary="用户注册", description="创建新用户账号")
async def register_user(req: UserRegisterRequest):
    """
    创建新用户账号
    
    - **username**: 用户名（必填）
    - **password**: 密码（必填）
    - **email**: 电子邮箱（可选）
    
    返回注册结果信息
    """
    logger.info("收到用户注册请求，用户名：%s", req.username)
    
    # 获取数据库会话
    db = next(get_db())
    try:
        success, message = create_user(db, req.username, req.password, req.email)
        if success:
            # 获取创建的用户信息
            user = db.query(User).filter(User.username == req.username).first()
            user_response = UserResponse(
                id=user.id,
                username=user.username,
                email=user.email,
                created_at=user.created_at.strftime("%Y-%m-%d")
            )
            return AuthResponse(success=True, message=message, user=user_response)
        else:
            return AuthResponse(success=False, message=message)
    except Exception as e:
        logger.error("用户注册失败：%s", str(e))
        return AuthResponse(success=False, message="注册失败，请稍后重试")

# 用户登录接口
@app.post("/login", response_model=AuthResponse, summary="用户登录", description="用户账号登录验证")
async def login_user(req: UserLoginRequest):
    """
    用户账号登录验证
    
    - **username**: 用户名（必填）
    - **password**: 密码（必填）
    
    返回登录结果信息和用户数据
    """
    logger.info("收到用户登录请求，用户名：%s", req.username)
    
    # 获取数据库会话
    db = next(get_db())
    try:
        success, user, message = authenticate_user(db, req.username, req.password)
        if success and user:
            user_response = UserResponse(
                id=user.id,
                username=user.username,
                email=user.email,
                created_at=user.created_at.strftime("%Y-%m-%d")
            )
            return AuthResponse(success=True, message=message, user=user_response)
        else:
            return AuthResponse(success=False, message=message)
    except Exception as e:
        logger.error("用户登录失败：%s", str(e))
        return AuthResponse(success=False, message="登录失败，请稍后重试")

@app.post("/predict", response_model=PredictResponse, summary="个股预测", description="基于AI模型预测指定股票的买卖信号和相关指标")
async def predict_stock(req: PredictRequest):
    """
    预测个股的买卖信号和技术指标
    
    - **stock_code**: 股票代码（6位数字，与name参数二选一）
    - **name**: 股票名称（与stock_code参数二选一）
    
    返回包含以下信息的预测结果：
    - 股票基本信息（名称、代码、板块）
    - 价格和预测信号（买入/卖出/持有）
    - 预测概率和情绪分析
    - 技术指标（RSI、布林带、动量等）
    """
    logger.info("收到预测请求，股票代码：%s，股票名称：%s", req.stock_code, req.name)
    if not req.stock_code and not req.name:
        raise HTTPException(status_code=400, detail="必须提供股票代码或股票名称")
    
    if req.stock_code:
        if len(req.stock_code) != 6 or not req.stock_code.isdigit():
            raise HTTPException(status_code=400, detail="无效的股票代码（必须为6位数字）")
        symbol = req.stock_code
        # 如果提供了股票代码和名称，使用提供的名称
        if req.name:
            name = req.name
        else:
            # 从股票数据库中查询真实的股票名称
            try:
                stocks_df = get_all_stocks()
                stock_row = stocks_df[stocks_df['code'] == symbol]
                if not stock_row.empty:
                    name = stock_row.iloc[0]['name']
                else:
                    # 如果找不到，使用股票代码作为默认名称
                    name = symbol
            except Exception as e:
                logger.warning(f"获取股票 {symbol} 的名称失败：{e}")
                # 异常情况下使用股票代码作为默认名称
                name = symbol
    else:
        # 确保name字段不为空
        if not req.name:
            raise HTTPException(status_code=400, detail="当股票代码为空时，必须提供股票名称")
            
        # 根据股票名称获取股票代码
        try:
            stocks_df = get_all_stocks()
            # 优先精确匹配
            exact_match = stocks_df[stocks_df['name'] == req.name]
            if not exact_match.empty:
                matched_stock = exact_match.iloc[0]
            else:
                # 如果没有精确匹配，再尝试模糊匹配
                fuzzy_match = stocks_df[stocks_df['name'].str.contains(req.name, case=False, na=False)]
                logger.info("fuzzy_match: %s", fuzzy_match)
                if fuzzy_match.empty:
                    raise IndexError("No matching stocks found")
                matched_stock = fuzzy_match.iloc[0]
                
            symbol = matched_stock['code']
            name = matched_stock['name']
            logger.info("匹配到股票：%s（%s）", name, symbol)
        except IndexError:
            raise HTTPException(status_code=404, detail=f"未找到股票名称为'{req.name}'的股票")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"查找股票名称时发生错误: {str(e)}")
    
    result = predict_signal(symbol, name)
    if result is None:
        raise HTTPException(status_code=400, detail="数据不足或股票代码无效")
    
    return result

@app.get("/stocks", summary="获取股票列表", description="获取所有A股股票的代码和名称列表，用于前端搜索功能")
async def get_stocks_list(q: Optional[str] = Query(None, description="搜索关键词，支持股票代码或名称模糊匹配")):
    """
    获取所有A股股票的代码和名称列表
    
    - **q**: 可选的搜索关键词，支持股票代码或名称的模糊匹配
    
    返回包含股票代码和名称的列表
    """
    logger.info("收到股票列表请求，搜索关键词：%s", q)
    stocks_df = get_all_stocks()
    
    # 如果有搜索关键词，进行过滤
    if q:
        stocks_df = stocks_df[(stocks_df['code'].str.contains(q)) | (stocks_df['name'].str.contains(q, case=False, na=False))]
    
    # 转换为响应格式
    results = []
    for _, row in stocks_df.iterrows():
        results.append({
            "code": row['code'],
            "name": row['name'],
            "board": get_market_board(row['code'])
        })
    
    return {"stocks": results}

@app.post("/scan", summary="全市场扫描", description="扫描全市场股票，筛选出符合条件的股票")
async def scan_stocks(req: ScanRequest):
    """
    扫描全市场股票，筛选出符合条件的股票
    
    - **max_count**: 最大返回数量
    - **min_prob**: 最小预测概率阈值
    - **board**: 市场板块筛选（全部/主板/创业板/科创板）
    
    返回符合条件的股票列表
    """
    logger.info("收到全市场扫描请求，板块：%s，最大数量：%s，最小概率：%s", req.board, req.max_count, req.min_prob)
    stocks_df = get_all_stocks()
    if req.board != "全部":
        stocks_df = stocks_df[stocks_df['code'].apply(get_market_board) == req.board]

    results = []
    for _, row in stocks_df.iterrows():
        if len(results) >= req.max_count:
            break
        res = predict_signal(row['code'], row['name'])
        if res and res["prob"] >= req.min_prob:
            results.append(res)
        if len(results) >= 100:  # 安全上限
            break

    results.sort(key=lambda x: x["prob"], reverse=True)
    return {"stocks": results[:req.max_count]}

@app.post("/backtest", response_model=BacktestResponse, summary="策略回测", description="回测AI选股策略的历史表现")
async def run_backtest(req: BacktestRequest):
    """
    回测AI选股策略的历史表现
    
    - **top_k**: 每天选择的股票数量
    - **min_prob**: 最小预测概率阈值
    - **board**: 市场板块筛选（全部/主板/创业板/科创板）
    - **lookback_days**: 回测的历史天数
    
    返回策略的历史表现指标
    """
    logger.info(f"收到回测请求，参数：{req}")
    try:
        result = backtest_ai_strategy_cached(
            board_filter=req.board,
            top_k=req.top_k,
            min_prob=req.min_prob,
            lookback_days=req.lookback_days
        )
        return result
    except Exception as e:
        logger.error(f"回测失败：{str(e)}")
        raise HTTPException(status_code=500, detail=f"回测失败：{str(e)}")

@app.post("/history-predict", response_model=HistoryPredictListResponse, summary="历史预测查询", description="查询历史预测结果")
async def get_history_predictions(req: HistoryPredictRequest):
    """
    查询历史预测结果
    
    - **stock_code**: 股票代码（可选）
    - **predict_date**: 预测日期，格式为YYYY-MM-DD（可选）
    - **start_date**: 开始日期，格式为YYYY-MM-DD（可选）
    - **end_date**: 结束日期，格式为YYYY-MM-DD（可选）
    - **limit**: 返回结果的最大数量，默认100（可选）
    
    返回符合条件的历史预测结果列表
    """
    logger.info(f"收到历史预测查询请求，参数：{req}")
    try:
        # 查询历史预测结果
        results = query_predict_results(
            stock_code=req.stock_code,
            predict_date=req.predict_date,
            start_date=req.start_date,
            end_date=req.end_date,
            limit=req.limit
        )
        
        # 转换日期格式
        formatted_results = []
        for result in results:
            # 转换日期对象为字符串
            if hasattr(result['predict_date'], 'strftime'):
                result['predict_date'] = result['predict_date'].strftime('%Y-%m-%d')
            if hasattr(result['created_at'], 'strftime'):
                result['created_at'] = result['created_at'].strftime('%Y-%m-%d')
            if hasattr(result['update_time'], 'strftime'):
                result['update_time'] = result['update_time'].strftime('%Y-%m-%d %H:%M:%S')
            
            # 转换布尔值（如果需要）
            if isinstance(result['price_above_bb_upper'], str):
                result['price_above_bb_upper'] = result['price_above_bb_upper'] == 'Y'
            if isinstance(result['mom_weakening'], str):
                result['mom_weakening'] = result['mom_weakening'] == 'Y'
            
            formatted_results.append(result)
        
        # 返回响应
        return HistoryPredictListResponse(
            total=len(formatted_results),
            predictions=formatted_results
        )
    except Exception as e:
        logger.error(f"查询历史预测结果失败：{str(e)}")
        raise HTTPException(status_code=500, detail=f"查询历史预测结果失败：{str(e)}")