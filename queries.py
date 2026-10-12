"""查询与分析层：把清洗后的数据变成页面要用的统计结果。

分工说明：
- 筛选（WHERE）与分组计数/均值用 SQL —— 这是数据库的主场；
- 中位数这类 MySQL 没有内置函数、写起来绕的统计，交给 pandas
  （"SQL 取数 + pandas 算统计"是实际项目里最常见的组合）。
对应规格：specs/recruitment-analytics/spec.md
"""

from pathlib import Path

import pandas as pd

# 三维筛选：请求参数名 → jobs 表列名（同名）
FILTER_FIELDS = ("city", "edu", "exp")

_STOPWORDS_FILE = Path(__file__).resolve().parent / "data" / "stopwords.txt"


def _load_stopwords(path=_STOPWORDS_FILE) -> set:
    if not path.exists():
        return set()
    return {
        line.strip().lower()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }


STOPWORDS = _load_stopwords()


def _sql_in(values) -> str:
    """生成 IN 子句的占位符串（值为空时由调用方跳过该条件）。"""
    return ", ".join(["%s"] * len(values))


# ---------------- 筛选解析（5.1） ----------------

def parse_filters(params) -> dict:
    """从请求参数提取三维筛选；空串 / None 一律视为"不限"。"""
    out = {}
    for field in FILTER_FIELDS:
        value = (params.get(field) or "").strip()
        out[field] = value or None
    return out


def _where(filters) -> tuple[str, list]:
    """把筛选条件编译为 WHERE 子句与参数列表（多条件取交集）。"""
    conds, params = [], []
    for field in FILTER_FIELDS:
        value = (filters or {}).get(field)
        if value:
            conds.append(f"{field} = %s")
            params.append(value)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    return where, params


# ---------------- 总览（5.2） ----------------

def get_overview(conn, filters=None) -> dict:
    """总览四项指标：职位总数 / 平均薪资 / 职位最多的城市 / 最高频技能。

    注意：Top 技能取全量技能数据（技能表不含城市/经验/学历维度，
    按规格"技能数据的来源与筛选边界"处理）。
    """
    where, params = _where(filters)
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*), AVG(salary_avg) FROM jobs {where}", params)
        total, avg = cur.fetchone()

        cur.execute(
            f"SELECT city FROM jobs {where} GROUP BY city ORDER BY COUNT(*) DESC, city ASC LIMIT 1",
            params,
        )
        row = cur.fetchone()
        top_city = row[0] if row else None

        top_skill = None
        skill_top = get_skill_top(conn, top_n=1)
        if skill_top:
            top_skill = skill_top[0]["skill"]

    return {
        "job_count": int(total),
        "avg_salary": float(avg) if avg is not None else None,
        "top_city": top_city,
        "top_skill": top_skill,
    }


# ---------------- 分组聚合与排行（5.3） ----------------

def get_group_stats(conn, dimension, filters=None) -> pd.DataFrame:
    """按 城市 / 学历 / 经验 分组：职位数量、平均薪资、薪资中位数。

    返回 DataFrame，列：value, n, avg_salary, median_salary；
    排序规则（规格）：职位数降序，并列按名称字典序。
    职位数量计"全部行"，薪资统计只计 salary_avg 非空的行（缺失自动跳过）。
    """
    if dimension not in FILTER_FIELDS:
        raise ValueError(f"不支持的维度：{dimension}（可用：{', '.join(FILTER_FIELDS)}）")

    where, params = _where(filters)
    df = pd.read_sql(f"SELECT {dimension} AS dim, salary_avg FROM jobs {where}", conn, params=params)

    g = df.groupby("dim", dropna=False)
    out = pd.DataFrame(
        {
            "n": g.size(),
            "avg_salary": g["salary_avg"].mean(),
            "median_salary": g["salary_avg"].median(),
        }
    ).reset_index()
    out = out.rename(columns={"dim": "value"})
    out = out.sort_values(["n", "value"], ascending=[False, True]).reset_index(drop=True)
    return out


