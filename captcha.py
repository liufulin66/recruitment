"""登录验证码：生成 4 位随机字符并渲染为 SVG（零依赖）。

机制（对应规格 specs/user-auth/spec.md 的"登录验证码 / 验证码一次性使用"）：
- 调用方把生成的码存入会话；
- 校验时"取出即作废"（一次性），无论对错，失败刷新页面自动换新码，防脚本重放。

强度说明：SVG 里的文字可被 OCR，属演示级强度——本地场景可接受（设计文档已记录取舍）。
"""

import random

# 去掉易混字符（0/O、1/l/I），减少"看错验证码"的坏体验
CHARS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LEN = 4
SESSION_KEY = "captcha_code"

_COLORS = ("#5470c6", "#91cc75", "#ee6666", "#73c0de", "#9a60b4", "#3ba272")


def generate_code():
    """生成 4 位随机验证码（大写字母 + 数字）。"""
    return "".join(random.choices(CHARS, k=CODE_LEN))


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
