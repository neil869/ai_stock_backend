# data_fetch.py
import pandas as pd
import numpy as np
import time
import warnings
import logging
from datetime import datetime
import os
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 导入数据库操作模块
from db import query_stock_data, check_data_completeness, batch_insert_stock_data
from trade_calendar import get_current_trading_day

# 配置logging
logger = logging.getLogger(__name__)
# 设置为DEBUG级别以查看详细日志
logger.setLevel(logging.DEBUG)

# 设置akshare请求头
os.environ['AKSHARE_HEADERS'] = '{"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}'
warnings.filterwarnings('ignore')

try:
    import akshare as ak
    import baostock as bs
except ImportError as e:
    raise RuntimeError(f"Missing dependency: {e}")

# ==============================
# 📦 Baostock 初始化
# ==============================
_bs_initialized = False


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
# 📊 数据获取（双源容错 + 数据库缓存）
# ==============================
def get_stock_daily(symbol: str):
    """
    双源容错获取个股日线数据（优先从数据库获取，其次本地缓存，最后外部API）
    返回标准 DataFrame：index=datetime, columns=[open, high, low, close, volume]
    volume 单位：股（非手）
    """
    # 1. 首先从数据库获取数据
    logger.info(f"[{symbol}] 尝试从数据库获取数据...")
    last_trading_day = get_current_trading_day()
    logger.info(f"[{symbol}] 最近交易日为 {last_trading_day}")
    # 拼装为时间格式 15:00:00
    last_trading_day_str = last_trading_day.strftime("%Y-%m-%d") + " 15:00:00"
    # 检查数据库中数据是否完整
    is_complete = check_data_completeness(symbol, required_days=365, as_of_date=last_trading_day_str)
    
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
            
            # 获取交易日历（这里暂时使用简单的判断，后面会引入calendar模块）
            is_trading_day = True
            
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
                            # 调试日志：输出保存数据的基本信息
                            logger.debug(f"[{symbol}] 准备保存当天数据，共 {len(save_df)} 条")
                            logger.debug(f"[{symbol}] 保存当天数据前5行:\n{save_df.head()}")

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
                # 查询近三年数据
                start_date=(pd.Timestamp.today() - pd.DateOffset(years=3)).strftime("%Y-%m-%d"),
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
                logger.info(f"[{symbol}] 成功保存 {len(df_bs)} 条 Baostock 数据到数据库")
                # 调试日志：输出返回数据的基本信息
                logger.debug(f"[{symbol}] 返回 Baostock 数据形状: {df_bs.shape}")
                logger.debug(f"[{symbol}] 返回 Baostock 数据后5行:\n{df_bs[['open', 'high', 'low', 'close', 'volume']].tail()}")
                # 返回完整数据
                return df_bs[['open', 'high', 'low', 'close', 'volume']].copy()
            else:
                logger.warning(f"[{symbol}] Baostock 数据不足（{len(df_bs)} 条）")
                continue

        except Exception as e:
            logger.error(f"[{symbol}] Baostock 尝试 {attempt+1}/3 失败: {str(e)[:120]}")
            # 异常时重新初始化连接
            _logout_baostock()
        time.sleep(2)  # 增加等待时间
    return pd.DataFrame()