def get_top_cities(conn, top_n=10, filters=None) -> list[dict]:
    """城市排行（Top-N）：按职位数量降序，输出职位数与平均薪资。"""
    where, params = _where(filters)
    sql = (
        f"SELECT city, COUNT(*) AS n, AVG(salary_avg) AS avg_salary "
        f"FROM jobs {where} GROUP BY city ORDER BY n DESC, city ASC LIMIT %s"
    )
    with conn.cursor() as cur:
        cur.execute(sql, [*params, top_n])
        return [
            {"city": city, "n": int(n), "avg_salary": float(a) if a is not None else None}
            for city, n, a in cur.fetchall()
        ]


# ---------------- 技能词频与共现（5.4 / 5.5） ----------------

def get_skill_top(conn, top_n=15) -> list[dict]:
    """技能词频 Top-N：英文大小写归并（LOWER）+ 停用词过滤。

    词频 = 出现的岗位数（同一岗位内重复出现只计一次）。
    全量统计、不参与三维筛选（规格：技能数据的来源与筛选边界）。
    """
    words = tuple(sorted(STOPWORDS))
    cond = f"WHERE LOWER(skill) NOT IN ({_sql_in(words)})" if words else ""
    sql = f"""
        SELECT LOWER(skill) AS skill, COUNT(DISTINCT source_map_id) AS jobs
        FROM job_skills {cond}
        GROUP BY LOWER(skill)
        ORDER BY jobs DESC, skill ASC
        LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, [*words, top_n])
        return [{"skill": skill, "n": int(n)} for skill, n in cur.fetchall()]


def build_cooccurrence_matrix(pairs, skills) -> list[list[int]]:
    """纯函数：把 (技能1, 技能2, 共现次数) 铺成对称矩阵。"""
    index = {s: i for i, s in enumerate(skills)}
    n = len(skills)
    matrix = [[0] * n for _ in range(n)]
    for s1, s2, count in pairs:
        i, j = index.get(s1), index.get(s2)
        if i is None or j is None:
            continue
        matrix[i][j] = count
        matrix[j][i] = count
    return matrix


def get_skill_cooccurrence(conn, top_n=10) -> dict:
    """Top-N 技能的共现矩阵：统计"同一岗位内"两两同时出现的次数。

    返回 {"skills": [...], "matrix": [[...]]}；
    对角线补上各技能自身的岗位数，热力图观感更完整。
    """
    top = get_skill_top(conn, top_n=top_n)
    skills = [t["skill"] for t in top]
    if not skills:
        return {"skills": [], "matrix": []}

    words = tuple(sorted(STOPWORDS))
    stop_cond = (
        f"AND LOWER(a.skill) NOT IN ({_sql_in(words)}) "
        f"AND LOWER(b.skill) NOT IN ({_sql_in(words)})"
        if words else ""
    )
    ph = _sql_in(skills)
    sql = f"""
        SELECT LOWER(a.skill) AS s1, LOWER(b.skill) AS s2,
               COUNT(DISTINCT a.source_map_id) AS c
        FROM job_skills a
        JOIN job_skills b
          ON a.source_map_id = b.source_map_id
         AND LOWER(a.skill) < LOWER(b.skill)
        WHERE LOWER(a.skill) IN ({ph}) AND LOWER(b.skill) IN ({ph}) {stop_cond}
        GROUP BY s1, s2
    """
    params = [*skills, *skills, *words, *words]
    with conn.cursor() as cur:
        cur.execute(sql, params)
        pairs = cur.fetchall()

    matrix = build_cooccurrence_matrix(pairs, skills)
    freq = {t["skill"]: t["n"] for t in top}
    for i, s in enumerate(skills):
        matrix[i][i] = freq[s]
    return {"skills": skills, "matrix": matrix}
