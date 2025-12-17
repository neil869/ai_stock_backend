# backtest.py
import pandas as pd
import numpy as np
import time
import logging
from datetime import datetime, timedelta
import warnings
import os
import pickle

# 配置logging
logger = logging.getLogger(__name__)

# 设置akshare请求头
os.environ['AKSHARE_HEADERS'] = '{"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}'
warnings.filterwarnings('ignore')

try:
    import akshare as ak
    from lightgbm import LGBMClassifier
    from sklearn.utils.class_weight import compute_class_weight
    from data_fetch import get_stock_daily
    from predict import calc_features_safe
    from db import save_backtest_result, query_backtest_results
    from stock_utils import get_market_board
    # 导入交易日历相关功能（这里暂时使用简单的判断，后面会引入calendar模块）
except ImportError as e:
    raise RuntimeError(f"Missing dependency: {e}")

# 回测缓存
_backtest_cache = {}
_last_backtest_update = {}

# 缓存文件路径定义
BACKTEST_CACHE_FILE = 'backtest_cache.pkl'


# ==============================
# 📁 缓存本地持久化功能
# ==============================
def load_backtest_cache():
    """
    从文件加载回测结果缓存
    """
    global _backtest_cache, _last_backtest_update
    try:
        if os.path.exists(BACKTEST_CACHE_FILE):
            with open(BACKTEST_CACHE_FILE, 'rb') as f:
                data = pickle.load(f)
                if isinstance(data, dict) and 'cache' in data and 'last_update' in data:
                    _backtest_cache = data['cache']
                    _last_backtest_update = data['last_update']
                    logger.info(f"从本地文件加载回测缓存成功，共 {len(_backtest_cache)} 条数据")
                    return True
    except Exception as e:
        logger.error(f"加载回测缓存失败：{e}")
    return False


def save_backtest_cache():
    """
    将回测结果缓存保存到文件
    """
    try:
        with open(BACKTEST_CACHE_FILE, 'wb') as f:
            pickle.dump({
                'cache': _backtest_cache,
                'last_update': _last_backtest_update
            }, f)
        logger.info(f"回测缓存已保存到本地文件，共 {len(_backtest_cache)} 条数据")
        return True
    except Exception as e:
        logger.error(f"保存回测缓存失败：{e}")
    return False


