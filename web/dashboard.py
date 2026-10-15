"""仪表盘路由与按请求加载的分析页面上下文。"""

from flask import Blueprint, g, render_template, request

import charts
from db import get_db
from queries import (
    get_filter_options,
    get_group_stats,
    get_overview,
    get_province_totals,
    get_salary_values,
    get_skill_cooccurrence,
    get_skill_top,
    get_snapshots,
    get_top_cities,
    parse_filters,
    resolve_snapshot,
)

bp = Blueprint("dashboard", __name__)


def _query(fn, *args):
    return fn(get_db(), *args)


def _group_stats(dimension, filters):
    return get_group_stats(get_db(), dimension, filters, include_median=False)


def _filters():
    if "filters" not in g:
        g.snapshots = _query(get_snapshots)
        g.filters = parse_filters(request.args)
        resolve_snapshot(None, g.filters, snapshots=g.snapshots)
    return g.filters


@bp.context_processor
def inject_dashboard():
    """只为分析页面查库；快照列表与路由共享，不重复查询。"""
    f = _filters()
    current = next((s for s in g.snapshots if s["id"] == f["snapshot_id"]), None)
    return {
        "snapshots": g.snapshots,
        "current_snapshot": current,
        "filter_options": _query(get_filter_options, f["snapshot_id"]),
    }


@bp.route("/")
def index():
    f = _filters()
    overview = _query(get_overview, f)
    edu_stats = _group_stats("edu", f)
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


@bp.route("/salary")
def salary():
    f = _filters()
    values = _query(get_salary_values, f)
    cities = _query(get_top_cities, 10, f)
    exp_stats = _group_stats("exp", f)
    edu_stats = _group_stats("edu", f)
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


@bp.route("/geo")
def geo():
    f = _filters()
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


@bp.route("/skills")
def skills():
    f = _filters()  # 仅用于导航/页脚传参；技能统计恒为当前期次全量（规格边界）
    top = _query(get_skill_top, 100, f["snapshot_id"])
    co = _query(get_skill_cooccurrence, 12, f["snapshot_id"])
    return render_template(
        "skills.html",
        page="skills",
        filters=f,
        has_skills=bool(top),
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


@bp.route("/company")
def company():
    f = _filters()
    edu_stats = _group_stats("edu", f)
    exp_stats = _group_stats("exp", f)
    return render_template(
        "company.html",
        page="company",
        filters=f,
        charts=[
            charts.pie_share(list(edu_stats["value"]), list(edu_stats["n"]), "学历要求占比"),
            charts.pie_share(list(exp_stats["value"]), list(exp_stats["n"]), "经验要求占比"),
        ],
    )
