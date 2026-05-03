# 第一批并行任务领取说明

本文档用于启动第一批并行开发任务。建议分别在 4 个新窗口或 AI 应用中执行任务 A、B、C、L。

所有子任务窗口都必须先阅读：

- `docs/home-library-web-app-plan.md`
- `docs/parallel-development-plan.md`
- `docs/api-contract.md`
- `docs/database-schema.md`
- `docs/frontend-spec.md`

## 通用要求

1. 只修改自己任务范围内的文件。
2. 如需修改公共 API、数据库字段或目录结构，必须在最终汇报中明确说明。
3. 每个任务完成后必须给出验证命令和测试结果。
4. 不要删除其他任务窗口生成的文件。
5. 输出格式必须使用本文档末尾的汇报模板。

## 任务 A：项目骨架与公共规范

### 任务目标

完善仓库根目录规范，让新开发者能快速理解项目结构、启动方式和协作规则。

### 负责范围

- `README.md`
- `.gitignore`
- `.editorconfig`
- `.env.example`
- `docs/`
- 根目录说明文件

### 建议工作

1. 检查现有目录结构是否符合 `docs/parallel-development-plan.md`。
2. 补充根目录 README 的开发说明。
3. 补充环境变量解释。
4. 维护文档索引。
5. 可新增 `docs/development.md` 说明本地开发流程。

### 不负责

- 不实现后端业务代码。
- 不实现前端页面。
- 不改数据库模型。

### 验收标准

- 新开发者能通过 README 明白项目目标、目录结构和下一步开发方式。
- `.env.example` 覆盖后端、前端、Ollama 和外部检索配置。
- 文档索引完整。

### 可复制提示词

```text
你正在参与 Home Library 家庭藏书管理系统的并行开发。
请先阅读 docs/home-library-web-app-plan.md、docs/parallel-development-plan.md、docs/api-contract.md、docs/database-schema.md、docs/frontend-spec.md。
你只负责任务 A：项目骨架与公共规范。
请完善 README、.gitignore、.editorconfig、.env.example 和必要的 docs 开发说明。
不要实现后端业务代码或前端页面。
完成后按 docs/first-wave-task-briefs.md 的汇报模板输出结果。
```

## 任务 B：后端基础框架

### 任务目标

搭建可运行的 FastAPI 后端基础服务。

### 负责范围

- `backend/app/main.py`
- `backend/app/core/`
- `backend/app/api/`
- `backend/app/db/`
- `backend/pyproject.toml`
- `backend/README.md`

### 必须实现

- FastAPI app
- CORS 配置
- 设置读取
- 路由注册
- 健康检查
- 版本接口
- 统一错误响应雏形

### 接口

```text
GET /api/health
GET /api/version
```

### 不负责

- 不实现用户登录。
- 不实现图书 CRUD。
- 不实现数据库业务模型。

### 验收标准

- 后端可启动。
- `/api/health` 返回正常。
- `/api/version` 返回应用名称和版本。
- 有基础测试或至少有明确验证命令。

### 可复制提示词

```text
你正在参与 Home Library 家庭藏书管理系统的并行开发。
请先阅读 docs/home-library-web-app-plan.md、docs/parallel-development-plan.md、docs/api-contract.md、docs/database-schema.md、docs/frontend-spec.md。
你只负责任务 B：后端基础框架。
请在 backend/ 中搭建 FastAPI 基础服务，实现配置、CORS、路由注册、GET /api/health、GET /api/version 和基础错误响应。
不要实现认证、图书 CRUD 或数据库业务模型。
完成后按 docs/first-wave-task-briefs.md 的汇报模板输出结果。
```

## 任务 C：数据库模型与迁移

### 任务目标

根据数据库设计实现 SQLAlchemy 模型、Pydantic Schema 和初始化数据。

### 负责范围

- `backend/app/models/`
- `backend/app/schemas/`
- `backend/app/db/`
- `backend/alembic/`

### 必须实现

- `users`
- `books`
- `categories`
- `locations`
- `tags`
- `book_tags`
- `borrow_records`
- `reading_notes`
- `external_book_results`
- `ai_tasks`
- 简化中图法种子数据
- 默认管理员初始化逻辑

### 不负责

- 不实现 API 路由。
- 不实现前端页面。
- 不实现 Ollama 调用。

### 验收标准

- 数据库可初始化。
- 内置分类可写入。
- 表关系符合 `docs/database-schema.md`。
- 迁移或初始化流程可重复执行。

### 可复制提示词

```text
你正在参与 Home Library 家庭藏书管理系统的并行开发。
请先阅读 docs/home-library-web-app-plan.md、docs/parallel-development-plan.md、docs/api-contract.md、docs/database-schema.md、docs/frontend-spec.md。
你只负责任务 C：数据库模型与迁移。
请根据 docs/database-schema.md 实现 SQLAlchemy 模型、Pydantic Schema、数据库初始化和简化中图法种子数据。
不要实现 API 路由或前端页面。
完成后按 docs/first-wave-task-briefs.md 的汇报模板输出结果。
```

## 任务 L：前端基础框架

### 任务目标

搭建 Vue 3 前端基础框架、路由、状态管理、API 客户端和基础布局。

### 负责范围

- `frontend/package.json`
- `frontend/src/main.ts`
- `frontend/src/router/`
- `frontend/src/stores/`
- `frontend/src/api/`
- `frontend/src/layouts/`
- `frontend/src/styles/`

### 必须实现

- Vite + Vue 3 + TypeScript
- Element Plus
- Vue Router
- Pinia
- API client
- 登录态 store
- 路由守卫
- 主布局
- 登录页占位
- 首页占位

### 不负责

- 不实现完整图书管理页面。
- 不实现分类位置业务页面。
- 不实现图表和智能入库页面。

### 验收标准

- 前端可启动。
- `/login` 可访问。
- `/` 需要登录或使用临时开发态处理。
- API client 能配置 `VITE_API_BASE_URL`。

### 可复制提示词

```text
你正在参与 Home Library 家庭藏书管理系统的并行开发。
请先阅读 docs/home-library-web-app-plan.md、docs/parallel-development-plan.md、docs/api-contract.md、docs/database-schema.md、docs/frontend-spec.md。
你只负责任务 L：前端基础框架。
请在 frontend/ 中搭建 Vue 3 + TypeScript + Vite + Element Plus + Pinia + Vue Router 基础框架，实现 API client、登录态 store、路由守卫、主布局、登录页占位和首页占位。
不要实现完整图书、分类、位置或智能入库业务页面。
完成后按 docs/first-wave-task-briefs.md 的汇报模板输出结果。
```

## 汇报模板

```text
任务编号：
任务名称：
完成内容：
修改文件：
新增接口：
数据库变更：
本地验证命令：
测试结果：
遗留问题：
需要总控窗口协调的事项：
```

