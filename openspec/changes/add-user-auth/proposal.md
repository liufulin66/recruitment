# Proposal

## Why

仪表盘当前人人可看，没有用户体系。需要补上"本地账号"闭环：**必须登录才能访问数据页面**，没有账号可在登录页现场注册——为演示与答辩补齐用户侧形态。

## What Changes

- 新增 `user-auth` 能力：注册 / 登录 / 登出 / 会话保持 / 访问保护
  - 未登录访问任何数据页面 → 重定向登录页；登录成功后跳回原目标页
  - 注册成功自动登录；用户名去空格、不区分大小写；密码至少 6 位、仅存哈希
  - 登录页提供"记住我"：勾选 7 天内免登录，不勾关浏览器即退
- 新增 `auth.py`：`users` 表（应用启动时自动创建）、密码哈希（`werkzeug.security`，零新依赖）、会话辅助
- `app.py` 增加统一访问门卫；`templates/base.html` 导航显示当前用户与"退出"；新增登录页、注册页（沿用现有视觉风格）
- 会话签名密钥 `RECRUIT_SECRET_KEY` 进 `.env`（与数据库口令同一管理方式）；Cookie 显式 `SameSite=Lax` + `HttpOnly`
- 测试适配：现有页面用例改为"先登录再访问"；新增注册 / 登录 / 门卫 / 登出用例
- 文档：`docs/run.md` 补账号说明与首次使用流程
- **明确不做**：角色 / 权限区分、找回密码、修改密码、邮箱验证、登录限流

## Capabilities

### New Capabilities

- `user-auth`: 本地账号体系——注册、登录、登出、会话保持与访问保护

### Modified Capabilities

无（`web-dashboard` 等既有规格不变；访问门卫行为归 `user-auth` 能力拥有）。

## Impact

- 代码：新增 `auth.py`、`templates/login.html`、`templates/register.html`；改动 `app.py`、`templates/base.html`、`config.py`、`tests/test_app.py`、`docs/run.md`
- 数据：`recruitment` 库新增 `users` 表（启动时自动创建）
- 配置：`.env` / `.env.example` 新增 `RECRUIT_SECRET_KEY`
- 依赖：无新增（密码哈希与会话均使用现有 Flask / werkzeug 能力）
