"""图表组装：把查询结果变成 pyecharts 图表（服务端生成 ECharts 配置）。

约定：
- 页面只负责摆放；标题、坐标轴、旋转角等一律在这里集中管理；
- 图表 JS 资源已本地化到 static/assets（离线可演示）；
- 数据为空时返回 None，由页面显示空态提示。
"""

import pandas as pd
from pyecharts import options as opts
from pyecharts.charts import Bar, Boxplot, HeatMap, Map, Pie, WordCloud
from pyecharts.globals import CurrentConfig

# pyecharts 默认从 CDN 加载 echarts JS；改为本地 static（文件来源见 static/assets/README）
CurrentConfig.ONLINE_HOST = "/static/assets/"


def _title(text):
    return opts.TitleOpts(title=text)


def bar(x_data, y_data, title, y_name="数量", rotate=0):
    """通用柱状图；x_data 为空返回 None。"""
    if not x_data:
        return None
    chart = (
        Bar()
        .add_xaxis([str(v) for v in x_data])
        .add_yaxis(
            y_name,
            [None if v is None else round(float(v), 1) for v in y_data],
            label_opts=opts.LabelOpts(is_show=False),
        )
        .set_global_opts(
            title_opts=_title(title),
            xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=rotate)),
            yaxis_opts=opts.AxisOpts(name=y_name),
        )
    )
    return chart.render_embed()


def top_cities_chart(cities):
    """城市职位数量 Top-N 柱状图。"""
    return bar(
        [c["city"] for c in cities],
        [c["n"] for c in cities],
        f"职位数量 · 城市 Top{len(cities)}",
    )


def avg_salary_chart(names, avgs, title):
    """按某维度分组的平均薪资对比图。"""
    return bar(names, avgs, title, y_name="平均薪资（元/月）", rotate=30)


def salary_hist(values, step=2000, title="薪资分布（每 2000 元一档）"):
    """薪资直方图：把逐条薪资按固定宽度分箱计数。"""
    values = [v for v in values if v is not None]
    if not values:
        return None
    top = int(max(values))
    bins = list(range(0, top + step, step))
    labels = [f"{bins[i] // 1000}k-{bins[i + 1] // 1000}k" for i in range(len(bins) - 1)]
    counts = pd.cut(pd.Series(values), bins=bins, right=False, labels=labels).value_counts(sort=False)
    return bar(labels, list(counts), title, y_name="职位数")


def salary_boxplot(values, title="薪资箱线图（整体）"):
    """箱线图：用 1.5×IQR 规则求上下须（须外视为离群点，不计入图形）。"""
    s = pd.Series([v for v in values if v is not None])
    if s.empty:
        return None
    q1, median, q3 = s.quantile([0.25, 0.5, 0.75])
    iqr = q3 - q1
    low = float(s[s >= q1 - 1.5 * iqr].min())
    high = float(s[s <= q3 + 1.5 * iqr].max())
    chart = (
        Boxplot()
        .add_xaxis(["全部职位"])
        .add_yaxis("薪资", [[round(low), round(q1), round(median), round(q3), round(high)]])
        .set_global_opts(title_opts=_title(title), yaxis_opts=opts.AxisOpts(name="元/月"))
    )
    return chart.render_embed()


def pie_share(names, values, title):
    """占比环图。"""
    if not names:
        return None
    chart = (
        Pie()
        .add(
            "",
            [list(z) for z in zip(names, values)],
            radius=["40%", "66%"],
            label_opts=opts.LabelOpts(formatter="{b}: {d}%"),
        )
        .set_global_opts(
            title_opts=_title(title),
            legend_opts=opts.LegendOpts(orient="vertical", pos_right="5%"),
        )
    )
    return chart.render_embed()


def city_map(pairs, title="职位数量 · 中国地图（按省份汇总）"):
    """中国地图热力图；pairs = [(城市, 数量), ...]。"""
    if not pairs:
        return None
    chart = (
        Map()
        .add("职位数量", [[city, int(n)] for city, n in pairs], "china")
        .set_global_opts(
            title_opts=_title(title),
            visualmap_opts=opts.VisualMapOpts(max_=max(int(n) for _, n in pairs), is_piecewise=False),
        )
    )
    return chart.render_embed()


def skill_wordcloud(skills, title="技能词云"):
    """词云；skills = [(技能词, 岗位数), ...]。"""
    if not skills:
        return None
    chart = (
        WordCloud()
        .add("", [(s, int(n)) for s, n in skills], word_size_range=[14, 64], shape="circle")
        .set_global_opts(title_opts=_title(title))
    )
    return chart.render_embed()


def skill_cooccurrence_heatmap(skills, matrix, title="技能共现热力图"):
    """共现热力图：行列 = Top-N 技能，格值 = 同岗位共现次数。"""
    if not skills:
        return None
    data = [[i, j, int(matrix[i][j])] for i in range(len(skills)) for j in range(len(skills))]
    biggest = max(max(row) for row in matrix)
    chart = (
        HeatMap()
        .add_xaxis(skills)
        .add_yaxis("共现次数", skills, data, label_opts=opts.LabelOpts(is_show=False))
        .set_global_opts(
            title_opts=_title(title),
            visualmap_opts=opts.VisualMapOpts(min_=0, max_=biggest),
            xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=40)),
        )
    )
    return chart.render_embed()
