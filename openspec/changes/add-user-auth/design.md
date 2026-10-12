# Design

## Context

- 首个 change `add-recruitment-analysis-system` 已归档（28/28 任务、47 条测试全绿）；现有栈：Flask 3.1.3 + PyMySQL + pyecharts，页面样式集中在 `templates/base.html`
- 现有页面测试经由 `app.test_client()` 直接访问，无登录概念——本 change 需要适配
- 既有模式延续：密钥进 `.env`、朴素优先、讲原理、OpenSpec 流程
- 动机与范围见 `proposal.md`；行为契约见 `specs/user-auth/spec.md`

## Goals / Non-Goals

**Goals:**

- 用现有依赖实现完整的"注册 → 登录 → 访问 → 登出"闭环，行为朴素、可逐段讲解
- 与现有代码结构（`app.py` / `db.py` / `templates/`）风格保持一致

**Non-Goals:**

- 不做角色 / 权限、找回 / 修改密码、邮箱验证、登录限流（见 proposal 明确不做）
- 不引入 flask-login 等新依赖

## Decisions

### D1 手写轻量认证，不引入 flask-login

- **Why**：功能面小（3 条路由 + 一个门卫），手写更能讲清"会话到底是什么"；零新依赖
- **Alternatives**：flask-login——成熟但多一层抽象与概念，本地演示收益低，被否

### D2 会话 = Flask 内置签名 Cookie；"记住我" = permanent session

登录成功写 `session["user_id"]`；勾选"记住我"时 `session.permanent = True` 且 `PERMANENT_SESSION_LIFETIME = 7 天`；未勾选则是浏览器会话 Cookie。

- **Why**：Flask 的 session 不是服务器存储，而是把数据签名后放进 Cookie，服务器用密钥验签还原——无需会话表，原理可讲透
- **Alternatives**：服务端 Session 表——本地单机场景过度设计，被否

### D3 密码哈希用 werkzeug.security

`generate_password_hash` / `check_password_hash`（默认 pbkdf2-sha256、自带随机盐）；Flask 自带依赖，零新增。

### D4 访问门卫：`before_request` + 白名单

在 `app.py` 注册 `before_request`：放行 `login`、`register`、`static` 三个端点；其余端点未登录一律 302 到 `/login?next=原路径`；已登录访问 login / register 跳回总览。

- **Why**：集中一处、不易漏；白名单显式列出，安全边界一目了然
- **Alternatives**：逐路由装饰器——易漏且重复，被否

### D5 users 表与启动自建

`users(id, username, password_hash, created_at)`，username 唯一；`auth.py` 提供 `ensure_users_table()`，应用启动时调用（`CREATE TABLE IF NOT EXISTS`），免手动建表。用户名存原文（保留大小写展示），查重与登录均按 `LOWER(username)` 比较。

### D6 CSRF：显式 SameSite=Lax，不手写 token（用户已拍板）

显式设置 `SESSION_COOKIE_SAMESITE="Lax"`（叠加默认 HttpOnly），依赖浏览器同源策略挡跨站表单请求；不手写 token 的取舍记录在案：本地单机演示、攻击面小，若未来上线再补。

- **Alternatives**：一次性 token——多约 20 行、多一个知识点；用户选择先不做

### D7 签名密钥：`.env` 注入，缺省随机

`RECRUIT_SECRET_KEY` 从 `.env` 读取（与数据库口令同一机制）；未配置时以 `secrets.token_hex(32)` 随机生成（开发可接受：重启后旧会话失效），`.env.example` 留占位。

## Risks / Trade-offs

- [现有页面测试会被门卫全部拦截] → 测试加"登录辅助"（幂等测试账号：注册失败则登录）；门卫与拒绝路径单独用例
- [测试账号在 users 表残留] → 辅助函数采用固定测试用户名并容忍已存在（注册→登录二选一），可重复运行
- [暴力试密码无防护] → 本地演示接受，记录为已知限制（proposal 已声明不做限流）
- [密钥 / 口令入库] → 延续 `.env` 机制，仓库只留 `.env.example` 占位
- [无状态会话：登出只清浏览器 Cookie，旧 Cookie 值在有效期内的理论上可重放（签名不过期）] → 本地演示接受；如需"登出即强失效"，需引入服务端会话存储（见 D2 备选），记录为已知取舍

## Migration Plan

纯新增：`users` 表由应用启动自建，无数据迁移；回滚 = 删除 `auth.py` 与两个模板、还原 `app.py` 门卫改动、删除 `users` 表。

## Open Questions

- 无
