"""批量入库与快照替换事务；失败时回滚整期变更。"""

import pandas as pd

from etl.schema import TARGET_JOB_TABLE, TARGET_SKILL_TABLE
from etl.sources import ETLValidationError, validate_replacement


def register_snapshot(conn, meta) -> int:
    """注册快照元数据并返回其 id（按 label 存在则更新、不存在则插入，天然幂等）。

    不用 INSERT ... ON DUPLICATE KEY UPDATE：其取旧值的 VALUES() 写法
    在 MySQL 8.0.20+ 已标记废弃，显式分支没有版本兼容顾虑、语义也更直白。
    """
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM snapshots WHERE label = %s", (meta["label"],))
        row = cur.fetchone()
        if row:
            cur.execute(
                "UPDATE snapshots SET source = %s, period = %s, note = %s WHERE label = %s",
                (meta["source"], meta["period"], meta["note"], meta["label"]),
            )
            return row[0]
        cur.execute(
            "INSERT INTO snapshots (label, source, period, note) VALUES (%s, %s, %s, %s)",
            (meta["label"], meta["source"], meta["period"], meta["note"]),
        )
        return cur.lastrowid


def insert_jobs(conn, df: pd.DataFrame, snapshot_id: int):
    """清洗主表批量入库（行均归属 snapshot_id；与技能表共用一条事务，由 main 统一提交）。"""
    cols = ["job_name", "company", "city", "salary_min", "salary_max", "salary_avg",
            "salary_raw", "edu", "exp", "key_word", "snapshot_id"]
    data = [
        (*(None if pd.isna(v) else v for v in row), snapshot_id)
        for row in df[cols[:-1]].itertuples(index=False, name=None)
    ]
    sql = f"INSERT INTO {TARGET_JOB_TABLE} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})"
    with conn.cursor() as cur:
        cur.executemany(sql, data)


def insert_skills(conn, rows, snapshot_id: int, chunk_size=20000):
    """技能行分批 executemany（行均归属 snapshot_id）；整个写入过程一条事务。

    对比：逐条 INSERT（如数据集自带 dump 的导入）每条都要刷一次盘，
    6 万条要 23 分钟；事务 + 批量提交后同样的量级只需几十秒。
    """
    sql = f"INSERT INTO {TARGET_SKILL_TABLE} (snapshot_id, source_map_id, key_word, skill) VALUES (%s, %s, %s, %s)"
    with conn.cursor() as cur:
        for start in range(0, len(rows), chunk_size):
            chunk = [(snapshot_id, *row) for row in rows[start:start + chunk_size]]
            cur.executemany(sql, chunk)


def remove_snapshot(conn, label):
    """按标签解析实际 id；只执行 DML，提交由外层替换事务负责。"""
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM snapshots WHERE label = %s FOR UPDATE", (label,))
        row = cur.fetchone()
        if row is None:
            return
        cur.execute(f"DELETE FROM {TARGET_JOB_TABLE} WHERE snapshot_id = %s", (row[0],))
        cur.execute(f"DELETE FROM {TARGET_SKILL_TABLE} WHERE snapshot_id = %s", (row[0],))
        cur.execute("DELETE FROM snapshots WHERE id = %s", (row[0],))


def replace_snapshot(conn, meta, jobs_df, skill_records, replaces=None):
    validate_replacement(meta["label"], replaces)
    if jobs_df.empty:
        raise ETLValidationError("清洗后没有岗位，保留已有快照")
    try:
        snapshot_id = register_snapshot(conn, meta)
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM {TARGET_JOB_TABLE} WHERE snapshot_id = %s", (snapshot_id,))
            cur.execute(f"DELETE FROM {TARGET_SKILL_TABLE} WHERE snapshot_id = %s", (snapshot_id,))
        insert_jobs(conn, jobs_df, snapshot_id)
        insert_skills(conn, skill_records, snapshot_id)
        if replaces is not None:
            remove_snapshot(conn, replaces)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return snapshot_id
