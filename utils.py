# utils.py
import pandas as pd
import numpy as np
import time
import warnings
import logging
from datetime import datetime
import os
import pickle
# AkShare 获取（增加重试次数、超时处理和指数退避）
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 导入数据库操作模块
from db import query_stock_data, check_data_completeness, batch_insert_stock_data, init_db, test_db_connection

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

# 设置akshare请求头
os.environ['AKSHARE_HEADERS'] = '{"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}'
warnings.filterwarnings('ignore')

try:
    import akshare as ak
    from lightgbm import LGBMClassifier
    from snownlp import SnowNLP
    import jieba
    import baostock as bs
    from db import save_predict_result, query_predict_results  # 导入数据库操作函数
except ImportError as e:
    raise RuntimeError(f"Missing dependency: {e}")

# ==============================
# 📦 Baostock 初始化
# ==============================
_bs_initialized = False

# 缓存文件路径定义
STOCKS_CACHE_FILE = 'stocks_cache.pkl'
PREDICT_CACHE_FILE = 'predict_cache.pkl'

# 全局股票列表缓存
_stocks_cache = None
_last_update_date = None

# predict_signal缓存
_predict_cache = {}
_last_predict_update = {}

# 定时任务标志
_stocks_refreshing = False
_predict_refreshing = False

import threading
import time
from datetime import datetime, timedelta

# 获取交易日历缓存
_trade_calendar = None
_trade_calendar_updated = None

def get_trade_calendar():
    """
    获取交易日历，使用akshare获取新浪财经的交易日历
    缓存机制：每天更新一次日历
    """
    global _trade_calendar, _trade_calendar_updated
    today = datetime.today().date()
    
    # 如果缓存为空或超过一天未更新，则更新缓存
    if _trade_calendar is None or _trade_calendar_updated != today:
        try:
            logger.info("更新交易日历缓存")
            # 获取1990年至今的交易日历
            df = ak.tool_trade_date_hist_sina()
            # 转换为日期类型
            df['trade_date'] = pd.to_datetime(df['trade_date'], format='%Y%m%d').dt.date
            # 只保留交易日期列
            _trade_calendar = set(df['trade_date'])
            _trade_calendar_updated = today
            logger.info("交易日历缓存更新成功")
        except Exception as e:
            logger.error(f"获取交易日历失败: {str(e)}")
            # 如果获取失败，使用简单的周一到周五作为备选
            _trade_calendar = None
            _trade_calendar_updated = None
    
    return _trade_calendar

def get_next_trading_day(base_date=None):
    """
    获取下一个交易日，考虑周末和法定假期
    
    Args:
        base_date: 基准日期，如果为None则使用当前日期
        
    Returns:
        date: 下一个交易日的日期
    """
    if base_date is None:
        base_date = datetime.today().date()
    elif isinstance(base_date, str):
        base_date = datetime.strptime(base_date, '%Y-%m-%d').date()
    
    trade_calendar = get_trade_calendar()
    
    # 从基准日期的下一天开始查找
    next_day = base_date + timedelta(days=1)
    
    while True:
        # 首先检查是否是交易日
        if trade_calendar is not None:
            if next_day in trade_calendar:
                return next_day
        else:
            # 如果没有交易日历，使用简单的周一到周五规则
            if next_day.weekday() < 5:  # 0-4代表周一到周五
                return next_day
        
        # 不是交易日，继续查找下一天
        next_day += timedelta(days=1)

def _init_baostock():
    """
    初始化 Baostock 连接，增加重连机制
    """
    global _bs_initialized
    try:
        # 先尝试登出旧连接
        if _bs_initialized:
            bs.logout()
            _bs_initialized = False
            time.sleep(1)  # 等待 1 秒后重新登录
        
        # 重新登录
        lg = bs.login()
        if lg.error_code != '0':
            logger.error(f"[Baostock] Login failed: {lg.error_msg}")
            return False
        else:
            _bs_initialized = True
            logger.info("[Baostock] Login successful")
            return True
    except Exception as e:
        logger.error(f"[Baostock] Login exception: {str(e)}")
        _bs_initialized = False
        return False

def _logout_baostock():
    global _bs_initialized
    if _bs_initialized:
        try:
            bs.logout()
            logger.info("[Baostock] Logout successful")
        except Exception as e:
            logger.error(f"[Baostock] Logout exception: {str(e)}")
        finally:
            _bs_initialized = False

# ==============================
# 📁 缓存本地持久化功能
# ==============================
import pickle

