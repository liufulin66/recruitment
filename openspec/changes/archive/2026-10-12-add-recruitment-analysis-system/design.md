# Design

## Context

- 项目现状：`D:\code\Py-Recruitment` 近乎空项目——仅有 `main.py`（候选人筛选控制台演示，保留不动）与健康可用的 `.venv`（Python 3.12.10，已装 5 个依赖，见 `requirements.txt`）
- 运行环境：Windows 11 单机；MySQL 8.0 服务已就绪（`recruitment` 库 + 专用账号 `recruit`）；git 仓库已初始化
- 已知环境隐患：PyCharm 模块解释器（`.idea/Py-Recruitment.iml`）仍指向 LibreOffice 的 `python.exe`，实施前需切到 `.venv`
- 数据集（已定）：GitHub 开源项目 radishT/Job_Analysis 的数据库导出——2018 年 BOSS直聘岗位主表 46,353 条 + 岗位技能表 60,033 条（原始文件在 `data/raw/`，不入 git）
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
| 分词 | jieba（备用） | 技能数据已是结构化技能词，当前不在关键路径；如后续对职位名/描述做文本分析再启用 |

### D3 数据库表结构（原始层 + 清洗层）

- 原始层（只读暂存，导入自数据集 SQL 导出）：`job_data`（岗位主表：title/company/city/salary/experience/education/url/key_word）、`key_map`（岗位技能表：key_word + Java 序列化技能映射 blob）
- 清洗层 `jobs` 表（utf8mb4）：`id`、`job_name`、`company`、`city`、`salary_min`、`salary_max`、`salary_avg`（三者可为 NULL=缺失）、`salary_raw`（原始文本留证）、`edu`、`exp`、`key_word`；索引 `city`、`edu`、`exp`
- 技能表 `job_skills`：`key_word` + 解码后的技能词集合（供词频与共现）
- **Why**：分析场景是"按维度过滤 + 聚合"，主表宽表最直观；原始层保留"可复现 + 留证"；技能数据与主表无关联键，独立成表
- **Alternatives**：城市/公司规范化维表——对本规模过度设计，被否
- 空值策略：薪资缺失置 NULL；参与计数类统计、不参与薪资类统计（对齐 `recruitment-analytics` 口径）

### D4 筛选联动：URL 参数 + 服务端重渲染

筛选控件为普通表单（GET），条件编码进 URL（如 `?city=杭州&edu=本科`）；Flask 路由读取参数 → 拼 WHERE → SQL 聚合 → pyecharts 重新渲染；页面导航链接携带当前参数。

- **Why**：不写 JS 即获得联动；URL 可刷新、可收藏、可复现
- **Alternatives**：AJAX 无刷新联动——留作后续增强，不在本次范围

### D5 薪资解析口径

支持形态与折算规则以 `specs/data-pipeline` 场景为准（覆盖数据实态如 `15k-25k` 小写 k）；实现为纯函数 + 用例表（先写测试用例集，再实现解析）。

- **Why**：薪资是所有分析的地基、最易出错，必须以用例固化
- **Alternatives**：只解析 `x-yK` 主流形态——覆盖率低，被否

### D6 技能分析链路

技能数据来自数据集自带的岗位技能表（Java 序列化 HashMap，存技能词→计数）：ETL 以"hex → 字节 → 扫描 TC_STRING"方式解码为技能词集合；词频与共现基于解码结果统计；噪声词（`without`、`prepare` 等）用停用词表过滤，英文大小写归并。停用词表独立文件维护、可增补。

- **Why**：数据集已把技能提取为结构化词，重新分词反而引入噪声；解码一次、两处（词频/共现）复用
- **Alternatives**：对职位名称做 jieba 分词生成"岗位词云"——后续增强；TF-IDF / TextRank——不做

### D7 页面与路由

5 个页面各一条路由（`/`、`/salary`、`/geo`、`/skills`、`/company`），共享同一套筛选参数解析与查询函数；每页由若干"查询 + 图表组装"构成。

- **Why**：横切逻辑（筛选解析、来源标注）只写一次
- **Alternatives**：单页长滚动——导航清晰性差，被否

## Risks / Trade-offs

- [数据集字段不齐 / 脏数据] → 已核字段与样例值（经验字段混入学历如 ` 1-3年本科`，归一阶段拆分）；公司规模/行业按条件呈现；必填字段缺失即报错
- [技能表为 Java 序列化 blob，需自制解码] → 以"hex→字节→扫描 TC_STRING"解码，并用已知样例（web/java 岗位的技能词）人工对照校验
- [薪资解析边界形态多] → 先写用例表（面议 / 13薪 / 千 / 万 / 年薪 / 小写 k）再实现；解析失败按口径置缺失
- [pyecharts 地图资源依赖] → 地图图表的 JS 资源在实现时验证（必要时本地化），依赖版本锁定到 requirements
- [中文编码全链路] → 库/表/连接/响应全 utf8mb4（原始表导入后先做字符集转换），SQL 导出文件以显式字符集导入
- [Windows 控制台中文输出] → 沿用 `main.py` 中 `sys.stdout.reconfigure(encoding="utf-8")` 的既有经验

## Migration Plan

全新系统、无数据迁移。落地顺序：环境准备（已完成：MySQL 建库建账号、`.venv` 装依赖、`git init`；待办：IDE 解释器切换）→ 数据集导入暂存 → ETL → 查询层 → 逐页实现 → 联调验收。回滚策略：本阶段全部为新增文件与新增数据库表，删除即可回退。

## Open Questions

- 无（数据集已定：radishT/Job_Analysis 数据库导出；公司规模/行业维度按 specs 条件性规则呈现"数据不包含该维度"）
