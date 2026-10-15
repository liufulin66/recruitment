"""MySQL 集成测试底座：显式选择独立测试库，逐例准备与清理固定样例。"""

import os
import re
import unittest

from werkzeug.security import generate_password_hash

from config import DB
from db import get_connection
from web import create_app, init_database

TEST_USER = "test_user"
TEST_PASSWORD = "test123456"
TEST_PASSWORD_HASH = generate_password_hash(TEST_PASSWORD)


def test_db_settings():
    name = os.environ.get("RECRUIT_TEST_DB_NAME")
    if not name:
        raise unittest.SkipTest("未启用 MySQL 集成测试：请设置 RECRUIT_TEST_DB_NAME，详见 docs/testing.md")
    if not re.fullmatch(r"[A-Za-z0-9_]+_test(?:_[A-Za-z0-9_]+)?", name):
        raise ValueError("测试库名必须包含 _test 后缀（其后可带 _运行标识）")
    if name.casefold() == DB["database"].casefold():
        raise ValueError("测试库不能与日常使用的数据库相同")
    settings = dict(DB, database=name)
    for key in ("host", "port", "user", "password"):
        value = os.environ.get(f"RECRUIT_TEST_DB_{key.upper()}")
        if value is not None:
            settings[key] = int(value) if key == "port" else value
    return settings


def clear_tables(conn):
    with conn.cursor() as cur:
        for table in ("captcha_challenges", "users", "job_skills", "jobs", "snapshots"):
            cur.execute(f"DELETE FROM {table}")
    conn.commit()


def seed_data(conn):
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO snapshots (id, label, source, period, note) VALUES (%s, %s, %s, %s, %s)",
            [(1, "2018", "fixture-2018", "2018 年", "测试样例，含技能"),
             (2, "2020", "fixture-2020", "2020 年 4 月公开快照", "12 城市 IT 岗位样本，无逐条发布日期，无技能数据")],
        )
        cur.executemany(
            "INSERT INTO jobs (snapshot_id, job_name, company, city, salary_avg, edu, exp) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            [(1, "Python", "A", "杭州", 10000, "本科", "1-3年"),
             (1, "Java", "B", "杭州", 20000, "本科", "3-5年"),
             (1, "分析师", "C", "北京", None, "大专", "不限"),
             (1, "工程师", "D", "北京", 30000, "硕士", "3-5年"),
             (2, "后端", "E", "北京", 40000, "本科", "5-10年"),
             (2, "前端", "F", "上海", 50000, "本科", "3-5年")],
        )
        cur.executemany(
            "INSERT INTO job_skills (snapshot_id, source_map_id, key_word, skill) VALUES (%s, %s, %s, %s)",
            [(1, 1, "kw", "python"), (1, 1, "kw", "mysql"),
             (1, 2, "kw", "Python"), (1, 3, "kw", "java"), (1, 3, "kw", "mysql"),
             (1, 4, "kw", "without")],
        )
        cur.execute("INSERT INTO users (username, password_hash) VALUES (%s, %s)",
                    (TEST_USER, TEST_PASSWORD_HASH))
    conn.commit()


class MySQLTestCase(unittest.TestCase):
    keep_app_context = True

    @classmethod
    def setUpClass(cls):
        # 显式启用后，连接/建表失败直接算错误，不静默跳过。
        cls.db_settings = test_db_settings()
        cls.app = create_app({"TESTING": True, "SECRET_KEY": "isolated-test-key", "DB": cls.db_settings})
        with cls.app.app_context():
            init_database()

    def setUp(self):
        if self.keep_app_context:
            context = self.app.app_context()
            context.push()
            self.addCleanup(context.pop)
        self.conn = get_connection(self.db_settings)
        self.addCleanup(self.conn.close)
        clear_tables(self.conn)
        self.addCleanup(clear_tables, self.conn)
        seed_data(self.conn)
