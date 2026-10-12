"""项目配置：本地 MySQL 连接参数与 Web 会话配置。

安全说明：数据库口令与会话签名密钥都不写死在代码里（写死 = 进 git = 泄露）。
从项目根目录的 `.env` 文件读取；该文件不入 git（见 .gitignore），模板见 `.env.example`。
"""

import os
import secrets
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

# Web 服务
WEB = {"host": "127.0.0.1", "port": 5000}

# 页脚数据来源标注（规格：每个页面展示来源与覆盖时间范围）
DATA_SOURCE = "radishT/Job_Analysis（GitHub 开源项目，2018 年 BOSS直聘岗位数据）"
DATA_PERIOD = "2018 年"
SALARY_NOTE = "薪资为折算口径：取区间中点；带薪月数（如 13 薪）按月数 ÷ 12 折算为等效月薪"

# 会话签名密钥：从 .env 读取；未配置时随机生成（重启后旧会话失效，开发可接受）
SECRET_KEY = _env.get("RECRUIT_SECRET_KEY") or secrets.token_hex(32)

# 会话 Cookie 防护（规格：HttpOnly + SameSite=Lax）与"记住我"时长
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_HTTPONLY = True
REMEMBER_ME_DAYS = 7
