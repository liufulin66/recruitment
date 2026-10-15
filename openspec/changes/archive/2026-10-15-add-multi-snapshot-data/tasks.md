# Tasks

## 1. 数据集获取与画像基线

- [x] 1.1 获取 bosszp CSV 到 `data/raw/`（克隆 jhcoco/bosszp 复制 `全国-热门城市岗位数据.csv`），并在 `data/README.md` 增补获取路径与文件说明（维持 `raw/` 不入 git 的惯例）。验证：文件在位，README 写的路径按步骤可复现
- [x] 1.2 CSV 数据画像：行数、列清单、`job_area`/`work_year`/`education`/`job_salary` 取值清单与格式抽样、爬取时间证据（仓库提交记录/数据内容）；据此确认列映射表与期次标签（`2021` 或实测修正），行数显著低于预期（<1000）时与用户确认是否继续。验证：画像结论（含最终标签与映射表）落在 design.md 的对应决策处或任务备注
- [x] 1.3 记录改造前基线：当前 `jobs`/`job_skills` 行数与关键统计（各城市 Top3、技能词频 Top5），作为 2018 期改造后不回归的锚点。验证：基线数值记录在案（任务备注或测试夹具）

## 2. 快照数据模型

- [x] 2.1 `snapshots` 表：DDL（`id, label UNIQUE, source, period, note`）加入 ETL 建表流程，含 2018/2021 两期的元数据注册（按 label upsert，重跑不重复插入）。验证：连续跑两次注册，表内每期仍只有一行，元数据可查
- [x] 2.2 `jobs`/`job_skills` DDL 增加 `snapshot_id INT NOT NULL` 与索引（`idx_snapshot`），迁移按设计的"DROP 重建"路径：迁移步骤（DROP 两表 → 依次跑两期 ETL）写入 `docs/etl.md`。验证：新 DDL 建表成功且含新列；文档步骤照跑能通

## 3. ETL 按快照改造

- [x] 3.1 快照声明配置与 CLI：`etl/run_etl.py` 支持 `--snapshot <label>`，无参数时报错并列出可用期次；每期声明（来源形态、字段映射、是否含技能数据）落入代码内配置。验证：无参运行报错信息含期次列表；`--snapshot 2018` 正确路由到暂存表路径
- [x] 3.2 2018 期路径改造：`TRUNCATE` 改为事务内 `DELETE WHERE snapshot_id=%s` 再插入（行均带 snapshot_id）；重导 2018 期后行数与任务 1.3 基线一致，再跑一遍行数不变。验证：两次运行行数一致且等于基线（批内幂等 + 无回归）
- [x] 3.3 2021 期路径：pandas 直读 CSV → 按画像确认的映射表转统一字段 → 复用清洗函数入库（`key_word` 置空）；`normalize_experience` 补"在校/应届 → 应届生"归并规则并加单测。验证：2021 期入库成功；两期并存时重导 2021，2018 期行数不变；新规则单测通过
- [x] 3.4 ETL 校验与测试收口：`validate_sources` 按快照声明校验（声明无技能的期期不再强制技能表，主数据缺列仍终止）；更新 `tests/test_etl.py`。验证：`.venv\Scripts\python.exe -m unittest discover -s tests -t .` 全绿

## 4. 查询层期次隔离

- [x] 4.1 `parse_filters` 增加期次维度（URL 参数 `snapshot=<label>`，无参数默认取 `snapshots` 最新一期），`_where` 永远注入 `snapshot_id` 条件；`get_filter_options` 城市清单按当前期次取。验证：单测覆盖默认最新期、label 解析、未知 label 报错/回退行为
- [x] 4.2 技能查询期次隔离：`get_skill_top` 与 `get_skill_cooccurrence` 带期次过滤（共现自连接两侧都限定同一 `snapshot_id`）。验证：集成测试构造两期相同 `source_map_id` 的技能数据，断言各期词频互不累计；2021 期技能查询返回空列表
- [x] 4.3 查询测试收口：更新 `tests/test_queries.py` 既有用例到四维筛选语义。验证：unittest 全绿

## 5. Web 层期次支持

- [x] 5.1 路由与全局注入：全部页面经 `parse_filters` 获得期次参数；`inject_globals` 注入当前期次元数据（来源/时间范围/覆盖说明）与期次选项；`config.py` 移除 `DATA_SOURCE`/`DATA_PERIOD`（`SALARY_NOTE` 保留）。验证：不带参数访问任一页默认渲染最新期；带 `?snapshot=2018` 时统计与页脚均按 2018 期
- [x] 5.2 模板改造：筛选条加期次下拉（导航保留筛选参数）；页脚改用动态元数据；技能页对无技能数据的期次显示"本期数据不含技能信息"降级提示。验证：2018 期技能页图表正常、2021 期显示降级提示且无报错
- [x] 5.3 Web 测试收口：更新 `tests/test_app.py` 中页脚/筛选相关断言，补期次切换用例。验证：unittest 全绿

## 6. 端到端集成验证

- [x] 6.1 全链路演练：DROP 重建三表 → 依次跑两期 ETL → 全部测试 → 手动过五个页面核对：默认最新期、期次切换后图表与页脚联动、城市选项随期次变化、技能页降级、导航保留筛选。验证：核对清单全过，测试全绿
- [x] 6.2 文档一致性：更新 `README.md` 数据来源段落与 `docs/etl.md`、`docs/run.md` 中涉及数据形态/运行命令的描述，按文档命令实测一遍。验证：文档所述与实际行为一致，命令照跑能通

## Workflow follow-up

- 实现与验证全部完成后，归档 change（`/opsx:archive`），快照维度规格并入主规格
- 趋势对比页作为后续独立 change 立项（探索阶段已明确出范围）
