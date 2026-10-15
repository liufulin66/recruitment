"""内存中的清洗与技能展开，不读写数据库。"""

import pandas as pd

from etl.cleaning import normalize_city, normalize_education, normalize_experience, parse_salary
from etl.skills import decode_skill_map


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
