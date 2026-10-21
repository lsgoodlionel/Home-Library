# Home Library Backend

FastAPI 后端，使用 SQLAlchemy、Pydantic 和 SQLite 实现。

## 技术栈

- **FastAPI** — Web 框架
- **SQLAlchemy 2.x** — ORM
- **Pydantic v2** — 数据校验
- **Alembic** — 数据库迁移
- **passlib + bcrypt** — 密码哈希
- **PyJWT** — JWT 认证
- **SQLite** — 默认数据库（可切换 PostgreSQL）

## 目录结构

```text
backend/
  app/
    api/
      routes/
        system.py     GET /api/health, GET /api/version
        auth.py       POST /api/auth/login, POST /api/auth/logout, GET /api/auth/me
        users.py      GET/POST /api/users, PATCH/DELETE /api/users/{id}
      router.py       路由注册总入口
    core/
      config.py       配置读取（pydantic-settings）
      errors.py       统一错误响应格式
      security.py     密码哈希、JWT 签发/验证、认证依赖
    db/
      session.py      SQLAlchemy engine 与 get_db 依赖
      init_db.py      建表、种子分类、默认管理员
      seeds/          简化中图法种子数据
    models/           SQLAlchemy 模型
    schemas/          Pydantic schema
    services/
      auth_service.py 登录认证、记录登录时间
      user_service.py 用户 CRUD 业务逻辑
    tests/            pytest 测试
  alembic/            数据库迁移文件
  pyproject.toml
```

## 环境配置

```bash
cp ../.env.example ../.env
# 按需修改 APP_SECRET_KEY、DATABASE_URL 等
```

关键环境变量：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `APP_SECRET_KEY` | `dev-secret-change-me-in-production` | JWT 签名密钥，生产必须修改 |
| `APP_ACCESS_TOKEN_EXPIRE_SECONDS` | `86400` | Token 有效期（秒） |
| `DATABASE_URL` | `sqlite:///./home_library.db` | 数据库连接字符串 |
| `INITIAL_ADMIN_USERNAME` | `admin` | 初始管理员用户名 |
| `INITIAL_ADMIN_PASSWORD` | `change-me` | 初始管理员密码 |
| `OLLAMA_ENABLED` | `false` | AI 总开关；关闭时不会请求 Ollama |
| `OLLAMA_BASE_URL` | `https://openclaw.lsgood.cn` | 本地或远程 Ollama 地址 |
| `OLLAMA_TRUSTED_BASE_URL` | `https://openclaw.lsgood.cn` | 后端与 smoke 可携带 Access 凭据的独立 HTTPS 信任 Origin |
| `OLLAMA_DEFAULT_MODEL` | `qwen3.5:4b` | AI 接口默认使用的模型 |
| `OLLAMA_CONNECT_TIMEOUT_SECONDS` | `20` | 建立连接超时（秒） |
| `OLLAMA_READ_TIMEOUT_SECONDS` | `180` | 模型读取/生成超时（秒） |
| `OLLAMA_VERIFY_TLS` | `true` | 是否验证 HTTPS 证书 |
| `OLLAMA_CF_ACCESS_CLIENT_ID` | 空 | Cloudflare Access Client ID，环境引导 |
| `OLLAMA_CF_ACCESS_CLIENT_SECRET` | 空 | Cloudflare Access Secret，环境引导 |
| `OLLAMA_OPTIONAL` | `true` | Ollama 不可用时系统仍可启动，AI 接口返回清晰错误 |

Access 凭据只有在账号有效 Ollama URL 与服务器受信任 URL 的 origin 完全一致时才会发送，不会通过 API、日志或审计记录返回。AI 请求失败不会影响 `/api/health` 或非 AI 图书功能。

## 安装与启动

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# 初始化数据库（建表 + 种子数据 + 默认管理员）
python -m app.db.init_db

# 启动开发服务器
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Swagger UI：http://127.0.0.1:8000/docs

## 认证说明

所有受保护接口均需要 `Authorization: Bearer <token>` 请求头。

**登录流程：**

```bash
# 登录获取 Token
curl -X POST http://127.0.0.1:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "change-me"}'

# 使用 Token 访问受保护接口
curl http://127.0.0.1:8000/api/auth/me \
  -H "Authorization: Bearer <token>"
```

