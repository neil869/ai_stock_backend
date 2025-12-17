# models.py
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List

class PredictRequest(BaseModel):
    """个股预测请求模型"""
    stock_code: Optional[str] = Field(None, description="股票代码（6位数字，与name二选一）")
    name: Optional[str] = Field(None, description="股票名称（与stock_code二选一）")
    
    model_config = ConfigDict(json_schema_extra={"example": {"stock_code": "600000", "name": "浦发银行"}})

class PredictResponse(BaseModel):
    """个股预测响应模型"""
    name: str = Field(..., description="股票名称")
    stock_code: str = Field(..., description="股票代码")
    board: str = Field(..., description="市场板块")
    price: float = Field(..., description="当前价格")
    signal: str = Field(..., description="预测信号（买入/卖出/持有）")
    prob: float = Field(..., description="预测概率")
    sentiment_label: str = Field(..., description="情感分析标签")
    sentiment_score: float = Field(..., description="情感分析分数")
    date: str = Field(..., description="数据日期")
    rsi: float = Field(..., description="相对强弱指标")
    price_above_bb_upper: bool = Field(..., description="价格是否突破布林带上轨")
    mom_weakening: bool = Field(..., description="动量是否减弱")
    drawdown_5d: float = Field(..., description="5日回撤")
    reason: str = Field(..., description="预测理由")

class ScanRequest(BaseModel):
    """全市场扫描请求模型"""
    min_prob: float = Field(55.0, description="最小预测概率阈值")
    max_count: int = Field(20, description="返回结果的最大数量")
    board: str = Field("全部", description="市场板块筛选")
    
    model_config = ConfigDict(json_schema_extra={"example": {"min_prob": 60.0, "max_count": 10, "board": "主板"}})

class BacktestRequest(BaseModel):
    """策略回测请求模型"""
    top_k: int = Field(5, description="每天选择的股票数量")
    min_prob: float = Field(55.0, description="最小预测概率阈值")
    board: str = Field("全部", description="市场板块筛选")
    lookback_days: int = Field(120, description="回测的历史天数")
    
    model_config = ConfigDict(json_schema_extra={"example": {"top_k": 5, "min_prob": 58.0, "board": "创业板", "lookback_days": 60}})

class BacktestResponse(BaseModel):
    """策略回测响应模型"""
    total_return: float = Field(..., description="总收益率")
    annualized_return: float = Field(..., description="年化收益率")
    sharpe: float = Field(..., description="夏普比率")
    max_drawdown: float = Field(..., description="最大回撤")
    win_rate: float = Field(..., description="胜率")

class HistoryPredictRequest(BaseModel):
    """历史预测结果查询请求模型"""
    stock_code: Optional[str] = Field(None, description="股票代码")
    predict_date: Optional[str] = Field(None, description="预测日期，格式为YYYY-MM-DD")
    start_date: Optional[str] = Field(None, description="开始日期，格式为YYYY-MM-DD")
    end_date: Optional[str] = Field(None, description="结束日期，格式为YYYY-MM-DD")
    limit: int = Field(100, description="返回结果的最大数量，默认100")

class HistoryPredictResponse(BaseModel):
    """历史预测结果响应模型"""
    id: int = Field(..., description="记录ID")
    stock_name: str = Field(..., description="股票名称")
    stock_code: str = Field(..., description="股票代码")
    board: str = Field(..., description="市场板块")
    price: float = Field(..., description="当前价格")
    signal: str = Field(..., description="预测信号")
    prob: float = Field(..., description="预测概率")
    sentiment_label: str = Field(..., description="情感分析标签")
    sentiment_score: float = Field(..., description="情感分析分数")
    rsi: float = Field(..., description="相对强弱指标")
    price_above_bb_upper: bool = Field(..., description="价格是否突破布林带上轨")
    mom_weakening: bool = Field(..., description="动量是否减弱")
    drawdown_5d: float = Field(..., description="5日回撤")
    reason: str = Field(..., description="预测理由")
    predict_date: str = Field(..., description="预测日期")
    created_at: str = Field(..., description="创建日期")
    update_time: str = Field(..., description="更新时间")

class HistoryPredictListResponse(BaseModel):
    """历史预测结果列表响应模型"""
    total: int = Field(..., description="总记录数")
    predictions: List[HistoryPredictResponse] = Field(..., description="预测结果列表")

# 用户认证相关模型
class UserRegisterRequest(BaseModel):
    """用户注册请求模型"""
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")
    email: Optional[str] = Field(None, description="电子邮箱")
    
    model_config = ConfigDict(json_schema_extra={"example": {"username": "admin", "password": "password123", "email": "admin@example.com"}})

class UserLoginRequest(BaseModel):
    """用户登录请求模型"""
    username: str = Field(..., description="用户名或邮箱")
    password: str = Field(..., description="密码")
    
    model_config = ConfigDict(json_schema_extra={"example": {"username": "user@example.com", "password": "password123"}})

class UserResponse(BaseModel):
    """用户信息响应模型"""
    id: int = Field(..., description="用户ID")
    username: str = Field(..., description="用户名")
    email: Optional[str] = Field(None, description="电子邮箱")
    created_at: str = Field(..., description="创建时间")

class AuthResponse(BaseModel):
    """认证响应模型"""
    success: bool = Field(..., description="认证是否成功")
    message: str = Field(..., description="响应消息")
    user: Optional[UserResponse] = Field(None, description="用户信息")