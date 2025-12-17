# predict.py
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
    from lightgbm import LGBMClassifier
    from sklearn.utils.class_weight import compute_class_weight
    from db import save_predict_result, query_predict_results
    from data_fetch import get_stock_daily
    from stock_utils import get_market_board, analyze_stock_sentiment
    from trade_calendar import is_trading_day, is_trading_hours, get_next_trading_day
except ImportError as e:
    raise RuntimeError(f"Missing dependency: {e}")

# predict_signal缓存
_predict_cache = {}
_last_predict_update = {}

# 定时任务标志
_predict_refreshing = False

# 缓存文件路径定义
PREDICT_CACHE_FILE = 'predict_cache.pkl'


# ==============================
# 📁 缓存本地持久化功能
# ==============================
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


def predict_signal(symbol, name, train_window=200):
    """
    预测股票买卖信号
    - symbol: 股票代码
    - name: 股票名称
    - train_window: 训练窗口大小
    """
    logger.info(f"开始预测股票 {symbol} ({name}) 的信号")
    try:        
        # 获取股票数据
        df = get_stock_daily(symbol)
        if df is None or df.empty or len(df) < train_window + 1:
            logger.warning(f"[{symbol}] 数据不足或获取失败，无法进行预测")
            return None
    
        # 获取最新数据日期
        latest_data_date = df.index[-1].date()
        
        # 使用交易日历模块获取下一个交易日作为预测日期
        predict_date = get_next_trading_day(latest_data_date)
        predict_date_str = predict_date.strftime('%Y-%m-%d')
        
        as_of_date = df.index[-1]
        train_dates = df.index[-(train_window + 1):-1]

        logger.info(f"使用 {train_window} 天数据训练模型，预测日期：{predict_date_str}")

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
        
        # 组合最终理由
        reason = "".join(reasons) + "。"

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
