"""验证码回归：真实 MySQL 下的过期、刷新撤销、旧 Cookie 重放及并发消费。"""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import MagicMock, patch
import unittest

import captcha
from tests.support import MySQLTestCase, TEST_USER, TEST_PASSWORD
from web import create_app


class TestCaptchaUnit(unittest.TestCase):
    def test_missing_id_does_not_connect(self):
        with patch("db.get_connection") as connect:
            self.assertFalse(captcha.consume(None, "CODE"))
            connect.assert_not_called()

    def test_unicode_input_is_rejected_without_error(self):
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value.fetchone.return_value = ("CODE", 1)
        with patch("db.get_connection", return_value=conn):
            self.assertFalse(captcha.consume("id", "中文"))
        conn.commit.assert_called_once_with()

    def test_error_rolls_back_and_closes(self):
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value.execute.side_effect = RuntimeError("db error")
        with patch("db.get_connection", return_value=conn):
            with self.assertRaisesRegex(RuntimeError, "db error"):
                captcha.consume("id", "CODE")
        conn.rollback.assert_called_once_with()
        conn.close.assert_called_once_with()


class TestCaptchaDatabase(MySQLTestCase):
    def test_expiry(self):
        challenge_id, code = captcha.issue()
        with self.conn.cursor() as cur:
            cur.execute("SELECT TIMESTAMPDIFF(SECOND, UTC_TIMESTAMP(6), expires_at) "
                        "FROM captcha_challenges WHERE id = %s", (challenge_id,))
            self.assertIn(cur.fetchone()[0], (299, 300))
            cur.execute("UPDATE captcha_challenges SET expires_at = UTC_TIMESTAMP(6) - INTERVAL 1 SECOND "
                        "WHERE id = %s", (challenge_id,))
        self.conn.commit()
        self.assertFalse(captcha.consume(challenge_id, code))

    def test_refresh_revokes_previous_challenge(self):
        old_id, old_code = captcha.issue()
        new_id, new_code = captcha.issue(old_id)
        self.assertFalse(captcha.consume(old_id, old_code))
        self.assertTrue(captcha.consume(new_id, new_code.lower()))
        self.assertFalse(captcha.consume(new_id, new_code))

    def test_old_cookie_cannot_restore_consumed_challenge(self):
        client = self.app.test_client()
        with patch("captcha.generate_code", return_value="TEST"):
            self.assertEqual(client.get("/captcha").status_code, 200)
        old_cookie = client.get_cookie("session").value
        response = client.post("/login", data={"username": TEST_USER, "password": "wrong", "captcha": "TEST"})
        self.assertIn("用户名或密码错误", response.get_data(as_text=True))
        client.set_cookie("session", old_cookie)
        response = client.post("/login", data={"username": TEST_USER, "password": TEST_PASSWORD, "captcha": "TEST"})
        self.assertIn("验证码错误", response.get_data(as_text=True))

    def test_two_application_instances_share_challenges(self):
        first = self.app.test_client()
        with patch("captcha.generate_code", return_value="TEST"):
            first.get("/captcha")
        second_app = create_app({"TESTING": True, "SECRET_KEY": self.app.secret_key, "DB": self.db_settings})
        second = second_app.test_client()
        second.set_cookie("session", first.get_cookie("session").value)
        response = second.post("/login", data={"username": TEST_USER, "password": TEST_PASSWORD, "captcha": "TEST"})
        self.assertEqual(response.status_code, 302)

    def test_only_one_concurrent_request_can_consume(self):
        challenge_id, code = captcha.issue()
        barrier = Barrier(2)

        def consume():
            with self.app.app_context():
                barrier.wait(timeout=5)
                return captcha.consume(challenge_id, code)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: consume(), range(2)))
        self.assertEqual(sorted(results), [False, True])
