# Design

## Context

现状是单快照架构：`etl/run_etl.py` 从暂存表 `job_data`/`key_map`（2018 SQL 导出）读数 → 清洗 → `TRUNCATE jobs/job_skills` 整库覆盖。查询层（`queries.py`）全部聚合无期次概念；页脚来源标注是 `config.py` 里两个全局字符串。动机见 proposal.md。

本设计的目标数据集：jhcoco/bosszp 仓库自带的 `全国-热门城市岗位数据.csv`（2021-01-12 随仓库首次提交，此后未更新）。**画像实测（2026-10-15）**：130 行、10 列齐全、格式与现有清洗函数完全兼容（薪资 `25-50K·15薪`、城市 `北京·海淀区·上地`，经验/学历取值全部命中现有档位）；实测取值中未出现 `经验在校/应届`（归并规则保留为防御性补丁）；无技能列；样本为 34 家大厂的技术岗（本科 120/130）。行数远低于预期，已经用户确认继续——本期价值在于验证多期架构，而非 2021 年的分析结论。

## Goals / Non-Goals

**Goals:**

- 多期数据共存：任一时刻库里可同时保有 2018 期与 2021 期，各自完整可查
- 按快照摄入与幂等：重导某期不动他期
- 统计永不混期：所有查询天然带期次约束，默认最新期
- 加第三期只需：声明一份快照配置 + 放一个数据文件，零 schema 变更

**Non-Goals:**

- 跨期趋势对比图表（独立后续 change）
- 接入 2024/2025 更新数据集（多期架构建成后是纯数据活）
- `jobs` 与 `job_skills` 行级关联（现模型两表本就松耦合，借 `key_word` 语境关联，不借本次重构）
- 期次权限/多用户隔离（本地单用户项目）

## Decisions

### D1: 快照维度用元数据表建模，不用裸标签列

`jobs`/`job_skills` 各加 `snapshot_id INT NOT NULL`，指向新表 `snapshots`（`id, label UNIQUE, source, period, note`）。备选是直接在两表放 VARCHAR 标签列——被否：页脚动态标注需要"来源/时间范围/覆盖说明"这些元数据，裸标签放不下；标签散落两表难演进。元数据表让 web-dashboard 的"数据来源标注"直接查表，加第三期零变更。

"最新期"判定取 `snapshots.id` 最大（快照按时间先后登记，id 即序）。备选显式排序列被否：单用户本地项目，插入序就是时间序，不值得多一列维护。

### D2: `job_skills` 的岗位标识只在快照内唯一——技能统计全程带期次

`source_map_id` 指向各数据集内部的技能映射 id，两期必然撞号（各自从 1 起）。`job_skills` 加 `snapshot_id` 后：词频 `COUNT(DISTINCT source_map_id)` 加 `WHERE snapshot_id=?`；共现自连接 `ON a.source_map_id = b.source_map_id AND a.snapshot_id = b.snapshot_id`。备选"建全局唯一岗位表再把技能挂上去"被否：现有模型 `jobs`/`job_skills` 本无行级外键，为技能隔离重构全链路不成比例。

### D3: ETL 按快照运行；摄入按来源分路，清洗共享

- 入口：`python -m etl.run_etl --snapshot <label>`；无参数时报错列出可用期次（不默认跑全部，防误触全量重导）
- 每期一份快照声明（代码内配置字典）：label、来源标注、覆盖说明、数据形态（2018=暂存表+技能表；2021=CSV 路径+列映射+无技能）
- 2018 路径：暂存表读取 + Java blob 解码，原样保留
- 2021 路径：pandas 直读 CSV（不经 MySQL 暂存——CSV 已是干净表格，入库暂存是无谓中转）→ 列映射到统一字段 → 进同一套清洗函数
- 幂等实现：`TRUNCATE` 改为事务内 `DELETE FROM jobs WHERE snapshot_id=%s`（同量级毫秒级，性能无虞）再插入

备选"所有来源先统一入暂存表再 ETL"被否：为 CSV 强加一层 MySQL 中转，只增加导入步骤没有收益。

### D4: 存量迁移用"重建"而非"加列回填"

