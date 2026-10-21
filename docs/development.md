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
| `OLLAMA_ENABLED` | `false` | AI 开关；如不使用 Ollama 保持关闭 |
| `OLLAMA_BASE_URL` | `https://openclaw.lsgood.cn` | 本地或远程 Ollama 地址 |
| `OLLAMA_DEFAULT_MODEL` | `qwen3.5:4b` | 默认模型 |
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
npm run typecheck
```

### 前端测试

```bash
npm run typecheck
npm run test                 # Vitest 单元测试
npm run test:e2e             # Playwright E2E 冒烟测试
```

## Ollama（可选）

AI 功能（分类推荐、标签生成等）可使用本地或 Cloudflare Access 保护的远程 Ollama。默认 `OLLAMA_ENABLED=false`；Ollama 不可用时系统仍可正常运行，AI 接口返回稳定中文错误，登录、藏书、借阅、统计和备份不受影响。

```bash
# 安装 Ollama（macOS）
brew install ollama

# 启动服务
ollama serve

# 拉取推荐模型（中文书籍分类）
ollama pull qwen3.5:4b

# 验证
curl http://localhost:11434/api/tags
```

本地运行后端时设置：

```env
OLLAMA_ENABLED=true
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_DEFAULT_MODEL=qwen3.5:4b
```

远程模式当前使用 `https://openclaw.lsgood.cn`，`ollama.lsgood.cn` 不是当前默认地址。Access Client ID/Secret 可通过后端环境引导，或由管理员在安全传输下经双重认证成对写入后端加密存储；前端不能读取保存值，也不得持久化输入。运行只读 smoke 前还需设置 `OLLAMA_TRUSTED_BASE_URL`；脚本仅在其规范化 Origin 与 `OLLAMA_BASE_URL` 完全一致时携带凭据。可用 `bash scripts/tests/test-ollama-cloudflare-smoke-test.sh` 运行第三方地址、端口、协议、默认端口、IPv6、用户信息和控制字符安全矩阵。

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
A: 连接失败调整 `OLLAMA_CONNECT_TIMEOUT_SECONDS`，模型生成慢调整 `OLLAMA_READ_TIMEOUT_SECONDS`；本地模型可先用 `ollama run qwen3.5:4b` 验证。

**Q: SQLite 数据库路径错误**
A: `DATABASE_URL` 的相对路径相对于后端工作目录（`backend/`），建议使用绝对路径或在 `backend/` 目录下启动服务。


### 管理员 AI 配置开发验证

全局配置、当前运行状态、当前账号偏好分别验证。无数据库记录时保持环境行为；迁移 `0002` 不应自动插入覆盖。保存、刷新、模型列表、保存成功但健康失败、保留/替换/清除凭据、恢复环境、账号偏好保留及禁用 AI 后非 AI 导航均属于验收范围。

本机直连后端的写操作需要回环 peer 加回环浏览器 Origin/Referer；Docker Nginx 不是回环 peer，应使用 HTTPS 和精确可信代理，见部署文档。测试只用运行时生成的合成凭据；禁止在命令参数、日志、截图、trace、video、错误 DOM 快照或 Git 中记录秘密。截图前实测密码输入为空，并扫描 API、审计、数据库、日志和 browser storage；输出仅布尔、计数和稳定错误码。

受控 HTTPS 上游应在每个 worker 内执行 TLS 握手并设置握手/请求超时；不可把同步 HTTPServer 的 listening socket 直接包成 TLS，否则一个停滞握手即可阻塞全部探针。用停滞客户端与正常并发请求验证夹具本身，避免将夹具超时误诊为业务分类错误。

本轮 Docker 后端验收使用缓存基础镜像加当前源码构建并验证迁移；这不等同于从零完成生产 Dockerfile 的系统包/工具链引导。任何新下载前必须在实际执行环境有界测量官方及候选源，选择可用最快源并保留官方回退，不把区域镜像固化为生产默认。
