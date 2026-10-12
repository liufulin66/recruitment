# 运行说明（Web 仪表盘）

## 前置条件

1. MySQL 服务已启动，`recruitment` 库已建（见 `data/README.md`）
2. 已配置 `.env`（数据库口令，模板见 `.env.example`）
3. 已运行 ETL 把数据准备好（见 `docs/etl.md`）
4. 依赖已安装：`.venv\Scripts\python.exe -m pip install -r requirements.txt`

## 启动

```bash
.venv\Scripts\python.exe -m app
```

- 默认监听 `http://127.0.0.1:5000/`（端口可在 `config.py` 的 `WEB` 里修改）
- 调试模式已开启：改代码自动重载；`Ctrl+C` 停止

## 页面导览

| 路由 | 页面 | 内容 |
| --- | --- | --- |
| `/` | 总览 | 指标卡（职位数 / 均薪 / Top 城市 / Top 技能）+ 代表图表 |
| `/salary` | 薪资 | 分布直方图、箱线图、按城市 / 经验 / 学历的平均薪资对比 |
| `/geo` | 地域 | 城市排行柱状图 + 中国地图热力图 |
| `/skills` | 技能 | 词云、词频 Top30、共现热力图（全量口径，不参与顶部筛选） |
| `/company` | 要求·公司 | 学历 / 经验占比环图（公司规模、行业：数据不包含） |

- 顶部筛选条（城市 / 经验 / 学历）作用于除技能页外的图表；筛选条件写入 URL，可刷新、可收藏、跨页保持
- 页脚标注数据来源与覆盖时间范围

## 常见问题

- 端口被占：修改 `config.py` 中 `WEB["port"]`
- 图表空白：确认 `static/assets/` 下三个 JS 文件存在（echarts 主库 / 词云扩展 / 中国地图）
