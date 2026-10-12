# 数据集说明

## 来源

GitHub 开源项目 [radishT/Job_Analysis](https://github.com/radishT/Job_Analysis)（2018 年的招聘岗位爬取与分析项目）中的数据库导出文件。

## 文件清单

| 文件 | 内容 | 行数 |
| --- | --- | --- |
| `raw/job_data.sql` | 岗位主表（2018 年 BOSS直聘）：职位名 / 公司 / 城市 / 薪资区间 / 经验 / 学历 / 链接 | 46,353 |
| `raw/key_map.sql` | 岗位技能表：每个岗位的技能映射（Java 序列化 blob，ETL 阶段解码） | 60,033 |

## 导入（MySQL）

```bash
mysql -h 127.0.0.1 -u recruit -p --default-character-set=utf8mb4 recruitment < data/raw/job_data.sql
mysql -h 127.0.0.1 -u recruit -p --default-character-set=utf8mb4 recruitment < data/raw/key_map.sql
```

## 备注

- 数据为 2018 年快照；页面展示时需注明数据来源与时间范围
- `raw/` 不入 git（体积大，可按上述来源重新获取）
- 原始文件为 MySQL 5.5 时代的 Navicat 导出（utf8），导入后统一转换为 utf8mb4
