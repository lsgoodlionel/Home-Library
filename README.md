# Home Library — 家藏书库

面向家庭场景的轻量级藏书管理系统。记录藏书信息、精确定位书架位置、支持网络检索补全、通过本地 Ollama 模型辅助分类与标签生成。

## 功能概览

- ✅ 图书增删改查，支持手动录入、ISBN 查询、书名联网检索
- ✅ 简化中图法分类体系（一级 + 常用二级），支持自定义扩展
- ✅ 四层位置管理：房间 / 书架 / 层数 / 具体位置
- ✅ 用户登录与角色权限（管理员 / 普通用户 / 访客）
- ✅ 接入 Open Library、Google Books 等外部数据源
- ✅ 调用本地 Ollama 模型完成分类推荐、标签生成、摘要整理、重复检测、自然语言解析
- ✅ 借阅管理、归还记录、阅读状态与阅读笔记
- ✅ CSV / Excel / JSON 导入导出，含导入预览、字段映射和错误报告
- ✅ 首页仪表盘、统计分析页和轻量图表
- ✅ 用户管理页、系统设置页、Docker Compose 部署、备份脚本和测试体系

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Vue 3 + TypeScript + Vite + Element Plus + Pinia |
| 后端 | FastAPI + SQLAlchemy + Pydantic |
| 数据库 | SQLite（MVP），可切换 PostgreSQL |
| 认证 | JWT Bearer Token |
| AI | Ollama HTTP API（本地模型） |
| 搜索 | SQLite FTS5，后续可扩展向量检索 |
| 部署 | Docker Compose |

## 目录结构

```text
Home-Library/
├── README.md                  本文件
├── .env.example               环境变量模板（含注释说明）
├── .gitignore
├── .editorconfig
├── docker-compose.yml         Docker Compose 编排
├── e2e/                       Playwright E2E 冒烟测试
├── scripts/                   运维脚本（备份等）
│
├── docs/                      项目文档
│   ├── DOCS_INDEX.md          文档索引
│   ├── home-library-web-app-plan.md    完整产品方案
│   ├── parallel-development-plan.md   并行开发分工计划
│   ├── api-contract.md        前后端 API 契约
│   ├── database-schema.md     数据库表结构
│   ├── frontend-spec.md       前端开发规范
│   ├── first-wave-task-briefs.md      第一批任务领取说明
│   ├── development.md         本地开发流程
│   ├── deployment.md          Docker / NAS 部署与备份恢复
│   └── contributing.md        并行开发协作规则
│
├── backend/                   FastAPI 后端
│   ├── app/
│   │   ├── api/               路由层（各模块 router）
│   │   ├── core/              配置、安全、依赖
│   │   ├── db/                数据库连接与初始化
│   │   ├── models/            SQLAlchemy 模型
│   │   ├── schemas/           Pydantic schema
│   │   ├── services/          业务逻辑层
│   │   ├── prompts/           Ollama Prompt 模板
│   │   └── tests/             后端测试
│   ├── alembic/               数据库迁移
│   ├── pyproject.toml         Python 依赖
│   └── README.md
│
├── frontend/                  Vue 3 前端
│   ├── src/
│   │   ├── api/               API 客户端（按模块拆分）
│   │   ├── assets/            静态资源
│   │   ├── components/        公共组件
│   │   ├── layouts/           页面布局
│   │   ├── pages/             页面（按路由组织）
│   │   ├── router/            Vue Router 配置
│   │   ├── stores/            Pinia 状态管理
│   │   ├── styles/            全局样式
│   │   └── types/             TypeScript 类型定义
│   ├── package.json
│   ├── package-lock.json
│   ├── playwright.config.ts
│   ├── vitest.config.ts
│   └── README.md
│
└── docker/                    Dockerfile 与 Nginx 配置
```

## 快速开始

### 前提条件

- Python 3.11+
- Node.js 20+
- [Ollama](https://ollama.ai)（可选，用于 AI 功能）

### 1. 复制环境变量

```bash
cp .env.example .env
# 按需修改 .env 中的配置
```

### 2. 启动后端

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

健康检查：`GET http://127.0.0.1:8000/api/health`

### 3. 启动前端

```bash
cd frontend
npm install
npm run dev
```

默认访问 `http://localhost:5173`

### 4. 启动 Ollama（可选）

```bash
ollama serve
ollama pull qwen2.5   # 推荐中文模型
```

### Docker Compose

```bash
cp .env.example .env
docker compose up -d --build
curl http://localhost/api/health
```

默认使用宿主机 `80` 端口；如端口被占用，在 `.env` 中设置 `HTTP_PORT=8080`。完整部署、NAS、备份和恢复说明见 [`docs/deployment.md`](docs/deployment.md)。

## 测试与质量

```bash
cd backend
uv run pytest

cd ../frontend
npm install
npm run typecheck
npm run build
npm run test
npm run test:e2e
```

当前收尾验证结果：

| 检查项 | 结果 |
|---|---|
| 后端全量测试 | `145 passed, 1 warning` |
| 前端类型检查 | 通过 |
| 前端构建 | 通过，仅 Vite chunk size warning |
| Vitest | `1 passed / 3 tests passed` |
| Playwright E2E | `3 passed` |

## 环境变量

详见 [`.env.example`](.env.example)，完整说明见 [`docs/development.md`](docs/development.md)。

## 文档

| 文档 | 说明 |
|---|---|
| [完整产品方案](docs/home-library-web-app-plan.md) | 功能、角色、数据模型、API 设计 |
| [并行开发分工](docs/parallel-development-plan.md) | 任务拆分、分支策略、协作规则 |
| [API 契约](docs/api-contract.md) | 前后端接口协议 |
| [数据库设计](docs/database-schema.md) | 表结构与关系 |
| [前端规范](docs/frontend-spec.md) | 组件、目录、类型约定 |
| [本地开发流程](docs/development.md) | 环境搭建、命令参考 |
| [协作规则](docs/contributing.md) | 分支管理、汇报模板 |
| [文档索引](docs/DOCS_INDEX.md) | 所有文档入口 |

## 开发分工

本项目采用并行开发模式，各任务独立进行。详见 [`docs/parallel-development-plan.md`](docs/parallel-development-plan.md) 和 [`docs/contributing.md`](docs/contributing.md)。

### A-T 完成状态

所有 A-T 子任务均已完成并集成到 `main`：

| 批次 | 任务 | 状态 |
|---|---|---|
| 基础 | A 项目骨架、B 后端基础、C 数据库模型、L 前端基础 | ✅ 已完成 |
| 核心业务 | D 认证、E 图书、F 分类位置、M 图书前端、N 分类位置前端 | ✅ 已完成 |
| 智能能力 | G 外部检索、H Ollama 后端、O 智能入库前端 | ✅ 已完成 |
| 增强功能 | I 借阅阅读后端、J 统计后端、K 导入导出、P 借阅阅读前端、Q 仪表盘统计前端 | ✅ 已完成 |
| 收尾 | R 用户设置前端、S 部署运维、T 测试质量 | ✅ 已完成 |

### 主要提交记录

- `a16ece5` Task R: add frontend users and settings pages
- `bf01d53` Task S: add Docker deployment and operations docs
- `e38129c` Task T: add test and quality coverage
- 本次收尾提交：锁定 `frontend/package-lock.json`，更新 A-T 完成标记、产品方案实现状态和 README

## 许可证

家庭内部使用项目，暂未设置开源协议。
