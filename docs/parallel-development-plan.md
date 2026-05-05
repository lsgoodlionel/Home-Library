# Home Library 并行开发任务分工计划

## 1. 计划目的

本文档用于把家庭藏书管理系统拆分成多个可并行开发的子任务，方便在若干个新窗口、AI 应用或开发成员中同步推进。

本窗口只负责：

- 维护总方案
- 汇总各子任务进展
- 统一接口契约
- 统一数据模型
- 处理跨模块冲突
- 最终集成与验收

其他窗口或 AI 应用应分别领取独立子任务，按本文档约定输出代码、接口、测试和说明。

## 2. 推荐总体技术栈

```text
frontend: Vue 3 + TypeScript + Vite + Element Plus
backend: FastAPI + SQLAlchemy + Pydantic
database: SQLite first, PostgreSQL compatible later
auth: JWT
ai: Ollama HTTP API
search: SQLite FTS5
deployment: Docker Compose
```

## 3. 仓库建议结构

```text
Home-Library/
  README.md
  docs/
    home-library-web-app-plan.md
    parallel-development-plan.md
    api-contract.md
    database-schema.md
    frontend-spec.md
    deployment.md
  backend/
    app/
      api/
      core/
      db/
      models/
      schemas/
      services/
      tests/
    alembic/
    pyproject.toml
    README.md
  frontend/
    src/
      api/
      assets/
      components/
      layouts/
      pages/
      router/
      stores/
      styles/
      types/
    package.json
    README.md
  docker/
  docker-compose.yml
  .env.example
```

## 4. 开发协作规则

1. 每个子任务在独立窗口或独立分支中开发。
2. 每个子任务必须先阅读 `docs/home-library-web-app-plan.md` 和本文档。
3. 子任务不得随意修改公共接口，确需修改时先更新接口契约文档。
4. 后端以 OpenAPI 为接口来源，前端以接口类型定义调用。
5. 数据库字段命名统一使用 snake_case。
6. 前端 TypeScript 类型统一使用 camelCase。
7. 所有时间字段使用 ISO 8601 字符串。
8. 金额字段后端使用整数分，前端展示为元。
9. ISBN 字段保存清洗后的标准字符串，同时保留原始输入可选。
10. 所有 AI 输出必须经过 JSON schema 校验，不能直接信任模型文本。

## 5. 分支建议

```text
main
dev
feature/backend-foundation
feature/frontend-foundation
feature/books-crud
feature/categories-locations
feature/search-ai
feature/import-export
feature/borrow-reading
feature/stats-dashboard
feature/docker-deploy
feature/tests
```

## 6. 总体里程碑

### M0：方案与契约

目标：完成项目骨架前的公共设计。

交付物：

- 完整方案
- API 契约
- 数据库 schema
- 前端页面规范
- 开发分工计划

### M1：基础可运行系统

目标：前后端能启动，用户能登录，能访问首页。

交付物：

- 后端 FastAPI 项目
- 前端 Vue 项目
- 登录接口
- 登录页
- 基础布局
- SQLite 初始化

### M2：藏书管理 MVP

目标：完成图书、分类、位置的基本管理。

交付物：

- 图书 CRUD
- 分类 CRUD
- 位置 CRUD
- 图书列表
- 图书详情
- 新增编辑图书
- 基础搜索

### M3：智能录入

目标：接入外部书籍检索和 Ollama。

交付物：

- ISBN 查询
- 书名搜索
- 候选结果导入
- Ollama 分类推荐
- 标签生成
- 重复检测初版

### M4：家庭管理增强

目标：加入借阅、阅读、统计和导入导出。

交付物：

- 借阅记录
- 阅读笔记
- 导入导出
- 仪表盘统计
- 分类和位置图表

### M5：部署验收

目标：可在本机或 NAS 上部署。

交付物：

- Docker Compose
- `.env.example`
- 备份恢复脚本
- 用户文档
- 测试报告

## 7. 子任务拆分

