"""第 5 组用例：筛选解析（含期次）/ SQL 聚合 / 技能统计 / 共现矩阵 / 省份汇总。

纯函数部分无条件运行；集成用例必须显式指定独立测试库，已启用后连接失败视为错误。
"""

import unittest

from tests.support import MySQLTestCase

from queries import (
    CITY_TO_PROVINCE,
    STOPWORDS,
    _where,
    aggregate_by_province,
    build_cooccurrence_matrix,
    get_filter_options,
    get_group_stats,
    get_overview,
    get_province_totals,
    get_skill_cooccurrence,
    get_skill_top,
    get_top_cities,
    parse_filters,
    resolve_snapshot,
)


class TestParseFilters(unittest.TestCase):
    def test_empties_become_none(self):
        f = parse_filters({"city": "", "edu": None, "exp": "  ", "snapshot": ""})
        self.assertEqual(f, {"snapshot": None, "city": None, "edu": None, "exp": None})

    def test_values_kept(self):
        f = parse_filters({"city": "杭州", "edu": "本科", "snapshot": "2018"})
        self.assertEqual(f["snapshot"], "2018")
        self.assertEqual(f["city"], "杭州")
        self.assertEqual(f["edu"], "本科")
        self.assertIsNone(f["exp"])


class TestWhere(unittest.TestCase):
    def test_snapshot_always_injected(self):
        """规格：期次条件永远注入——即使其他维度全部不限。"""
        where, params = _where({"snapshot_id": 2})
        self.assertEqual((where, params), ("WHERE snapshot_id = %s", [2]))

    def test_intersection_order(self):
        where, params = _where({"snapshot_id": 2, "city": "杭州", "edu": None, "exp": "不限"})
        self.assertEqual(where, "WHERE snapshot_id = %s AND city = %s AND exp = %s")
        self.assertEqual(params, [2, "杭州", "不限"])


class TestCachedSnapshotResolution(unittest.TestCase):
    def test_unknown_label_falls_back_and_updates_selection(self):
        f = parse_filters({"snapshot": "missing"})
        snapshots = [{"id": 2, "label": "2020"}, {"id": 1, "label": "2018"}]
        self.assertEqual(resolve_snapshot(None, f, snapshots=snapshots), 2)
        self.assertEqual(f["snapshot"], "2020")

    def test_empty_snapshot_list(self):
        f = parse_filters({})
        self.assertIsNone(resolve_snapshot(None, f, snapshots=[]))


class TestCooccurrenceMatrix(unittest.TestCase):
    def test_spec_scenario(self):
        """规格场景：A{python,mysql}、B{python} -> python-mysql 共现 1。"""
        pairs = [("mysql", "python", 1)]
        m = build_cooccurrence_matrix(pairs, ["python", "mysql"])
        self.assertEqual(m, [[0, 1], [1, 0]])


class TestAggregateByProvince(unittest.TestCase):
    def test_aggregate(self):
        """纯函数：城市数量按省份汇总；未知城市略过。"""
        mapping = {"杭州": "浙江", "宁波": "浙江", "北京": "北京"}
        totals = aggregate_by_province(
            [("杭州", 10), ("宁波", 5), ("北京", 7), ("未知城", 3)], mapping=mapping
        )
        self.assertEqual(totals, {"浙江": 15, "北京": 7})


