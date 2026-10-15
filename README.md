# 招聘数据分析与可视化分析系统

基于 **多期 BOSS直聘招聘数据快照（2018 IT 岗位 + 2020 年 4 月公开的 12 城市 IT 样本）** 的本地数据分析 Web 系统：
按快照清洗入库 → 多维统计分析 → 交互式仪表盘，并带本地账号体系与登录验证码。

## 数据概览

| 期次 | 覆盖说明 | 原始岗位数 | 清洗后岗位数 | 技能记录数 |
| --- | --- | ---: | ---: | ---: |
| 2018 | 多关键词 IT 岗位，含技能数据 | 46,353 | 36,790 | 577,373 |
| 2020（默认） | 2020 年 4 月公开的 12 城市 IT 岗位样本 | 28,162 | 24,841 | 0 |

2020 期没有逐条发布日期和技能明细，技能页会显示相应提示；其公开年份不代表全年采集范围。两期按快照独立统计。

旧版本的 2021 小样本已由 2020 替换。已有数据库升级前，先按 [迁移与回滚说明](docs/etl.md#2-从-20182021-升级至-20182020) 备份旧快照，再执行 `--snapshot 2020`；2018 数据保持不变。

## 功能特性

- **数据管线**：**多期快照共存**（批内幂等；2020 成功导入时原子替换旧 2021）、薪资字符串解析（区间 / 13 薪 / 年薪折算）、城市与学历经验枚举归一、去重（快照内，2018 期实测移除 9,563 条重复岗位）、技能表解码（Java 序列化 blob）、多来源摄入（SQL 暂存表 / CSV 直读）
- **分析维度**：薪资分布与箱线、城市排行与**省份热力地图**、学历 / 经验要求、**技能词云与共现热力图**（按期隔离统计）
- **Web 仪表盘**：5 个页面（总览 / 薪资 / 地域 / 技能 / 要求·公司），顶部筛选条（**期次** / 城市 / 经验 / 学历）联动，默认 2020、页脚按期动态标注，筛选状态随 URL 跨页保持
- **账号体系**：注册 / 登录 / 登出、未登录访问一律拦截并跳回原页、记住我（7 天）、**登录 SVG 验证码**（MySQL 状态，5 分钟有效，一次性消费）
- **工程化**：OpenSpec 规格驱动开发、**单元测试与隔离的 MySQL 集成测试**、前端 JS 资源本地化（**离线可运行**）

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
 离线（数据准备，按快照）                  在线（Web 服务）
 ┌──────────────────────────┐          ┌─────────────────────────────────────┐
 │ data/raw/（SQL + CSV）    │          │ 浏览器                              │
 │    │                     │          │   │ 未登录 → 登录页（含验证码）      │
 │    v                     │          │   v                                 │
 │ ETL：清洗·解码·去重       │  MySQL   │ Flask 门卫 → 路由 → SQL 聚合查询     │
 │ (run_etl --snapshot N)   │ ───────> │   │ 期次条件永远注入，默认最新期      │
 │    │                     │  (干净表) │   v                                 │
 │    └──> jobs / job_skills│          │ pyecharts 渲染图表 → 页面            │
 │        + snapshots 元数据 │          │                                     │
 └──────────────────────────┘          └─────────────────────────────────────┘
```

## 快速开始

> 环境：Windows / Python 3.12 / MySQL 8.0（命令为 Windows 写法；Linux / macOS 用户把 `.venv\Scripts\` 换成 `.venv/bin/` 即可）

先克隆项目并创建虚拟环境：

```bash
git clone https://github.com/liufulin66/recruitment.git
cd recruitment
python -m venv .venv
```

在项目根目录继续执行。以下 MySQL 导入命令使用 Git Bash / CMD 的 `<` 重定向；PowerShell 用户可通过 `cmd /c` 执行，数据集下载的 PowerShell 命令见 [数据集说明](data/README.md)。

```bash
# 1. 创建数据库与专用账号（utf8mb4），参考 data/README.md
# 2. 配置环境变量：复制 .env.example 为 .env，填入数据库口令（会话密钥可留空自动生成）

# 3. 安装依赖
.venv\Scripts\python.exe -m pip install -r requirements.txt

# 4. 获取数据集（两期；来源与获取方式见 data/README.md）
#    2018 期：两个 SQL 导出需先导入 MySQL 暂存表（命令如下）
#    2020 期：固定版本 CSV 下载到 data/raw/ 并核验 SHA-256（ETL 直读文件，无需导入）
mysql -h 127.0.0.1 -u recruit -p --default-character-set=utf8mb4 recruitment < data/raw/job_data.sql
mysql -h 127.0.0.1 -u recruit -p --default-character-set=utf8mb4 recruitment < data/raw/key_map.sql

# 5. 按顺序导入 2018、2020；存量 2021 升级先按 docs/etl.md 备份
.venv\Scripts\python.exe -m etl.run_etl --snapshot 2018   # 约 25-30 秒
.venv\Scripts\python.exe -m etl.run_etl --snapshot 2020   # 成功后替换旧 2021；2018 保持不变

# 6. 显式初始化应用表（首次运行或升级后执行；不删除现有数据）
.venv\Scripts\python.exe -m app init-db

# 7. 启动服务，浏览器打开 http://127.0.0.1:5000
.venv\Scripts\python.exe -m app
```

首次使用没有账号：访问任意页面会跳转登录页，点"去注册"注册一个本地账号即可。

详细文档：数据管线见 [`docs/etl.md`](docs/etl.md)，页面与运行说明见 [`docs/run.md`](docs/run.md)。

## 目录结构

```
├── app.py              # 启动与 init-db 入口；导入不连接数据库
├── web/                # 应用工厂、认证路由、分析页面与请求上下文
├── auth.py             # 账号校验、密码哈希、唯一索引查重
├── captcha.py          # MySQL 一次性验证码（5 分钟有效）与 SVG
├── db.py               # 请求内复用连接、统一关闭；命令行独立连接
├── domain.py           # 学历与经验公共档位
├── queries.py          # 筛选、SQL 聚合及按需中位数统计
├── charts.py           # pyecharts 图表组装
├── etl/                # 来源、清洗、表结构、入库事务与流程编排
├── templates/          # 页面与共享图表片段
├── static/assets/      # 本地化的图表 JS
├── examples/           # 独立的候选人筛选示例
├── data/               # 数据集说明、固定映射与 raw/（不入 git）
├── docs/               # 运行、数据管线、架构与测试说明
├── tests/              # 单元测试、独立测试库集成测试与固定样例
└── openspec/           # 能力规格与历史设计存档
```

## 测试

```bash
.venv\Scripts\python.exe -m unittest discover -s tests -t . -v
```

默认运行不依赖数据库的用例；未启用的 MySQL 集成测试会明确标记为跳过。
要验证真实 SQL、注册登录、验证码并发消费和 ETL 事务，请先准备独立测试库，再设置
`RECRUIT_TEST_DB_NAME` 运行同一条命令。启用后数据库连接失败会直接报错。

测试库准备与完整命令见 [`docs/testing.md`](docs/testing.md)，结构与原理见 [`docs/architecture.md`](docs/architecture.md)。

测试库准备好后，PowerShell 中执行：

```powershell
$env:RECRUIT_TEST_DB_NAME = "recruitment_test"
.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -t . -v
Remove-Item Env:RECRUIT_TEST_DB_NAME
```

2026-10-15 验收：117 项测试全部通过、无跳过，OpenSpec 严格校验 5 项通过，实际业务库 17 次页面检查通过；覆盖原子替换与失败回滚、重导幂等、旧链接回退、技能空态及验证码并发消费。详细结果见 [运行说明](docs/run.md)。

## 数据来源与口径

- **多期快照共存**（页面默认展示 2020，页脚按当前期次动态标注来源与覆盖范围）：
  - 2018 期：[radishT/Job_Analysis](https://github.com/radishT/Job_Analysis)（GitHub 开源项目，2018 年 BOSS直聘岗位爬取，多关键词全量 IT 岗位约 3.7 万条，含技能数据）
  - 2020 期：[ccclll777/bosszp](https://github.com/ccclll777/bosszp)（固定版本，2020 年 4 月公开的 12 城市 IT 样本：原始 28,162 条、清洗后 24,841 条，无逐条发布日期、无技能明细；非全国全年全量）
  - 注意：两期采样方式和覆盖范围不同，不据此推断整体市场涨跌；旧 2021 已由 2020 替换，旧链接回退 2020
- **薪资口径**：取区间中点；带薪月数（如 `·13薪`）按月数 ÷ 12 折算为等效月薪
- **技能数据**：2018 期数据集自带的岗位技能表（含少量源数据拼写噪声，如 `angualar`，按原样保留）；技能统计按期隔离
- **本地文件**：原始数据、数据库内容、迁移备份、`.env` 和虚拟环境保留在本机；克隆仓库后按 [数据集说明](data/README.md) 获取来源文件，并按 [ETL 文档](docs/etl.md) 导入

## 开发方式

本项目采用 [OpenSpec](https://github.com/Fission-AI/OpenSpec) 规格驱动开发：
每个功能先产出 `proposal → design → specs → tasks` 四件套、验收后归档；
历史 change（数据管线+仪表盘、账号体系）的完整设计与决策记录保留在 `openspec/changes/archive/`。