### A-T 完成状态总览

截至当前集成版本，A-T 全部子任务均已完成、提交并推送到 `main`。各任务最终落点如下：

| 任务 | 名称 | 状态 | 代表性交付 |
|---|---|---|---|
| A | 项目骨架与公共规范 | ✅ 已完成 | README、`.env.example`、协作文档、文档索引 |
| B | 后端基础框架 | ✅ 已完成 | FastAPI 工厂、配置、CORS、健康检查、版本接口 |
| C | 数据库模型与迁移 | ✅ 已完成 | SQLAlchemy 模型、Pydantic schema、Alembic、分类种子 |
| D | 认证与用户管理 | ✅ 已完成 | JWT 登录、用户 CRUD、管理员权限 |
| E | 图书 CRUD 后端 | ✅ 已完成 | 图书分页、详情、新增、编辑、删除、批量更新 |
| F | 分类与位置后端 | ✅ 已完成 | 分类树、分类 CRUD、位置 CRUD、引用保护 |
| G | 外部书籍检索后端 | ✅ 已完成 | Open Library、Google Books、缓存、候选导入 |
| H | Ollama 智能能力后端 | ✅ 已完成 | 模型列表、分类、标签、摘要、重复判断、自然语言解析 |
| I | 借阅与阅读后端 | ✅ 已完成 | 借出、归还、借阅历史、阅读笔记、阅读状态更新 |
| J | 统计后端 | ✅ 已完成 | 总览、分类/位置分布、阅读状态、入库趋势 |
| K | 导入导出后端 | ✅ 已完成 | CSV / JSON / Excel 导入预览、确认导入、导出 |
| L | 前端基础框架 | ✅ 已完成 | Vue 3、Router、Pinia、API client、登录守卫、布局 |
| M | 前端图书管理界面 | ✅ 已完成 | 图书列表、详情、新增、编辑、筛选、表单 |
| N | 前端分类与位置管理 | ✅ 已完成 | 分类树、位置分组、选择组件、管理员路由 |
| O | 前端智能检索与 AI 入库 | ✅ 已完成 | 智能导入向导、候选选择、AI 推荐卡片 |
| P | 前端借阅与阅读界面 | ✅ 已完成 | 借阅页、阅读页、笔记组件、图书详情入口 |
| Q | 前端仪表盘与统计页 | ✅ 已完成 | 首页指标、统计页、轻量 SVG/CSS 图表 |
| R | 系统设置与用户管理前端 | ✅ 已完成 | 用户管理页、系统设置页、本地设置存储 |
| S | 部署与运维 | ✅ 已完成 | Dockerfile、Compose、Nginx、备份脚本、部署文档 |
| T | 测试与质量保障 | ✅ 已完成 | 后端回归、Vitest、Playwright E2E 骨架、测试文档 |

最终验证状态：

- 后端全量测试：`145 passed, 1 warning`
- 前端类型检查：通过
- 前端构建：通过，仅有 Vite chunk size 提示
- Vitest：`1 passed / 3 tests passed`
- Playwright E2E：`3 passed`

## ✅ 任务 A：项目骨架与公共规范（已完成）

适合窗口：总控窗口或架构窗口。

目标：

- 建立仓库目录结构
- 生成公共配置
- 明确代码风格
- 提供前后端启动说明

负责范围：

- `README.md`
- `docs/`
- `.gitignore`
- `.editorconfig`
- `.env.example`
- 根目录开发说明

交付物：

- 仓库骨架
- 文档索引
- 本地开发命令
- 环境变量说明

验收标准：

- 新开发者可以根据 README 知道如何启动项目。
- 前后端目录边界清晰。
- 文档能指导后续任务独立开发。

## ✅ 任务 B：后端基础框架（已完成）

适合窗口：后端基础开发。

目标：

- 搭建 FastAPI 服务
- 建立配置、数据库连接、异常处理、路由注册
- 提供健康检查接口

负责范围：

