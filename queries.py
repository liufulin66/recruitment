"""查询与分析层：把清洗后的数据变成页面要用的统计结果。

分工说明：
- 筛选（WHERE）与分组计数/均值用 SQL —— 这是数据库的主场；
- 中位数这类 MySQL 没有内置函数、写起来绕的统计，交给 pandas
  （"SQL 取数 + pandas 算统计"是实际项目里最常见的组合）。
对应规格：specs/recruitment-analytics/spec.md
"""

import json
from pathlib import Path

import pandas as pd

from domain import EDU_TIERS, EXP_TIERS

# 三维筛选：请求参数名 → jobs 表列名（同名）；第四维"期次"（snapshot）单独处理——
# 它不是 jobs 的取值筛选，而是数据归属维度（label -> snapshot_id 需查 snapshots 表）
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
    """从请求参数提取四维筛选（期次 + 城市/学历/经验）；空串 / None 一律视为"不限"。

    期次此处只提取 label；label -> snapshot_id 的解析见 resolve_snapshot（需查库）。
    """
    out = {"snapshot": (params.get("snapshot") or "").strip() or None}
    for field in FILTER_FIELDS:
        value = (params.get(field) or "").strip()
        out[field] = value or None
    return out


def resolve_snapshot(conn, filters, snapshots=None) -> int | None:
    """把期次 label 解析为 snapshot_id 并写入 filters（返回 id）。

    未指定期次 -> 最新一期（snapshots.id 最大：登记序即时间序）；
    未知 label 同样回退最新期（旧链接里的期次被移除后页面仍可用，
    期次下拉会如实显示当前实际期次）。
    """
    label = (filters or {}).get("snapshot")
    if snapshots is None:
        snapshots = get_snapshots(conn)
    current = next((s for s in snapshots if s["label"] == label), None)
    if current is None and snapshots:
        current = max(snapshots, key=lambda s: s["id"])
    filters["snapshot_id"] = current["id"] if current else None
    if label and current:
        filters["snapshot"] = current["label"]
    return filters["snapshot_id"]


def get_snapshots(conn) -> list[dict]:
    """全部快照（期次下拉选项与页脚元数据的数据源），按登记序返回。"""
    with conn.cursor() as cur:
        cur.execute("SELECT id, label, source, period, note FROM snapshots ORDER BY id")
        return [
            {"id": i, "label": label, "source": source, "period": period, "note": note}
            for i, label, source, period, note in cur.fetchall()
        ]


def _where(filters) -> tuple[str, list]:
    """把筛选条件编译为 WHERE 子句与参数列表（多条件取交集）。

    期次条件永远注入（规格：统计 MUST NOT 混合多个快照）——这是"永不混期"
    的落点。filters 必须先经 resolve_snapshot 写入 snapshot_id；空库时
    snapshot_id 为 None，条件不匹配任何行，页面自然呈现空态。
    """
    conds, params = ["snapshot_id = %s"], [filters["snapshot_id"]]
    for field in FILTER_FIELDS:
        value = filters.get(field)
        if value:
            conds.append(f"{field} = %s")
            params.append(value)
    return "WHERE " + " AND ".join(conds), params


# ---------------- 总览（5.2） ----------------

def get_overview(conn, filters) -> dict:
    """总览四项指标：职位总数 / 平均薪资 / 职位最多的城市 / 最高频技能。

    注意：Top 技能取当前期次的全量技能数据（技能表不含城市/经验/学历维度，
    按规格"技能数据的来源与筛选边界"处理）；无技能数据的期次该指标为空。
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
        skill_top = get_skill_top(conn, top_n=1, snapshot_id=filters["snapshot_id"])
        if skill_top:
            top_skill = skill_top[0]["skill"]

    return {
        "job_count": int(total),
        "avg_salary": float(avg) if avg is not None else None,
        "top_city": top_city,
        "top_skill": top_skill,
    }


# ---------------- 分组聚合与排行（5.3） ----------------

def get_group_stats(conn, dimension, filters, *, include_median=True) -> pd.DataFrame:
    """按 城市 / 学历 / 经验 分组：职位数量、平均薪资、薪资中位数。

    返回 DataFrame，列：value, n, avg_salary，默认包含 median_salary；
    页面不需要中位数时传 include_median=False，由 SQL 聚合，避免拉取明细。
    排序规则（规格）：职位数降序，并列按名称字典序。
    职位数量计"全部行"，薪资统计只计 salary_avg 非空的行（缺失自动跳过）。
    """
    if dimension not in FILTER_FIELDS:
        raise ValueError(f"不支持的维度：{dimension}（可用：{', '.join(FILTER_FIELDS)}）")

    where, params = _where(filters)
    if not include_median:
        sql = (
            f"SELECT {dimension} AS value, COUNT(*) AS n, AVG(salary_avg) AS avg_salary "
            f"FROM jobs {where} GROUP BY {dimension} ORDER BY n DESC, value IS NULL ASC, value ASC"
        )
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        out = pd.DataFrame(rows, columns=["value", "n", "avg_salary"])
        out["avg_salary"] = pd.to_numeric(out["avg_salary"], errors="coerce")
        return out
    with conn.cursor() as cur:
        cur.execute(f"SELECT {dimension} AS dim, salary_avg FROM jobs {where}", params)
        df = pd.DataFrame(cur.fetchall(), columns=["dim", "salary_avg"])
    df["salary_avg"] = pd.to_numeric(df["salary_avg"], errors="coerce")

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


def get_top_cities(conn, top_n, filters) -> list[dict]:
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

def get_skill_top(conn, top_n=15, snapshot_id=None) -> list[dict]:
    """技能词频 Top-N：英文大小写归并（LOWER）+ 停用词过滤，按期次隔离。

    词频 = 出现的岗位数（同一岗位内重复出现只计一次）。
    不参与城市/经验/学历筛选（规格：技能数据的来源与筛选边界）；
    source_map_id 仅在同一快照内唯一，跨期统计会把不同期的技能记到
    同一岗位名下，因此必须带期次过滤。
    """
    words = tuple(sorted(STOPWORDS))
    cond = (
        f"WHERE snapshot_id = %s AND LOWER(skill) NOT IN ({_sql_in(words)})"
        if words else "WHERE snapshot_id = %s"
    )
    sql = f"""
        SELECT LOWER(skill) AS skill, COUNT(DISTINCT source_map_id) AS jobs
        FROM job_skills {cond}
        GROUP BY LOWER(skill)
        ORDER BY jobs DESC, skill ASC
        LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, [snapshot_id, *words, top_n])
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


