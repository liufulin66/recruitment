"""Web 服务：招聘数据分析仪表盘（Flask，5 个页面）。

运行方式（项目根目录）：
    .venv\\Scripts\\python.exe -m app
浏览器打开 http://127.0.0.1:5000/

对应规格：specs/web-dashboard/spec.md
"""

from flask import Flask, render_template, request

import charts
from config import DATA_PERIOD, DATA_SOURCE, SALARY_NOTE, WEB
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


def _query(fn, *args):
    """每次查询开一条连接、用完即关（本地单用户规模，够用且简单）。"""
    conn = get_connection()
    try:
        return fn(conn, *args)
    finally:
        conn.close()


@app.context_processor
def inject_globals():
    """全站共享：页脚来源标注（规格：从配置读取）+ 筛选控件选项。"""
    return {
        "DATA_SOURCE": DATA_SOURCE,
        "DATA_PERIOD": DATA_PERIOD,
        "SALARY_NOTE": SALARY_NOTE,
        "filter_options": _query(get_filter_options),
    }


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
