"""
股票助手 —— Tushare 数据采集 + MySQL 存储 + qwen-agent SQL 查询工具
SQL 工具逻辑来自 assistant_stock.py，连股票专属数据库，只允许 SELECT
"""

import os
import json
from datetime import date
import pymysql
import tushare as ts
import pandas as pd
from sqlalchemy import create_engine
from qwen_agent.tools.base import BaseTool, register_tool

from config import (
    TUSHARE_TOKEN,
    MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DB,
)

# ====== 股票助手 system prompt（来自 assistant_stock.py）======
STOCK_SYSTEM_PROMPT = """我是股票助手，以下是关于股票相关表的字段，我可能会编写对应的SQL(运行环境是MySQL8.0)，对数据进行查询
-- 股票日线价格表
CREATE TABLE stock_daily_price (
    ts_code VARCHAR(20) NOT NULL,                  -- TS股票代码，例如：000001.SZ
    trade_date CHAR(8) NOT NULL,                   -- 交易日期
    open double(255,2) NULL,                       -- 开盘价
    high double(255,2) NULL,                       -- 最高价
    low double(255,2) NULL,                        -- 最低价
    close double(255,2) NULL,                      -- 收盘价
    pre_close double(255,2) NULL,                  -- 前收盘价
    `change` double(255,2) NULL,                   -- 涨跌额
    pct_chg double(255,2) NULL,                    -- 涨跌幅
    vol BIGINT NULL,                               -- 成交量
    amount double(255,2) NULL,                     -- 成交额
    turnover_rate double(255,2) NULL,              -- 换手率
    volume_ratio double(255,2) NULL,               -- 量比
    total_share double(255,2) NULL,                -- 总股本
    float_share double(255,2) NULL,                -- 流通股本
    total_mv double(255,2) NULL,                   -- 总市值
    circ_mv double(255,2) NULL,                    -- 流通市值
    pe double(255,2) NULL,                         -- 市盈率
    ps double(255,2) NULL,                         -- 市销率
    limit_status VARCHAR(16) NULL,                 -- 涨跌停状态，0：正常，1：涨停，-1：跌停
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (ts_code, trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 股票名称表
CREATE TABLE stock_name (
    ts_code VARCHAR(16) NOT NULL PRIMARY KEY,      -- TS股票代码，例如：000001.SZ
    symbol VARCHAR(16) DEFAULT NULL,               -- 股票代码
    name VARCHAR(64) DEFAULT NULL,                 -- 股票名称
    area VARCHAR(64) DEFAULT NULL,                 -- 所属地区
    industry VARCHAR(128) DEFAULT NULL,            -- 所属行业
    list_date VARCHAR(16) DEFAULT NULL,            -- 上市日期
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 两张表按照 ts_code 字段关联
-- 例如：
-- SELECT a.*, b.name, b.industry 
-- FROM stock_daily_price a 
-- JOIN stock_name b ON a.ts_code = b.ts_code

我将回答用户关于股票相关的问题，只支持 SELECT 查询操作
"""

STOCK_SUGGESTIONS = [
    "查询最近一周涨幅前10的股票",
    "2026年3月27日开盘高开3个点，收盘对于开盘低5个点以上，返回包括股票代码，股票名称，开盘价，收盘价，涨跌幅的表格，按换手率排序",
    "2026年3月25日，2026年3月26日，2026年3月27日连续三天收盘价大于开盘价，股价每天上涨小于3个点的股票，返回包括股票代码，股票名称，开盘价，收盘价，涨跌幅的表格，按换手率排序",
    "2026年3月26日涨停，2026年3月27日大跌的股票（跌幅大于5个点），返回包括股票代码，股票名称，开盘价，收盘价，涨跌幅的表格，按换手率排序",
]


