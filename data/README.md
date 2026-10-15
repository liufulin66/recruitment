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

### 第二期（2020 年 4 月公开快照）

来源为 [ccclll777/bosszp](https://github.com/ccclll777/bosszp)，固定提交 `2dcc08a8ff0c79a0afda3d150c1a9618ebe6e390`（文件提交于 2020-04-21）。这是已由作者预处理的 **12 城市 IT 岗位样本**，无逐条发布日期、无技能明细；公开时间不能代表全年采集范围，也不代表全国全量。

```powershell
New-Item -ItemType Directory -Force data/raw | Out-Null
Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/ccclll777/bosszp/2dcc08a8ff0c79a0afda3d150c1a9618ebe6e390/job_data_clean_price.csv' -OutFile 'data/raw/bosszp_2020_job_data_clean_price.csv'
Get-FileHash data/raw/bosszp_2020_job_data_clean_price.csv -Algorithm SHA256
```

文件为 UTF-8 BOM CSV，3,515,794 字节，28,162 条记录。SHA-256：`16c3f579564292e76e58f7cc22c9e98e18ec89421da63f9cc5954b7b4a737bdc`。该文件无需手动导入 MySQL，ETL 直接读取；成功导入 2020 时在同一事务内移除旧 2021 快照，详见 `docs/etl.md`。

原始城市分布：北京 3370、深圳 3161、上海 3112、杭州 3097、广州 2577、南京 2298、成都 2196、武汉 2100、西安 1784、苏州 1689、天津 1472、重庆 1306。

搜索类别共 10 类：算法工程师、人工智能、Java、PHP、Web前端、Android、iOS、数据分析、数据挖掘、数据架构师；类别不作为技能。学历缺失 105 条、经验缺失 49 条，缺失不补造为“不限”。`job_company_tag` 为混合标签，不拆解为公司规模或行业。

项目共享清洗流程实测：28,162 条读取、移除 3,321 条重复、保留 **24,841 条岗位**；有效薪资 24,841 条、缺失 0 条，技能 0 条。薪资上下限为元/月，中点作为平均薪资；不采用来源的 `job_ave_salary`，不猜测薪月数。清洗后平均月薪约 15,270.55 元，最低端点 1,000 元、最高端点 260,000 元，均为样本原值。

清洗后城市：北京 2846、上海 2704、深圳 2668、杭州 2564、广州 2324、南京 2024、成都 2023、武汉 1915、西安 1630、苏州 1565、天津 1355、重庆 1223；12 城市均有省份映射。清洗后学历缺失 103 条、经验缺失 40 条，非空枚举均可归入现有档位。公司名沿用共享清洗规则，不额外去除首尾空白；因此结果比探索时把公司也 trim 的预估多 1 条。

2026-10-15 已在本地业务库完成替换及重导验收：2018 的 36,790 条岗位、577,373 条技能的完整内容 SHA-256 均与迁移前一致，账号仍为 36 个；2020 为 24,841 条岗位、0 技能，2021 元数据及派生记录无残留。重复导入后 2020 业务内容校验值不变。备份与机器可读验收记录保存在 `raw/2020-migration/`（不入 Git），恢复方式见 `docs/etl.md`。

## 文件清单

| 文件 | 内容 | 行数 |
| --- | --- | --- |
| `raw/job_data.sql` | 2018 期岗位主表（BOSS直聘）：职位名 / 公司 / 城市 / 薪资区间 / 经验 / 学历 / 链接 | 46,353 |
| `raw/key_map.sql` | 2018 期岗位技能表：每个岗位的技能映射（Java 序列化 blob，ETL 阶段解码） | 60,033 |
| `raw/bosszp_2020_job_data_clean_price.csv` | 2020 年 4 月公开快照：12 城市 IT 岗位、元/月数值薪资上下限，无技能明细 | 28,162 |

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

- 数据为多期快照共存（2018 IT 岗位 / 2020 年 4 月公开的 12 城市 IT 样本，采样方式不同）；页面按当前期次注明来源与覆盖范围，不据此推断市场整体涨跌
- `raw/` 不入 git（体积大，可按上述来源重新获取）
- 2018 期原始文件为 MySQL 5.5 时代的 Navicat 导出（utf8），导入后统一转换为 utf8mb4