# ==============================
# 📊 回测功能
# ==============================
def backtest_ai_strategy(symbol, name, start_date='2023-01-01', end_date='2024-12-31', initial_capital=100000, transaction_cost=0.001):
    """
    回测AI策略的性能
    - symbol: 股票代码
    - name: 股票名称
    - start_date: 回测开始日期
    - end_date: 回测结束日期
    - initial_capital: 初始资金
    - transaction_cost: 交易成本
    """
    logger.info(f"开始回测股票 {symbol} ({name}) 的AI策略")
    try:
        # 获取股票数据
        df = get_stock_daily(symbol)
        if df is None or df.empty:
            logger.warning(f"[{symbol}] 数据不足或获取失败，无法进行回测")
            return None

        # 筛选回测期间的数据
        df = df[(df.index >= start_date) & (df.index <= end_date)]
        if len(df) < 200:
            logger.warning(f"[{symbol}] 回测期间数据不足，无法进行回测")
            return None

        # 初始化回测参数
        capital = initial_capital
        shares = 0
        trades = []
        positions = []
        daily_values = []

        train_window = 100  # 训练窗口大小
        test_window = 10    # 测试窗口大小

        # 分批次回测
        for i in range(train_window, len(df), test_window):
            # 训练数据
            train_end = i - 1
            train_data = df.iloc[:train_end+1]
            
            # 测试数据
            test_start = i
            test_end = min(i + test_window - 1, len(df) - 1)
            test_data = df.iloc[test_start:test_end+1]

            if len(train_data) < 100 or len(test_data) < 1:
                continue

            # 训练模型
            X_train = []
            y_train = []

            for j in range(60, len(train_data)):
                window_data = train_data.iloc[:j]
                feat = calc_features_safe(window_data)
                if feat is None:
                    continue
                X_train.append(feat)
                ret = (train_data.iloc[j]['close'] - train_data.iloc[j-1]['close']) / train_data.iloc[j-1]['close']
                y_train.append(int(ret > 0))

            if len(X_train) < 50:
                continue

            X_train = pd.DataFrame(X_train)
            y_train = np.array(y_train)

            # 处理类别不平衡问题
            classes = np.unique(y_train)
            class_weight = dict(zip(classes, compute_class_weight('balanced', classes=classes, y=y_train))) if len(classes) == 2 else None

            # 训练模型
            model = LGBMClassifier(
                n_estimators=80,
                max_depth=4,
                random_state=42,
                verbose=-1,
                class_weight=class_weight
            )
            model.fit(X_train, y_train)

            # 回测测试集
            for idx, (date, row) in enumerate(test_data.iterrows()):
                # 计算特征
                window_data = df.iloc[:test_start+idx]
                feat = calc_features_safe(window_data)
                if feat is None:
                    continue

                # 预测信号
                prob = model.predict_proba([feat.reindex(X_train.columns, fill_value=0)])[0][1]
                
                # 生成交易信号
                signal = 0  # 0: 持有, 1: 买入, -1: 卖出
                if prob > 0.6:
                    signal = 1
                elif prob < 0.4:
                    signal = -1

                # 执行交易
                if signal == 1 and shares == 0:
                    # 买入
                    shares_to_buy = capital // (row['close'] * 100) * 100
                    cost = shares_to_buy * row['close'] * (1 + transaction_cost)
                    if cost <= capital:
                        shares = shares_to_buy
                        capital -= cost
                        trades.append({
                            'date': date,
                            'action': 'buy',
                            'price': row['close'],
                            'shares': shares_to_buy,
                            'capital': capital,
                            'total_value': capital + shares * row['close']
                        })
                elif signal == -1 and shares > 0:
                    # 卖出
                    proceeds = shares * row['close'] * (1 - transaction_cost)
                    capital += proceeds
                    trades.append({
                        'date': date,
                        'action': 'sell',
                        'price': row['close'],
                        'shares': shares,
                        'capital': capital,
                        'total_value': capital
                    })
                    shares = 0

                # 记录每日价值
                daily_value = capital + (shares * row['close'] if shares > 0 else 0)
                daily_values.append({
                    'date': date,
                    'value': daily_value,
                    'return': (daily_value / initial_capital - 1) * 100
                })

        if not daily_values:
            logger.warning(f"[{symbol}] 回测期间无有效数据，无法生成回测结果")
            return None

        # 计算回测指标
        df_values = pd.DataFrame(daily_values)
        df_values.set_index('date', inplace=True)
        df_values['cumulative_return'] = (df_values['value'] / initial_capital - 1) * 100

        # 计算最大回撤
        df_values['peak'] = df_values['value'].cummax()
        df_values['drawdown'] = (df_values['value'] - df_values['peak']) / df_values['peak'] * 100
        max_drawdown = df_values['drawdown'].min()

        # 计算年化收益率
        start_date = df_values.index[0]
        end_date = df_values.index[-1]
        days = (end_date - start_date).days
        annual_return = (df_values['value'].iloc[-1] / initial_capital) ** (365 / days) - 1
        annual_return_pct = annual_return * 100

        # 计算夏普比率
        daily_returns = df_values['value'].pct_change().dropna()
        sharpe_ratio = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252) if daily_returns.std() != 0 else 0

        # 计算胜率
        if trades:
            winning_trades = [t for t in trades if t['action'] == 'sell' and t['total_value'] > initial_capital]
            win_rate = len(winning_trades) / len(trades) * 100 if len(trades) > 0 else 0
        else:
            win_rate = 0

        # 生成回测结果
        backtest_result = {
            'stock_code': symbol,
            'stock_name': name,
            'board': get_market_board(symbol),
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': end_date.strftime('%Y-%m-%d'),
            'initial_capital': initial_capital,
            'final_capital': df_values['value'].iloc[-1],
            'total_return_pct': (df_values['value'].iloc[-1] / initial_capital - 1) * 100,
            'annual_return_pct': annual_return_pct,
            'max_drawdown_pct': max_drawdown,
            'sharpe_ratio': sharpe_ratio,
            'win_rate_pct': win_rate,
            'total_trades': len(trades),
            'daily_values': df_values['cumulative_return'].to_dict()
        }

        # 保存回测结果到数据库
        save_backtest_result(backtest_result)

        logger.info(f"股票 {symbol} ({name}) 的AI策略回测完成")
        return backtest_result

    except Exception as e:
        logger.error(f"[{symbol}] 回测失败: {str(e)}", exc_info=True)
        return None


def backtest_ai_strategy_cached(symbol, name, start_date='2023-01-01', end_date='2024-12-31', initial_capital=100000, transaction_cost=0.001):
    """
    带缓存的回测AI策略函数
    - symbol: 股票代码
    - name: 股票名称
    - start_date: 回测开始日期
    - end_date: 回测结束日期
    - initial_capital: 初始资金
    - transaction_cost: 交易成本
    """
    # 检查缓存
    cache_key = f"{symbol}_{start_date}_{end_date}_{initial_capital}_{transaction_cost}"
    now = time.time()
    
    # 缓存有效期为24小时
    if cache_key in _backtest_cache and (now - _last_backtest_update.get(cache_key, 0) < 24 * 3600):
        logger.info(f"使用缓存的回测结果: {symbol} ({name})")
        return _backtest_cache[cache_key]
    
    # 执行回测
    result = backtest_ai_strategy(symbol, name, start_date, end_date, initial_capital, transaction_cost)
    
    # 更新缓存
    if result:
        _backtest_cache[cache_key] = result
        _last_backtest_update[cache_key] = now
        logger.info(f"更新回测缓存: {symbol} ({name})")
        save_backtest_cache()  # 保存缓存到文件
    
    return result
