"""ETL 主流程：暂存表 -> 校验 -> 清洗 -> 技能解码 -> 建表 -> 幂等入库 -> 统计。

运行方式（项目根目录）：
    .venv\\Scripts\\python.exe -m etl.run_etl

对应规格：specs/data-pipeline/spec.md
  - 必填字段校验 / 薪资解析 / 枚举归一 / 去重 / 幂等入库 / 技能表解码留存
"""

import sys
import time

import pandas as pd

from db import get_connection
from etl.cleaning import (
    normalize_city,
    normalize_education,
    normalize_experience,
    parse_salary,
)
from etl.skills import decode_skill_map

# 原始暂存表（由 data/raw 的两个 SQL 导出导入）
SOURCE_JOB_TABLE = "job_data"
SOURCE_SKILL_TABLE = "key_map"
# 清洗后目标表
TARGET_JOB_TABLE = "jobs"
TARGET_SKILL_TABLE = "job_skills"

# 主数据必填字段（规格：缺失即终止并指出）
REQUIRED_JOB_COLUMNS = ("title", "company", "city", "salary", "experience", "education")

DDL_JOBS = f"""
CREATE TABLE IF NOT EXISTS {TARGET_JOB_TABLE} (
  id INT AUTO_INCREMENT PRIMARY KEY,
  job_name VARCHAR(200) NOT NULL,
  company VARCHAR(200),
  city VARCHAR(50),
  salary_min DOUBLE,
  salary_max DOUBLE,
  salary_avg DOUBLE,
  salary_raw VARCHAR(50),
  edu VARCHAR(20),
  exp VARCHAR(20),
  key_word VARCHAR(10),
  KEY idx_city (city),
  KEY idx_edu (edu),
  KEY idx_exp (exp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

DDL_SKILLS = f"""
CREATE TABLE IF NOT EXISTS {TARGET_SKILL_TABLE} (
  id INT AUTO_INCREMENT PRIMARY KEY,
  source_map_id INT NOT NULL,
  key_word VARCHAR(10) NOT NULL,
  skill VARCHAR(64) NOT NULL,
  KEY idx_skill (skill),
  KEY idx_source (source_map_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""


class ETLValidationError(Exception):
    """数据源校验失败（规格要求：终止执行并明确指出缺失项）。"""


def validate_sources(job_df: pd.DataFrame, skill_table_ok: bool):
    """校验主数据必填字段与技能表存在性，失败即抛 ETLValidationError。"""
    missing = [c for c in REQUIRED_JOB_COLUMNS if c not in job_df.columns]
    if missing:
        raise ETLValidationError(f"数据集缺少必填字段：{', '.join(missing)}")
    if not skill_table_ok:
        raise ETLValidationError("数据源中不存在岗位技能表（key_map）或技能表为空")


def load_sources(conn):
    """读取暂存表：岗位主表交给 pandas；技能表含 blob，用游标读取。"""
    job_df = pd.read_sql(f"SELECT * FROM {SOURCE_JOB_TABLE}", conn)

    with conn.cursor() as cur:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {SOURCE_SKILL_TABLE}")
        except Exception:
            return job_df, []  # 技能表不存在 -> 交给校验环节报错
        if cur.fetchone()[0] == 0:
            return job_df, []
        cur.execute(f"SELECT id, key_word, key_words_map FROM {SOURCE_SKILL_TABLE}")
        skill_rows = cur.fetchall()
    return job_df, skill_rows


def _norm(series, func):
    """对整列应用归一函数；空值（NaN/None）统一置为 None。"""
    return series.map(lambda v: func(v) if pd.notna(v) else None)


def clean_jobs(job_df: pd.DataFrame):
    """清洗主表：薪资解析 + 枚举归一 + 去重；返回 (清洗后 DataFrame, 统计字典)。"""
    df = job_df.copy()
    df["job_name"] = _norm(df["title"], str)
    df["job_name"] = df["job_name"].str.strip()
    df["company"] = _norm(df["company"], str)

    # 薪资：逐行过纯函数（None=缺失，不写数值）
    parsed = df["salary"].map(lambda v: parse_salary(v) if pd.notna(v) else None)
    df["salary_min"] = parsed.map(lambda t: t[0] if t else None)
    df["salary_max"] = parsed.map(lambda t: t[1] if t else None)
    df["salary_avg"] = parsed.map(lambda t: t[2] if t else None)
    df["salary_raw"] = df["salary"]

    df["city"] = _norm(df["city"], normalize_city)
    df["edu"] = _norm(df["education"], normalize_education)
    df["exp"] = _norm(df["experience"], normalize_experience)

    before = len(df)
    df = df.drop_duplicates(subset=["job_name", "company", "city"], keep="first")
    stats = {
        "读取岗位行数": before,
        "去重移除": before - len(df),
        "薪资缺失": int(parsed.isna().sum()),
    }
    return df, stats


def decode_all_skills(skill_rows):
    """解码全部技能映射 -> (行列表, 统计)；行 = (source_map_id, key_word, skill)。"""
    rows, empty_maps = [], 0
    for map_id, key_word, blob in skill_rows:
        skills = decode_skill_map(blob or b"")
        if not skills:
            empty_maps += 1
            continue
        rows.extend((map_id, key_word, s) for s in skills)
    stats = {
        "技能映射数": len(skill_rows),
        "解码技能总条数": len(rows),
        "空技能映射": empty_maps,
    }
    return rows, stats


def insert_jobs(conn, df: pd.DataFrame):
    """清洗主表批量入库（与技能表共用一条事务，由 main 统一提交）。"""
    cols = ["job_name", "company", "city", "salary_min", "salary_max", "salary_avg",
            "salary_raw", "edu", "exp", "key_word"]
    data = [
        tuple(None if pd.isna(v) else v for v in row)
        for row in df[cols].itertuples(index=False, name=None)
    ]
    sql = f"INSERT INTO {TARGET_JOB_TABLE} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})"
    with conn.cursor() as cur:
        cur.executemany(sql, data)


def insert_skills(conn, rows, chunk_size=20000):
    """技能行分批 executemany；整个写入过程一条事务。

    对比：逐条 INSERT（如数据集自带 dump 的导入）每条都要刷一次盘，
    6 万条要 23 分钟；事务 + 批量提交后同样的量级只需几十秒。
    """
    sql = f"INSERT INTO {TARGET_SKILL_TABLE} (source_map_id, key_word, skill) VALUES (%s, %s, %s)"
    with conn.cursor() as cur:
        for start in range(0, len(rows), chunk_size):
            cur.executemany(sql, rows[start:start + chunk_size])


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows 控制台中文输出
    started = time.time()

    conn = get_connection()
    try:
        # 1) 读取 + 校验
        job_df, skill_rows = load_sources(conn)
        validate_sources(job_df, skill_table_ok=bool(skill_rows))

        # 2) 清洗 + 解码
        jobs_df, job_stats = clean_jobs(job_df)
        skill_records, skill_stats = decode_all_skills(skill_rows)

        # 3) 覆盖式写入（幂等：重跑结果与单次一致）
        with conn.cursor() as cur:
            cur.execute(DDL_JOBS)
            cur.execute(DDL_SKILLS)
            cur.execute(f"TRUNCATE TABLE {TARGET_JOB_TABLE}")
            cur.execute(f"TRUNCATE TABLE {TARGET_SKILL_TABLE}")

        insert_jobs(conn, jobs_df)
        insert_skills(conn, skill_records)
        conn.commit()

        # 4) 统计
        print("=== ETL 完成 ===")
        for k, v in {**job_stats, **skill_stats}.items():
            print(f"{k}: {v:,}")
        print(f"入库: jobs {len(jobs_df):,} 行 / job_skills {len(skill_records):,} 行")
        print(f"耗时: {time.time() - started:.1f}s")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
