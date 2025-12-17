# calendar.py
import pandas as pd
import time
import logging
from datetime import datetime, date, timedelta
import os
import pickle
import warnings

# 配置logging
logger = logging.getLogger(__name__)

# 设置akshare请求头
os.environ['AKSHARE_HEADERS'] = '{"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}'
warnings.filterwarnings('ignore')

try:
    import akshare as ak
    import numpy as np
    # 导入交易日历相关功能
except ImportError as e:
    raise RuntimeError(f"Missing dependency: {e}")

# 交易日历缓存
_trade_calendar_cache = {}
_last_trade_calendar_update = None

# 缓存文件路径定义
TRADE_CALENDAR_CACHE_FILE = 'trade_calendar_cache.pkl'


# ==============================
# 📁 缓存本地持久化功能
# ==============================
def load_trade_calendar_cache():
    """
    从文件加载交易日历缓存
    """
    global _trade_calendar_cache, _last_trade_calendar_update
    try:
        if os.path.exists(TRADE_CALENDAR_CACHE_FILE):
            with open(TRADE_CALENDAR_CACHE_FILE, 'rb') as f:
                data = pickle.load(f)
                if isinstance(data, dict) and 'calendar' in data and 'last_update' in data:
                    _trade_calendar_cache = data['calendar']
                    _last_trade_calendar_update = data['last_update']
                    logger.info(f"从本地文件加载交易日历缓存成功")
                    return True
    except Exception as e:
        logger.error(f"加载交易日历缓存失败：{e}")
    return False


def save_trade_calendar_cache():
    """
    将交易日历缓存保存到文件
    """
    try:
        with open(TRADE_CALENDAR_CACHE_FILE, 'wb') as f:
            pickle.dump({
                'calendar': _trade_calendar_cache,
                'last_update': _last_trade_calendar_update
            }, f)
        logger.info(f"交易日历缓存已保存到本地文件")
        return True
    except Exception as e:
        logger.error(f"保存交易日历缓存失败：{e}")
    return False


# ==============================
# 📅 交易日历功能
# ==============================
def get_trade_calendar(start_year=2020, end_year=2030):
    """
    获取指定年份范围内的交易日历
    - start_year: 开始年份
    - end_year: 结束年份
    """
    global _trade_calendar_cache, _last_trade_calendar_update
    
    # 检查缓存是否存在且未过期（7天）
    if _trade_calendar_cache and _last_trade_calendar_update and (time.time() - _last_trade_calendar_update < 7 * 24 * 3600):
        logger.info("使用缓存的交易日历")
        return _trade_calendar_cache
    
    try:
        logger.info(f"获取 {start_year} 到 {end_year} 的交易日历")
        
        # 尝试从akshare获取交易日历，如果失败则使用默认实现
        try:
            # 尝试不同的函数名
            if hasattr(ak, 'stock_zh_a_trade_calendar'):
                trade_calendar_df = ak.stock_zh_a_trade_calendar(symbol="SSE")
            elif hasattr(ak, 'stock_trade_calendar'):
                trade_calendar_df = ak.stock_trade_calendar(symbol="SSE")
            elif hasattr(ak, 'zh_stock_trade_calendar'):
                trade_calendar_df = ak.zh_stock_trade_calendar(symbol="SSE")
            else:
                # 如果没有找到合适的函数，使用默认实现
                raise AttributeError("akshare库中没有找到合适的交易日历函数")
            
            trade_calendar_df['trade_date'] = pd.to_datetime(trade_calendar_df['trade_date'])
            
            # 筛选年份范围
            trade_calendar_df = trade_calendar_df[
                (trade_calendar_df['trade_date'].dt.year >= start_year) &
                (trade_calendar_df['trade_date'].dt.year <= end_year)
            ]
        except Exception as e:
            logger.warning(f"从akshare获取交易日历失败，使用默认实现: {e}")
            # 创建默认的交易日历（周一至周五，不考虑节假日）
            dates = pd.date_range(f'{start_year}-01-01', f'{end_year}-12-31', freq='D')
            # 筛选周一至周五
            weekday_dates = dates[dates.weekday < 5]
            trade_calendar_df = pd.DataFrame({'trade_date': weekday_dates})
        
        # 转换为日期列表
        trade_dates = trade_calendar_df['trade_date'].tolist()
        trade_dates_set = set(trade_dates)
        
        # 构建缓存数据
        _trade_calendar_cache = {
            'trade_dates': trade_dates,
            'trade_dates_set': trade_dates_set,
            'start_year': start_year,
            'end_year': end_year
        }
        
        # 更新缓存时间
        _last_trade_calendar_update = time.time()
        
        # 保存缓存
        save_trade_calendar_cache()
        
        logger.info(f"成功获取 {len(trade_dates)} 个交易日")
        return _trade_calendar_cache
        
    except Exception as e:
        logger.error(f"获取交易日历失败: {str(e)}", exc_info=True)
        # 如果获取失败，尝试使用本地缓存
        if os.path.exists(TRADE_CALENDAR_CACHE_FILE):
            logger.info("获取交易日历失败，尝试使用本地缓存")
            load_trade_calendar_cache()
        return _trade_calendar_cache