`jobs`/`job_skills` 是纯派生数据，源头（暂存表 + CSV）都在本地。迁移 = 建 `snapshots` 表 → 两张目标表 DROP 重建（DDL 带 `snapshot_id`）→ 依次跑两期 ETL。备选 `ALTER TABLE ADD COLUMN` + UPDATE 回填被否：多三步且引入"列先 NULL 后补"的中间态；本地库重建只要几十秒。`users` 表（auth）与本次无关，不动。

### D5: 查询层——期次在 `_where` 之前解析，默认最新期

`parse_filters` 增加期次参数（URL 用 `snapshot=<label>`）；解析顺序：有参数→label 查 `snapshots` 得 id；无参数→取 id 最大者。**期次条件永远注入 WHERE**（即使默认），从根上杜绝混期统计。`get_filter_options` 的城市清单按当前期次取（两期城市集合不同）。总览的"最高频技能"对无技能期次返回空。

### D6: 2021 适配层——映射表 + 一条经验归并规则

列映射：`job_name→title 语义`、`com_name→company`、`job_area→city`、`job_salary→salary`、`work_year→experience`、`education→education`；`key_word` 置空（CSV 无搜索关键词列）。清洗函数全部复用，仅 `normalize_experience` 补一条：前缀"在校/应届"→"应届生"档（现有正则匹配不到该写法；画像实测该数据集未出现此取值，规则作为防御性补丁保留）。薪资解析零改动。

### D7: Web 层——期次进筛选条，页脚动态化

- 全部路由经 `parse_filters` 自然获得期次参数；筛选条模板加期次下拉（选项来自 `snapshots` 表）
- `inject_globals` 注入当前期次元数据（source/period/note），页脚模板改用之；`config.py` 的 `DATA_SOURCE`/`DATA_PERIOD` 退役删除（`SALARY_NOTE` 保留——折算口径与期次无关）
- 技能页对无技能期次显示"本期数据不含技能信息"提示（复用现有空态容错机制，`get_skill_top` 返回空即触发）

### D8: 数据集获取与画像先行

`data/README.md` 增补 bosszp CSV 获取路径（克隆仓库复制文件，`raw/` 维持不入 git）。数据画像已完成（2026-10-15）：130 行、映射表确认无需修正、爬取时间证据为 2021-01-12 首次提交——**期次标签定 `2021`**；行数低于预期已经用户确认继续。

### D9: 测试策略

- 纯函数单测：`normalize_experience` 新规则、期次解析（默认最新期/label 解析）
- ETL 集成：两期先后入库后行数断言（2018 期金样例行数与改造前一致）、重导 2021 后 2018 行数不变
- 查询隔离：构造两期同岗位组合，断言各期统计互不串号；无技能期次技能统计返回空

## Risks / Trade-offs

- [CSV 实际取值与 README 描述有漂移] → 任务 1 画像先行，映射按实测定；必填字段校验兜底报错
- [两期总体不同质（全 IT 岗位 vs 数据类岗位），未来误读对比结论] → 快照元数据强制带覆盖范围说明并上页脚；趋势对比明确出范围
- [2021 期技能页空，观感下降] → 规格已定义降级提示文案；属数据集固有限制，页脚注明
- [DELETE 代替 TRUNCATE 的写放大] → 单期 5 万行量级，事务内 DELETE 实测毫秒级，忽略
- [快照声明硬编码在 ETL 配置] → 第三期到来时改一处配置；在本地项目规模下可接受，不引入配置文件机制

## Migration Plan

1. 建 `snapshots` 表 → 注册 2018、2021 两期元数据
2. DROP 并按新 DDL 重建 `jobs`/`job_skills`
3. 跑 2018 期 ETL → 行数与改造前基线一致（**基线 2026-10-15 实测：jobs 36,790 行 / job_skills 577,373 行**）
4. 跑 2021 期 ETL → 两期并存
5. 验证页面：默认最新期渲染、期次切换、技能页 2021 降级、页脚动态标注

回滚：git revert 代码；数据层面 DROP 三表重跑旧 ETL 即可完整还原（`users` 表不受影响）。
