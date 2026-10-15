"""按快照运行 ETL：来源读取、纯函数清洗、事务替换与统计输出。

运行：python -m etl.run_etl --snapshot 2018
"""

import argparse
import sys
import time

from db import get_connection
from etl.repository import replace_snapshot
from etl.schema import ensure_tables
from etl.sources import (ETLValidationError, SNAPSHOT_CONFIGS, load_csv, load_sources,
                         validate_replacement, validate_sources)
from etl.transforms import clean_jobs, decode_all_skills


def parse_snapshot_arg():
    """解析 --snapshot；缺省时报错并列出可用期次。

    不设默认期次：显式指定期次是对"本次要动哪一期数据"的确认，
    防止无参误触导致意外重导。
    """
    parser = argparse.ArgumentParser(description="按快照清洗入库（多期共存）")
    parser.add_argument("--snapshot", help="期次标签，如 2018 / 2020")
    args = parser.parse_args()
    if not args.snapshot:
        parser.error(
            "必须用 --snapshot 指定期次（可用："
            + " / ".join(c["label"] for c in SNAPSHOT_CONFIGS) + "）"
        )
    return args.snapshot


def run_snapshot(conn, config):
    """处理一期数据；只有校验、清洗成功后才修改该期数据与元信息。"""
    replaces = config.get("replaces")
    validate_replacement(config["label"], replaces)
    ensure_tables(conn)
    if config["form"] == "staging":
        job_df, skill_rows = load_sources(conn)
    else:
        job_df, skill_rows = load_csv(config), []
    validate_sources(job_df, skill_table_ok=bool(skill_rows), require_skills=config["has_skills"])
    jobs_df, job_stats = clean_jobs(job_df)
    if jobs_df.empty:
        raise ETLValidationError("清洗后没有岗位，保留已有快照")
    skill_records, skill_stats = decode_all_skills(skill_rows)
    snapshot_id = replace_snapshot(conn, config, jobs_df, skill_records, replaces=replaces)
    return {
        **job_stats, **skill_stats,
        "snapshot_id": snapshot_id, "jobs": len(jobs_df), "job_skills": len(skill_records),
    }


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    started = time.time()
    label = parse_snapshot_arg()
    config = next((c for c in SNAPSHOT_CONFIGS if c["label"] == label), None)
    if config is None:
        sys.exit(f"未知快照：{label}（可用：{' / '.join(c['label'] for c in SNAPSHOT_CONFIGS)}）")
    conn = get_connection()
    try:
        stats = run_snapshot(conn, config)
    finally:
        conn.close()
    print(f"=== ETL 完成（快照 {label}） ===")
    for key, value in stats.items():
        if key not in ("snapshot_id", "jobs", "job_skills"):
            print(f"{key}: {value:,}")
    print(f"入库: jobs {stats['jobs']:,} 行 / job_skills {stats['job_skills']:,} 行")
    print(f"耗时: {time.time() - started:.1f}s")


if __name__ == "__main__":
    main()
