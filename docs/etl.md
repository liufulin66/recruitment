# ETL 使用说明（数据准备阶段）

把 `data/raw/` 的数据集清洗入库到 `jobs` / `job_skills`：2018 期是 SQL 暂存表；2020 期是固定版本 CSV（来源、下载命令和 SHA-256 见 `data/README.md`）。2020 表示 2020 年 4 月公开的 12 城市 IT 岗位样本，无逐条发布日期和技能明细。

## 前置条件

- MySQL 服务已启动；`recruitment` 库与账号已创建（见 `data/README.md`）
- 依赖已安装：`.venv\Scripts\python.exe -m pip install -r requirements.txt`
- 数据库口令已配置：复制 `.env.example` 为 `.env` 并填写（`.env` 不入 git，只为本地运行供口令）

## 1. 导入 2018 期原始数据（一次性；重导入会先删表再建）

```bash
mysql -h 127.0.0.1 -u recruit -p --default-character-set=utf8mb4 recruitment < data/raw/job_data.sql
mysql -h 127.0.0.1 -u recruit -p --default-character-set=utf8mb4 recruitment < data/raw/key_map.sql
```

导完可顺手统一字符集：

```sql
ALTER TABLE job_data CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE key_map  CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

2020 的 CSV 无需导入暂存表，ETL 直接读 `data/raw/bosszp_2020_job_data_clean_price.csv`。先核验 SHA-256 为 `16c3f579564292e76e58f7cc22c9e98e18ec89421da63f9cc5954b7b4a737bdc`。原始数值上下限按元/月转换，中点作为平均薪资；缺失、非有限数、负数或倒置区间整组记为薪资缺失，岗位保留。混合公司标签不拆解，搜索类别不推断为技能。

## 2. 从 2018/2021 升级至 2018/2020

本次不重建表、不清空整库。先完成隔离测试库验证，并确认业务库已登记 2018/2021；已有 2018 的登记 id 应小于本次新建的 2020。若还有未预期的快照，先核查其来源，不删除无关期次来强行满足默认展示要求。

迁移前按快照范围导出 2021 的 `snapshots`、`jobs`、`job_skills`，保留字段名、主键和内容；记录 2018 元数据及两张派生表的行数和内容 SHA-256、账号数量。保留旧 CSV 与旧来源配置，备份放在不入 Git 的 `data/raw/2020-migration/`。本次迁移产物：

- `baseline.json`：迁移前快照信息、2018 岗位/技能数量和内容校验值、账号数量。
- `snapshot-2021.json`：2021 三表字段名与原始记录。
- `restore-2021.sql`：受控事务恢复 2021 并移除 2020，仅操作这两个标签的派生记录；已在独立测试库实际恢复验证。
- `legacy-2021-config.json`：旧 2021 来源配置；原始 `全国-热门城市岗位数据.csv` 继续保留。

读取、来源字段校验、清洗及非空检查全部通过后，才执行数据替换事务：写入 2020 元数据和岗位/技能 → 删除 2021 岗位/技能和元数据 → 一次提交。任一步异常整体回滚；建表 DDL 在此前执行。替代关系由 `sources.py` 的 `replaces: "2021"` 声明控制，仅允许 2020→2021，命令不接受任意删除标签。

成功后核验只提供 2018/2020，2018 内容校验值和账号数量不变、2021 无残留，重复运行 2020 幂等。默认展示 2020，旧 `snapshot=2021` 链接回退 2020。新安装按 2018、2020 的顺序导入，已有 2018 重导不会新增登记 id。

回滚时先停服务，恢复本变更前的来源配置（可用 `legacy-2021-config.json` 恢复旧配置项并移除 2020 配置）；本次扩展兼容普通旧来源，或使用保存的原版本。然后在 Git Bash / CMD 中执行（口令交互输入）：

```bash
mysql -h 127.0.0.1 -u recruit -p --default-character-set=utf8mb4 recruitment < data/raw/2020-migration/restore-2021.sql
```

PowerShell 可使用 `cmd /c` 执行以上带 `<` 的命令。恢复后核验 2018/2021 标签、2018 内容校验值和账号数量；默认应为 2021，再启动服务。恢复文件保留原 id，使用前确认它属于当前库的本次迁移；不重新导入暂存 SQL、不重建整库。备份只保存在当前机器，部署到其他机器前须另外生成对应备份。

更早的单快照表没有 `snapshot_id`，不能直接执行本节迁移；先按原多期迁移方案升级表结构，再接入本次替换。

## 3. 运行清洗入库（按快照；项目根目录）

```bash
.venv\Scripts\python.exe -m etl.run_etl --snapshot 2018   # 2018 期：读暂存表 + Java blob 技能解码
.venv\Scripts\python.exe -m etl.run_etl --snapshot 2020   # 直读 CSV，成功时原子替换旧 2021
```

预期输出（数值以实际为准）：

```
=== ETL 完成（快照 2018） ===
读取岗位行数: 46,353
去重移除: ...
薪资缺失: 0
技能映射数: 60,033
解码技能总条数: ...
空技能映射: ...
入库: jobs ... 行 / job_skills ... 行
```

2020 实测：读取 28,162 条、移除重复 3,321 条、入库 24,841 条岗位、0 条技能，薪资缺失 0；清洗后学历缺失 103、经验缺失 40，12 城市全部有省份映射。详见 `data/sample_values.md`。

**幂等（批内）**：普通重导只替换本期；2020 还会按声明移除被替代的 2021，2018 不变。2021 已不存在时重导 2020 正常完成，不累积重复。

## 4. 跑测试

```bash
.venv\Scripts\python.exe -m unittest discover -s tests -t . -v
```

技能解码金样例已固化在 tests/fixtures/，无需数据库。MySQL 集成测试必须显式指定独立测试库，准备方式见 [testing.md](testing.md)。

## 模块分工

`run_etl.py` 负责入口与编排；快照声明和来源适配在 `sources.py`；逐列清洗在 `transforms.py`；表结构在 `schema.py`；批量写入与快照替换事务在 `repository.py`。校验成功后才更新快照元信息和数据，写入失败整体回滚。
