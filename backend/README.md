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
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | 本地 Ollama 服务地址 |
| `OLLAMA_DEFAULT_MODEL` | `qwen2.5` | AI 接口默认使用的模型 |
| `OLLAMA_TIMEOUT_SECONDS` | `30` | Ollama 请求超时时间 |
| `OLLAMA_OPTIONAL` | `true` | Ollama 不可用时系统仍可启动，AI 接口返回清晰错误 |

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

完整接口契约见 [`docs/api-contract.md`](../docs/api-contract.md)。