def is_trading_day(query_date):
    """
    判断给定日期是否为交易日
    - date: 日期对象或日期字符串
    """
    if isinstance(query_date, str):
        query_date = pd.to_datetime(query_date)
    # 如果query_date是date对象，转换为datetime对象
    if isinstance(query_date, date):
        query_date = datetime.combine(query_date, datetime.min.time())
    
    # 获取交易日历
    calendar = get_trade_calendar()
    if not calendar or 'trade_dates_set' not in calendar:
        logger.error("交易日历缓存不存在或格式错误")
        return False
    
    # 判断是否为交易日
    logger.info(f"{query_date} 是否为交易日: {query_date in calendar['trade_dates_set']}")
    return query_date in calendar['trade_dates_set']


def get_next_trading_day(date=None, count=1):
    """
    获取下一个交易日
    - date: 基准日期，默认为今天
    - count: 获取第几个下一个交易日，默认为1
    """
    if date is None:
        date = datetime.now().date()
    elif isinstance(date, str):
        date = pd.to_datetime(date).date()
    elif hasattr(date, 'date'):
        date = date.date()
    
    # 获取交易日历
    calendar = get_trade_calendar()
    if not calendar or 'trade_dates' not in calendar:
        return None
    
    # 找到下一个交易日
    trade_dates = [d.date() for d in calendar['trade_dates']]
    trade_dates.sort()
    
    found = False
    result = date
    found_count = 0
    
    while not found and result <= trade_dates[-1]:
        result += timedelta(days=1)
        if result in trade_dates:
            found_count += 1
            if found_count == count:
                found = True
    
    return result if found else None


def get_previous_trading_day(date=None, count=1):
    """
    获取上一个交易日
    - date: 基准日期，默认为今天
    - count: 获取第几个上一个交易日，默认为1
    """
    if date is None:
        date = datetime.now().date()
    elif isinstance(date, str):
        date = pd.to_datetime(date).date()
    elif hasattr(date, 'date'):
        date = date.date()
    
    # 获取交易日历
    calendar = get_trade_calendar()
    if not calendar or 'trade_dates' not in calendar:
        return None
    
    # 找到上一个交易日
    trade_dates = [d.date() for d in calendar['trade_dates']]
    trade_dates.sort()
    
    found = False
    result = date
    found_count = 0
    
    while not found and result >= trade_dates[0]:
        result -= timedelta(days=1)
        if result in trade_dates:
            found_count += 1
            if found_count == count:
                found = True
    
    return result if found else None


def get_trading_days_in_range(start_date, end_date):
    """
    获取指定范围内的所有交易日
    - start_date: 开始日期
    - end_date: 结束日期
    """
    if isinstance(start_date, str):
        start_date = pd.to_datetime(start_date).date()
    elif hasattr(start_date, 'date'):
        start_date = start_date.date()
    
    if isinstance(end_date, str):
        end_date = pd.to_datetime(end_date).date()
    elif hasattr(end_date, 'date'):
        end_date = end_date.date()
    
    # 获取交易日历
    calendar = get_trade_calendar()
    if not calendar or 'trade_dates' not in calendar:
        return []
    
    # 筛选指定范围内的交易日
    trade_dates = [d.date() for d in calendar['trade_dates']]
    trade_dates.sort()
    
    result = []
    for date in trade_dates:
        if start_date <= date <= end_date:
            result.append(date)
    
    return result


def is_trading_hours():
    """
    判断当前时间是否在交易时段内
    交易时段：周一至周五 9:30-11:30, 13:00-15:00
    """
    current_time = datetime.now()
    current_date = current_time.date()
    current_hour = current_time.hour
    current_minute = current_time.minute
    current_weekday = current_time.weekday()
    
    # 判断是否为周末
    if current_weekday >= 5:
        return False
    
    # 判断是否为交易日
    if not is_trading_day(current_date):
        return False
    
    # 判断是否在交易时段内
    if 9 <= current_hour < 15:
        if (current_hour == 9 and current_minute >= 30) or (10 <= current_hour < 11) or (current_hour == 11 and current_minute <= 30) or (13 <= current_hour < 15):
            return True
    
    return False


def get_next_trading_hours_start(date=None):
    """
    获取下一个交易时段的开始时间
    - date: 基准日期，默认为今天
    """
    if date is None:
        date = datetime.now().date()
    elif isinstance(date, str):
        date = pd.to_datetime(date).date()
    elif hasattr(date, 'date'):
        date = date.date()
    
    # 获取下一个交易日
    next_trading_day = get_next_trading_day(date)
    if not next_trading_day:
        return None
    
    # 下一个交易时段的开始时间是下一个交易日的9:30
    return datetime.combine(next_trading_day, datetime.min.time()) + timedelta(hours=9, minutes=30)


def get_current_trading_day():
    """
    获取当前交易日
    如果当前时间在交易时段内，返回今天
    否则返回上一个交易日
    """
    current_time = datetime.now()
    current_date = current_time.date()
    logger.info(f"当前时间 {current_time}，当前日期为 {current_date}")
    # 如果current_date不是‘yyyy-mm-dd hh:mm:ss’格式，强制转换为datetime对象
    if not isinstance(current_date, datetime):
        current_date = datetime.combine(current_date, datetime.min.time())
    logger.info(f"转换后的当前日期为 {current_date}")
    if is_trading_day(current_date):
        return current_date
    else:
        return get_previous_trading_day(current_date)
