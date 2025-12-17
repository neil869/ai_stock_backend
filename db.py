# 数据库操作模块
import os
import time
import logging
from datetime import datetime
import pandas as pd
from sqlalchemy import create_engine, Column, String, Float, Date, DateTime, Integer, BigInteger, MetaData, Table, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy import text
import bcrypt  # 用于密码哈希
from trade_calendar import get_current_trading_day

# 配置日志
logger = logging.getLogger(__name__)

# 数据库连接配置
# 默认使用SQLite作为备选，方便开发和测试
DB_CONFIG = {
    'db_type': os.getenv('DB_TYPE', 'sqlite'),  # sqlite 或 mysql
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '3306'),
    'username': os.getenv('DB_USERNAME', 'root'),
    'password': os.getenv('DB_PASSWORD', ''),
    'database': os.getenv('DB_DATABASE', 'stock_data'),
    'sqlite_path': os.getenv('SQLITE_PATH', 'stock_data.db')
}

# 创建数据库引擎
if DB_CONFIG['db_type'] == 'mysql':
    DATABASE_URL = f"mysql+pymysql://{DB_CONFIG['username']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}?charset=utf8mb4"
else:
    DATABASE_URL = f"sqlite:///{DB_CONFIG['sqlite_path']}"

# 创建引擎，使用NullPool避免连接池问题
try:
    engine = create_engine(DATABASE_URL, poolclass=NullPool)
    Base = declarative_base()
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    metadata = MetaData()
    logger.info(f"成功创建数据库引擎: {DB_CONFIG['db_type']}")
except Exception as e:
    logger.error(f"创建数据库引擎失败: {str(e)}")
    raise RuntimeError(f"Database connection failed: {e}")

# 股票数据模型
class StockDaily(Base):
    __tablename__ = "stock_daily"
    
    symbol = Column(String(10), primary_key=True)
    date = Column(Date, primary_key=True)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(BigInteger, nullable=False)
    update_time = Column(DateTime, nullable=False, default=datetime.now)

# 预测结果模型
class PredictResult(Base):
    __tablename__ = "predict_results"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(10), index=True, nullable=False)
    stock_name = Column(String(100), nullable=False)
    board = Column(String(50), nullable=False)
    price = Column(Float, nullable=False)
    signal = Column(String(20), nullable=False)
    prob = Column(Float, nullable=False)
    sentiment_label = Column(String(20), nullable=False)
    sentiment_score = Column(Float, nullable=False)
    rsi = Column(Float, nullable=False)
    price_above_bb_upper = Column(String(5), nullable=False)  # 使用字符串存储布尔值
    mom_weakening = Column(String(5), nullable=False)  # 使用字符串存储布尔值
    drawdown_5d = Column(Float, nullable=False)
    reason = Column(Text, nullable=False)  # 新增：预测理由
    predict_date = Column(Date, index=True, nullable=False)
    created_at = Column(Date, nullable=False, default=datetime.now().date)
    update_time = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

# 用户模型
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password = Column(String(100), nullable=False)  # 存储哈希后的密码
    email = Column(String(100), unique=True, nullable=True)
    created_at = Column(Date, nullable=False, default=datetime.now().date)
    updated_at = Column(Date, nullable=False, default=datetime.now().date, onupdate=datetime.now().date)

# 股票列表模型
class StockList(Base):
    __tablename__ = "stock_list"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(10), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    board = Column(String(50), nullable=False)
    created_at = Column(Date, nullable=False, default=datetime.now().date)
    update_time = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