**权限级别：**

- `admin` — 可访问所有接口，包括用户管理
- `member` — 可访问藏书、借阅、笔记等接口，不可访问用户管理
- `guest` — 只读访问（后续扩展）

## 测试

```bash
cd backend
pytest              # 运行全部测试
pytest -v           # 详细输出
pytest app/tests/test_auth.py    # 仅认证测试
pytest app/tests/test_users.py   # 仅用户管理测试
```

## 接口列表

### 系统

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/health` | 公开 | 健康检查 |
| GET | `/api/version` | 公开 | 版本信息 |

### 全局 AI 配置与账号偏好

`GET/PUT/DELETE /api/system/ai-config` 仅管理员可用，`POST /api/system/ai-config/test` 执行已保存配置的只读测试。PUT/DELETE 同时校验当前管理员密码、环境 `UPGRADE_PASSWORD` 和安全传输。账号 `/api/ai/config` 保留地址/模型偏好；不接收全局开关、可信地址、TLS、超时或 Access 凭据。

迁移 `0002_system_ai_settings` 增加单例全局覆盖与追加审计；无记录时继续使用环境配置，不自动生成覆盖。数据库优先于环境和程序默认值，保存/恢复立即失效健康缓存。审计只记录操作者、动作、版本和字段名，不记录字段值。

Access 使用 AES-GCM + HKDF 从稳定 `APP_SECRET_KEY` 派生密钥后加密。弱密钥不能保存新凭据；密文损坏或密钥不匹配时不发送 Access，非敏感配置和非 AI 模块继续可用。API 只返回配置状态布尔值，不返回明文、密文或长度。密钥要求、备份恢复及可信代理配置见 `docs/deployment.md`。

完整配置更新使用数据库版本条件检查并一次写入全部字段；并发修改/删除或首次创建冲突返回 HTTP 409，需刷新后重新确认提交，失败方不写审计且不失效缓存。数据库故障返回稳定中文 500；回滚与敏感对象均留在内部 outcome 帧，向外异常不携带 SQL 参数或原始异常链。AI 关闭时 `/ai/models` 不构造客户端，先记录安全失败任务并清理运行时引用，再返回 `AI_SERVICE_DISABLED`。

### AI 运维

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/ai/health?refresh=false` | 登录用户 | 读取最近一次脱敏状态；`refresh=true` 主动检查 |
| POST | `/api/ai/test-connection` | 管理员 | 普通连接测试；仅显式传入 `{"generate": true}` 才执行最小生成 |

### 认证

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| POST | `/api/auth/login` | 公开 | 登录，返回 JWT Token |
| POST | `/api/auth/logout` | 公开 | 退出（客户端删除 Token） |
| GET | `/api/auth/me` | 登录用户 | 当前用户信息 |

### 用户管理

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/users` | 管理员 | 用户分页列表 |
| POST | `/api/users` | 管理员 | 创建用户 |
| PATCH | `/api/users/{id}` | 管理员 | 编辑用户角色/状态/显示名/邮箱 |
| DELETE | `/api/users/{id}` | 管理员 | 禁用用户（MVP 不物理删除） |

### AI / Ollama

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/ai/models` | MVP 未强制 | 读取本地 Ollama 模型列表 |
| POST | `/api/ai/classify-book` | MVP 未强制 | 推荐分类、标签和理由 |
| POST | `/api/ai/generate-tags` | MVP 未强制 | 生成图书标签 |
| POST | `/api/ai/summarize-book` | MVP 未强制 | 整理内容简介和作者简介 |
| POST | `/api/ai/detect-duplicate` | MVP 未强制 | 判断两条图书记录是否重复 |
| POST | `/api/ai/natural-search` | MVP 未强制 | 将自然语言解析为结构化搜索条件 |

### 图书导入导出

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| POST | `/api/books/import/preview` | MVP 未强制 | 上传 CSV、JSON 或 Excel 文件并返回字段映射后的预览、错误和提示 |
| POST | `/api/books/import` | MVP 未强制 | 确认导入；如存在错误则不写入任何数据 |
| GET | `/api/books/export?format=csv` | MVP 未强制 | 导出图书，`format` 支持 `csv`、`json`、`xlsx` |

完整接口契约见 [`docs/api-contract.md`](../docs/api-contract.md)。
