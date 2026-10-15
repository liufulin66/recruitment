"""认证路由：登录、注册、登出及验证码。"""

from urllib.parse import quote

from flask import Blueprint, Response, redirect, render_template, request, session, url_for

import auth
import captcha

bp = Blueprint("auth", __name__)


def _safe_next(next_path):
    """只接受站内相对路径（防止借 next 跳去外部站点）；非 ASCII 字符做百分号编码。

    形如 /salary?city=杭州（含中文）的路径直接放进 Location 响应头会编码失败，
    这里统一 quote 成纯 ASCII 的安全 URI。
    """
    if next_path and next_path.startswith("/") and not next_path.startswith("//"):
        return quote(next_path, safe="/?=&%#")
    return None


# ---------------- 账号：登录 / 注册 / 登出 / 验证码 ----------------

@bp.route("/captcha")
def captcha_image():
    """答案留在服务器，随机标识写入会话，刷新时撤销旧挑战。"""
    challenge_id, code = captcha.issue(session.get(captcha.SESSION_KEY))
    session[captcha.SESSION_KEY] = challenge_id
    return Response(
        captcha.captcha_svg(code),
        mimetype="image/svg+xml",
        headers={"Cache-Control": "no-store"},  # 禁止缓存，保证每次都是新码
    )


@bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    next_path = request.values.get("next", "")
    if request.method == "POST":
        # MySQL 原子消费；即使重放旧 Cookie，也不能恢复已消费的挑战。
        challenge_id = session.pop(captcha.SESSION_KEY, None)
        if not captcha.consume(challenge_id, request.form.get("captcha")):
            error = "验证码错误"
        else:
            user = auth.verify_login(request.form.get("username"), request.form.get("password"))
            if user:
                session.clear()  # 清旧会话再写入，避免会话固定问题
                session["user_id"] = user[0]
                session["username"] = user[1]
                # 勾选"记住我"：会话升级为 7 天永久会话；否则关浏览器即失效
                session.permanent = bool(request.form.get("remember_me"))
                return redirect(_safe_next(next_path) or url_for("dashboard.index"))
            error = "用户名或密码错误"
    return render_template("login.html", page="login", filters={}, error=error, next_path=next_path)


@bp.route("/register", methods=["GET", "POST"])
def register():
    error = None
    next_path = request.values.get("next", "")
    if request.method == "POST":
        try:
            user_id, username = auth.register(request.form.get("username"), request.form.get("password"))
        except auth.AuthError as exc:
            error = str(exc)
        else:
            session.clear()
            session["user_id"] = user_id
            session["username"] = username
            return redirect(_safe_next(next_path) or url_for("dashboard.index"))
    return render_template("register.html", page="register", filters={}, error=error, next_path=next_path)


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