# ====== 股票专属 SQL 工具（来自 assistant_stock.py 的 ExcSQLTool 逻辑）======
@register_tool('exc_sql_stock')
class ExcSQLStockTool(BaseTool):
    """股票 SQL 查询工具，只允许 SELECT，连股票数据库，返回最多20行"""
    description = '对于生成的SQL，进行SQL查询，只支持SELECT操作'
    parameters = [{
        'name': 'sql_input',
        'type': 'string',
        'description': '生成的SQL语句，只允许SELECT查询',
        'required': True
    }]

    def call(self, params: str, **kwargs) -> str:
        args = json.loads(params)
        sql_input = args['sql_input']

        # 只允许 SELECT 操作（与 assistant_stock.py 保持一致）
        if not sql_input.strip().upper().startswith('SELECT'):
            return "错误：只支持 SELECT 查询操作，禁止其他操作"

        try:
            engine = create_engine(
                f'mysql+mysqlconnector://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}?charset=utf8mb4',
                connect_args={'connect_timeout': 10}, pool_size=10, max_overflow=20
            )
            df = pd.read_sql(sql_input, engine)
            # 返回前20行（与 assistant_stock.py 保持一致）
            return df.head(20).to_markdown(index=False)
        except Exception as e:
            return f"SQL执行出错: {str(e)}"


# ====== 数据库连接（用于数据采集写入）======
def get_conn():
    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DB,
        charset='utf8mb4',
        autocommit=False,
    )


