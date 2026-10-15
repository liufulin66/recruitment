"""CSV 适配在读库前完成；样例独立于公开大文件。"""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pandas as pd

from etl.sources import ETLValidationError, SNAPSHOT_CONFIGS, load_csv
from etl.transforms import clean_jobs


class TestCSVSource(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "jobs.csv"
        self.config = deepcopy(next(c for c in SNAPSHOT_CONFIGS if c["label"] == "2020"))
        self.config["path"] = str(self.path)

    def load(self, lows=(8000,), highs=(13000,)):
        count = len(lows)
        pd.DataFrame({
            "job_title": [f"工程师{i}" for i in range(count)],
            "job_company": ["A"] * count, "company_city": ["杭州"] * count,
            "job_education": [None] * count, "job_experience": [None] * count,
            "job_type": ["Java"] * count,
            "job_low_salary": lows, "job_high_salary": highs,
            "job_ave_salary": [999999] * count,
        }).to_csv(self.path, index=False)
        return load_csv(self.config)

    def test_numeric_monthly_salary_and_missing_fields(self):
        source = self.load()
        jobs, stats = clean_jobs(source)
        row = jobs.iloc[0]
        self.assertEqual((row.salary_min, row.salary_max, row.salary_avg), (8000, 13000, 10500))
        self.assertEqual(row.salary_raw, "8000元-13000元")
        self.assertIsNone(row.edu)
        self.assertIsNone(row.exp)
        self.assertEqual(row.key_word, "Java")
        self.assertEqual(stats["薪资缺失"], 0)
        self.assertFalse(self.config["has_skills"])

    def test_invalid_numeric_ranges_are_entirely_missing(self):
        lows = [None, 8000, float("inf"), 8000, -1, 13000, "bad"]
        highs = [13000, None, 13000, float("inf"), 13000, 8000, 13000]
        jobs, stats = clean_jobs(self.load(lows, highs))
        self.assertEqual(len(jobs), len(lows))
        self.assertEqual(stats["薪资缺失"], len(lows))
        self.assertTrue(jobs[["salary_min", "salary_max", "salary_avg"]].isna().all().all())

    def test_zero_and_fractional_salary(self):
        jobs, _ = clean_jobs(self.load([0, "8000.25"], [0, "13000.75"]))
        self.assertEqual(list(jobs.salary_avg), [0, 10500.5])

    def test_missing_original_column_names_are_reported(self):
        self.load()
        for missing in ("job_low_salary", "job_high_salary", "job_title", "company_city"):
            with self.subTest(column=missing):
                df = pd.read_csv(self.path)
                df.drop(columns=missing).to_csv(self.path, index=False)
                with self.assertRaisesRegex(ETLValidationError, missing):
                    load_csv(self.config)
                self.load()

    def test_text_csv_remains_compatible(self):
        salaries = ["15-25K", "20-30万/年", "15-25K·13薪"]
        pd.DataFrame({"raw_salary": salaries}).to_csv(self.path, index=False)
        source = load_csv({"path": str(self.path), "columns": {"salary": "raw_salary"}})
        from etl.cleaning import parse_salary
        self.assertEqual(list(source.salary), salaries)
        self.assertTrue(source.key_word.isna().all())
        self.assertEqual(parse_salary(source.salary[0]), (15000, 25000, 20000))
        self.assertAlmostEqual(parse_salary(source.salary[1])[2], 250000 / 12)
        self.assertAlmostEqual(parse_salary(source.salary[2])[2], 20000 * 13 / 12)

    def test_config_declares_only_approved_replacement(self):
        self.assertEqual([c["label"] for c in SNAPSHOT_CONFIGS], ["2018", "2020"])
        self.assertEqual([(c["label"], c["replaces"]) for c in SNAPSHOT_CONFIGS if c.get("replaces")],
                         [("2020", "2021")])
        self.assertIn("12 城市 IT", self.config["note"])
        self.assertIn("无逐条发布日期", self.config["note"])
        self.assertIn("无技能数据", self.config["note"])
        self.assertEqual(self.config["period"], "2020 年 4 月公开快照")