def load_stocks_cache():
    """
    从本地文件加载股票列表缓存
    """
    global _stocks_cache, _last_update_date
    try:
        if os.path.exists(STOCKS_CACHE_FILE):
            with open(STOCKS_CACHE_FILE, 'rb') as f:
                cache_data = pickle.load(f)
                _stocks_cache = cache_data['stocks']
                _last_update_date = cache_data['last_update']
                logger.info(f"从本地缓存加载股票列表成功，共 {len(_stocks_cache)} 条数据，最后更新日期：{_last_update_date}")
                return True
    except Exception as e:
        logger.error(f"加载本地股票列表缓存失败：{e}")
    return False

def save_stocks_cache():
    """
    将股票列表缓存保存到本地文件
    """
    global _stocks_cache, _last_update_date
    try:
        if _stocks_cache is not None and _last_update_date is not None:
            cache_data = {
                'stocks': _stocks_cache,
                'last_update': _last_update_date
            }
            with open(STOCKS_CACHE_FILE, 'wb') as f:
                pickle.dump(cache_data, f)
            logger.info(f"股票列表缓存已保存到本地文件：{STOCKS_CACHE_FILE}")
            return True
    except Exception as e:
        logger.error(f"保存股票列表缓存到本地失败：{e}")
    return False

def load_predict_cache():
    """
    从数据库加载预测结果缓存
    """
    global _predict_cache, _last_predict_update
    try:
        # 从数据库加载最近的预测结果
        results = query_predict_results(limit=1000)  # 加载最近1000条预测结果
        if results:
            # 转换为缓存格式
            _predict_cache = {}
            _last_predict_update = {}
            for result in results:
                symbol = result['stock_code']
                _predict_cache[symbol] = {
                    'name': result['stock_name'],
                    'stock_code': result['stock_code'],
                    'board': result['board'],
                    'price': result['price'],
                    'signal': result['signal'],
                    'prob': result['prob'],
                    'sentiment_label': result['sentiment_label'],
                    'sentiment_score': result['sentiment_score'],
                    'date': result['predict_date'].strftime('%Y-%m-%d') if hasattr(result['predict_date'], 'strftime') else result['predict_date'],
                    'rsi': result['rsi'],
                    'price_above_bb_upper': result['price_above_bb_upper'],
                    'mom_weakening': result['mom_weakening'],
                    'drawdown_5d': result['drawdown_5d']
                }
                _last_predict_update[symbol] = datetime.now().timestamp()
            logger.info(f"从数据库加载预测结果成功，共 {len(_predict_cache)} 条数据")
            return True
    except Exception as e:
        logger.error(f"加载数据库预测结果缓存失败：{e}")
    return False

def save_predict_cache():
    """
    不再需要将预测结果缓存保存到本地文件，预测结果已直接保存到数据库
    """
    logger.info("预测结果已直接保存到数据库，不需要再保存到本地文件")
    return True

# ============================== 
# 📊 工具函数
# ==============================
def get_market_board(symbol: str) -> str:
    if symbol.startswith('688'):
        return '科创板'
    elif symbol.startswith('300'):
        return '创业板'
    else:
        return '主板'

def get_all_stocks(force_refresh=False):
    """
    获取所有A股股票列表
    - force_refresh: 是否强制刷新缓存
    """
    global _stocks_cache, _last_update_date
    
    # 检查是否需要更新缓存（每天更新一次）
    current_date = datetime.now().date()
    if _stocks_cache is not None and not force_refresh and _last_update_date == current_date:
        return _stocks_cache.copy()
    
    try:
        # 获取股票数据
        logger.info("开始获取所有A股股票列表...")
        df = ak.stock_info_a_code_name()
        logger.info(f"获取到 {len(df)} 条股票数据")
        # 筛选A股股票（代码格式：6位数字，前缀为0、3、6）
        df = df[df['code'].str.match(r'^[036]\d{5}$')]
        logger.info(f"筛选后 {len(df)} 条股票数据")
        
        # 过滤掉ST、退市、B股等特殊股票
        df = df[~df['name'].str.contains('ST|退|B', case=False, na=False)]
        logger.info(f"过滤后 {len(df)} 条股票数据")   
        
        # 更新缓存
        _stocks_cache = df
        _last_update_date = current_date
        
        # 保存到本地文件
        save_stocks_cache()
        
        logger.info(f"缓存更新完成，共 {len(df)} 条有效股票数据")
        
        return df.copy()
    except Exception as e:
        # 如果获取失败但有缓存，返回缓存数据
        if _stocks_cache is not None:
            logger.warning(f"获取股票列表失败，但返回缓存数据：{e}") 
            return _stocks_cache.copy()
        raise RuntimeError(f"Failed to fetch stock list: {e}")

