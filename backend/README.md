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
| `OLLAMA_DEFAULT_MODEL` | `qwen3.5:4b` | AI 接口默认使用的模型 |
| `OLLAMA_CONNECT_TIMEOUT_SECONDS` | `20` | 建立连接超时（秒） |
| `OLLAMA_READ_TIMEOUT_SECONDS` | `180` | 模型读取/生成超时（秒） |
| `OLLAMA_VERIFY_TLS` | `true` | 是否验证 HTTPS 证书 |
| `OLLAMA_CF_ACCESS_CLIENT_ID` | 空 | Cloudflare Access Client ID，仅服务器环境 |
| `OLLAMA_CF_ACCESS_CLIENT_SECRET` | 空 | Cloudflare Access Secret，仅服务器环境 |
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
