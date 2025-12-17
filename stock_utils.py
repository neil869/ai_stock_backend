# stock_utils.py
import pandas as pd
import numpy as np
import time
import warnings
import logging
from datetime import datetime
import os
import pickle

# 配置logging
logger = logging.getLogger(__name__)

# 设置akshare请求头
os.environ['AKSHARE_HEADERS'] = '{"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}'
warnings.filterwarnings('ignore')

try:
    import akshare as ak
    from snownlp import SnowNLP
    import jieba
except ImportError as e:
    raise RuntimeError(f"Missing dependency: {e}")

# 缓存文件路径定义
STOCKS_CACHE_FILE = 'stocks_cache.pkl'

# 全局股票列表缓存
_stocks_cache = None
_last_update_date = None

# 定时任务标志
_stocks_refreshing = False


# ==============================
# 📁 缓存本地持久化功能
# ==============================
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
