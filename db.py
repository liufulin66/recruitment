"""数据库连接模块：统一从这里获取 MySQL 连接（ETL 与后续 Web 层共用）。"""

from contextlib import contextmanager

import pymysql
from flask import current_app, g, has_app_context, has_request_context

from config import DB


def get_connection(settings=None):
    """新建一个 MySQL 连接（utf8mb4；默认手动提交，便于用事务包裹批量写入）。"""
    if settings is None:
        settings = current_app.config["DB"] if has_app_context() else DB
    return pymysql.connect(**settings)


def get_db():
    """同一请求共享一条连接；连接只在第一次实际查询时创建。"""
    if "db" not in g:
        g.db = get_connection()
    return g.db


def close_db(error=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


@contextmanager
def connection():
    """Web 请求复用连接；命令行调用自己创建并关闭连接。"""
    if has_request_context():
        yield get_db()
    else:
        conn = get_connection()
        try:
            yield conn
        finally:
            conn.close()
