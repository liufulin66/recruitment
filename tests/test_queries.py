"""第 5 组用例：筛选解析 / SQL 聚合 / 技能统计 / 共现矩阵。

纯函数部分无条件运行；访问数据库的用例在 MySQL 不可用时自动跳过。
"""

import unittest

from queries import (
    STOPWORDS,
    _where,
    build_cooccurrence_matrix,
    get_group_stats,
    get_overview,
    get_skill_cooccurrence,
    get_skill_top,
    get_top_cities,
    parse_filters,
)


def _conn_or_skip(test_case):
    try:
        from db import get_connection
        return get_connection()
    except Exception as e:  # 数据库不可用时跳过
        test_case.skipTest(f"数据库不可用：{e}")


class TestParseFilters(unittest.TestCase):
    def test_empties_become_none(self):
        f = parse_filters({"city": "", "edu": None, "exp": "  "})
        self.assertEqual(f, {"city": None, "edu": None, "exp": None})

    def test_values_kept(self):
        f = parse_filters({"city": "杭州", "edu": "本科"})
        self.assertEqual(f["city"], "杭州")
        self.assertEqual(f["edu"], "本科")
        self.assertIsNone(f["exp"])


class TestWhere(unittest.TestCase):
    def test_none(self):
        where, params = _where(None)
        self.assertEqual((where, params), ("", []))

    def test_intersection_order(self):
        where, params = _where({"city": "杭州", "edu": None, "exp": "不限"})
        self.assertEqual(where, "WHERE city = %s AND exp = %s")
        self.assertEqual(params, ["杭州", "不限"])


class TestCooccurrenceMatrix(unittest.TestCase):
    def test_spec_scenario(self):
        """规格场景：A{python,mysql}、B{python} -> python-mysql 共现 1。"""
        pairs = [("mysql", "python", 1)]
        m = build_cooccurrence_matrix(pairs, ["python", "mysql"])
        self.assertEqual(m, [[0, 1], [1, 0]])


class TestAgainstDatabase(unittest.TestCase):
    """以下用例访问真实数据库（MySQL 不可用时整体跳过）。"""

    def setUp(self):
        self.conn = _conn_or_skip(self)

    def tearDown(self):
        self.conn.close()

    def test_overview_consistency(self):
        """总览数值与手写 SQL 一致（5.2 验证）。"""
        ov = get_overview(self.conn)
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM jobs")
            self.assertEqual(ov["job_count"], cur.fetchone()[0])

        ov_bj = get_overview(self.conn, {"city": "北京"})
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*), AVG(salary_avg) FROM jobs WHERE city = '北京'")
            n, avg = cur.fetchone()
        self.assertEqual(ov_bj["job_count"], n)
        self.assertAlmostEqual(ov_bj["avg_salary"], float(avg), places=2)

    def test_top_cities_sorted(self):
        cities = get_top_cities(self.conn, top_n=5)
        self.assertEqual(len(cities), 5)
        ns = [c["n"] for c in cities]
        self.assertEqual(ns, sorted(ns, reverse=True))

    def test_group_stats_sorted(self):
        df = get_group_stats(self.conn, "edu")
        self.assertIn("median_salary", df.columns)
        ns = list(df["n"])
        self.assertEqual(ns, sorted(ns, reverse=True))
        self.assertIn("本科", set(df["value"]))
        with self.assertRaises(ValueError):
            get_group_stats(self.conn, "title")

    def test_skill_top_rules(self):
        """词频 Top-N：全部小写、无停用词、频次降序，含 java（5.4 验证）。"""
        top = get_skill_top(self.conn, top_n=20)
        self.assertGreaterEqual(len(top), 10)
        ns = [t["n"] for t in top]
        self.assertEqual(ns, sorted(ns, reverse=True))
        names = [t["skill"] for t in top]
        self.assertTrue(all(s == s.lower() for s in names))
        self.assertFalse(set(names) & STOPWORDS)
        self.assertIn("java", names)

    def test_cooccurrence_shape(self):
        """共现矩阵：n×n 对称、对角线为频次（5.5 验证）。"""
        co = get_skill_cooccurrence(self.conn, top_n=6)
        skills, m = co["skills"], co["matrix"]
        self.assertEqual(len(skills), 6)
        self.assertTrue(all(len(row) == 6 for row in m))
        for i in range(6):
            self.assertGreater(m[i][i], 0)
            for j in range(6):
                self.assertEqual(m[i][j], m[j][i])
        idx = {s: i for i, s in enumerate(skills)}
        if "java" in idx and "mysql" in idx:  # 合理抽查：这俩常同岗出现
            self.assertGreater(m[idx["java"]][idx["mysql"]], 1000)


if __name__ == "__main__":
    unittest.main()
