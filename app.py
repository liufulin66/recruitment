"""Web 服务：招聘数据分析仪表盘（Flask，5 个页面 + 本地账号登录）。

运行方式（项目根目录）：
    .venv\\Scripts\\python.exe -m app
浏览器打开 http://127.0.0.1:5000/

对应规格：specs/web-dashboard/spec.md、specs/user-auth/spec.md
"""

from datetime import timedelta
from urllib.parse import quote

from flask import Flask, redirect, render_template, request, session, url_for

import auth
import charts
from config import (
    DATA_PERIOD,
    DATA_SOURCE,
    REMEMBER_ME_DAYS,
    SALARY_NOTE,
    SECRET_KEY,
    SESSION_COOKIE_HTTPONLY,
    SESSION_COOKIE_SAMESITE,
    WEB,
)
from db import get_connection
from queries import (
    get_filter_options,
    get_group_stats,
    get_overview,
    get_province_totals,
    get_salary_values,
    get_skill_cooccurrence,
    get_skill_top,
    get_top_cities,
    parse_filters,
)

app = Flask(__name__)

# 会话签名密钥（.env 注入；未配置则每次启动随机生成，旧登录会失效）
app.secret_key = SECRET_KEY
# 会话 Cookie 防护与"记住我"时长（规格：HttpOnly + SameSite=Lax）
app.config["SESSION_COOKIE_SAMESITE"] = SESSION_COOKIE_SAMESITE
app.config["SESSION_COOKIE_HTTPONLY"] = SESSION_COOKIE_HTTPONLY
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=REMEMBER_ME_DAYS)

# 启动时确保 users 表存在（幂等）
auth.ensure_users_table()


def _query(fn, *args):
    """每次查询开一条连接、用完即关（本地单用户规模，够用且简单）。"""
    conn = get_connection()
    try:
        return fn(conn, *args)
    finally:
        conn.close()


@app.context_processor
def inject_globals():
    """全站共享：页脚来源标注 + 筛选控件选项 + 当前登录用户名。"""
    return {
        "DATA_SOURCE": DATA_SOURCE,
        "DATA_PERIOD": DATA_PERIOD,
        "SALARY_NOTE": SALARY_NOTE,
        "filter_options": _query(get_filter_options),
        "current_user": session.get("username"),
    }


# ---------------- 访问门卫（规格：访问保护） ----------------

@app.before_request
def require_login():
    """除白名单外一律要求登录；未登录重定向登录页并记住原目标路径。"""
    if request.endpoint is None:  # 未知路径交给 404 处理
        return None
    if request.endpoint in ("login", "register"):
        if session.get("user_id"):  # 已登录又访问登录 / 注册页 -> 回总览
            return redirect(url_for("index"))
        return None
    if request.endpoint == "static":  # 静态资源放行（登录页样式、图表 JS 依赖它）
        return None
    if not session.get("user_id"):
        target = request.path
        if request.query_string:
            target += "?" + request.query_string.decode("utf-8")
        return redirect(url_for("login", next=target))
    return None


def _safe_next(next_path):
    """只接受站内相对路径（防止借 next 跳去外部站点）；非 ASCII 字符做百分号编码。

    形如 /salary?city=杭州（含中文）的路径直接放进 Location 响应头会编码失败，
    这里统一 quote 成纯 ASCII 的安全 URI。
    """
    if next_path and next_path.startswith("/") and not next_path.startswith("//"):
        return quote(next_path, safe="/?=&%#")
    return None


# ---------------- 账号：登录 / 注册 / 登出 ----------------

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    next_path = request.values.get("next", "")
    if request.method == "POST":
        user = auth.verify_login(request.form.get("username"), request.form.get("password"))
        if user:
            session.clear()  # 清旧会话再写入，避免会话固定问题
            session["user_id"] = user[0]
            session["username"] = user[1]
            # 勾选"记住我"：会话升级为 7 天永久会话；否则关浏览器即失效
            session.permanent = bool(request.form.get("remember_me"))
            return redirect(_safe_next(next_path) or url_for("index"))
        error = "用户名或密码错误"
    return render_template("login.html", page="login", filters={}, error=error, next_path=next_path)


@app.route("/register", methods=["GET", "POST"])
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
            return redirect(_safe_next(next_path) or url_for("index"))
    return render_template("register.html", page="register", filters={}, error=error, next_path=next_path)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------- 数据页面 ----------------

@app.route("/")
def index():
    f = parse_filters(request.args)
    overview = _query(get_overview, f)
    edu_stats = _query(get_group_stats, "edu", f)
    return render_template(
        "index.html",
        page="index",
        filters=f,
        overview=overview,
        charts=[
            charts.top_cities_chart(_query(get_top_cities, 10, f)),
            charts.pie_share(list(edu_stats["value"]), list(edu_stats["n"]), "学历要求分布"),
        ],
    )


@app.route("/salary")
def salary():
    f = parse_filters(request.args)
    values = _query(get_salary_values, f)
    cities = _query(get_top_cities, 10, f)
    exp_stats = _query(get_group_stats, "exp", f)
    edu_stats = _query(get_group_stats, "edu", f)
    return render_template(
        "salary.html",
        page="salary",
        filters=f,
        charts=[
            charts.salary_hist(values),
            charts.salary_boxplot(values),
            charts.avg_salary_chart(
                [c["city"] for c in cities], [c["avg_salary"] for c in cities], "城市平均薪资 Top10"
            ),
            charts.avg_salary_chart(
                list(exp_stats["value"]), list(exp_stats["avg_salary"]), "经验要求 × 平均薪资"
            ),
            charts.avg_salary_chart(
                list(edu_stats["value"]), list(edu_stats["avg_salary"]), "学历要求 × 平均薪资"
            ),
        ],
    )


@app.route("/geo")
def geo():
    f = parse_filters(request.args)
    top10 = _query(get_top_cities, 10, f)
    provinces = _query(get_province_totals, f)  # 城市数按省份汇总后上地图
    return render_template(
        "geo.html",
        page="geo",
        filters=f,
        charts=[
            charts.top_cities_chart(top10),
            charts.city_map([(r["province"], r["n"]) for r in provinces]),
        ],
    )


@app.route("/skills")
def skills():
    f = parse_filters(request.args)  # 仅用于导航传参；技能统计恒为全量（规格边界）
    top = _query(get_skill_top, 100)
    co = _query(get_skill_cooccurrence, 12)
    return render_template(
        "skills.html",
        page="skills",
        filters=f,
        charts=[
            charts.skill_wordcloud([(t["skill"], t["n"]) for t in top]),
            charts.bar(
                [t["skill"] for t in top[:30]],
                [t["n"] for t in top[:30]],
                "技能词频 Top30（按岗位数）",
                y_name="岗位数",
                rotate=40,
            ),
            charts.skill_cooccurrence_heatmap(co["skills"], co["matrix"]),
        ],
    )


@app.route("/company")
def company():
    f = parse_filters(request.args)
    edu_stats = _query(get_group_stats, "edu", f)
    exp_stats = _query(get_group_stats, "exp", f)
    return render_template(
        "company.html",
        page="company",
        filters=f,
        charts=[
            charts.pie_share(list(edu_stats["value"]), list(edu_stats["n"]), "学历要求占比"),
            charts.pie_share(list(exp_stats["value"]), list(exp_stats["n"]), "经验要求占比"),
        ],
    )


if __name__ == "__main__":
    app.run(host=WEB["host"], port=WEB["port"], debug=True)
