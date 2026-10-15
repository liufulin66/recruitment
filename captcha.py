"""登录验证码：生成 4 位随机字符并渲染为 SVG（零依赖）。

机制（对应规格 specs/user-auth/spec.md 的"登录验证码 / 验证码一次性使用"）：
- Cookie 会话只保存随机标识，答案与 5 分钟有效期保存在 MySQL；
- 用行锁串行化“取出并删除”，无论对错都消费，旧 Cookie 也不能重放。

强度说明：SVG 里的文字可被 OCR，属演示级强度——本地场景可接受（设计文档已记录取舍）。
"""

import random
import secrets

from db import connection

# 去掉易混字符（0/O、1/l/I），减少"看错验证码"的坏体验
CHARS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LEN = 4
SESSION_KEY = "captcha_id"
TTL_SECONDS = 5 * 60

DDL_CAPTCHA = """
CREATE TABLE IF NOT EXISTS captcha_challenges (
  id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin PRIMARY KEY,
  code VARCHAR(4) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  expires_at DATETIME(6) NOT NULL,
  KEY idx_expires (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

_COLORS = ("#5470c6", "#91cc75", "#ee6666", "#73c0de", "#9a60b4", "#3ba272")


def generate_code():
    """生成 4 位随机验证码（大写字母 + 数字）。"""
    return "".join(secrets.choice(CHARS) for _ in range(CODE_LEN))


def ensure_captcha_table():
    """由 init-db 显式创建，不在导入或请求中执行 DDL。"""
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(DDL_CAPTCHA)
        conn.commit()


def issue(previous_id=None):
    """创建新挑战并撤销当前会话的旧挑战；返回 (随机标识, 答案)。"""
    challenge_id, code = secrets.token_urlsafe(32), generate_code()
    with connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM captcha_challenges WHERE expires_at <= UTC_TIMESTAMP(6)")
                if previous_id:
                    cur.execute("DELETE FROM captcha_challenges WHERE id = %s", (previous_id,))
                cur.execute(
                    "INSERT INTO captcha_challenges (id, code, expires_at) "
                    "VALUES (%s, %s, TIMESTAMPADD(SECOND, %s, UTC_TIMESTAMP(6)))",
                    (challenge_id, code, TTL_SECONDS),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return challenge_id, code


def consume(challenge_id, given):
    """锁定并删除挑战后提交；并发请求只有一个能读到答案。"""
    if not challenge_id:
        return False
    with connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT code, expires_at > UTC_TIMESTAMP(6) FROM captcha_challenges "
                    "WHERE id = %s FOR UPDATE",
                    (challenge_id,),
                )
                row = cur.fetchone()
                cur.execute("DELETE FROM captcha_challenges WHERE id = %s", (challenge_id,))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    answer = (given or "").strip().upper()
    return bool(row and row[1] and secrets.compare_digest(row[0].encode(), answer.encode()))


def captcha_svg(code):
    """把验证码画成 SVG 字符串：每个字符随机旋转/偏移/配色，叠加干扰线。"""
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="44" viewBox="0 0 120 44">',
        '<rect width="120" height="44" fill="#f6f7f9" rx="6"/>',
    ]
    for _ in range(4):  # 干扰线
        parts.append(
            f'<line x1="{random.randint(0, 120)}" y1="{random.randint(0, 44)}" '
            f'x2="{random.randint(0, 120)}" y2="{random.randint(0, 44)}" '
            f'stroke="{random.choice(_COLORS)}" stroke-opacity="0.35"/>'
        )
    for i, ch in enumerate(code):
        x = 16 + i * 26
        y = random.randint(28, 34)
        angle = random.randint(-24, 24)
        parts.append(
            f'<text x="{x}" y="{y}" transform="rotate({angle} {x} {y})" '
            f'font-family="Consolas, monospace" font-size="24" font-weight="700" '
            f'fill="{random.choice(_COLORS)}">{ch}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)
