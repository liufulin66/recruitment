# Design

## Context

- 项目现状：`D:\code\Py-Recruitment` 近乎空项目——仅有 `main.py`（候选人筛选控制台演示，保留不动）与健康可用的 `.venv`（Python 3.12.10，无第三方依赖）
- 运行环境：Windows 11 单机；本机尚无 MySQL 服务；目录尚未初始化 git
- 已知环境隐患：PyCharm 模块解释器（`.idea/Py-Recruitment.iml`）仍指向 LibreOffice 的 `python.exe`，实施前需切到 `.venv`
- 约束：全部数据与页面本地运行；中文数据需全链路 UTF-8（库/表 utf8mb4）；协作方式为"先讲原理、方案确认后再实现"
- 动机与范围见 `proposal.md`；功能契约见 `specs/`（本文不重复）

## Goals / Non-Goals

**Goals:**

- 离线数据准备与在线展示分离，清洗入库可重复执行
- 分析口径集中定义、所有页面复用（避免每张图各写一套逻辑）
- 实现朴素、可读、便于逐段讲解（教学优先于抽象）

**Non-Goals:**

- 不做部署 / 多用户 / 并发性能优化（本地单用户演示）
- 不做爬虫、时间趋势、薪资预测、登录权限（见 proposal 范围）
- Web 请求不触发原始数据清洗（清洗只发生在离线阶段）
- 不引入 ORM，不引入前端工程化工具链

## Decisions

### D1 离线 ETL 与在线服务分离

清洗入库是离线过程（数据更新时重跑）；Web 服务只读数据库。

- **Why**：启动快、边界清晰；数据库成为唯一数据源，筛选查询全部走 SQL
- **Alternatives**：Web 启动时现读 CSV——省一步但没有存储层、每次启动重解析，被否

### D2 技术栈

| 环节 | 选择 | 理由（备选） |
| --- | --- | --- |
| 清洗 | pandas | 向量化表操作直观；备选：标准库 csv + 循环（分组聚合要手写大量循环） |
| 存储 | MySQL（用户选定） | 备选 SQLite 更轻，但 MySQL 为用户明确选择（存储层完整性 / 学习目标） |
| 查询 | PyMySQL + 手写 SQL | 聚合查询是学习重点，SQL 透明可控；备选 SQLAlchemy ORM（多一层抽象、藏掉 SQL） |
| Web | Flask | 微框架、路由直观；备选 Django（过重）、FastAPI（异步概念多） |
| 图表 | pyecharts | 服务端用 Python 生成 ECharts 配置，不写 JS；备选原生 ECharts + JSON 接口（工作量大一截） |
| 分词 | jieba | 中文分词事实标准；备选按空格切（中文不可行） |

### D3 数据库表结构（单宽表）

`jobs` 表（utf8mb4）：`id`、`job_name`、`company`、`city`、`salary_min`、`salary_max`、`salary_avg`（三者可为 NULL=缺失）、`salary_raw`（原始文本留证）、`edu`、`exp`、`company_size`（可空）、`industry`（可空）、`skills_text`（技能/描述原文）。

- 索引：`city`、`edu`、`exp`（筛选与分组用）；演示规模不建更多
- **Why**：分析场景是"按维度过滤 + 聚合"，单宽表最直观、SQL 简单
- **Alternatives**：城市/公司规范化维表——对本规模过度设计，被否
- 空值策略：薪资缺失置 NULL；参与计数类统计、不参与薪资类统计（对齐 `recruitment-analytics` 口径）

### D4 筛选联动：URL 参数 + 服务端重渲染

筛选控件为普通表单（GET），条件编码进 URL（如 `?city=杭州&edu=本科`）；Flask 路由读取参数 → 拼 WHERE → SQL 聚合 → pyecharts 重新渲染；页面导航链接携带当前参数。

- **Why**：不写 JS 即获得联动；URL 可刷新、可收藏、可复现
- **Alternatives**：AJAX 无刷新联动——留作后续增强，不在本次范围

### D5 薪资解析口径

支持形态与折算规则以 `specs/data-pipeline` 场景为准；实现为纯函数 + 用例表（先写测试用例集，再实现解析）。

- **Why**：薪资是所有分析的地基、最易出错，必须以用例固化
- **Alternatives**：只解析 `x-yK` 主流形态——覆盖率低，被否

### D6 技能分析链路

清洗时保留原文 → 分析时 jieba 分词（含停用词表、英文大小写归并）→ 词频 Top-N 与两两共现矩阵。停用词表以独立文件维护、可增补。

- **Why**：分词结果同时影响词云与共现，集中一处实现
- **Alternatives**：TF-IDF / TextRank 关键词算法——后续增强，本次不做

### D7 页面与路由

5 个页面各一条路由（`/`、`/salary`、`/geo`、`/skills`、`/company`），共享同一套筛选参数解析与查询函数；每页由若干"查询 + 图表组装"构成。

- **Why**：横切逻辑（筛选解析、来源标注）只写一次
- **Alternatives**：单页长滚动——导航清晰性差，被否

## Risks / Trade-offs

- [数据集字段不齐 / 脏数据] → 实施第一步先验证所选数据集的字段与样例值；公司规模/行业按条件呈现；必填字段缺失即报错
- [薪资解析边界形态多] → 先写用例表（面议 / 13薪 / 千 / 万 / 年薪）再实现；解析失败按口径置缺失
- [本机 MySQL 环境搭建受阻] → 实施第一步提供逐步安装指引（含 utf8mb4、建库脚本）；若最终不可用，与用户重新确认替代方案，不在本设计内隐式切换
- [pyecharts 地图资源依赖] → 地图图表的 JS 资源在实现时验证（必要时本地化），依赖版本锁定到 requirements
- [中文编码全链路] → CSV 显式 encoding、库/表/连接 utf8mb4、HTTP 响应 UTF-8，均列入实施任务
- [Windows 控制台中文输出] → 沿用 `main.py` 中 `sys.stdout.reconfigure(encoding="utf-8")` 的既有经验

## Migration Plan

全新系统、无数据迁移。落地顺序：环境准备（MySQL 安装建库、`.venv` 装依赖、`git init`、IDE 解释器切换）→ ETL → 查询层 → 逐页实现 → 联调验收。回滚策略：本阶段全部为新增文件与新增数据库，删除即可回退。

## Open Questions

- 具体数据集：实施第一步从候选池按字段覆盖度选定并验证样例值；规格已将公司规模/行业设为条件性维度，该选择不影响架构与规格
