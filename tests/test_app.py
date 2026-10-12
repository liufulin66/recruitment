"""页面与账号流程用例：需要数据库；不可用时整体跳过。

- TestAppPages：原页面冒烟（改为"先登录再访问"）；
- TestAuthFlow：注册 / 登录 / 验证码 / 门卫 / 会话 / 登出等规格场景。
"""

import unittest
import uuid

TEST_USER = "test_user"
TEST_PASSWORD = "test123456"


class AppTestCase(unittest.TestCase):
    """公共底座：确认数据库可用，准备 app 与"默认已登录"的 client 工厂。"""

    @classmethod
    def setUpClass(cls):
        try:
            from db import get_connection

            conn = get_connection()
            conn.close()
        except Exception as e:
            raise unittest.SkipTest(f"数据库不可用：{e}")
        from app import app

        app.testing = True
        cls.app = app

    def client(self, logged_in=True):
        """返回一个新 client；默认已完成登录（幂等测试账号）。"""
        c = self.app.test_client()
        if logged_in:
            self._ensure_login(c)
        return c

    @classmethod
    def _seed_captcha(cls, client, code="TEST"):
        """把固定验证码写进会话（绕过图形交互，便于测试登录提交）。"""
        with client.session_transaction() as sess:
            sess["captcha_code"] = code

    @classmethod
    def _login(cls, client, username, password, **extra):
        """带（固定）验证码提交登录。"""
        cls._seed_captcha(client)
        data = {"username": username, "password": password, "captcha": "TEST", **extra}
        return client.post("/login", data=data)

    @classmethod
    def _ensure_login(cls, client):
        """测试账号不存在则注册（会自动登录），存在则直接登录——幂等，可反复跑。"""
        resp = client.post("/register", data={"username": TEST_USER, "password": TEST_PASSWORD})
        if resp.status_code == 302:
            return
        cls._login(client, TEST_USER, TEST_PASSWORD)


class TestAppPages(AppTestCase):
    """页面冒烟（登录后访问）。"""

    def test_all_pages_return_200(self):
        """规格场景：5 个页面均正常渲染。"""
        c = self.client()
        for path in ("/", "/salary", "/geo", "/skills", "/company"):
            with self.subTest(path=path):
                self.assertEqual(c.get(path).status_code, 200)

    def test_filter_marks_selected_and_applies(self):
        """筛选生效：下拉选中 + 数据随筛选变化。"""
        html = self.client().get("/?city=杭州").get_data(as_text=True)
        self.assertIn('value="杭州" selected', html)
        self.assertIn("1,258", html)  # 杭州岗位数（当前数据）

    def test_nav_keeps_filters(self):
        """规格场景：跨页导航保留筛选条件（链接自带当前参数）。"""
        html = self.client().get("/salary?city=杭州").get_data(as_text=True)
        self.assertIn("/skills?city=%E6%9D%AD%E5%B7%9E", html)

    def test_empty_result_renders(self):
        """规格场景：无数据也返回 200，并显示空态提示。"""
        resp = self.client().get("/?city=不存在的城市")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("暂无数据", resp.get_data(as_text=True))

    def test_nav_shows_user_and_logout(self):
        """规格场景：导航展示当前用户名与退出入口。"""
        html = self.client().get("/").get_data(as_text=True)
        self.assertIn(TEST_USER, html)
        self.assertIn("退出", html)


