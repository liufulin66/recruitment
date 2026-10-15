"""账号写入异常处理，不依赖 MySQL。"""

import unittest
from unittest.mock import MagicMock, patch

from pymysql import IntegrityError

import auth


class TestRegisterIntegrityError(unittest.TestCase):
    def test_duplicate_key_becomes_user_error(self):
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value.execute.side_effect = IntegrityError(1062, "duplicate")
        with patch("db.get_connection", return_value=conn), \
             patch("auth.generate_password_hash", return_value="hash"):
            with self.assertRaisesRegex(auth.AuthError, "用户名已被占用"):
                auth.register("tester", "password")
        conn.rollback.assert_called_once_with()
        conn.commit.assert_not_called()
        conn.close.assert_called_once_with()

    def test_other_integrity_errors_are_not_hidden(self):
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value.execute.side_effect = IntegrityError(1048, "null")
        with patch("db.get_connection", return_value=conn), \
             patch("auth.generate_password_hash", return_value="hash"):
            with self.assertRaises(IntegrityError):
                auth.register("tester", "password")
        conn.rollback.assert_called_once_with()
