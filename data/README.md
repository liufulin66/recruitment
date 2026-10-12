# 数据集说明

## 来源

GitHub 开源项目 [radishT/Job_Analysis](https://github.com/radishT/Job_Analysis)（2018 年的招聘岗位爬取与分析项目）中的数据库导出文件。

获取方式：克隆原仓库后，把下列两个文件复制到本项目的 `data/raw/`（原仓库目录层级较深，按路径直达）：

| 复制到本项目 | 原仓库中的路径 |
| --- | --- |
| `data/raw/job_data.sql` | `result/模块一_各大省会招聘概况/数据清洗阶段-2018-4-26/清洗前_lagou.sql+job_data.sql/job_data.sql` |
| `data/raw/key_map.sql` | `result/模块二_各大编程语言的工作能力成熟度分析/数据清洗阶段-2018-4-27/清洗后_key_map.sql/key_map.sql` |

一条龙的 bash 写法（Git Bash / Linux / macOS）：

```bash
git clone --depth 1 https://github.com/radishT/Job_Analysis.git /tmp/job-analysis
mkdir -p data/raw
cp "/tmp/job-analysis/result/模块一_各大省会招聘概况/数据清洗阶段-2018-4-26/清洗前_lagou.sql+job_data.sql/job_data.sql" data/raw/
cp "/tmp/job-analysis/result/模块二_各大编程语言的工作能力成熟度分析/数据清洗阶段-2018-4-27/清洗后_key_map.sql/key_map.sql" data/raw/
ls -la data/raw   # 预期两个文件约 10MB / 37MB
```

## 文件清单

| 文件 | 内容 | 行数 |
| --- | --- | --- |
| `raw/job_data.sql` | 岗位主表（2018 年 BOSS直聘）：职位名 / 公司 / 城市 / 薪资区间 / 经验 / 学历 / 链接 | 46,353 |
| `raw/key_map.sql` | 岗位技能表：每个岗位的技能映射（Java 序列化 blob，ETL 阶段解码） | 60,033 |

## 初始化数据库（首次）

用 root（或具备建库权限的账号）执行：

```sql
CREATE DATABASE IF NOT EXISTS recruitment
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'recruit'@'localhost' IDENTIFIED BY '改成你的口令';
GRANT ALL PRIVILEGES ON recruitment.* TO 'recruit'@'localhost';
FLUSH PRIVILEGES;
```

然后把 `.env.example` 复制为 `.env` 并填入同一个口令（ETL 与应用都从这里读取凭据）。

## 导入（MySQL）

```bash
mysql -h 127.0.0.1 -u recruit -p --default-character-set=utf8mb4 recruitment < data/raw/job_data.sql
mysql -h 127.0.0.1 -u recruit -p --default-character-set=utf8mb4 recruitment < data/raw/key_map.sql
```

## 备注

- 数据为 2018 年快照；页面展示时需注明数据来源与时间范围
- `raw/` 不入 git（体积大，可按上述来源重新获取）
- 原始文件为 MySQL 5.5 时代的 Navicat 导出（utf8），导入后统一转换为 utf8mb4
