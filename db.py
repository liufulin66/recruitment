"""数据库连接模块：统一从这里获取 MySQL 连接（ETL 与后续 Web 层共用）。"""

import pymysql

from config import DB


def get_connection():
    """新建一个 MySQL 连接（utf8mb4；默认手动提交，便于用事务包裹批量写入）。"""
    return pymysql.connect(**DB)