- `backend/app/main.py`
- `backend/app/core/`
- `backend/app/db/`
- `backend/app/api/`
- `backend/pyproject.toml`

接口：

```text
GET /api/health
GET /api/version
```

交付物：

- 可启动 FastAPI 服务
- SQLite 连接
- CORS 配置
- 基础错误响应格式
- 单元测试骨架

验收标准：

- `GET /api/health` 返回正常。
- 后端可以在本地启动。
- 测试命令可以运行。

## ✅ 任务 C：数据库模型与迁移（已完成）

适合窗口：数据库开发。

目标：

- 实现核心数据模型
- 建立初始化数据
- 支持简化中图法分类种子数据

负责范围：

- `backend/app/models/`
- `backend/app/schemas/`
- `backend/app/db/init_db.py`
- `backend/alembic/`

核心表：

- users
- books
- categories
- locations
- tags
- book_tags
- borrow_records
- reading_notes
- external_book_results
- ai_tasks

交付物：

- SQLAlchemy 模型
- Pydantic schema
- 数据库迁移
- 分类种子数据

验收标准：

- 初始化数据库后内置分类存在。
- 表关系正确。
- 迁移可重复执行。

## ✅ 任务 D：认证与用户管理（已完成）

适合窗口：后端认证开发。

目标：

- 实现登录、当前用户、用户管理和权限控制。

负责范围：

- `backend/app/api/auth.py`
- `backend/app/api/users.py`
- `backend/app/core/security.py`
- `backend/app/services/auth_service.py`
- `backend/app/services/user_service.py`

接口：

```text
POST /api/auth/login
POST /api/auth/logout
GET  /api/auth/me
POST /api/users
GET  /api/users
PATCH /api/users/{id}
DELETE /api/users/{id}
```

交付物：

- JWT 登录
- 密码哈希
- 当前用户依赖
- 管理员权限依赖
- 默认管理员初始化

验收标准：

- 未登录不能访问受保护接口。
- 普通用户不能访问管理员接口。
- 密码不明文存储。

## ✅ 任务 E：图书 CRUD 后端（已完成）

适合窗口：后端业务开发。

目标：

- 实现图书增删改查、基础搜索、分页和筛选。

负责范围：

- `backend/app/api/books.py`
- `backend/app/services/book_service.py`
- `backend/app/schemas/book.py`

接口：

```text
GET    /api/books
GET    /api/books/{id}
POST   /api/books
PATCH  /api/books/{id}
DELETE /api/books/{id}
POST   /api/books/batch-update
```

交付物：

- 图书分页列表
- 图书详情
- 新增图书
- 编辑图书
- 删除图书
- 按关键词搜索
- 按分类、位置、状态筛选

验收标准：

- 能创建一本完整图书记录。
- 能按书名、作者、ISBN 搜索。
- 能按分类和位置筛选。

## ✅ 任务 F：分类与位置后端（已完成）

适合窗口：后端业务开发。

目标：

- 实现分类树和家庭书架位置管理。

负责范围：

- `backend/app/api/categories.py`
- `backend/app/api/locations.py`
- `backend/app/services/category_service.py`
- `backend/app/services/location_service.py`

接口：

```text
GET    /api/categories
POST   /api/categories
PATCH  /api/categories/{id}
DELETE /api/categories/{id}

GET    /api/locations
POST   /api/locations
PATCH  /api/locations/{id}
DELETE /api/locations/{id}
```

交付物：

- 分类树
- 分类 CRUD
- 位置 CRUD
- 删除保护
- 分类排序
- 位置完整路径生成

验收标准：

- 系统分类不能被误删。
- 已被图书使用的分类和位置不能直接删除。
- 前端可直接渲染分类树。

## ✅ 任务 G：外部书籍检索后端（已完成）

适合窗口：后端集成开发。

目标：

- 根据 ISBN、书名、书名加作者检索网络图书信息。

负责范围：

