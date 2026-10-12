"""项目配置：本地 MySQL 连接参数。

安全说明：数据库口令不写死在代码里（写死 = 进 git = 一旦仓库公开就泄露）。
口令从项目根目录的 `.env` 文件读取；该文件不入 git（见 .gitignore），
模板见 `.env.example`。没有 .env 时回退读环境变量 RECRUIT_DB_PASSWORD。
"""

import os
from pathlib import Path


def _load_env_file(path: Path) -> dict:
    """读取极简 .env（每行 KEY=VALUE；空行与 # 开头的行忽略）。"""
    data = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            data[key.strip()] = value.strip()
    return data


_ROOT = Path(__file__).resolve().parent
_env = _load_env_file(_ROOT / ".env")

DB = {
    "host": _env.get("RECRUIT_DB_HOST", "127.0.0.1"),
    "port": int(_env.get("RECRUIT_DB_PORT", "3306")),
    "user": _env.get("RECRUIT_DB_USER", "recruit"),
    "password": _env.get("RECRUIT_DB_PASSWORD") or os.environ.get("RECRUIT_DB_PASSWORD", ""),
    "database": _env.get("RECRUIT_DB_NAME", "recruitment"),
    "charset": "utf8mb4",
}