# ====== 获取股票基本信息 ======
def fetch_and_save_stock_names() -> dict:
    pro = ts.pro_api(TUSHARE_TOKEN)
    df = pro.stock_basic(
        ts_code='', name='', exchange='', market='',
        is_hs='', list_status='', limit='', offset='',
        fields=['symbol', 'name', 'area', 'industry', 'list_date', 'ts_code'],
    )
    if df.empty:
        return {'success': False, 'message': '未获取到股票基本信息', 'count': 0}

    conn = get_conn()
    create_sql = """
    CREATE TABLE IF NOT EXISTS stock_name (
        ts_code   VARCHAR(16)  NOT NULL PRIMARY KEY,
        symbol    VARCHAR(16)  DEFAULT NULL,
        name      VARCHAR(64)  DEFAULT NULL,
        area      VARCHAR(64)  DEFAULT NULL,
        industry  VARCHAR(128) DEFAULT NULL,
        list_date VARCHAR(16)  DEFAULT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
    upsert_sql = """
    INSERT INTO stock_name (ts_code, symbol, name, area, industry, list_date)
    VALUES (%s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
        symbol=VALUES(symbol), name=VALUES(name), area=VALUES(area),
        industry=VALUES(industry), list_date=VALUES(list_date);
    """
    rows = [
        (row.ts_code, row.symbol, row.name, row.area, row.industry, row.list_date)
        for row in df.itertuples(index=False)
    ]
    try:
        with conn.cursor() as cur:
            cur.execute(create_sql)
            for i in range(0, len(rows), 1000):
                cur.executemany(upsert_sql, rows[i:i+1000])
        conn.commit()
        return {'success': True, 'message': f'成功写入 {len(rows)} 条股票基本信息', 'count': len(rows)}
    except Exception as e:
        conn.rollback()
        return {'success': False, 'message': f'写入失败：{str(e)}', 'count': 0}
    finally:
        conn.close()


# ====== 获取股票当日行情 ======
def fetch_and_save_today_price() -> dict:
    trade_date = date.today().strftime('%Y%m%d')
    return fetch_and_save_price_by_date(trade_date)


# ====== 获取指定日期行情 ======
def fetch_and_save_price_by_date(trade_date: str) -> dict:
    pro = ts.pro_api(TUSHARE_TOKEN)

    df_daily = pro.daily(
        ts_code='', trade_date=trade_date,
        start_date='', end_date='', limit='', offset='',
        fields=['ts_code', 'trade_date', 'open', 'high', 'low', 'close',
                'pre_close', 'change', 'pct_chg', 'vol', 'amount'],
    )
    if df_daily.empty:
        return {
            'success': False,
            'message': f'未获取到 {trade_date} 的日线数据（可能是非交易日）',
            'count': 0,
            'trade_date': trade_date,
        }

    df_basic = pro.daily_basic(
        ts_code='', trade_date=trade_date,
        start_date='', end_date='', limit='', offset='',
        fields=['ts_code', 'trade_date', 'turnover_rate', 'volume_ratio',
                'total_share', 'float_share', 'total_mv', 'circ_mv',
                'pe', 'ps', 'limit_status'],
    )

    df = df_daily.merge(df_basic, on=['ts_code', 'trade_date'], how='left')
    df = df.astype(object).where(df.notna(), None)

    conn = get_conn()
    create_sql = """
    CREATE TABLE IF NOT EXISTS stock_daily_price (
        ts_code       VARCHAR(20)  NOT NULL,
        trade_date    CHAR(8)      NOT NULL,
        open          DOUBLE(255,2) NULL,
        high          DOUBLE(255,2) NULL,
        low           DOUBLE(255,2) NULL,
        close         DOUBLE(255,2) NULL,
        pre_close     DOUBLE(255,2) NULL,
        `change`      DOUBLE(255,2) NULL,
        pct_chg       DOUBLE(255,2) NULL,
        vol           BIGINT NULL,
        amount        DOUBLE(255,2) NULL,
        turnover_rate DOUBLE(255,2) NULL,
        volume_ratio  DOUBLE(255,2) NULL,
        total_share   DOUBLE(255,2) NULL,
        float_share   DOUBLE(255,2) NULL,
        total_mv      DOUBLE(255,2) NULL,
        circ_mv       DOUBLE(255,2) NULL,
        pe            DOUBLE(255,2) NULL,
        ps            DOUBLE(255,2) NULL,
        limit_status  VARCHAR(16)  NULL,
        updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY (ts_code, trade_date)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
    upsert_sql = """
    INSERT INTO stock_daily_price (
        ts_code, trade_date, open, high, low, close, pre_close, `change`, pct_chg,
        vol, amount, turnover_rate, volume_ratio, total_share, float_share,
        total_mv, circ_mv, pe, ps, limit_status
    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    ON DUPLICATE KEY UPDATE
        open=VALUES(open), high=VALUES(high), low=VALUES(low), close=VALUES(close),
        pre_close=VALUES(pre_close), `change`=VALUES(`change`), pct_chg=VALUES(pct_chg),
        vol=VALUES(vol), amount=VALUES(amount), turnover_rate=VALUES(turnover_rate),
        volume_ratio=VALUES(volume_ratio), total_share=VALUES(total_share),
        float_share=VALUES(float_share), total_mv=VALUES(total_mv),
        circ_mv=VALUES(circ_mv), pe=VALUES(pe), ps=VALUES(ps),
        limit_status=VALUES(limit_status);
    """
    rows = [
        (
            row.ts_code, row.trade_date, row.open, row.high, row.low,
            row.close, row.pre_close, row.change, row.pct_chg, row.vol, row.amount,
            getattr(row, 'turnover_rate', None), getattr(row, 'volume_ratio', None),
            getattr(row, 'total_share', None), getattr(row, 'float_share', None),
            getattr(row, 'total_mv', None), getattr(row, 'circ_mv', None),
            getattr(row, 'pe', None), getattr(row, 'ps', None),
            getattr(row, 'limit_status', None),
        )
        for row in df.itertuples(index=False)
    ]
    try:
        with conn.cursor() as cur:
            cur.execute(create_sql)
            for i in range(0, len(rows), 1000):
                cur.executemany(upsert_sql, rows[i:i+1000])
        conn.commit()
        return {
            'success': True,
            'message': f'成功写入 {trade_date} 共 {len(rows)} 条行情数据',
            'count': len(rows),
            'trade_date': trade_date,
        }
    except Exception as e:
        conn.rollback()
        return {'success': False, 'message': f'写入失败：{str(e)}', 'count': 0, 'trade_date': trade_date}
    finally:
        conn.close()
