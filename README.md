# 招聘数据分析与可视化分析系统

基于 **2018 年 BOSS直聘招聘数据集（46,353 条岗位）** 的本地数据分析 Web 系统：
数据清洗入库 → 多维统计分析 → 交互式仪表盘，并带本地账号体系与登录验证码。

## 功能特性

- **数据管线**：薪资字符串解析（区间 / 13 薪 / 年薪折算）、城市与学历经验枚举归一、去重（实测移除 9,563 条重复岗位）、技能表解码（Java 序列化 blob）、幂等覆盖式入库
- **分析维度**：薪资分布与箱线、城市排行与**省份热力地图**、学历 / 经验要求、**技能词云与共现热力图**
- **Web 仪表盘**：5 个页面（总览 / 薪资 / 地域 / 技能 / 要求·公司），顶部筛选条（城市 / 经验 / 学历）联动，筛选状态随 URL 跨页保持
- **账号体系**：注册 / 登录 / 登出、未登录访问一律拦截并跳回原页、记住我（7 天）、**登录 SVG 验证码**（一次性校验，防重放）
- **工程化**：OpenSpec 规格驱动开发、**67 条自动化测试**、前端 JS 资源本地化（**离线可运行**）

## 技术栈

| 环节 | 技术选型 |
| --- | --- |
| 语言 | Python 3.12 |
| 数据清洗 | pandas（向量化处理）+ 纯函数模块 + unittest 用例固化 |
| 存储 | MySQL 8.0（全链路 utf8mb4） |
| 查询 | PyMySQL + 手写 SQL 聚合（中位数等交给 pandas，"SQL 取数 + pandas 算统计"分工） |
| Web | Flask 3（Jinja 模板服务端渲染） |
| 图表 | pyecharts（ECharts 配置由 Python 生成，JS 资源本地化到 `static/assets/`） |
| 账号 | 手写轻量认证：werkzeug 密码哈希 + Flask 签名 Cookie 会话 + `before_request` 门卫 |

## 架构

```
 离线（数据准备）                          在线（Web 服务）
 ┌──────────────────────────┐          ┌─────────────────────────────────────┐
 │ data/raw/*.sql（数据集）  │          │ 浏览器                              │
 │    │                     │          │   │ 未登录 → 登录页（含验证码）      │
 │    v                     │          │   v                                 │
 │ ETL：清洗·解码·去重       │  MySQL   │ Flask 门卫 → 路由 → SQL 聚合查询     │
 │ (python -m etl.run_etl)  │ ───────> │   │                                 │
 │    │                     │  (干净表) │   v                                 │
 │    └──> jobs / job_skills│          │ pyecharts 渲染图表 → 页面            │
 └──────────────────────────┘          └─────────────────────────────────────┘
```

## 快速开始

> 环境：Windows / Python 3.12 / MySQL 8.0

```bash
# 1. 创建数据库与专用账号（utf8mb4），参考 data/README.md
# 2. 配置环境变量：复制 .env.example 为 .env，填入数据库口令（会话密钥可留空自动生成）

# 3. 安装依赖
.venv\Scripts\python.exe -m pip install -r requirements.txt

# 4. 导入原始数据集（数据集来源见 data/README.md）
mysql -h 127.0.0.1 -u recruit -p --default-character-set=utf8mb4 recruitment < data/raw/job_data.sql
mysql -h 127.0.0.1 -u recruit -p --default-character-set=utf8mb4 recruitment < data/raw/key_map.sql

# 5. 运行 ETL（清洗 + 技能解码 + 入库，约 25 秒；可重复执行/幂等）
.venv\Scripts\python.exe -m etl.run_etl

# 6. 启动服务，浏览器打开 http://127.0.0.1:5000
.venv\Scripts\python.exe -m app
```

首次使用没有账号：访问任意页面会跳转登录页，点"去注册"注册一个本地账号即可。

详细文档：数据管线见 [`docs/etl.md`](docs/etl.md)，页面与运行说明见 [`docs/run.md`](docs/run.md)。

## 目录结构

```
├── app.py              # Flask 应用：5 个数据页面 + 登录门卫
├── auth.py             # 账号：users 表自建 / 密码哈希 / 注册与凭据校验
├── captcha.py          # 登录验证码：随机码 + SVG 渲染（零依赖）
├── queries.py          # 查询与分析层：筛选编译 + 统计口径（SQL / pandas）
├── charts.py           # pyecharts 图表组装（JS 资源本地化）
├── etl/                # 数据管线：cleaning（解析归一）/ skills（技能解码）/ run_etl（主流程）
├── templates/          # Jinja 模板（base + 5 页面 + 登录/注册）
├── static/assets/      # 本地化的 ECharts / 词云 / 中国地图 JS
├── data/               # 数据集说明（raw/ 不入库）；样例值与城市-省份对照
├── docs/               # etl.md（数据管线）/ run.md（运行说明）
├── tests/              # 67 条自动化测试（unittest）
└── openspec/           # 规格驱动开发：specs/（4 个能力规格）+ changes/archive/（设计与任务存档）
```

## 测试

```bash
.venv\Scripts\python.exe -m unittest discover -s tests -t . -v
```

共 67 条用例（清洗解析 / 技能解码 / ETL 校验 / 查询统计 / 页面与账号流程）；
依赖数据库的用例在 MySQL 不可用时自动跳过。

## 数据来源与口径

- **来源**：[radishT/Job_Analysis](https://github.com/radishT/Job_Analysis)（GitHub 开源项目，2018 年 BOSS直聘岗位爬取）
- **覆盖时间**：2018 年（页面页脚已标注）
- **薪资口径**：取区间中点；带薪月数（如 `·13薪`）按月数 ÷ 12 折算为等效月薪
- **技能数据**：数据集自带的岗位技能表（含少量源数据拼写噪声，如 `angualar`，按原样保留）

## 开发方式

本项目采用 [OpenSpec](https://github.com/Fission-AI/OpenSpec) 规格驱动开发：
每个功能先产出 `proposal → design → specs → tasks` 四件套、验收后归档；
历史 change（数据管线+仪表盘、账号体系）的完整设计与决策记录保留在 `openspec/changes/archive/`。