- `backend/app/api/search.py`
- `backend/app/services/external_books/`
- `backend/app/schemas/external_book.py`

接口：

```text
GET  /api/search/books?query=
GET  /api/search/isbn/{isbn}
POST /api/search/import-result
```

建议数据源：

- Open Library API
- Google Books API
- 可扩展的 provider 接口

交付物：

- 外部数据源抽象
- ISBN 查询
- 书名查询
- 结果归一化
- 检索缓存
- 候选结果导入

验收标准：

- 任一 provider 失败不影响其他 provider。
- 返回结果字段统一。
- 可以把候选结果导入为图书。

## ✅ 任务 H：Ollama 智能能力后端（已完成）

适合窗口：AI 集成开发。

目标：

- 接入本地 Ollama，完成分类、标签、摘要、重复判断、自然语言搜索解析。

负责范围：

- `backend/app/api/ai.py`
- `backend/app/services/ollama_service.py`
- `backend/app/services/ai_tasks.py`
- `backend/app/prompts/`

接口：

```text
POST /api/ai/classify-book
POST /api/ai/generate-tags
POST /api/ai/summarize-book
POST /api/ai/detect-duplicate
POST /api/ai/natural-search
GET  /api/ai/models
```

交付物：

- Ollama 配置
- 模型列表读取
- Prompt 模板
- JSON 输出校验
- AI 任务记录
- 超时和失败处理

验收标准：

- Ollama 不可用时系统仍可运行。
- AI 输出不合法时返回明确错误。
- 分类推荐能返回分类号、分类名、置信度和理由。

## ✅ 任务 I：借阅与阅读后端（已完成）

适合窗口：后端业务开发。

目标：

- 实现借阅、归还、阅读记录、阅读笔记。

负责范围：

- `backend/app/api/borrow.py`
- `backend/app/api/reading.py`
- `backend/app/services/borrow_service.py`
- `backend/app/services/reading_service.py`

接口：

```text
POST /api/borrow
POST /api/borrow/{id}/return
GET  /api/borrow/records
GET  /api/borrow/active

GET    /api/books/{id}/notes
POST   /api/books/{id}/notes
PATCH  /api/notes/{id}
DELETE /api/notes/{id}
```

交付物：

- 当前借出列表
- 借阅历史
- 归还操作
- 阅读笔记 CRUD
- 阅读状态更新

验收标准：

- 图书借出后状态同步为借出。
- 归还后状态同步为在架。
- 阅读笔记与用户和图书正确关联。

## ✅ 任务 J：统计后端（已完成）

适合窗口：后端统计开发。

目标：

- 为首页和统计页提供数据。

负责范围：

- `backend/app/api/stats.py`
- `backend/app/services/stats_service.py`

接口：

```text
GET /api/stats/overview
GET /api/stats/categories
GET /api/stats/locations
GET /api/stats/reading
GET /api/stats/timeline
```

交付物：

- 藏书总数
- 分类分布
- 位置分布
- 阅读状态统计
- 入库时间趋势
- 最近入库
- 当前借出

验收标准：

- 首页仪表盘所需数据完整。
- 统计接口响应结构稳定。

## ✅ 任务 K：导入导出后端（已完成）

适合窗口：后端工具开发。

目标：

- 支持 CSV、Excel、JSON 导入导出。

负责范围：

- `backend/app/api/import_export.py`
- `backend/app/services/import_export_service.py`

接口：

```text
POST /api/books/import
GET  /api/books/export
POST /api/books/import/preview
```

交付物：

- CSV 导入
- Excel 导入
- JSON 导出
- 字段映射
- 导入预览
- 错误报告
- 重复检测

验收标准：

- 导入错误不会写入半截数据。
- 导出文件可重新导入。
- 错误行有明确提示。

## ✅ 任务 L：前端基础框架（已完成）

适合窗口：前端基础开发。

目标：

- 搭建 Vue 3 前端项目、路由、状态管理、API 客户端和基础布局。

负责范围：