def get_guba_posts(symbol: str, pages=2):
    try:
        df = ak.stock_guba_em(symbol=symbol)
        if df.empty:
            return []
        df = df.sort_values('read_count', ascending=False).head(pages * 20)
        posts = (df['title'].fillna('') + '。' + df['content'].fillna('')).tolist()
        return [p for p in posts if len(p) > 10]
    except Exception:
        return []

def basic_sentiment_score(text: str) -> float:
    try:
        s = SnowNLP(text)
        return s.sentiments * 2 - 1
    except:
        return 0.0

def analyze_stock_sentiment(symbol: str) -> dict:
    posts = get_guba_posts(symbol, pages=2)
    if not posts:
        return {"score": 0.0, "label": "❓ 无数据"}
    
    scores = [basic_sentiment_score(p) for p in posts[:30]]
    avg_score = np.mean(scores) if scores else 0.0
    
    if avg_score > 0.3:
        label = "🔥 看涨"
    elif avg_score < -0.2:
        label = "❄️ 看跌"
    else:
        label = "😐 中性"
    
    return {"score": round(avg_score, 3), "label": label}

# ==============================
# 📈 数据获取（双源容错 + 数据库缓存）
# ==============================
def get_stock_daily(symbol: str):
    """
    双源容错获取个股日线数据（优先从数据库获取，其次本地缓存，最后外部API）
    返回标准 DataFrame：index=datetime, columns=[open, high, low, close, volume]
    volume 单位：股（非手）
    """
    # 1. 首先从数据库获取数据
    logger.info(f"[{symbol}] 尝试从数据库获取数据...")
    
    # 检查数据库中数据是否完整
    is_complete = check_data_completeness(symbol)
    if is_complete:
        # 数据完整，直接从数据库获取
        df_db = query_stock_data(symbol)
        if not df_db.empty:
            logger.info(f"[{symbol}] 从数据库获取到完整数据，共 {len(df_db)} 条")
            
            # 检查当前时间是否在交易时段
            today = datetime.now().date()
            current_time = datetime.now()
            current_hour = current_time.hour
            current_minute = current_time.minute
            
            # 获取交易日历
            trade_calendar = get_trade_calendar()
            is_trading_day = today in trade_calendar if trade_calendar is not None else True
            
            # 判断是否在交易时段（9:30-11:30, 13:00-15:00）
            is_trading_hours = False
            if 9 <= current_hour < 15:
                if (current_hour == 9 and current_minute >= 30) or (10 <= current_hour < 11) or (current_hour == 11 and current_minute <= 30) or (13 <= current_hour < 15):
                    is_trading_hours = True
            
            logger.info(f"当前时间: {current_time}, 是交易日: {is_trading_day}, 是交易时间: {is_trading_hours}")
            
            # 如果是交易日并且在交易时段，重新获取当天的数据
            if is_trading_day and is_trading_hours:
                logger.info(f"[{symbol}] 当天交易时段，重新获取当天数据")
                
                # 构造查询条件，只获取当天的数据
                today_str = today.strftime("%Y%m%d")
                
                try:
                    # 为AkShare配置请求重试策略
                    session = requests.Session()
                    retry_strategy = Retry(
                        total=3,
                        status_forcelist=[429, 500, 502, 503, 504],
                        allowed_methods=["HEAD", "GET", "OPTIONS"],
                        backoff_factor=1  # 指数退避
                    )
                    adapter = HTTPAdapter(max_retries=retry_strategy)
                    session.mount("http://", adapter)
                    session.mount("https://", adapter)
                    
                    # 设置全局超时
                    session.timeout = 10  # 10秒超时
                    
                    # 替换AkShare的默认会话
                    ak._session = session
                    
                    # 获取当天的数据
                    df_today = ak.stock_zh_a_hist(
                        symbol=symbol,
                        period="daily",
                        start_date=today_str,
                        end_date=today_str,
                        adjust="qfq"
                    )
                    
                    if not df_today.empty:
                        # 重命名中文列
                        df_today.rename(columns={
                            '日期': 'date',
                            '开盘': 'open',
                            '最高': 'high',
                            '最低': 'low',
                            '收盘': 'close',
                            '成交量': 'volume',      # 单位：手
                            '成交额': 'amount',
                            '涨跌幅': 'pct_chg',
                            '换手率': 'turnover'
                        }, inplace=True)
                        df_today['date'] = pd.to_datetime(df_today['date'])
                        df_today.set_index('date', inplace=True)
                        df_today.sort_index(inplace=True)
                        # 转换成交量为“股”
                        df_today['volume'] = df_today['volume'] * 100
                        # 清洗异常值
                        df_today = df_today[
                            (df_today['close'] > 0.1) &
                            (df_today['close'] < 1000) &
                            (df_today['volume'] >= 0)
                        ]
                        
                        if not df_today.empty:
                            # 更新数据库
                            save_df = df_today[['open', 'high', 'low', 'close', 'volume']].copy().reset_index()
                            batch_insert_stock_data(save_df, symbol)
                            
                            # 更新内存中的数据
                            if today in df_db.index.date:
                                # 如果数据库中已有当天的数据，替换它
                                df_db = df_db[df_db.index.date != today]
                                df_db = pd.concat([df_db, df_today])
                                df_db.sort_index(inplace=True)
                            else:
                                # 如果数据库中没有当天的数据，添加它
                                df_db = pd.concat([df_db, df_today])
                                df_db.sort_index(inplace=True)
                            
                            logger.info(f"[{symbol}] 成功更新当天数据")
                        else:
                            logger.warning(f"[{symbol}] 当天数据异常，不更新")
                    else:
                        logger.warning(f"[{symbol}] 未获取到当天数据")
                except Exception as e:
                    logger.warning(f"[{symbol}] 获取当天数据失败: {str(e)[:100]}")
            
            return df_db
        else:
            logger.warning(f"[{symbol}] 数据库查询无结果")
    else:
        logger.info(f"[{symbol}] 数据库数据不完整，需要从外部API获取数据")
    
    # 为AkShare配置请求重试策略
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"],
        backoff_factor=1  # 指数退避
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    # 设置全局超时
    session.timeout = 10  # 10秒超时
    
    for attempt in range(3):  # 增加到3次重试
        try:
            # 替换AkShare的默认会话
            ak._session = session
            
            df_ak = ak.stock_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date="20100101",
                end_date=pd.Timestamp.today().strftime("%Y%m%d"),
                adjust="qfq"
            )
            if not df_ak.empty:
                # 重命名中文列
                df_ak.rename(columns={
                    '日期': 'date',
                    '开盘': 'open',
                    '最高': 'high',
                    '最低': 'low',
                    '收盘': 'close',
                    '成交量': 'volume',      # 单位：手
                    '成交额': 'amount',
                    '涨跌幅': 'pct_chg',
                    '换手率': 'turnover'
                }, inplace=True)
                df_ak['date'] = pd.to_datetime(df_ak['date'])
                df_ak.set_index('date', inplace=True)
                df_ak.sort_index(inplace=True)
                # 转换成交量为“股”
                df_ak['volume'] = df_ak['volume'] * 100
                # 清洗异常值
                df_ak = df_ak[
                    (df_ak['close'] > 0.1) &
                    (df_ak['close'] < 1000) &
                    (df_ak['volume'] >= 0)
                ]
                if len(df_ak) >= 100:
                    # 保存到数据库（保存完整数据，包括当天可能未收盘的数据）
                    save_df = df_ak[['open', 'high', 'low', 'close', 'volume']].copy().reset_index()
                    batch_insert_stock_data(save_df, symbol)
                    
                    # 不再保存到本地缓存，数据已直接保存到数据库
                    
                    # 返回完整数据
                    return df_ak[['open', 'high', 'low', 'close', 'volume']].copy()
                else:
                    logger.warning(f"[{symbol}] AkShare 数据不足（{len(df_ak)} 条）")
        except Exception as e:
            err_str = str(e)
            logger.warning(f"[{symbol}] AkShare 尝试 {attempt+1}/3 失败: {err_str[:120]}")
        time.sleep(2)  # 增加等待时间

    # === 降级到 Baostock ===
    for attempt in range(3):  # Baostock 也增加重试次数
        try:
            # 确保 Baostock 连接有效，如果失败则重新连接
            if not _bs_initialized or not _init_baostock():
                logger.warning(f"[{symbol}] Baostock 连接失败，尝试重新连接...")
                if not _init_baostock():
                    time.sleep(2)
                    continue
            
            # 构造代码
            if symbol.startswith(('6', '9')):
                code = f"sh.{symbol}"
            else:
                code = f"sz.{symbol}"
            
            rs = bs.query_history_k_data_plus(
                code,
                "date,open,high,low,close,volume,amount",
                start_date="2010-01-01",
                end_date=pd.Timestamp.today().strftime("%Y-%m-%d"),
                frequency="d",
                adjustflag="3"  # 后复权
            )
            
            # 检查查询是否成功
            if rs.error_code != '0':
                logger.error(f"[{symbol}] Baostock 查询失败: {rs.error_msg}")
                # 查询失败可能是连接失效，重新初始化连接
                _logout_baostock()
                time.sleep(1)
                continue
            
            data_list = []
            while rs.next():
                data_list.append(rs.get_row_data())
            
            if not data_list:
                logger.warning(f"[{symbol}] Baostock 无数据")
                continue

            df_bs = pd.DataFrame(data_list, columns=['date','open','high','low','close','volume','amount'])
            df_bs['date'] = pd.to_datetime(df_bs['date'])
            df_bs.set_index('date', inplace=True)
            df_bs.sort_index(inplace=True)
            
            # 转换数值类型
            for col in ['open','high','low','close','volume','amount']:
                df_bs[col] = pd.to_numeric(df_bs[col], errors='coerce')
            df_bs.dropna(inplace=True)
            
            # 清洗
            df_bs = df_bs[
                (df_bs['close'] > 0.1) &
                (df_bs['close'] < 1000) &
                (df_bs['volume'] >= 0)
            ]
            
            if len(df_bs) >= 100:
                # 保存到数据库
                save_df = df_bs[['open', 'high', 'low', 'close', 'volume']].copy().reset_index()
                batch_insert_stock_data(save_df, symbol)
            else:
                logger.warning(f"[{symbol}] Baostock 数据不足（{len(df_bs)} 条）")
                continue

        except Exception as e:
            logger.error(f"[{symbol}] Baostock 尝试 {attempt+1}/3 失败: {str(e)[:120]}")
            # 异常时重新初始化连接
            _logout_baostock()
        time.sleep(2)  # 增加等待时间
    return pd.DataFrame()