class TestAuthFlow(AppTestCase):
    """账号流程规格场景。"""

    def test_gate_redirects_anonymous(self):
        """门卫：未登录访问数据页 -> 302 到登录页并带 next；登录/注册/验证码/静态资源放行。"""
        c = self.client(logged_in=False)
        resp = c.get("/")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.headers["Location"].startswith("/login?next="))
        self.assertEqual(c.get("/login").status_code, 200)
        self.assertEqual(c.get("/register").status_code, 200)
        self.assertEqual(c.get("/captcha").status_code, 200)
        self.assertEqual(c.get("/static/assets/echarts.min.js").status_code, 200)

    def test_register_success_autologin(self):
        """规格场景：注册成功自动登录。"""
        c = self.client(logged_in=False)
        name = f"reg_{uuid.uuid4().hex[:8]}"
        resp = c.post("/register", data={"username": name, "password": "abc12345"})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(c.get("/").status_code, 200)  # 已自动登录（否则会被门卫拦 302）

    def test_register_duplicate_and_short_password(self):
        """规格场景：重名（不区分大小写）拒绝；密码过短拒绝。"""
        self.client()  # 先确保测试账号存在（幂等）
        c = self.client(logged_in=False)
        resp = c.post("/register", data={"username": TEST_USER.upper(), "password": "abc12345"})
        self.assertIn("用户名已被占用", resp.get_data(as_text=True))
        resp = c.post("/register", data={"username": "whoever", "password": "12345"})
        self.assertIn("密码长度至少", resp.get_data(as_text=True))

    def test_captcha_image_and_session(self):
        """规格场景：验证码接口返回图形并写入会话；未登录可访问。"""
        c = self.client(logged_in=False)
        resp = c.get("/captcha")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.mimetype, "image/svg+xml")
        with c.session_transaction() as sess:
            code = sess.get("captcha_code")
        self.assertTrue(code and len(code) == 4)

    def test_captcha_required_and_wrong(self):
        """规格场景：验证码缺失 / 错误 -> 提示验证码错误，不进行凭据校验。"""
        self.client()  # 确保账号存在（若此处误用正确凭证也不该因此通过）
        c = self.client(logged_in=False)
        resp = c.post("/login", data={"username": TEST_USER, "password": TEST_PASSWORD})
        self.assertIn("验证码错误", resp.get_data(as_text=True))

        self._seed_captcha(c, "TEST")
        resp = c.post(
            "/login", data={"username": TEST_USER, "password": TEST_PASSWORD, "captcha": "XXXX"}
        )
        self.assertIn("验证码错误", resp.get_data(as_text=True))

    def test_captcha_one_time(self):
        """规格场景：验证码一次性——同一码二次提交被拒（防重放）。"""
        self.client()  # 确保账号存在
        c = self.client(logged_in=False)
        self._seed_captcha(c, "TEST")
        # 第一次：验证码对、密码错 -> 验证码被消耗
        resp = c.post("/login", data={"username": TEST_USER, "password": "wrong", "captcha": "TEST"})
        self.assertIn("用户名或密码错误", resp.get_data(as_text=True))
        # 第二次：旧验证码已作废 -> 即使密码正确也提示验证码错误
        resp = c.post(
            "/login", data={"username": TEST_USER, "password": TEST_PASSWORD, "captcha": "TEST"}
        )
        self.assertIn("验证码错误", resp.get_data(as_text=True))

    def test_login_wrong_credentials(self):
        """规格场景：凭证错误统一提示，不透露具体原因。"""
        self.client()  # 确保账号存在
        c = self.client(logged_in=False)
        resp = self._login(c, TEST_USER, "wrong-pass")
        self.assertIn("用户名或密码错误", resp.get_data(as_text=True))

    def test_login_redirects_back(self):
        """规格场景：登录成功后跳回登录前要访问的页面。"""
        self.client()  # 确保账号存在
        c = self.client(logged_in=False)
        resp = self._login(c, TEST_USER, TEST_PASSWORD, next="/salary?city=杭州")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/salary", resp.headers["Location"])

    def test_remember_me_session(self):
        """规格场景：勾选记住我 -> 永久会话；未勾选 -> 浏览器会话。"""
        self.client()  # 确保账号存在
        c = self.client(logged_in=False)
        self._login(c, TEST_USER, TEST_PASSWORD, remember_me="1")
        with c.session_transaction() as sess:
            self.assertTrue(sess.permanent)

        c2 = self.client(logged_in=False)
        self._login(c2, TEST_USER, TEST_PASSWORD)
        with c2.session_transaction() as sess:
            self.assertFalse(sess.permanent)

    def test_cookie_flags(self):
        """规格场景：会话 Cookie 带 HttpOnly 与 SameSite=Lax。"""
        self.client()  # 确保账号存在
        c = self.client(logged_in=False)
        resp = self._login(c, TEST_USER, TEST_PASSWORD)
        cookies = "; ".join(resp.headers.getlist("Set-Cookie"))
        self.assertIn("HttpOnly", cookies)
        self.assertIn("SameSite=Lax", cookies)

    def test_password_not_plaintext(self):
        """规格场景：数据库只存哈希、不存明文。"""
        self.client()  # 确保账号存在
        from db import get_connection

        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT password_hash FROM users WHERE username = %s", (TEST_USER,))
                (stored,) = cur.fetchone()
        finally:
            conn.close()
        self.assertNotEqual(stored, TEST_PASSWORD)
        self.assertNotIn(TEST_PASSWORD, stored)

    def test_logout(self):
        """规格场景：登出后会话失效、需重新登录。"""
        c = self.client()
        self.assertEqual(c.get("/").status_code, 200)
        resp = c.get("/logout")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(c.get("/").status_code, 302)  # 再次被门卫拦截

    def test_logged_in_visiting_login_redirects(self):
        """规格场景：已登录访问登录页 -> 直接回总览。"""
        c = self.client()
        self.assertEqual(c.get("/login").status_code, 302)


if __name__ == "__main__":
    unittest.main()
