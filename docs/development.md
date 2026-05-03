# 本地开发流程

## 前提条件

| 工具 | 最低版本 | 说明 |
|---|---|---|
| Python | 3.11 | 后端运行时 |
| Node.js | 20 | 前端构建工具 |
| Git | 2.x | 版本控制 |
| Ollama | 最新 | 可选，AI 功能所需 |

## 克隆仓库

```bash
git clone <仓库地址>
cd Home-Library
```

## 环境变量

```bash
cp .env.example .env
```

`.env` 中各变量的完整说明见 [`.env.example`](../.env.example) 的注释。开发时通常只需关注：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `APP_SECRET_KEY` | `change-this-secret` | 必须修改，用于 JWT 签名 |
| `DATABASE_URL` | `sqlite:///./home_library.sqlite3` | SQLite 路径，开发时无需修改 |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | 如不使用 Ollama 可忽略 |
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000/api` | 前端请求后端的地址 |

## 后端开发

### 安装依赖

```bash
cd backend
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

依赖清单位于 `backend/pyproject.toml`（由任务 B 创建）。

### 初始化数据库

```bash
# 运行迁移（或首次初始化）
alembic upgrade head

# 写入种子数据（简化中图法分类、默认管理员）
python -m app.db.init_db
```

### 启动开发服务器

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

访问 `http://127.0.0.1:8000/docs` 查看 Swagger UI。

### 运行测试

```bash
pytest
pytest -v                       # 详细输出
pytest app/tests/test_health.py # 指定文件
```

### 代码检查

```bash
ruff check .                    # Linting
ruff format .                   # 格式化
mypy app/                       # 类型检查
```

## 前端开发

### 安装依赖

```bash
cd frontend
npm install
```

### 启动开发服务器

```bash
npm run dev
```

默认访问 `http://localhost:5173`。

### 构建生产版本

```bash
npm run build
npm run preview              # 本地预览构建产物
```

### 类型检查与 Lint

```bash
npm run type-check
npm run lint
```

## Ollama（可选）

AI 功能（分类推荐、标签生成等）依赖本地 Ollama 服务。`.env` 中 `OLLAMA_OPTIONAL=true` 时，Ollama 不可用系统仍可正常运行，AI 接口会返回服务不可用的错误信息。

```bash
# 安装 Ollama（macOS）
brew install ollama

# 启动服务
ollama serve

# 拉取推荐模型（中文书籍分类）
ollama pull qwen2.5

# 验证
curl http://localhost:11434/api/tags
```

## 同时运行前后端

推荐打开两个终端窗口分别运行后端和前端，或使用以下一行命令（需要 `npm-run-all` 或 `concurrently`）：

```bash
# 方式一：两个终端分别运行
# 终端 1
cd backend && uvicorn app.main:app --reload
# 终端 2
cd frontend && npm run dev
```

## 验证整体启动

```bash
# 后端健康检查
curl http://127.0.0.1:8000/api/health

# 后端版本
curl http://127.0.0.1:8000/api/version

# 前端
open http://localhost:5173
```

## 目录约定

- 后端字段命名：`snake_case`
- 前端 TypeScript 类型：`camelCase`（API 响应字段由 `axios` 拦截器自动转换，或前端适配层处理）
- 时间字段：ISO 8601 字符串（含时区，如 `2026-05-03T10:00:00+08:00`）
- 金额：后端存整数分（`price_cents`），前端展示除以 100 显示为元

## 常见问题

**Q: 后端启动报 `ModuleNotFoundError`**
A: 确认已激活虚拟环境（`source .venv/bin/activate`）且已运行 `pip install -e ".[dev]"`。

**Q: 前端请求报跨域错误**
A: 检查 `.env` 中 `CORS_ORIGINS` 是否包含前端地址，以及 `VITE_API_BASE_URL` 是否正确。

**Q: Ollama 调用超时**
A: 增大 `OLLAMA_TIMEOUT_SECONDS`，或先用 `ollama run qwen2.5` 手动测试模型是否正常。

**Q: SQLite 数据库路径错误**
A: `DATABASE_URL` 的相对路径相对于后端工作目录（`backend/`），建议使用绝对路径或在 `backend/` 目录下启动服务。