- `frontend/src/main.ts`
- `frontend/src/router/`
- `frontend/src/stores/`
- `frontend/src/api/`
- `frontend/src/layouts/`
- `frontend/src/styles/`

交付物：

- Vite 项目
- Element Plus
- 路由守卫
- 登录状态管理
- API 请求封装
- 主布局
- 顶部导航或侧边栏

验收标准：

- 前端能启动。
- 登录后进入首页。
- 未登录访问受保护页面会跳转登录页。

## ✅ 任务 M：前端图书管理界面（已完成）

适合窗口：前端业务开发。

目标：

- 实现图书列表、详情、新增、编辑、删除和筛选。

负责范围：

- `frontend/src/pages/books/`
- `frontend/src/components/book/`

页面：

- 图书列表页
- 图书详情页
- 新增图书页
- 编辑图书页

交付物：

- 表格视图
- 卡片视图
- 封面展示
- 搜索框
- 高级筛选
- 分页
- 图书表单
- 分类和位置选择器

验收标准：

- 可以完整录入一本书。
- 可以搜索、筛选、编辑图书。
- 表单校验完整。

## ✅ 任务 N：前端分类与位置管理（已完成）

适合窗口：前端业务开发。

目标：

- 实现分类树、位置管理和批量移动入口。

负责范围：

- `frontend/src/pages/categories/`
- `frontend/src/pages/locations/`
- `frontend/src/components/category/`
- `frontend/src/components/location/`

交付物：

- 分类树
- 分类表单
- 位置列表
- 位置表单
- 位置完整路径展示

验收标准：

- 分类树可展开、选择、编辑。
- 位置能按房间和书架组织展示。

## ✅ 任务 O：前端智能检索与 AI 入库（已完成）

适合窗口：前端集成开发。

目标：

- 实现 ISBN、书名检索、候选结果选择、Ollama 分类推荐。

负责范围：

- `frontend/src/pages/smart-import/`
- `frontend/src/components/ai/`

交付物：

- ISBN 输入
- 书名加作者输入
- 候选结果列表
- 候选结果对比
- 一键导入
- AI 分类推荐卡片
- 标签推荐

验收标准：

- 用户能从候选结果生成图书草稿。
- 用户能接受或修改 AI 分类建议。
- AI 失败时界面有可理解提示。

## ✅ 任务 P：前端借阅与阅读界面（已完成）

适合窗口：前端业务开发。

目标：

- 实现借阅管理和阅读笔记。

负责范围：

- `frontend/src/pages/borrow/`
- `frontend/src/pages/reading/`
- `frontend/src/components/notes/`

交付物：

- 借出表单
- 当前借出列表
- 借阅历史
- 归还操作
- 阅读笔记列表
- Markdown 笔记编辑
- 阅读状态更新

验收标准：

- 图书详情页能进入借阅和笔记操作。
- 借出、归还后状态即时更新。

## ✅ 任务 Q：前端仪表盘与统计页（已完成）

适合窗口：前端可视化开发。

目标：

- 实现首页仪表盘和统计分析。

负责范围：

- `frontend/src/pages/dashboard/`
- `frontend/src/pages/stats/`
- `frontend/src/components/charts/`

交付物：

- 藏书总数卡片
- 分类分布图
- 位置分布图
- 阅读状态图
- 最近入库列表
- 当前借出列表
- 入库趋势图

验收标准：

- 首页展示关键统计。
- 图表在桌面和移动端不重叠。

## ✅ 任务 R：系统设置与用户管理前端（已完成）

适合窗口：前端后台管理开发。

目标：

- 实现用户管理、Ollama 设置、数据源设置、备份设置。

负责范围：

- `frontend/src/pages/settings/`
- `frontend/src/pages/users/`

交付物：

- 用户列表
- 创建用户
- 修改角色
- 禁用用户
- Ollama 地址配置
- 默认模型配置
- 外部检索开关

验收标准：

- 普通用户看不到管理入口。
- 管理员能完成用户管理操作。

