"""本地账号体系：users 表、密码哈希、注册与凭据校验。

安全要点（对应规格 specs/user-auth/spec.md）：
- 密码只存 Werkzeug 生成的自带随机盐哈希，永不存明文；
- 用户名查重与登录比对都不区分大小写（存储保留原始大小写用于展示）；
- 登录失败不区分"用户不存在 / 密码错误"，防止用户枚举。
"""

from werkzeug.security import check_password_hash, generate_password_hash
from pymysql import IntegrityError

from db import connection

MIN_PASSWORD_LEN = 6
MAX_USERNAME_LEN = 50


class AuthError(Exception):
    """注册 / 登录校验失败（异常消息直接面向用户展示）。"""


def ensure_users_table():
    """显式初始化时调用：确保 users 表存在（幂等，可反复执行）。"""
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                  id INT AUTO_INCREMENT PRIMARY KEY,
                  username VARCHAR(50) NOT NULL,
                  password_hash VARCHAR(255) NOT NULL,
                  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  UNIQUE KEY uk_username (username)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        conn.commit()


def register(username, password):
    """注册新账号；成功返回 (user_id, username)，失败抛 AuthError。

    注意：users 表用 utf8mb4_unicode_ci 排序规则，等值比较天然不区分大小写，
    所以唯一约束与登录查询无需额外 LOWER()。
    """
    username = (username or "").strip()
    if not username:
        raise AuthError("请输入用户名")
    if len(username) > MAX_USERNAME_LEN:
        raise AuthError(f"用户名过长（最多 {MAX_USERNAME_LEN} 个字符）")
    if not password or len(password) < MIN_PASSWORD_LEN:
        raise AuthError(f"密码长度至少 {MIN_PASSWORD_LEN} 位")

    password_hash = generate_password_hash(password)
    with connection() as conn:
        try:
            # 唯一索引负责最终查重，避免“先查再插”的并发窗口。
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO users (username, password_hash) VALUES (%s, %s)",
                    (username, password_hash),
                )
                user_id = cur.lastrowid
            conn.commit()
        except IntegrityError as exc:
            conn.rollback()
            if exc.args[0] == 1062:
                raise AuthError("用户名已被占用") from exc
            raise
        except Exception:
            conn.rollback()
            raise
        return user_id, username


def verify_login(username, password):
    """校验凭据；成功返回 (user_id, username)，失败一律返回 None（不透露原因）。"""
    username = (username or "").strip()
    if not username or not password:
        return None
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, username, password_hash FROM users WHERE username = %s",
                (username,),
            )
            row = cur.fetchone()
    if not row or not check_password_hash(row[2], password):
        return None
    return row[0], row[1]