# ==============================
# 🤖 特征与预测
# ==============================
def calc_features_safe(df_slice):
    if len(df_slice) < 60:
        return None
    high = df_slice['high']
    low = df_slice['low']
    close = df_slice['close']
    volume = df_slice['volume']
    
    features = {}
    features['mom_5'] = close.iloc[-1] / close.iloc[-6] - 1 if len(close) >= 6 else 0
    features['mom_20'] = close.iloc[-1] / close.iloc[-21] - 1 if len(close) >= 21 else 0
    
    ma5 = close.tail(5).mean()
    ma20 = close.tail(20).mean()
    ma60 = close.tail(60).mean() if len(close) >= 60 else ma20
    features['ma5'] = ma5
    features['ma20'] = ma20
    features['ma60'] = ma60
    features['ma_align'] = int(ma5 > ma20 > ma60)
    features['price_to_ma20'] = (close.iloc[-1] - ma20) / ma20

    if len(close) >= 15:
        delta = close.diff().iloc[-14:]
        gain = delta.where(delta > 0, 0).mean()
        loss = (-delta.where(delta < 0, 0)).mean()
        rs = gain / loss if loss != 0 else 0
        features['rsi_14'] = 100 - (100 / (1 + rs)) if rs != 0 else 50
    else:
        features['rsi_14'] = 50

    if len(close) >= 26:
        ema12 = close.ewm(span=12, adjust=False).mean().iloc[-1]
        ema26 = close.ewm(span=26, adjust=False).mean().iloc[-1]
        dif = ema12 - ema26
        dif_series = close.ewm(span=12).mean() - close.ewm(span=26).mean()
        dea = dif_series.tail(9).mean()
        hist = (dif - dea) * 2
        features['macd_dif'] = dif
        features['macd_dea'] = dea
        features['macd_hist'] = hist
        features['macd_bullish'] = int(hist > 0)
    else:
        features.update({'macd_dif':0, 'macd_dea':0, 'macd_hist':0, 'macd_bullish':0})

    vol_ma5 = volume.tail(5).mean()
    features['vol_ratio_5'] = volume.iloc[-1] / vol_ma5 if vol_ma5 != 0 else 1

    if len(close) >= 20:
        bb_ma = close.tail(20).mean()
        bb_std = close.tail(20).std()
        bb_upper = bb_ma + 2 * bb_std
        bb_lower = bb_ma - 2 * bb_std
        price = close.iloc[-1]
        features['bb_width'] = (bb_upper - bb_lower) / bb_ma
        features['bb_position'] = (price - bb_lower) / (bb_upper - bb_lower) if bb_upper != bb_lower else 0.5
        features['price_above_bb_upper'] = int(price > bb_upper)
        features['price_below_bb_lower'] = int(price < bb_lower)
    else:
        features.update({'bb_width':0, 'bb_position':0.5, 'price_above_bb_upper':0, 'price_below_bb_lower':0})

    return pd.Series(features)

