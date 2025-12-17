# scheduler.py
import time
import threading
import logging
from datetime import datetime, timedelta
import os
import warnings

# 配置logging
logger = logging.getLogger(__name__)

# 设置akshare请求头
os.environ['AKSHARE_HEADERS'] = '{"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}'
warnings.filterwarnings('ignore')

try:
    import akshare as ak
    import pandas as pd
    from data_fetch import get_stock_daily
    from predict import predict_signal
    from stock_utils import load_stocks_cache, save_stocks_cache, get_all_stocks
    from db import init_db, update_stock_list
    from trade_calendar import is_trading_day
except ImportError as e:
    raise RuntimeError(f"Missing dependency: {e}")

# =================================
# ⏰ 定时任务配置
# =================================

# 股票列表定时更新间隔（24小时）
STOCK_LIST_UPDATE_INTERVAL = 24 * 3600

# 自动预测股票列表
AUTO_PREDICT_STOCKS = [
    {"symbol": "000001", "name": "平安银行"},
    {"symbol": "601138", "name": "工业富联"},
    {"symbol": "603336", "name": "宏辉果蔬"},
    {"symbol": "000651", "name": "格力电器"},
    {"symbol": "000858", "name": "五粮液"},
    {"symbol": "600519", "name": "贵州茅台"},
    {"symbol": "002594", "name": "比亚迪"},
    {"symbol": "600036", "name": "招商银行"},
    {"symbol": "601318", "name": "中国平安"},
    {"symbol": "600030", "name": "中信证券"}
]

# 自动预测间隔（1小时）
AUTO_PREDICT_INTERVAL = 3600

# 定时任务标志
_stock_list_refreshing = False
_predict_refreshing = False

# =================================
# ⏰ 定时任务函数
# =================================
def _scheduled_stock_list_update():
    """
    定时更新股票列表
    """
    global _stock_list_refreshing
    logger.info("启动股票列表定时更新任务")
    while True:
        try:
            if _stock_list_refreshing:
                logger.info("股票列表更新任务正在执行中，跳过本次")
                time.sleep(STOCK_LIST_UPDATE_INTERVAL)
                continue
            
            _stock_list_refreshing = True
            logger.info("开始执行股票列表更新任务")
            
            # 获取所有股票列表
            stocks = get_all_stocks()
            if not stocks.empty:
                logger.info(f"成功获取 {len(stocks)} 支股票列表")
                # 更新缓存
                save_stocks_cache()
                # 更新数据库
                update_stock_list(stocks)
            else:
                logger.warning("获取股票列表失败")
                
        except Exception as e:
            logger.error(f"股票列表定时更新失败: {str(e)}", exc_info=True)
        finally:
            _stock_list_refreshing = False
        
        # 等待下一次执行
        logger.info(f"股票列表更新任务完成，等待 {STOCK_LIST_UPDATE_INTERVAL/3600:.1f} 小时后执行下一次")
        time.sleep(STOCK_LIST_UPDATE_INTERVAL)


def _scheduled_stock_prediction():
    """
    定时预测已选股票
    """
    global _predict_refreshing
    logger.info("启动股票预测定时任务")
    while True:
        try:
            if _predict_refreshing:
                logger.info("股票预测任务正在执行中，跳过本次")
                time.sleep(AUTO_PREDICT_INTERVAL)
                continue
            
            # 判断当前时间是否需要执行预测
            current_time = datetime.now()
            current_date = current_time.date()
            current_hour = current_time.hour
            current_minute = current_time.minute
            current_weekday = current_time.weekday()
            
            # 检查是否为工作日
            if current_weekday >= 5:  # 周末
                logger.info("今天是周末，不执行股票预测任务")
                time.sleep(AUTO_PREDICT_INTERVAL)
                continue
            
            # 检查是否为交易日
            today_is_trading_day = is_trading_day(current_date)
            
            # 只有在交易日的15:00-16:00之间执行预测
            if today_is_trading_day and current_hour == 15 and 0 <= current_minute < 60:
                _predict_refreshing = True
                logger.info("开始执行股票预测任务")
                
                # 预测所有自动预测股票
                success_count = 0
                fail_count = 0
                
                for stock in AUTO_PREDICT_STOCKS:
                    symbol = stock["symbol"]
                    name = stock["name"]
                    try:
                        result = predict_signal(symbol, name)
                        if result:
                            logger.info(f"成功预测股票 {symbol} ({name})，信号：{result['signal']}")
                            success_count += 1
                        else:
                            logger.warning(f"预测股票 {symbol} ({name}) 失败")
                            fail_count += 1
                    except Exception as e:
                        logger.error(f"预测股票 {symbol} ({name}) 出错: {str(e)}", exc_info=True)
                        fail_count += 1
                
                logger.info(f"股票预测任务完成，成功预测 {success_count} 支股票，失败 {fail_count} 支股票")
                
            else:
                logger.info(f"当前时间 {current_time.strftime('%Y-%m-%d %H:%M:%S')} 不是股票预测时间，跳过本次")
                
        except Exception as e:
            logger.error(f"股票预测定时任务失败: {str(e)}", exc_info=True)
        finally:
            _predict_refreshing = False
        
        # 等待下一次执行
        logger.info(f"等待 {AUTO_PREDICT_INTERVAL/3600:.1f} 小时后执行下一次股票预测检查")
        time.sleep(AUTO_PREDICT_INTERVAL)

# =================================
# ⏰ 定时任务启动函数
# =================================
def start_scheduled_tasks():
    """
    启动所有定时任务
    """
    logger.info("正在启动定时任务系统...")
    
    try:
        # 初始化数据库
        init_db()
        
        # 加载股票列表缓存
        load_stocks_cache()
        
        # 启动股票列表定时更新线程
        stock_list_thread = threading.Thread(target=_scheduled_stock_list_update, daemon=True)
        stock_list_thread.start()
        logger.info("股票列表定时更新线程已启动")
        
        # 启动股票预测定时线程
        predict_thread = threading.Thread(target=_scheduled_stock_prediction, daemon=True)
        predict_thread.start()
        logger.info("股票预测定时线程已启动")
        
        logger.info("所有定时任务已成功启动")
        return True
        
    except Exception as e:
        logger.error(f"启动定时任务系统失败: {str(e)}", exc_info=True)
        return False
