"""4.1 校验用例（不依赖数据库：用构造的 DataFrame 模拟缺列 / 缺技能表）。"""

import unittest
from unittest.mock import MagicMock

import pandas as pd

from etl.sources import ETLValidationError, validate_sources
from etl.run_etl import run_snapshot

OK_COLUMNS = ["title", "company", "city", "salary", "experience", "education"]


class TestValidateSources(unittest.TestCase):
    def test_ok(self):
        df = pd.DataFrame({c: ["x"] for c in OK_COLUMNS})
        validate_sources(df, skill_table_ok=True)  # 不应抛异常

    def test_missing_salary_column(self):
        """规格场景：缺列 -> 终止并指出缺失字段。"""
        df = pd.DataFrame({c: ["x"] for c in OK_COLUMNS if c != "salary"})
        with self.assertRaises(ETLValidationError) as ctx:
            validate_sources(df, skill_table_ok=True)
        self.assertIn("salary", str(ctx.exception))

    def test_missing_skill_table(self):
        """规格场景：技能表缺失 -> 终止并指出技能表缺失。"""
        df = pd.DataFrame({c: ["x"] for c in OK_COLUMNS})
        with self.assertRaises(ETLValidationError) as ctx:
            validate_sources(df, skill_table_ok=False)
        self.assertIn("技能表", str(ctx.exception))

    def test_no_skills_declared_passes(self):
        """规格场景：快照声明无技能数据 -> 技能表不强制，校验通过。"""
        df = pd.DataFrame({c: ["x"] for c in OK_COLUMNS})
        validate_sources(df, skill_table_ok=False, require_skills=False)

    def test_skills_declared_but_missing(self):
        """规格场景：声明含技能数据但技能表缺失 -> 仍终止。"""
        df = pd.DataFrame({c: ["x"] for c in OK_COLUMNS})
        with self.assertRaises(ETLValidationError) as ctx:
            validate_sources(df, skill_table_ok=False, require_skills=True)
        self.assertIn("技能表", str(ctx.exception))


class TestReplacementPreflight(unittest.TestCase):
    def test_unapproved_replacements_fail_before_database_access(self):
        for label, replaces in (("2020", "2020"), ("2020", "2018"),
                                ("2020", "other"), ("2018", "2021")):
            with self.subTest(label=label, replaces=replaces):
                conn = MagicMock()
                with self.assertRaises(ETLValidationError):
                    run_snapshot(conn, {"label": label, "replaces": replaces})
                self.assertEqual(conn.mock_calls, [])


if __name__ == "__main__":
    unittest.main()
