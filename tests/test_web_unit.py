"""无需 MySQL 的 Web 边界测试，连接复用与认证页解耦的回归守卫。"""

import importlib
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from web import create_app


class TestApplicationFactory(unittest.TestCase):
    def test_import_and_factory_do_not_connect(self):
        with patch("db.pymysql.connect", side_effect=AssertionError("不应连接数据库")) as connect:
            import app

            importlib.reload(app)
            first = create_app({"TESTING": True, "SECRET_KEY": "first"})
            second = create_app({"TESTING": True, "SECRET_KEY": "second"})
            self.assertEqual(first.secret_key, "first")
            self.assertEqual(second.secret_key, "second")
            connect.assert_not_called()

    def test_public_pages_and_gate_do_not_query_analytics(self):
        app = create_app({"TESTING": True, "SECRET_KEY": "test"})
        with patch("db.pymysql.connect", side_effect=AssertionError("不应查询数据库")) as connect:
            client = app.test_client()
            for path in ("/login", "/register", "/static/assets/echarts.min.js"):
                response = client.get(path)
                self.assertEqual(response.status_code, 200)
                response.close()
            self.assertEqual(client.get("/salary").status_code, 302)
            self.assertEqual(client.get("/missing").status_code, 404)
            connect.assert_not_called()

    def test_salary_page_uses_one_connection_and_one_snapshot_query(self):
        app = create_app({"TESTING": True, "SECRET_KEY": "test"})
        conn = MagicMock()
        snapshots = [{"id": 1, "label": "2018", "period": "2018 年", "source": "fixture", "note": ""}]
        groups = pd.DataFrame({"value": ["本科"], "n": [1], "avg_salary": [20000]})
        with patch("db.get_connection", return_value=conn) as connect, \
             patch("web.dashboard.get_snapshots", return_value=snapshots) as get_snapshots, \
             patch("web.dashboard.get_salary_values", return_value=[20000]), \
             patch("web.dashboard.get_top_cities", return_value=[]), \
             patch("web.dashboard.get_group_stats", return_value=groups) as group_stats, \
             patch("web.dashboard.get_filter_options", return_value={"cities": [], "edus": [], "exps": []}):
            client = app.test_client()
            with client.session_transaction() as sess:
                sess["user_id"] = 1
                sess["username"] = "tester"
            self.assertEqual(client.get("/salary").status_code, 200)
            connect.assert_called_once_with()
            conn.close.assert_called_once_with()
            get_snapshots.assert_called_once_with(conn)
            self.assertEqual(group_stats.call_count, 2)
            self.assertTrue(all(c.kwargs == {"include_median": False} for c in group_stats.call_args_list))

    def test_connection_is_closed_on_query_error(self):
        app = create_app({"TESTING": True, "SECRET_KEY": "test"})
        conn = MagicMock()
        with patch("db.get_connection", return_value=conn), \
             patch("web.dashboard.get_snapshots", side_effect=RuntimeError("query failed")):
            client = app.test_client()
            with client.session_transaction() as sess:
                sess["user_id"] = 1
            with self.assertRaisesRegex(RuntimeError, "query failed"):
                client.get("/")
            conn.close.assert_called_once_with()
