"""分析表结构与显式建表入口。"""

# 清洗后目标表
TARGET_JOB_TABLE = "jobs"
TARGET_SKILL_TABLE = "job_skills"

DDL_JOBS = f"""
CREATE TABLE IF NOT EXISTS {TARGET_JOB_TABLE} (
  id INT AUTO_INCREMENT PRIMARY KEY,
  snapshot_id INT NOT NULL,
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
  KEY idx_snapshot (snapshot_id),
  KEY idx_city (city),
  KEY idx_edu (edu),
  KEY idx_exp (exp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

DDL_SKILLS = f"""
CREATE TABLE IF NOT EXISTS {TARGET_SKILL_TABLE} (
  id INT AUTO_INCREMENT PRIMARY KEY,
  snapshot_id INT NOT NULL,
  source_map_id INT NOT NULL,
  key_word VARCHAR(10) NOT NULL,
  skill VARCHAR(64) NOT NULL,
  KEY idx_snapshot (snapshot_id),
  KEY idx_skill (skill),
  KEY idx_source (snapshot_id, source_map_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

# 快照元数据表（多期数据共存：每期一行；jobs/job_skills 的 snapshot_id 指向此表）
DDL_SNAPSHOTS = """
CREATE TABLE IF NOT EXISTS snapshots (
  id INT AUTO_INCREMENT PRIMARY KEY,
  label VARCHAR(20) NOT NULL UNIQUE,
  source VARCHAR(255) NOT NULL,
  period VARCHAR(50) NOT NULL,
  note VARCHAR(255)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""



def ensure_tables(conn):
    with conn.cursor() as cur:
        for ddl in (DDL_SNAPSHOTS, DDL_JOBS, DDL_SKILLS):
            cur.execute(ddl)
