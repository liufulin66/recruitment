# ETL 使用说明（数据准备阶段）

把 `data/raw/` 的数据集导入 MySQL 暂存表，再清洗入库到 `jobs` / `job_skills` 两张表。

## 前置条件

- MySQL 服务已启动；`recruitment` 库与账号已创建（见 `data/README.md`）
- 依赖已安装：`.venv\Scripts\python.exe -m pip install -r requirements.txt`
- 数据库口令已配置：复制 `.env.example` 为 `.env` 并填写（`.env` 不入 git，只为本地运行供口令）

## 1. 导入原始数据（一次性；重导入会先删表再建）

```bash
mysql -h 127.0.0.1 -u recruit -p --default-character-set=utf8mb4 recruitment < data/raw/job_data.sql
mysql -h 127.0.0.1 -u recruit -p --default-character-set=utf8mb4 recruitment < data/raw/key_map.sql
```

导完可顺手统一字符集：

```sql
ALTER TABLE job_data CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE key_map  CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

## 2. 运行清洗入库（项目根目录）

```bash
.venv\Scripts\python.exe -m etl.run_etl
```

预期输出（数值以实际为准）：

```
=== ETL 完成 ===
读取岗位行数: 46,353
去重移除: ...
薪资缺失: 0
技能映射数: 60,033
解码技能总条数: ...
空技能映射: ...
入库: jobs ... 行 / job_skills ... 行
```

**幂等**：再跑一遍，行数与上遍一致（覆盖式写入）。

## 3. 跑测试

```bash
.venv\Scripts\python.exe -m unittest discover -s tests -t . -v
```

（`test_skills` 里的金样例需要 MySQL 暂存表在位；不可用时自动跳过。）
