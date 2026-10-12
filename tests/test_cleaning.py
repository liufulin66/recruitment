"""第 3 组用例：薪资解析与枚举归一。

组织约定：每个规格场景至少一个测试方法，方法上注释标注对应的规格场景；
真实数据形态（data/sample_values.md）作为补充用例。
对应规格：openspec/changes/add-recruitment-analysis-system/specs/data-pipeline/spec.md
"""

import unittest

from etl.cleaning import (
    normalize_city,
    normalize_education,
    normalize_experience,
    parse_salary,
)


class TestParseSalary(unittest.TestCase):
    """薪资字符串解析（规格场景 + 真实数据形态）。"""

    def test_k_range(self):
        """规格场景：K 区间。"""
        self.assertEqual(parse_salary("15-25K"), (15000.0, 25000.0, 20000.0))

    def test_lowercase_k_range(self):
        """规格场景：小写 k 区间（真实数据 100% 为此形态）。"""
        self.assertEqual(parse_salary("15k-25k"), (15000.0, 25000.0, 20000.0))

    def test_qian_wan_mix(self):
        """规格场景：千/万混合。"""
        self.assertEqual(parse_salary("6千-1.2万"), (6000.0, 12000.0, 9000.0))

    def test_yearly(self):
        """规格场景：年薪折算（两端点 ÷12，平均按换算后中点）。"""
        lo, hi, avg = parse_salary("20-30万/年")
        self.assertAlmostEqual(lo, 200000 / 12, delta=1)
        self.assertAlmostEqual(hi, 25000.0, delta=1)
        self.assertAlmostEqual(avg, (200000 / 12 + 25000) / 2, delta=1)

    def test_13_month(self):
        """规格场景：13 薪折算（最低/最高保持月薪，平均 = 中点 × 13 ÷ 12）。"""
        lo, hi, avg = parse_salary("15-25K·13薪")
        self.assertEqual(lo, 15000.0)
        self.assertEqual(hi, 25000.0)
        self.assertAlmostEqual(avg, 20000 * 13 / 12, delta=1)

    def test_single_value_k(self):
        self.assertEqual(parse_salary("12k"), (12000.0, 12000.0, 12000.0))

    def test_single_bare_number_is_k(self):
        """裸数字按中文招聘惯例以 k 计。"""
        self.assertEqual(parse_salary("10"), (10000.0, 10000.0, 10000.0))

    def test_single_yuan(self):
        self.assertEqual(parse_salary("9000元"), (9000.0, 9000.0, 9000.0))

    def test_mianyi_is_none(self):
        """规格场景：面议 -> 薪资缺失。"""
        self.assertIsNone(parse_salary("面议"))

    def test_empty_is_none(self):
        self.assertIsNone(parse_salary(""))
        self.assertIsNone(parse_salary(None))
        self.assertIsNone(parse_salary("   "))


class TestNormalizeCity(unittest.TestCase):
    def test_spec_scenario(self):
        """规格场景：城市归一。"""
        self.assertEqual(normalize_city("北京·朝阳区"), "北京")

    def test_city_suffix(self):
        self.assertEqual(normalize_city("北京市"), "北京")
        self.assertEqual(normalize_city("杭州市"), "杭州")

    def test_district_without_separator(self):
        self.assertEqual(normalize_city("深圳市南山区"), "深圳")

    def test_plain_city(self):
        self.assertEqual(normalize_city("杭州"), "杭州")


class TestNormalizeEducation(unittest.TestCase):
    def test_spec_scenario(self):
        """规格场景：学历归一（本科及以上 -> 本科）。"""
        self.assertEqual(normalize_education("本科及以上"), "本科")

    def test_real_values(self):
        """真实数据 7 个取值的归一（data/sample_values.md）。"""
        cases = {
            "本科": "本科",
            "大专": "大专",
            "硕士": "硕士",
            "博士": "博士",
            "不限": "不限",
            "学历不限": "不限",
            "高中": "高中及以下",
            "以下": "高中及以下",
        }
        for raw, want in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(normalize_education(raw), want)


class TestNormalizeExperience(unittest.TestCase):
    def test_spec_scenario(self):
        """规格场景：经验归一（3-5年 / 不限 入档）。"""
        self.assertEqual(normalize_experience("3-5年"), "3-5年")
        self.assertEqual(normalize_experience("不限"), "不限")

    def test_real_formats(self):
        """真实数据形态：前导空格 + 经验段 + 学历段拼接。"""
        cases = {
            " 1-3年本科": "1-3年",
            " 3-5年大专": "3-5年",
            " 5-10年本科": "5-10年",
            " 不限本科": "不限",
            " 1年以内本科": "1年以内",
            " 应届生本科": "应届生",
            "经验3-5年": "3-5年",
        }
        for raw, want in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(normalize_experience(raw), want)


if __name__ == "__main__":
    unittest.main()