# 回测结果模型
class BacktestResult(Base):
    __tablename__ = "backtest_results"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(10), index=True, nullable=False)
    stock_name = Column(String(100), nullable=False)
    board = Column(String(50), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    initial_capital = Column(Float, nullable=False)
    final_capital = Column(Float, nullable=False)
    total_return_pct = Column(Float, nullable=False)
    annual_return_pct = Column(Float, nullable=False)
    max_drawdown_pct = Column(Float, nullable=False)
    sharpe_ratio = Column(Float, nullable=False)
    win_rate_pct = Column(Float, nullable=False)
    total_trades = Column(Integer, nullable=False)
    daily_values = Column(String, nullable=True)  # 使用JSON字符串存储日价值数据
    created_at = Column(Date, nullable=False, default=datetime.now().date)
    update_time = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

# 创建数据库表
def create_tables():
    """创建数据库表"""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("数据库表创建成功")
    except Exception as e:
        logger.error(f"创建数据库表失败: {str(e)}")
        raise

# 获取数据库会话
def get_db():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 密码哈希函数
def hash_password(password):
    """将密码进行哈希处理"""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

# 密码验证函数
def verify_password(plain_password, hashed_password):
    """验证密码是否匹配"""
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

# 创建新用户
def create_user(db, username, password, email=None):
    """创建新用户"""
    # 检查用户名是否已存在
    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user:
        return False, "用户名已存在"
    
    # 检查邮箱是否已存在
    if email:
        existing_email = db.query(User).filter(User.email == email).first()
        if existing_email:
            return False, "邮箱已被注册"
    
    # 创建新用户
    hashed_pwd = hash_password(password)
    new_user = User(
        username=username,
        password=hashed_pwd,
        email=email
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return True, "用户创建成功"

# 验证用户
def authenticate_user(db, username, password):
    """验证用户身份"""
    # 首先尝试通过邮箱查找用户
    user = db.query(User).filter(User.email == username).first()
    
    # 如果邮箱不存在，再尝试通过用户名查找（保持向后兼容性）
    if not user:
        user = db.query(User).filter(User.username == username).first()
        
    if not user:
        return False, None, "用户不存在"
    
    if not verify_password(password, user.password):
        return False, None, "密码错误"
    
    return True, user, "验证成功"

# 获取用户信息
def get_user_by_username(db, username):
    """根据用户名获取用户信息"""
    return db.query(User).filter(User.username == username).first()

# 批量插入股票数据
def batch_insert_stock_data(df, symbol):
    """
    批量插入股票数据到数据库，避免重复插入
    
    Args:
        df: 股票数据DataFrame，需要包含date, open, high, low, close, volume字段
        symbol: 股票代码
    """
    try:
        # 确保日期格式正确
        df['date'] = pd.to_datetime(df['date']).dt.date
        
        # 添加股票代码和更新时间
        df['symbol'] = symbol
        # 设置更新时间为当前时间
        df['update_time'] = datetime.now()
        
        # 根据数据库类型选择不同的插入策略
        if DB_CONFIG['db_type'] == 'sqlite':
            # 创建一个临时表
            temp_table_name = 'temp_stock_daily'
            
            # 将数据先插入到临时表
            df[['symbol', 'date', 'open', 'high', 'low', 'close', 'volume', 'update_time']].to_sql(
                temp_table_name,
                con=engine,
                if_exists='replace',
                index=False,
                chunksize=1000
            )
            
            # 使用SQLite的INSERT OR REPLACE语句将临时表中的数据插入到正式表
            # 这样可以更新已存在的数据（如当天未收盘的数据）
            insert_query = text(f"""
            INSERT OR REPLACE INTO stock_daily (symbol, date, open, high, low, close, volume, update_time)
            SELECT symbol, date, open, high, low, close, volume, update_time FROM {temp_table_name}
            """)
            
            with engine.connect() as conn:
                result = conn.execute(insert_query)
                conn.commit()
                inserted_rows = result.rowcount
            
            # 删除临时表
            drop_temp_query = text(f"DROP TABLE IF EXISTS {temp_table_name}")
            with engine.connect() as conn:
                conn.execute(drop_temp_query)
                conn.commit()
        else:  # MySQL
            # 对于MySQL，我们使用INSERT ... ON DUPLICATE KEY UPDATE语法
            # 这样可以插入新数据并更新已存在的数据
            
            # 首先，创建一个临时表来存储数据
            temp_table_name = f"stock_daily_temp_{symbol}_{int(time.time())}"
            
            # 将数据写入临时表
            df.to_sql(
                temp_table_name,
                con=engine,
                if_exists='replace',
                index=False,
                chunksize=1000
            )
            
            # 使用INSERT ... ON DUPLICATE KEY UPDATE语句将临时表中的数据插入到正式表
            insert_query = text(f"""
            INSERT INTO stock_daily (symbol, date, open, high, low, close, volume, update_time)
            SELECT symbol, date, open, high, low, close, volume, update_time FROM {temp_table_name}
            ON DUPLICATE KEY UPDATE
                open = VALUES(open),
                high = VALUES(high),
                low = VALUES(low),
                close = VALUES(close),
                volume = VALUES(volume),
                update_time = VALUES(update_time)
            """)
            
            with engine.connect() as conn:
                result = conn.execute(insert_query)
                conn.commit()
                inserted_rows = result.rowcount
            
            # 删除临时表
            drop_temp_query = text(f"DROP TABLE IF EXISTS {temp_table_name}")
            with engine.connect() as conn:
                conn.execute(drop_temp_query)
                conn.commit()
            
            # 如果没有新数据或更新的数据，inserted_rows可能为0
            if inserted_rows == 0:
                inserted_rows = 0
        
        if inserted_rows == 0:
            logger.info(f"[{symbol}] 没有新数据需要插入到数据库")
        else:
            logger.info(f"[{symbol}] 成功插入 {inserted_rows} 条新数据到数据库")
        
        return True
    except Exception as e:
        logger.error(f"[{symbol}] 批量插入数据失败: {str(e)}")
        return False

# 查询股票数据
def query_stock_data(symbol, start_date=None, end_date=None):
    """
    查询指定股票代码的历史数据
    
    Args:
        symbol: 股票代码
        start_date: 开始日期，格式为'YYYY-MM-DD'
        end_date: 结束日期，格式为'YYYY-MM-DD'
        
    Returns:
        DataFrame: 股票历史数据
    """
    try:
        # 构建查询语句
        query = f"SELECT * FROM stock_daily WHERE symbol = '{symbol}'"
        
        # 添加日期过滤条件
        if start_date:
            query += f" AND date >= '{start_date}'"
        if end_date:
            query += f" AND date <= '{end_date}'"
        
        # 执行查询
        df = pd.read_sql(query, con=engine)
        
        if not df.empty:
            # 转换日期格式
            df['date'] = pd.to_datetime(df['date'])
            # 设置日期为索引
            df.set_index('date', inplace=True)
            # 排序
            df.sort_index(inplace=True)
            # 删除symbol列，因为已经通过查询条件确定
            df.drop(columns=['symbol'], inplace=True)
            
            logger.info(f"[{symbol}] 从数据库查询到 {len(df)} 条数据")
        
        return df
    except Exception as e:
        logger.error(f"[{symbol}] 查询数据失败: {str(e)}")
        return pd.DataFrame()

# 检查股票数据完整性，是否是在最近的交易日收盘后更新的
def check_data_completeness(symbol, required_days=365, as_of_date=None):
    """
    检查指定股票的数据完整性
    
    Args:
        symbol: 股票代码
        required_days: 需要的最少数据天数
        as_of_date: 检查数据完整性的日期，格式为'YYYY-MM-DD HH:MM:SS'
        
    Returns:
        bool: 如果数据完整返回True，否则返回False
        int: 现有数据天数
    """
    try:
        # 查询最新日期和更新时间
        query = f"SELECT MAX(date) as latest_date, MAX(update_time) as latest_update FROM stock_daily WHERE symbol = '{symbol}'"
        latest_date_df = pd.read_sql(query, con=engine)
        
        if latest_date_df.empty or pd.isna(latest_date_df.iloc[0]['latest_date']):
            return False
        # 判断latest_date_df.iloc[0]['latest_date']是否在上一个交易日收盘后更新的
        latest_date = latest_date_df.iloc[0]['latest_date']
        # 判断latest_date是否是交易日
        if latest_date != get_current_trading_day():
            logger.info(f"{latest_date} 不是最新交易日")
            return False

        latest_update = latest_date_df.iloc[0]['latest_update']

        logger.info(f"最近收盘时间为 {as_of_date}")
        
        # 判断是否有as_of_date参数
        if as_of_date:
            # 确保as_of_date是时间戳类型
            if isinstance(as_of_date, str):
                try:
                    as_of_date = datetime.strptime(as_of_date, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    as_of_date = pd.to_datetime(as_of_date)
            elif not isinstance(as_of_date, datetime.datetime):
                as_of_date = pd.to_datetime(as_of_date)
            
        # 确保latest_update是时间戳类型
        if isinstance(latest_update, str):
            try:
                # 先尝试解析包含毫秒的格式
                latest_update = datetime.strptime(latest_update, '%Y-%m-%d %H:%M:%S.%f')
            except ValueError:
                # 如果失败，再尝试解析不包含毫秒的格式
                latest_update = datetime.strptime(latest_update, '%Y-%m-%d %H:%M:%S')
        elif not isinstance(latest_update, datetime.datetime):
            latest_update = pd.to_datetime(latest_update)

        # 判断是否在最近的交易日收盘后更新的
        if as_of_date:
            if latest_update <= as_of_date:
                logger.info(f"[{symbol}] 最新更新时间 {latest_update} 早于或等于检查日期 {as_of_date}，数据完整性检查不通过")
                return False
            else:
                logger.info(f"[{symbol}] 数据完整性检查通过，最新更新时间为 {latest_update}")
                return True
        else:
            logger.info(f"[{symbol}] 未指定检查日期，默认检查数据完整性")
            return False
    
    except Exception as e:
        logger.error(f"[{symbol}] 检查数据完整性失败: {str(e)}")
        return False

# 保存预测结果到数据库
def save_predict_result(result):
    """
    将预测结果保存到数据库
    
    Args:
        result: 预测结果字典，包含以下键:
            - name: 股票名称
            - stock_code: 股票代码
            - board: 市场板块
            - price: 当前价格
            - signal: 预测信号
            - prob: 预测概率
            - sentiment_label: 情感分析标签
            - sentiment_score: 情感分析分数
            - date: 数据日期
            - rsi: 相对强弱指标
            - price_above_bb_upper: 价格是否突破布林带上轨
            - mom_weakening: 动量是否减弱
            - drawdown_5d: 5日回撤
            - reason: 预测理由
    """
    try:
        # 转换日期格式
        predict_date = datetime.strptime(result['date'], '%Y-%m-%d').date()
        
        # 保存到数据库
        db = SessionLocal()
        
        # 检查是否已经存在相同stock_code和predict_date的记录
        existing_result = db.query(PredictResult).filter(
            PredictResult.stock_code == result['stock_code'],
            PredictResult.predict_date == predict_date
        ).first()
        
        if existing_result:
            # 更新现有记录
            existing_result.stock_name = result['name']
            existing_result.board = result['board']
            existing_result.price = result['price']
            existing_result.signal = result['signal']
            existing_result.prob = result['prob']
            existing_result.sentiment_label = result['sentiment_label']
            existing_result.sentiment_score = result['sentiment_score']
            existing_result.rsi = result['rsi']
            existing_result.price_above_bb_upper = 'Y' if result['price_above_bb_upper'] else 'N'
            existing_result.mom_weakening = 'Y' if result['mom_weakening'] else 'N'
            existing_result.drawdown_5d = result['drawdown_5d']
            existing_result.reason = result.get('reason', '')
            # update_time会自动更新（因为模型中设置了onupdate属性）
        else:
            # 创建新记录
            predict_result = PredictResult(
                stock_code=result['stock_code'],
                stock_name=result['name'],
                board=result['board'],
                price=result['price'],
                signal=result['signal'],
                prob=result['prob'],
                sentiment_label=result['sentiment_label'],
                sentiment_score=result['sentiment_score'],
                rsi=result['rsi'],
                price_above_bb_upper='Y' if result['price_above_bb_upper'] else 'N',
                mom_weakening='Y' if result['mom_weakening'] else 'N',
                drawdown_5d=result['drawdown_5d'],
                reason=result.get('reason', ''),
                predict_date=predict_date,
                created_at=datetime.now().date()
            )
            db.add(predict_result)
        
        db.commit()
        db.close()
        
        logger.info(f"预测结果已保存到数据库: {result['stock_code']} - {result['name']} ({result['date']})")
        return True
    except Exception as e:
        logger.error(f"保存预测结果到数据库失败: {str(e)}")
        return False

# 查询预测结果
def query_predict_results(stock_code=None, predict_date=None, start_date=None, end_date=None, limit=100):
    """
    查询预测结果
    
    Args:
        stock_code: 股票代码，可选
        predict_date: 预测日期，格式为'YYYY-MM-DD'，可选
        start_date: 开始日期，格式为'YYYY-MM-DD'，可选
        end_date: 结束日期，格式为'YYYY-MM-DD'，可选
        limit: 返回结果的最大数量，默认100
        
    Returns:
        list: 预测结果列表
    """
    try:
        # 构建查询
        query = "SELECT * FROM predict_results WHERE 1=1"
        
        # 添加过滤条件
        if stock_code:
            query += f" AND stock_code = '{stock_code}'"
        if predict_date:
            query += f" AND predict_date = '{predict_date}'"
        if start_date:
            query += f" AND predict_date >= '{start_date}'"
        if end_date:
            query += f" AND predict_date <= '{end_date}'"
        
        # 添加排序和限制
        query += " ORDER BY predict_date DESC, id DESC LIMIT ?"
        
        # 执行查询
        df = pd.read_sql(query, con=engine, params=(limit,))
        
        if df.empty:
            logger.info("未查询到预测结果")
            return []
        
        # 转换数据类型
        df['price_above_bb_upper'] = df['price_above_bb_upper'] == 'Y'
        df['mom_weakening'] = df['mom_weakening'] == 'Y'
        
        # 转换为字典列表
        results = df.to_dict('records')
        
        logger.info(f"查询到 {len(results)} 条预测结果")
        return results
    except Exception as e:
        logger.error(f"查询预测结果失败: {str(e)}")
        return []

# 删除所有预测结果
def delete_all_predict_results():
    """
    删除所有预测结果
    
    Returns:
        bool: 操作是否成功
    """
    try:
        db = SessionLocal()
        count = db.query(PredictResult).delete()
        db.commit()
        db.close()
        
        logger.info(f"已删除所有预测结果，共 {count} 条")
        return True
    except Exception as e:
        logger.error(f"删除所有预测结果失败: {str(e)}")
        return False

# 删除旧数据
def delete_old_data(symbol, keep_days=1825):  # 保留5年数据
    """
    删除指定股票的旧数据
    
    Args:
        symbol: 股票代码
        keep_days: 需要保留的天数
    """
    try:
        # 计算删除日期
        delete_date = (datetime.now() - pd.Timedelta(days=keep_days)).strftime('%Y-%m-%d')
        
        # 执行删除
        delete_query = f"DELETE FROM stock_daily WHERE symbol = '{symbol}' AND date < '{delete_date}'"
        with engine.connect() as conn:
            result = conn.execute(delete_query)
            conn.commit()
            logger.info(f"[{symbol}] 删除了 {result.rowcount} 条旧数据")
            
        return True
    except Exception as e:
        logger.error(f"[{symbol}] 删除旧数据失败: {str(e)}")
        return False

# 初始化数据库
def init_db():
    """初始化数据库"""
    create_tables()
    logger.info("数据库初始化完成")

# 保存回测结果到数据库
def save_backtest_result(result):
    """
    将回测结果保存到数据库
    
    Args:
        result: 回测结果字典，包含以下键:
            - stock_code: 股票代码
            - stock_name: 股票名称
            - board: 所属板块
            - start_date: 回测开始日期
            - end_date: 回测结束日期
            - initial_capital: 初始资金
            - final_capital: 最终资金
            - total_return_pct: 总收益率
            - annual_return_pct: 年化收益率
            - max_drawdown_pct: 最大回撤
            - sharpe_ratio: 夏普比率
            - win_rate_pct: 胜率
            - total_trades: 总交易次数
            - daily_values: 每日价值数据（字典格式）
    """
    try:
        # 转换日期格式
        start_date = datetime.strptime(result['start_date'], '%Y-%m-%d').date()
        end_date = datetime.strptime(result['end_date'], '%Y-%m-%d').date()
        
        # 导入json模块用于处理daily_values
        import json
        
        # 保存到数据库
        db = SessionLocal()
        
        # 检查是否已经存在相同的回测结果
        existing_result = db.query(BacktestResult).filter(
            BacktestResult.stock_code == result['stock_code'],
            BacktestResult.start_date == start_date,
            BacktestResult.end_date == end_date,
            BacktestResult.initial_capital == result['initial_capital']
        ).first()
        
        if existing_result:
            # 更新现有记录
            existing_result.stock_name = result['stock_name']
            existing_result.board = result['board']
            existing_result.final_capital = result['final_capital']
            existing_result.total_return_pct = result['total_return_pct']
            existing_result.annual_return_pct = result['annual_return_pct']
            existing_result.max_drawdown_pct = result['max_drawdown_pct']
            existing_result.sharpe_ratio = result['sharpe_ratio']
            existing_result.win_rate_pct = result['win_rate_pct']
            existing_result.total_trades = result['total_trades']
            existing_result.daily_values = json.dumps(result['daily_values'])
            # update_time会自动更新
        else:
            # 创建新记录
            backtest_result = BacktestResult(
                stock_code=result['stock_code'],
                stock_name=result['stock_name'],
                board=result['board'],
                start_date=start_date,
                end_date=end_date,
                initial_capital=result['initial_capital'],
                final_capital=result['final_capital'],
                total_return_pct=result['total_return_pct'],
                annual_return_pct=result['annual_return_pct'],
                max_drawdown_pct=result['max_drawdown_pct'],
                sharpe_ratio=result['sharpe_ratio'],
                win_rate_pct=result['win_rate_pct'],
                total_trades=result['total_trades'],
                daily_values=json.dumps(result['daily_values']),
                created_at=datetime.now().date()
            )
            db.add(backtest_result)
        
        db.commit()
        db.close()
        
        logger.info(f"回测结果已保存到数据库: {result['stock_code']} - {result['stock_name']} ({result['start_date']} 至 {result['end_date']})")
        return True
    except Exception as e:
        logger.error(f"保存回测结果到数据库失败: {str(e)}")
        return False

# 查询回测结果
def query_backtest_results(stock_code=None, start_date=None, end_date=None, limit=100):
    """
    查询回测结果
    
    Args:
        stock_code: 股票代码，可选
        start_date: 开始日期，格式为'YYYY-MM-DD'，可选
        end_date: 结束日期，格式为'YYYY-MM-DD'，可选
        limit: 返回结果的最大数量，默认100
        
    Returns:
        list: 回测结果列表
    """
    try:
        # 构建查询
        query = "SELECT * FROM backtest_results WHERE 1=1"
        
        # 添加过滤条件
        if stock_code:
            query += f" AND stock_code = '{stock_code}'"
        if start_date:
            query += f" AND start_date >= '{start_date}'"
        if end_date:
            query += f" AND end_date <= '{end_date}'"
        
        # 添加排序和限制
        query += " ORDER BY created_at DESC, id DESC LIMIT ?"
        
        # 执行查询
        import json
        df = pd.read_sql(query, con=engine, params=(limit,))
        
        if df.empty:
            logger.info("未查询到回测结果")
            return []
        
        # 转换daily_values从JSON字符串到字典
        if 'daily_values' in df.columns:
            df['daily_values'] = df['daily_values'].apply(lambda x: json.loads(x) if x else {})
        
        # 转换为字典列表
        results = df.to_dict('records')
        
        logger.info(f"查询到 {len(results)} 条回测结果")
        return results
    except Exception as e:
        logger.error(f"查询回测结果失败: {str(e)}")
        return []

# 更新股票列表到数据库
def update_stock_list(df):
    """
    将股票列表更新到数据库
    
    Args:
        df: 股票列表DataFrame，包含code和name字段
    """
    try:
        db = SessionLocal()
        
        # 获取现有的股票代码列表
        existing_codes = {row[0] for row in db.query(StockList.code).all()}
        
        # 处理每个股票
        for _, row in df.iterrows():
            code = row['code']
            name = row['name']
            
            # 判断股票板块
            if code.startswith('688'):
                board = '科创板'
            elif code.startswith('300'):
                board = '创业板'
            else:
                board = '主板'
            
            if code in existing_codes:
                # 更新现有记录
                stock = db.query(StockList).filter(StockList.code == code).first()
                if stock.name != name:
                    stock.name = name
                    stock.board = board
                    logger.info(f"更新股票信息: {code} - {name}")
            else:
                # 创建新记录
                new_stock = StockList(code=code, name=name, board=board)
                db.add(new_stock)
                existing_codes.add(code)
                logger.info(f"新增股票: {code} - {name}")
        
        db.commit()
        db.close()
        
        logger.info(f"股票列表更新完成，共处理 {len(df)} 支股票")
        return True
    except Exception as e:
        logger.error(f"更新股票列表到数据库失败: {str(e)}")
        return False

# 测试数据库连接
def test_db_connection():
    """测试数据库连接"""
    try:
        with engine.connect() as conn:
            conn.execute("SELECT 1")
            logger.info("数据库连接成功")
            return True
    except Exception as e:
        logger.error(f"数据库连接失败: {str(e)}")
        return False

# 主函数用于测试
if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(level=logging.INFO)
    
    # 测试连接
    test_db_connection()