def predict_signal(symbol, name, train_window=200,):
    """
    预测股票买卖信号
    - symbol: 股票代码
    - name: 股票名称
    - train_window: 训练窗口大小
    """
    logger.info(f"开始预测股票 {symbol} ({name}) 的信号")
    try:
        # 判断当前时间是否在开盘日的交易时段（9:30-11:30, 13:00-15:00）
        current_time = datetime.now()
        current_date = current_time.date()
        current_hour = current_time.hour
        current_minute = current_time.minute
        current_seconds = current_time.second
        
        # 获取交易日历
        trade_calendar = get_trade_calendar()
        
        # 判断是否为开盘日的交易时段
        is_trading_day = current_date in trade_calendar if trade_calendar is not None else True
        is_trading_hours = False
        if 9 <= current_hour < 15:
            if (current_hour == 9 and current_minute >= 30) or (10 <= current_hour < 11) or (current_hour == 11 and current_minute <= 30) or (13 <= current_hour < 15):
                is_trading_hours = True
        # 确保15点整之后不处理
        if current_hour >= 15 and (current_minute > 0 or current_seconds > 0):
            is_trading_hours = False
        
        logger.info(f"当前时间: {current_time}, 是交易日: {is_trading_day}, 是交易时间: {is_trading_hours}")
        
        # 获取股票数据
        df = get_stock_daily(symbol)
        if df is None or df.empty or len(df) < train_window + 1:
            logger.warning(f"[{symbol}] 数据不足或获取失败，无法进行预测")
            return None
    
        # 获取最新数据日期
        latest_data_date = df.index[-1].date()
        
        # 获取下一个交易日作为预测日期
        predict_date = get_next_trading_day(latest_data_date)
        predict_date_str = predict_date.strftime('%Y-%m-%d')
        
        as_of_date = df.index[-1]
        train_dates = df.index[-(train_window + 1):-1]

        X_train = []
        y_train = []

        for d in train_dates:
            idx = df.index.get_loc(d)
            if idx + 1 >= len(df):
                continue
            next_day = df.index[idx + 1]
            df_upto_d = df.loc[:d]
            feat = calc_features_safe(df_upto_d)
            if feat is None:
                continue
            X_train.append(feat)
            ret = (df.loc[next_day, 'close'] - df.loc[d, 'close']) / df.loc[d, 'close']
            y_train.append(int(ret > 0))

        if len(X_train) < 50:
            return None

        X_train = pd.DataFrame(X_train)
        y_train = np.array(y_train)

        from sklearn.utils.class_weight import compute_class_weight
        classes = np.unique(y_train)
        class_weight = dict(zip(classes, compute_class_weight('balanced', classes=classes, y=y_train))) if len(classes) == 2 else None

        model = LGBMClassifier(
            n_estimators=80,
            max_depth=4,
            random_state=42,
            verbose=-1,
            class_weight=class_weight
        )
        model.fit(X_train, y_train)

        feat_pred = calc_features_safe(df[df.index <= as_of_date])
        if feat_pred is None:
            return None
        feat_pred = feat_pred.reindex(X_train.columns, fill_value=0)
        prob = model.predict_proba([feat_pred])[0][1]

        close = df['close']
        latest_close = close.iloc[-1]
        rsi = feat_pred.get('rsi_14', 50)
        price_above_bb = bool(feat_pred.get('price_above_bb_upper', 0))
        
        mom_weakening = False
        if len(close) >= 11:
            mom_recent = close.iloc[-1] / close.iloc[-6] - 1
            mom_prev = close.iloc[-6] / close.iloc[-11] - 1
            if mom_prev != 0:
                mom_weakening = mom_recent < mom_prev * 0.5

        drawdown_5d = 0
        if len(close) >= 5:
            recent_high = close.tail(5).max()
            if recent_high > 0:
                drawdown_5d = (recent_high - latest_close) / recent_high

        signal = "⚪ 观望"
        if prob > 0.60 and rsi < 70 and not price_above_bb and not mom_weakening:
            signal = "🟢 建仓"
        elif prob > 0.55 and rsi < 75:
            signal = "🟡 持有"
        elif (prob < 0.50) or (rsi > 75) or (price_above_bb and mom_weakening) or (drawdown_5d > 0.08):
            signal = "🔴 减仓"
        else:
            signal = "🟡 持有"

        senti = analyze_stock_sentiment(symbol)
        
        # 生成预测理由
        reasons = []
        
        # 基于预测概率的理由
        if prob > 0.60:
            reasons.append(f"AI模型预测上涨概率为{round(prob*100, 1)}%，属于较高水平")
        elif prob > 0.50:
            reasons.append(f"AI模型预测上涨概率为{round(prob*100, 1)}%，属于中性偏上水平")
        else:
            reasons.append(f"AI模型预测上涨概率为{round(prob*100, 1)}%，属于较低水平")
        
        # 基于RSI指标的理由
        if rsi > 75:
            reasons.append(f"RSI指标为{round(rsi, 1)}，处于超买区域，短期上涨压力较大")
        elif rsi < 30:
            reasons.append(f"RSI指标为{round(rsi, 1)}，处于超卖区域，短期下跌空间有限")
        elif rsi < 70:
            reasons.append(f"RSI指标为{round(rsi, 1)}，处于合理区间，具有上涨潜力")
        
        # 基于布林带的理由
        if price_above_bb:
            reasons.append("价格突破布林带上轨，短期可能面临回调压力")
        
        # 基于动量的理由
        if mom_weakening:
            reasons.append("动量正在减弱，上涨动能不足")
        else:
            reasons.append("动量保持稳定，上涨动能充足")
        
        # 基于5日回撤的理由
        if drawdown_5d > 0.08:
            reasons.append(f"5日回撤达到{round(drawdown_5d*100, 1)}%，短期调整幅度较大")
        
        # 基于情感分析的理由
        if senti["label"] == "正面":
            reasons.append(f"市场情绪为{senti['label']}，有利于股价上涨")
        elif senti["label"] == "负面":
            reasons.append(f"市场情绪为{senti['label']}，不利于股价上涨")
        
        # 根据预测信号定制理由开头
        signal_text = signal.split(' ')[1]  # 获取信号文本部分（如：建仓、持有、减仓、观望）
        reason_prefix = f"{signal_text}理由"
        
        # 组合最终理由
        reason = reason_prefix + "：" + "；".join(reasons) + "。"

        result = {
            "name": name,
            "stock_code": symbol,
            "board": get_market_board(symbol),
            "price": round(latest_close, 2),
            "signal": signal,
            "prob": round(prob * 100, 2),
            "sentiment_label": senti["label"],
            "sentiment_score": senti["score"],
            "date": predict_date_str,
            "rsi": round(rsi, 1),
            "price_above_bb_upper": price_above_bb,
            "mom_weakening": mom_weakening,
            "drawdown_5d": round(drawdown_5d * 100, 2),
            "reason": reason
        }
        
        # 将预测结果保存到数据库
        save_predict_result(result)
        return result
    except Exception as e:
        logger.error(f"[{symbol}] 预测失败: {str(e)}", exc_info=True)
        return None

