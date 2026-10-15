"""快照声明、来源适配与必填字段校验。"""

from decimal import Decimal, InvalidOperation
from math import isfinite
from pathlib import Path

import pandas as pd
from pymysql import ProgrammingError

SOURCE_JOB_TABLE = "job_data"
SOURCE_SKILL_TABLE = "key_map"
REQUIRED_JOB_COLUMNS = ("title", "company", "city", "salary", "experience", "education")

# 各期快照声明：元数据（label 即页面期次下拉与 URL 参数；来源/覆盖说明供页脚动态标注）
# + 数据源形态（摄入路径）：
#   form="staging"：SQL 导出已导入 MySQL 暂存表（2018 期，技能表为 Java blob，需解码）
#   form="csv"：pandas 直读 CSV，columns 为"统一字段 -> CSV 列"映射
SNAPSHOT_CONFIGS = [
    {
        "label": "2018",
        "source": "radishT/Job_Analysis（GitHub 开源项目，2018 年 BOSS直聘岗位数据）",
        "period": "2018 年",
        "note": "多关键词全量 IT 岗位（约 3.7 万条，含技能数据）",
        "form": "staging",
        "has_skills": True,
    },
    {
        "label": "2020",
        "source": "ccclll777/bosszp（GitHub，固定提交 2dcc08a8ff0c79a0afda3d150c1a9618ebe6e390）",
        "period": "2020 年 4 月公开快照",
        "note": "12 城市 IT 岗位样本，无逐条发布日期，无技能数据；非全年、非全国全量",
        "form": "csv",
        "path": "data/raw/bosszp_2020_job_data_clean_price.csv",
        "replaces": "2021",
        "salary_columns": {"min": "job_low_salary", "max": "job_high_salary"},
        "columns": {
            "title": "job_title",
            "company": "job_company",
            "city": "company_city",
            "experience": "job_experience",
            "education": "job_education",
            "key_word": "job_type",
        },
        "has_skills": False,
    },
]


class ETLValidationError(Exception):
    """数据源校验失败（规格要求：终止执行并明确指出缺失项）。"""


def validate_replacement(label, replaces):
    """替代关系不是任意删除入口；当前仅开放已批准的 2020→2021。"""
    if replaces is not None and (label, replaces) != ("2020", "2021"):
        raise ETLValidationError(f"未声明的快照替代关系：{label} → {replaces}")


def validate_sources(job_df: pd.DataFrame, skill_table_ok: bool, require_skills: bool = True):
    """校验主数据必填字段与技能表存在性，失败即抛 ETLValidationError。

    主数据六列必填恒定；技能表仅在该快照声明含技能数据（require_skills）时必填。
    """
    missing = [c for c in REQUIRED_JOB_COLUMNS if c not in job_df.columns]
    if missing:
        raise ETLValidationError(f"数据集缺少必填字段：{', '.join(missing)}")
    if require_skills and not skill_table_ok:
        raise ETLValidationError("数据源中不存在岗位技能表（key_map）或技能表为空")


def load_sources(conn):
    """读取暂存表：岗位主表交给 pandas；技能表含 blob，用游标读取。"""
    with conn.cursor() as cur:
        cur.execute(f"SELECT * FROM {SOURCE_JOB_TABLE}")
        job_df = pd.DataFrame(cur.fetchall(), columns=[c[0] for c in cur.description])
        try:
            cur.execute(f"SELECT COUNT(*) FROM {SOURCE_SKILL_TABLE}")
        except ProgrammingError as exc:
            if exc.args[0] == 1146:
                return job_df, []  # 只把缺表交给校验；其他数据库异常保留原始原因
            raise
        if cur.fetchone()[0] == 0:
            return job_df, []
        cur.execute(f"SELECT id, key_word, key_words_map FROM {SOURCE_SKILL_TABLE}")
        skill_rows = cur.fetchall()
    return job_df, skill_rows


_ROOT = Path(__file__).resolve().parent.parent  # 项目根（CSV 声明路径相对它解析）


def _monthly_salary(low, high):
    """数值来源显式按元/月适配；任一端无效时丢弃整组薪资。"""
    try:
        lo, hi = Decimal(str(low)), Decimal(str(high))
        if not (lo.is_finite() and hi.is_finite()
                and isfinite(float(lo)) and isfinite(float(hi)) and 0 <= lo <= hi):
            return None
    except (InvalidOperation, ValueError, OverflowError):
        return None
    return f"{lo:f}元-{hi:f}元"


def load_csv(config) -> pd.DataFrame:
    """先校验原始列，再适配统一字段；数值薪资显式声明为元/月。"""
    df = pd.read_csv(_ROOT / config["path"])
    salary_columns = config.get("salary_columns")
    required = list(config["columns"].values())
    if salary_columns:
        required.extend((salary_columns["min"], salary_columns["max"]))
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ETLValidationError(f"CSV 缺少来源字段：{', '.join(missing)}")
    if salary_columns:
        df["salary"] = [
            _monthly_salary(lo, hi)
            for lo, hi in zip(df[salary_columns["min"]], df[salary_columns["max"]])
        ]
    df = df.rename(columns={csv_col: unified for unified, csv_col in config["columns"].items()})
    if "key_word" not in df:
        df["key_word"] = None
    return df
