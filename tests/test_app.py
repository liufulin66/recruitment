"""页面与账号流程用例：显式选择独立测试库，固定样例逐例重置。

- TestAppPages：原页面冒烟（改为"先登录再访问"）；
- TestAuthFlow：注册 / 登录 / 验证码 / 门卫 / 会话 / 登出等规格场景。
"""

import unittest
import uuid
from unittest.mock import patch

import captcha
from tests.support import MySQLTestCase, TEST_USER, TEST_PASSWORD

class AppTestCase(MySQLTestCase):
    """每例使用独立测试库中的固定小样例。"""

    # HTTP 请求自己管理应用上下文，避免多个请求共享 g 中的筛选缓存。
    keep_app_context = False

    def client(self, logged_in=True):
        """返回一个新 client；默认已完成登录（幂等测试账号）。"""
        c = self.app.test_client()
        if logged_in:
            self._ensure_login(c)
        return c

    @classmethod
    def _seed_captcha(cls, client, code="TEST"):
        """把固定验证码写进会话（绕过图形交互，便于测试登录提交）。"""
        with patch("captcha.generate_code", return_value=code):
            response = client.get("/captcha")
        if response.status_code != 200:
            raise AssertionError("创建测试验证码失败")

    @classmethod
    def _login(cls, client, username, password, **extra):
        """带（固定）验证码提交登录。"""
        cls._seed_captcha(client)
        data = {"username": username, "password": password, "captcha": "TEST", **extra}
        return client.post("/login", data=data)

    @classmethod
    def _ensure_login(cls, client):
        """固定账号由测试样例准备，直接登录。"""
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
        """筛选生效：下拉选中 + 数据随筛选变化（2018 期杭州）。"""
        html = self.client().get("/?snapshot=2018&city=杭州").get_data(as_text=True)
        self.assertIn('value="2018" selected', html)
        self.assertIn('value="杭州" selected', html)
        self.assertIn("2", html)  # 2018 期杭州岗位数

    def test_default_latest_and_snapshot_switch(self):
        """规格场景：默认最新期；切换期次后统计与页脚联动；未知期次回退最新。"""
        html = self.client().get("/").get_data(as_text=True)  # 默认 2020
        self.assertIn("2", html)                     # 2020 期职位总数
        self.assertIn("fixture-2020", html)                  # 页脚来源随期次
        html18 = self.client().get("/?snapshot=2018").get_data(as_text=True)
        self.assertIn("4", html18)                # 2018 期职位总数
        self.assertIn("fixture-2018", html18)               # 页脚来源随之变化
        # 未知期次回退最新期（旧链接容错）
        self.assertIn("2", self.client().get("/?snapshot=不存在的期次").get_data(as_text=True))

    def test_retired_links_and_source_on_all_pages(self):
        client = self.client()
        for path in ("/", "/salary", "/geo", "/skills", "/company"):
            for query in ("", "?snapshot=2021", "?snapshot=2020&city=北京"):
                with self.subTest(path=path, query=query):
                    response = client.get(path + query)
                    self.assertEqual(response.status_code, 200)
                    html = response.get_data(as_text=True)
                    if query:
                        self.assertIn('value="2020" selected', html)
                    else:
                        self.assertIn('<option value="">最新</option>', html)
                    self.assertIn('value="2018"', html)
                    self.assertNotIn('value="2021"', html)
                    for text in ("fixture-2020", "2020 年 4 月公开快照", "12 城市 IT 岗位样本",
                                 "无逐条发布日期", "无技能数据"):
                        self.assertIn(text, html)
                    if "city=" in query:
                        self.assertIn('value="北京" selected', html)
                        self.assertIn("/salary?snapshot=2020&amp;city=%E5%8C%97%E4%BA%AC", html)
            with self.subTest(path=path, snapshot="2018"):
                html = client.get(path + "?snapshot=2018").get_data(as_text=True)
                self.assertIn('value="2018" selected', html)
                self.assertIn("fixture-2018", html)
                self.assertNotIn("12 城市 IT 岗位样本", html)

    def test_skills_degrade_for_snapshot_without_skills(self):
        """规格场景：无技能数据的期次显示降级提示，不呈现其他期数据。"""
        html = self.client().get("/skills").get_data(as_text=True)  # 默认 2020
        self.assertIn("本期数据不含技能信息", html)
        html18 = self.client().get("/skills?snapshot=2018").get_data(as_text=True)
        self.assertNotIn("本期数据不含技能信息", html18)

    def test_nav_keeps_filters(self):
        """规格场景：跨页导航保留筛选条件（含期次；链接自带当前参数）。

        断言里的 &amp; 是 Jinja2 对 href 中 & 的 HTML 转义，属预期输出。
        """
        html = self.client().get("/salary?snapshot=2018&city=杭州").get_data(as_text=True)
        self.assertIn("/skills?snapshot=2018&amp;city=%E6%9D%AD%E5%B7%9E", html)

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
        response = c.get("/static/assets/echarts.min.js")
        self.assertEqual(response.status_code, 200)
        response.close()

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
            challenge_id = sess.get(captcha.SESSION_KEY)
            self.assertNotIn("captcha_code", sess)
        self.assertTrue(challenge_id and len(challenge_id) >= 32)

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

        conn = get_connection(self.db_settings)
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