class TestAgainstDatabase(MySQLTestCase):
    """以下用例访问独立测试库中的固定小样例。

    约定：filters 一律经 resolve_snapshot 解析（期次条件永远注入 _where）。
    """

    def setUp(self):
        super().setUp()
        self.f_2018 = self._f("2018")
        self.f_latest = self._f()

    def _f(self, label=None):
        """构造并解析一份筛选（期次 + 三维）。"""
        f = parse_filters({"snapshot": label} if label else {})
        resolve_snapshot(self.conn, f)
        return f

    # ---------------- 期次解析（4.1） ----------------

    def test_default_snapshot_is_latest(self):
        """规格：未指定期次 -> 最新一期（snapshots.id 最大）。"""
        with self.conn.cursor() as cur:
            cur.execute("SELECT id FROM snapshots ORDER BY id DESC LIMIT 1")
            latest_id = cur.fetchone()[0]
        self.assertEqual(self.f_latest["snapshot_id"], latest_id)
        ov = get_overview(self.conn, self.f_latest)
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM jobs WHERE snapshot_id = %s", (latest_id,))
            self.assertEqual(ov["job_count"], cur.fetchone()[0])

    def test_unknown_snapshot_falls_back_to_latest(self):
        """未知期次回退最新期（旧链接容错：期次被移除后页面仍可用）。"""
        f = parse_filters({"snapshot": "不存在的期次"})
        self.assertEqual(resolve_snapshot(self.conn, f), self.f_latest["snapshot_id"])

    def test_two_snapshots_coexist(self):
        """规格：两期并存——各期统计独立，行数之和等于全表。"""
        f20 = self._f("2020")
        ov18 = get_overview(self.conn, self.f_2018)
        ov20 = get_overview(self.conn, f20)
        self.assertGreater(ov18["job_count"], ov20["job_count"])
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM jobs")
            self.assertEqual(cur.fetchone()[0], ov18["job_count"] + ov20["job_count"])

    # ---------------- 统计一致性（沿 5.2/5.4/5.5 验证，改为按期） ----------------

    def test_overview_consistency(self):
        """总览数值与手写 SQL 一致（2018 期）。"""
        ov = get_overview(self.conn, self.f_2018)
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM jobs WHERE snapshot_id = %s",
                (self.f_2018["snapshot_id"],))
            self.assertEqual(ov["job_count"], cur.fetchone()[0])

        ov_bj = get_overview(self.conn, {**self.f_2018, "city": "北京"})
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*), AVG(salary_avg) FROM jobs "
                "WHERE snapshot_id = %s AND city = '北京'",
                (self.f_2018["snapshot_id"],))
            n, avg = cur.fetchone()
        self.assertEqual(ov_bj["job_count"], n)
        self.assertAlmostEqual(ov_bj["avg_salary"], float(avg), places=2)

    def test_top_cities_sorted(self):
        cities = get_top_cities(self.conn, 5, self.f_2018)
        self.assertEqual(len(cities), 2)
        ns = [c["n"] for c in cities]
        self.assertEqual(ns, sorted(ns, reverse=True))

    def test_group_stats_sorted(self):
        df = get_group_stats(self.conn, "edu", self.f_2018)
        self.assertIn("median_salary", df.columns)
        ns = list(df["n"])
        self.assertEqual(ns, sorted(ns, reverse=True))
        self.assertIn("本科", set(df["value"]))
        with self.assertRaises(ValueError):
            get_group_stats(self.conn, "title", self.f_2018)

    def test_sql_summary_matches_detailed_statistics(self):
        # 缺失分组应与 pandas 一样放在同数量分组末尾，且整组缺薪资仍计职位数。
        with self.conn.cursor() as cur:
            cur.execute("INSERT INTO jobs (snapshot_id, job_name, city, edu, exp) "
                        "VALUES (1, 'missing-fields', NULL, NULL, NULL)")
        for dimension in ("city", "edu", "exp"):
            detailed = get_group_stats(self.conn, dimension, self.f_2018)
            summary = get_group_stats(self.conn, dimension, self.f_2018, include_median=False)
            self.assertEqual(list(summary["value"].fillna("__missing__")),
                             list(detailed["value"].fillna("__missing__")))
            self.assertEqual(list(summary["n"]), list(detailed["n"]))
            for actual, expected in zip(summary["avg_salary"], detailed["avg_salary"]):
                if actual == actual:  # NaN 表示整组薪资缺失
                    self.assertAlmostEqual(actual, expected)
                else:
                    self.assertNotEqual(expected, expected)
            self.assertNotIn("median_salary", summary.columns)

    def test_median_excludes_missing_salary(self):
        stats = get_group_stats(self.conn, "city", self.f_2018).set_index("value")
        self.assertEqual(stats.loc["杭州", "median_salary"], 15000)
        self.assertEqual(stats.loc["北京", "median_salary"], 30000)
        self.assertEqual(stats.loc["北京", "n"], 2)

    def test_summary_empty_result_preserves_columns(self):
        filters = {**self.f_2018, "city": "不存在的城市"}
        result = get_group_stats(self.conn, "city", filters, include_median=False)
        self.assertTrue(result.empty)
        self.assertEqual(list(result.columns), ["value", "n", "avg_salary"])

    def test_filter_options_per_snapshot(self):
        """规格：城市选项随期次变化（2020 期只有上海/北京）。"""
        opts20 = get_filter_options(self.conn, self._f("2020")["snapshot_id"])
        self.assertEqual(set(opts20["cities"]), {"上海", "北京"})
        opts18 = get_filter_options(self.conn, self.f_2018["snapshot_id"])
        self.assertEqual(set(opts18["cities"]), {"杭州", "北京"})

    # ---------------- 技能统计按期隔离（4.2） ----------------

    def test_skill_top_rules(self):
        """词频 Top-N：全部小写、无停用词、频次降序，含 java（2018 期）。"""
        top = get_skill_top(self.conn, top_n=20, snapshot_id=self.f_2018["snapshot_id"])
        self.assertEqual(len(top), 3)
        ns = [t["n"] for t in top]
        self.assertEqual(ns, sorted(ns, reverse=True))
        names = [t["skill"] for t in top]
        self.assertTrue(all(s == s.lower() for s in names))
        self.assertFalse(set(names) & STOPWORDS)
        self.assertIn("java", names)

    def test_snapshot_without_skills_returns_empty(self):
        """规格：无技能数据的期次 -> 技能统计为空，不回退其他期。"""
        top = get_skill_top(self.conn, top_n=10, snapshot_id=self._f("2020")["snapshot_id"])
        self.assertEqual(top, [])

    def test_skill_isolation_across_snapshots(self):
        """规格：source_map_id 仅快照内唯一——两期同 id 不得合并计数。"""
        sid18 = self.f_2018["snapshot_id"]
        sid20 = self._f("2020")["snapshot_id"]
        marker = "pythonzzz"  # 唯一标记词，避免与真实技能混淆
        with self.conn.cursor() as cur:
            # 构造两期同 source_map_id 的技能行：若跨期合并会计成 2 个岗位
            cur.execute(
                "INSERT INTO job_skills (snapshot_id, source_map_id, key_word, skill) "
                "VALUES (%s, 999001, 'kw', %s), (%s, 999001, 'kw', %s)",
                (sid18, marker, sid20, marker),
            )
            try:
                top18 = get_skill_top(self.conn, top_n=100000, snapshot_id=sid18)
                top20 = get_skill_top(self.conn, top_n=100000, snapshot_id=sid20)
                n18 = next(t["n"] for t in top18 if t["skill"] == marker)
                n20 = next(t["n"] for t in top20 if t["skill"] == marker)
                self.assertEqual((n18, n20), (1, 1))
            finally:
                cur.execute("DELETE FROM job_skills WHERE source_map_id = 999001")
        self.conn.commit()

    def test_cooccurrence_shape(self):
        """共现矩阵：n×n 对称、对角线为频次（2018 期）。"""
        co = get_skill_cooccurrence(self.conn, top_n=6, snapshot_id=self.f_2018["snapshot_id"])
        skills, m = co["skills"], co["matrix"]
        self.assertEqual(len(skills), 3)
        self.assertTrue(all(len(row) == len(skills) for row in m))
        for i in range(3):
            self.assertGreater(m[i][i], 0)
            for j in range(3):
                self.assertEqual(m[i][j], m[j][i])
        idx = {s: i for i, s in enumerate(skills)}
        if "java" in idx and "mysql" in idx:  # 合理抽查：这俩常同岗出现
            self.assertEqual(m[idx["java"]][idx["mysql"]], 1)

    # ---------------- 省份汇总（按期核对） ----------------

    def test_province_mapping_coverage(self):
        """城市→省份对照表覆盖库中全部城市（含两期；防止新增数据后地图静默掉色）。"""
        with self.conn.cursor() as cur:
            cur.execute("SELECT DISTINCT city FROM jobs")
            cities = {r[0] for r in cur.fetchall()}
        missing = cities - set(CITY_TO_PROVINCE)
        self.assertEqual(missing, set())

    def test_province_totals_sum(self):
        """省份汇总总数 == 该期职位数（映射完整时应严格相等；逐期核对）。"""
        for f in (self.f_2018, self._f("2020")):
            with self.conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM jobs WHERE snapshot_id = %s",
                    (f["snapshot_id"],))
                total = cur.fetchone()[0]
            self.assertEqual(sum(r["n"] for r in get_province_totals(self.conn, f)), total)


if __name__ == "__main__":
    unittest.main()