## ✅ 任务 S：部署与运维（已完成）

适合窗口：DevOps 开发。

目标：

- 实现本地和 NAS 部署。

负责范围：

- `docker-compose.yml`
- `docker/`
- `.env.example`
- `docs/deployment.md`

交付物：

- 后端 Dockerfile
- 前端 Dockerfile
- Nginx 配置
- SQLite 数据卷
- PostgreSQL 可选配置
- Ollama 可选服务
- 备份脚本

验收标准：

- `docker compose up` 后系统可访问。
- 数据持久化。
- 重启后数据不丢失。

## ✅ 任务 T：测试与质量保障（已完成）

适合窗口：测试开发。

目标：

- 建立后端、前端、端到端测试。

负责范围：

- `backend/app/tests/`
- `frontend/src/**/*.spec.ts`
- `e2e/`

交付物：

- 后端单元测试
- 后端接口测试
- 前端组件测试
- 基础 E2E 测试
- 测试数据工厂

验收标准：

- 登录流程通过。
- 图书 CRUD 流程通过。
- 分类、位置流程通过。
- 智能检索失败场景有测试。

## 8. 接口契约优先级

并行开发最容易冲突的地方是接口。建议先完成以下文档：

1. `docs/api-contract.md`
2. `docs/database-schema.md`
3. `docs/frontend-spec.md`

最小接口契约必须定义：

- 请求路径
- 请求方法
- 请求参数
- 请求体
- 响应体
- 错误格式
- 权限要求

统一错误格式：

```json
{
  "error": {
    "code": "BOOK_NOT_FOUND",
    "message": "图书不存在",
    "details": {}
  }
}
```

分页响应格式：

```json
{
  "items": [],
  "total": 0,
  "page": 1,
  "pageSize": 20
}
```

## 9. 子任务输出模板

每个开发窗口完成子任务后，应输出以下内容：

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

## 10. 总控窗口汇总流程

本窗口后续只执行开发汇总，建议按以下流程操作：

1. 收集子任务输出。
2. 检查是否修改了公共接口。
3. 合并数据库迁移。
4. 合并后端服务。
5. 合并前端页面。
6. 运行后端测试。
7. 运行前端构建。
8. 运行端到端关键流程。
9. 更新 README 和开发文档。
10. 形成阶段性验收报告。

## 11. 建议并行启动顺序

第一批并行任务：

- A：项目骨架与公共规范
- B：后端基础框架
- C：数据库模型与迁移
- L：前端基础框架

第二批并行任务：

- D：认证与用户管理
- E：图书 CRUD 后端
- F：分类与位置后端
- M：前端图书管理界面
- N：前端分类与位置管理

第三批并行任务：

- G：外部书籍检索后端
- H：Ollama 智能能力后端
- O：前端智能检索与 AI 入库

第四批并行任务：

- I：借阅与阅读后端
- J：统计后端
- K：导入导出后端
- P：前端借阅与阅读界面
- Q：前端仪表盘与统计页

第五批并行任务：

- R：系统设置与用户管理前端
- S：部署与运维
- T：测试与质量保障

## 12. 当前窗口后续职责

本窗口作为总控和汇总窗口，不建议直接承担大块功能开发。建议职责为：

- 接收其他窗口的实现结果
- 检查代码结构和接口一致性
- 合并冲突
- 统一命名和格式
- 补齐文档
- 运行全量测试
- 生成下一阶段任务
- 推送主仓库

## 13. 给子任务窗口的通用提示词

可复制以下提示词给新的 AI 开发窗口：

```text
你正在参与 Home Library 家庭藏书管理系统的并行开发。
请先阅读 docs/home-library-web-app-plan.md 和 docs/parallel-development-plan.md。
你只负责任务【填写任务编号和名称】。
请不要修改与你任务无关的模块。
如需调整公共 API、数据库字段或目录结构，请在输出中明确说明。
完成后请按以下格式汇报：
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
