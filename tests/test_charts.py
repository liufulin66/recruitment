"""图表模块用例：省份名与地图注册名的一致性（防"掉色"守卫）。

背景：china.js 注册的省级区域名是全称（广东省 / 北京市 / 内蒙古自治区…），
数据里是简称，必须由 map_region_name 补全后才对得上，否则地图整张变白板。
"""

import re
import unittest
from pathlib import Path
from unittest.mock import patch

from charts import map_region_name, salary_hist
from queries import CITY_TO_PROVINCE

CHINA_JS = Path(__file__).resolve().parent.parent / "static" / "assets" / "maps" / "china.js"


class TestMapRegionName(unittest.TestCase):
    def test_municipality(self):
        self.assertEqual(map_region_name("北京"), "北京市")

    def test_autonomous_region(self):
        self.assertEqual(map_region_name("广西"), "广西壮族自治区")
        self.assertEqual(map_region_name("内蒙古"), "内蒙古自治区")

    def test_sar(self):
        self.assertEqual(map_region_name("香港"), "香港特别行政区")

    def test_plain_province(self):
        self.assertEqual(map_region_name("广东"), "广东省")


class TestSalaryHistogram(unittest.TestCase):
    def test_boundary_maximum_is_not_lost(self):
        with patch("charts.bar") as bar:
            salary_hist([1000, 2000, 20000, 20000.5])
        labels, counts, _ = bar.call_args.args
        self.assertEqual(sum(counts), 4)
        self.assertEqual(counts[-1], 2)
        self.assertEqual(labels[-1], "20k-22k")

    def test_zero_only_has_one_bin(self):
        with patch("charts.bar") as bar:
            salary_hist([0, 0])
        self.assertEqual(bar.call_args.args[1], [2])

    def test_empty_returns_none(self):
        self.assertIsNone(salary_hist([None]))


class TestAgainstMapRegistration(unittest.TestCase):
    def test_all_provinces_match_map(self):
        """对照表里所有省份补全后缀后，必须都能在地图 JS 的注册名中找到。"""
        text = CHINA_JS.read_text(encoding="utf-8", errors="ignore")
        registered = set(re.findall(r'"name":"([^"]+)"', text)) - {""}
        self.assertGreater(len(registered), 30, "未从地图 JS 解析到注册区域名")

        full = {map_region_name(p) for p in set(CITY_TO_PROVINCE.values())}
        missing = full - registered
        self.assertEqual(missing, set(), f"以下省份名对不上地图注册名：{missing}")


if __name__ == "__main__":
    unittest.main()