def get_skill_cooccurrence(conn, top_n=10, snapshot_id=None) -> dict:
    """Top-N 技能的共现矩阵：统计"同一岗位内"两两同时出现的次数（按期次隔离）。

    返回 {"skills": [...], "matrix": [[...]]}；
    对角线补上各技能自身的岗位数，热力图观感更完整。
    自连接必须两侧都限定同一 snapshot_id：join 键 source_map_id 只在
    快照内唯一，不带期次的两期同名 id 会被当成同一岗位凑出假共现。
    """
    top = get_skill_top(conn, top_n=top_n, snapshot_id=snapshot_id)
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
          ON a.snapshot_id = b.snapshot_id
         AND a.source_map_id = b.source_map_id
         AND LOWER(a.skill) < LOWER(b.skill)
        WHERE a.snapshot_id = %s
          AND LOWER(a.skill) IN ({ph}) AND LOWER(b.skill) IN ({ph}) {stop_cond}
        GROUP BY s1, s2
    """
    params = [snapshot_id, *skills, *skills, *words, *words]
    with conn.cursor() as cur:
        cur.execute(sql, params)
        pairs = cur.fetchall()

    matrix = build_cooccurrence_matrix(pairs, skills)
    freq = {t["skill"]: t["n"] for t in top}
    for i, s in enumerate(skills):
        matrix[i][i] = freq[s]
    return {"skills": skills, "matrix": matrix}


# ---------------- 页面辅助（第 6 组） ----------------

def get_salary_values(conn, filters) -> list[float]:
    """筛选后全部记录的等效平均月薪（供直方图 / 箱线图；缺失薪资自动排除）。"""
    where, params = _where(filters)
    cond = (where + " AND") if where else "WHERE"
    with conn.cursor() as cur:
        cur.execute(f"SELECT salary_avg FROM jobs {cond} salary_avg IS NOT NULL", params)
        return [float(row[0]) for row in cur.fetchall()]


def get_filter_options(conn, snapshot_id) -> dict:
    """筛选控件选项：城市取当前期次的全部取值（按名称排序）；学历 / 经验用固定档位。

    城市清单按期次取（规格：筛选选项随期次变化）——两期覆盖的城市集合不同。
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT city FROM jobs "
            "WHERE snapshot_id = %s AND city IS NOT NULL ORDER BY city",
            (snapshot_id,),
        )
        cities = [row[0] for row in cur.fetchall()]
    return {"cities": cities, "edus": list(EDU_TIERS), "exps": list(EXP_TIERS)}


# ---------------- 省份汇总（中国地图用） ----------------

_PROVINCE_MAP_FILE = Path(__file__).resolve().parent / "data" / "city_province.json"


def _load_city_province() -> dict:
    if not _PROVINCE_MAP_FILE.exists():
        return {}
    return json.loads(_PROVINCE_MAP_FILE.read_text(encoding="utf-8"))


# 城市 → 省份简称（对应 ECharts 中国地图的省级区域名）
CITY_TO_PROVINCE = _load_city_province()


def aggregate_by_province(city_counts, mapping=None) -> dict:
    """纯函数：把 [(城市, 数量)] 按"城市→省份"对照汇总为 {省份: 数量}。

    对不上省份的城市直接略过（地图上也落不了位）；对照表完整性由测试保证。
    """
    m = CITY_TO_PROVINCE if mapping is None else mapping
    out = {}
    for city, n in city_counts:
        province = m.get(city)
        if province:
            out[province] = out.get(province, 0) + int(n)
    return out


def get_province_totals(conn, filters) -> list[dict]:
    """省份维度职位数（城市数量汇总；供中国地图着色），按数量降序。"""
    city_rows = get_top_cities(conn, top_n=1000, filters=filters)
    totals = aggregate_by_province([(r["city"], r["n"]) for r in city_rows])
    return [{"province": p, "n": n} for p, n in sorted(totals.items(), key=lambda kv: -kv[1])]
