"""第 6 组用例：Flask 页面冒烟（需要数据库；不可用时整体跳过）。"""

import unittest


class TestAppPages(unittest.TestCase):
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
        cls.client = app.test_client()

    def test_all_pages_return_200(self):
        """规格场景：5 个页面均正常渲染。"""
        for path in ("/", "/salary", "/geo", "/skills", "/company"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_filter_marks_selected_and_applies(self):
        """筛选生效：下拉选中 + 数据随筛选变化。"""
        html = self.client.get("/?city=杭州").get_data(as_text=True)
        self.assertIn('value="杭州" selected', html)
        self.assertIn("1,258", html)  # 杭州岗位数（当前数据）

    def test_empty_result_renders(self):
        """规格场景：无数据也返回 200，并显示空态提示。"""
        resp = self.client.get("/?city=不存在的城市")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("暂无数据", resp.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
