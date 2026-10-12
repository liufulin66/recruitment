"""账号模块用例：密码哈希、注册校验与凭据校验（需要数据库；不可用时跳过）。"""

import unittest
import uuid


class TestAuthModule(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from db import get_connection

            conn = get_connection()
            conn.close()
        except Exception as e:
            raise unittest.SkipTest(f"数据库不可用：{e}")
        import auth

        cls.auth = auth
        auth.ensure_users_table()

    @staticmethod
    def _name():
        return f"u_{uuid.uuid4().hex[:10]}"

    def test_register_and_verify(self):
        """哈希可验：注册后原密码可通过校验，错误密码不通过。"""
        name = self._name()
        user_id, username = self.auth.register(name, "abc12345")
        self.assertIsInstance(user_id, int)
        self.assertEqual(username, name)
        self.assertEqual(self.auth.verify_login(name, "abc12345")[0], user_id)
        self.assertIsNone(self.auth.verify_login(name, "wrong-pass"))
        self.assertIsNone(self.auth.verify_login("nobody_here", "abc12345"))

    def test_verify_case_insensitive_username(self):
        """登录比对不区分大小写。"""
        name = self._name()
        self.auth.register(name, "abc12345")
        self.assertIsNotNone(self.auth.verify_login(name.upper(), "abc12345"))

    def test_duplicate_case_insensitive(self):
        """重名拒绝：不区分大小写、忽略首尾空白。"""
        name = self._name()
        self.auth.register(name, "abc12345")
        with self.assertRaises(self.auth.AuthError):
            self.auth.register(f"  {name.upper()}  ", "abc12345")

    def test_short_password_rejected(self):
        """密码过短 / 为空拒绝。"""
        with self.assertRaises(self.auth.AuthError):
            self.auth.register(self._name(), "12345")
        with self.assertRaises(self.auth.AuthError):
            self.auth.register(self._name(), "")

    def test_empty_username_rejected(self):
        with self.assertRaises(self.auth.AuthError):
            self.auth.register("   ", "abc12345")

    def test_stored_as_hash(self):
        """不存明文（规格场景）。"""
        name = self._name()
        password = "abc12345"
        self.auth.register(name, password)
        from db import get_connection

        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT password_hash FROM users WHERE username = %s", (name,))
                (stored,) = cur.fetchone()
        finally:
            conn.close()
        self.assertNotIn(password, stored)


if __name__ == "__main__":
    unittest.main()
