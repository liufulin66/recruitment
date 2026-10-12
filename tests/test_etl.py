"""4.1 校验用例（不依赖数据库：用构造的 DataFrame 模拟缺列 / 缺技能表）。"""

import unittest

import pandas as pd

from etl.run_etl import ETLValidationError, validate_sources

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


if __name__ == "__main__":
    unittest.main()