def _scheduled_stocks_refresh():
    """
    定时刷新股票列表缓存的后台任务
    """
    # 第一次执行时先等待24小时，因为start_scheduled_tasks已经初始化了缓存
    time.sleep(86400)
    
    while True:
        try:
            # 刷新股票列表
            get_all_stocks(force_refresh=True)
            logger.info("股票列表缓存已更新")
        except Exception as e:
            logger.error(f"更新股票列表缓存失败: {e}")
        
        # 等待24小时
        time.sleep(86400)

# 配置用户选好的股票列表，用于自动预测
AUTO_PREDICT_STOCKS = [
    {"code": "601138", "name": "工业富联"},
    {"code": "603336", "name": "宏辉果蔬"},
    # 可以继续添加更多股票
]

# 自动预测任务执行间隔（秒）
AUTO_PREDICT_INTERVAL = 3600  # 每小时检查一次


def _scheduled_stock_prediction():
    """
    定时执行股票自动预测任务
    在每天收盘后（15:00之后）自动预测用户选好的股票
    """
    logger.info("股票自动预测任务已启动")
    
    while True:
        try:
            # 获取当前时间
            current_time = datetime.now()
            current_hour = current_time.hour
            current_minute = current_time.minute
            current_date = current_time.date()
            
            # 获取交易日历
            trade_calendar = get_trade_calendar()
            
            # 判断是否为交易日
            is_trading_day = current_date in trade_calendar if trade_calendar is not None else True
            
            # 判断是否为收盘后时间（15:00之后）
            is_after_market_close = current_hour >= 15
            
            logger.info(f"自动预测检查 - 当前时间: {current_time}, 是交易日: {is_trading_day}, 收盘后: {is_after_market_close}")
            
            # 仅在交易日的收盘后执行预测
            if is_trading_day and is_after_market_close:
                logger.info(f"开始执行自动预测任务，共 {len(AUTO_PREDICT_STOCKS)} 只股票")
                
                for stock in AUTO_PREDICT_STOCKS:
                    symbol = stock["code"]
                    name = stock["name"]
                    try:
                        logger.info(f"开始自动预测股票 {symbol} ({name})")
                        # 调用预测函数
                        result = predict_signal(symbol, name)
                        if result:
                            logger.info(f"股票 {symbol} ({name}) 预测完成：{result['signal']} (概率: {result['prob']}%)")
                        else:
                            logger.warning(f"股票 {symbol} ({name}) 预测失败")
                    except Exception as e:
                        logger.error(f"自动预测股票 {symbol} ({name}) 时出错: {str(e)}")
                        import traceback
                        traceback.print_exc()
                
                logger.info("所有股票自动预测任务完成")
            
            # 等待指定间隔后再次检查
            time.sleep(AUTO_PREDICT_INTERVAL)
            
        except Exception as e:
            logger.error(f"自动预测任务执行出错: {str(e)}")
            import traceback
            traceback.print_exc()
            # 出错后等待一段时间再重试
            time.sleep(300)


