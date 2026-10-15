# 测试与数据隔离

## 默认：无需数据库的单元测试

在项目根目录执行：

```powershell
.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -t . -v
```

未设置 `RECRUIT_TEST_DB_NAME` 时，仅运行不依赖 MySQL 的测试，集成测试会明确标记为跳过。应用导入、认证页面渲染、连接生命周期、清洗和图表边界等都有单元测试。

## 启用 MySQL 集成测试

必须使用可丢弃的独立测试库。测试会在每个用例前后清空这个库中的 `users`、`captcha_challenges`、`jobs`、`job_skills`、`snapshots` 五张测试表，并重建固定的小样例；不要向测试库存放需要保留的数据。同一个测试库不要同时运行多套测试。

先用 MySQL 管理员账号执行一次（无需手动建表）：

```sql
CREATE DATABASE IF NOT EXISTS recruitment_test
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

GRANT ALL PRIVILEGES ON recruitment_test.* TO 'recruit'@'localhost';
```

然后在 PowerShell 中执行：

```powershell
$env:RECRUIT_TEST_DB_NAME = "recruitment_test"
.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -t . -v
Remove-Item Env:RECRUIT_TEST_DB_NAME
```

测试读取上述**进程环境变量**，不会从 `.env` 自动启用。测试库名称须以 `_test` 结尾，或在 `_test` 后带下划线及运行标识（例如 `recruitment_test_ci123`），且不能等于应用数据库名称。测试程序只创建表，不自行创建数据库。

默认沿用应用的连接地址与账号。需要单独的测试服务或账号时，在当前终端设置 `RECRUIT_TEST_DB_HOST`、`RECRUIT_TEST_DB_PORT`、`RECRUIT_TEST_DB_USER`、`RECRUIT_TEST_DB_PASSWORD`；不要在聊天或提交记录中放入密码。

显式设置测试库后，连接失败、缺少权限或表结构错误会直接使测试失败，不会自动跳过。持续集成也应设置测试库变量。

## 验证范围

- 单元测试：清洗与枚举、数值月薪单位和无效区间、CSV 原始缺列校验、技能 blob 固定样例、直方图边界、应用工厂、认证页不查询分析表、请求复用与异常关闭、账号写入异常。
- MySQL 集成测试：五个分析页面、注册登录与会话、多期隔离、SQL 聚合与明细统计一致性、2020 替换 2021 的原子事务及故障回滚、重跑幂等、默认期次与旧链接回退。普通样例为 2018/2020，历史替换用例单独构造 2021；无需下载完整公开 CSV 即可运行测试。
- 验证码专项：5 分钟过期、刷新撤销、错误答案也消费、旧 Cookie 重放、两个应用实例共享，以及两个并发请求只有一个能消费成功。