def start_scheduled_tasks():
    """
    启动所有定时任务
    """
    # 启动时先尝试加载本地缓存
    load_stocks_cache()
    
    # 初始化数据库
    init_db()
    
    # 如果本地没有缓存或缓存过期，初始化股票列表缓存
    if _stocks_cache is None:
        get_all_stocks()
    
    # 启动股票列表定时更新任务
    stocks_thread = threading.Thread(target=_scheduled_stocks_refresh, daemon=True)
    stocks_thread.start()
    
    # 启动股票自动预测任务
    predict_thread = threading.Thread(target=_scheduled_stock_prediction, daemon=True)
    predict_thread.start()
    
    logger.info("所有定时更新任务已启动")

# ==============================
# 🔁 回测（简化版，仅返回指标）
# ==============================
def backtest_ai_strategy_cached(board_filter, top_k, min_prob, lookback_days):
    stocks_df = get_all_stocks()
    if board_filter != "全部":
        stocks_df = stocks_df[stocks_df['code'].apply(get_market_board) == board_filter].reset_index(drop=True)

    valid_symbols = []
    all_prices = {}
    for _, row in stocks_df.iterrows():
        symbol = row['code']
        df = get_stock_daily(symbol)
        if not df.empty and len(df) >= lookback_days + 50:
            all_prices[symbol] = df['close']
            valid_symbols.append(symbol)

    if not valid_symbols:
        return None

    common_dates = set(all_prices[valid_symbols[0]].index)
    for sym in valid_symbols[:5]:
        common_dates &= set(all_prices[sym].index)
    common_dates = sorted(common_dates)[-lookback_days:]
    if len(common_dates) < 30:
        return None

    nav = 1.0
    daily_rets = []

    for i in range(len(common_dates) - 1):
        t0 = common_dates[i]
        t1 = common_dates[i + 1]

        signals = []
        for sym in valid_symbols[:100]:  # 限100只防超时
            if t0 not in all_prices[sym].index or t1 not in all_prices[sym].index:
                continue
            try:
                full_df = get_stock_daily(sym)
                if t0 not in full_df.index:
                    continue
                df_upto_t0 = full_df[full_df.index <= t0]
                feat = calc_features_safe(df_upto_t0)
                if feat is None:
                    continue
                prob = 0.52  # 简化：实际应训练模型预测
                if prob >= min_prob / 100.0:
                    ret = (all_prices[sym].loc[t1] - all_prices[sym].loc[t0]) / all_prices[sym].loc[t0]
                    signals.append((prob, ret))
            except Exception:
                continue

        signals.sort(reverse=True)
        selected = signals[:top_k]
        daily_ret = np.mean([r for _, r in selected]) if selected else 0.0
        nav *= (1 + daily_ret)
        daily_rets.append(daily_ret)

    returns = pd.Series(daily_rets)
    total_ret = nav - 1
    annual_ret = (1 + total_ret) ** (252 / len(daily_rets)) - 1 if len(daily_rets) > 0 else 0
    vol = returns.std() * np.sqrt(252)
    sharpe = annual_ret / vol if vol != 0 else 0
    dd = (pd.Series(nav).cummax() - pd.Series(nav)) / pd.Series(nav).cummax()
    mdd = dd.max()
    win_rate = (returns > 0).mean()

    return {
        'total_return': float(total_ret),
        'annualized_return': float(annual_ret),
        'sharpe': float(sharpe),
        'max_drawdown': float(mdd),
        'win_rate': float(win_rate)
    }