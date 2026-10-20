# Home Library — 家藏书库

面向家庭场景的轻量级藏书管理系统。记录藏书信息、精确定位书架位置、支持网络检索补全，并通过本地或远程 Ollama 模型辅助分类与标签生成。

## 功能概览

- ✅ 图书增删改查，支持手动录入、ISBN 查询、书名联网检索
- ✅ 完整中图法分类体系：22 大类 + 213 二级 + 520 三级，共 755 个类目
- ✅ 四层位置管理：房间 / 书架 / 层数 / 具体位置
- ✅ 用户登录与角色权限（管理员 / 普通用户 / 访客）
- ✅ 接入 Open Library、Google Books 等外部数据源
- ✅ 调用本地或 Cloudflare Access 保护的远程 Ollama 完成分类推荐、标签生成、摘要整理、重复检测、自然语言解析
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
| AI | Ollama HTTP API（本地或远程模型，支持 Cloudflare Access） |
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
├── scripts/                   运维脚本
│   ├── deploy.sh              Linux / macOS / 群晖 一键部署
│   ├── deploy.ps1             Windows 一键部署（PowerShell）
│   ├── update.sh              Linux / macOS / 群晖 智能更新
│   ├── update.ps1             Windows 智能更新（PowerShell）
│   ├── auto-update-setup.sh   配置定时自动更新（systemd/cron/launchd）
│   └── backup.sh              数据库与文件备份
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

## 一键部署

> 基于 Docker，**无需手动安装依赖**，支持主流服务器和 NAS。

### Ubuntu / Debian / CentOS（自动安装 Docker）

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/lsgoodlionel/Home-Library/main/scripts/deploy.sh)
```

自定义端口和管理员密码：

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/lsgoodlionel/Home-Library/main/scripts/deploy.sh) \
  -p 8080 -u admin -w "MyPass123"
```

### macOS

```bash
# 需先安装 Docker Desktop，建议用 8080（80 需 root）
bash <(curl -fsSL https://raw.githubusercontent.com/lsgoodlionel/Home-Library/main/scripts/deploy.sh) -p 8080
```

### Windows（PowerShell 管理员）

```powershell
irm https://raw.githubusercontent.com/lsgoodlionel/Home-Library/main/scripts/deploy.ps1 | iex
```

### 群晖 NAS

- **图形界面**：Container Manager → 项目 → 导入 `docker-compose.yml` 和 `.env`
- **SSH 命令行**：同 Linux 脚本，加 `-d` 参数

> 完整说明、参数列表和常见问题见 [`docs/deploy.md`](docs/deploy.md)

---

## 更新

### 手动一键更新

```bash
# Linux / macOS / 群晖
bash ~/home-library/scripts/update.sh

# Windows
.\scripts\update.ps1
```

更新流程：检查新版本 → 备份数据库 → 拉取代码 → 重建镜像 → 健康检查（失败自动回滚）

### 配置自动更新（定时）

```bash
# Linux / macOS：默认每天凌晨 3 点，自动选择 systemd timer / cron / launchd
bash ~/home-library/scripts/auto-update-setup.sh

# 自定义时间（每天 2:30）
bash ~/home-library/scripts/auto-update-setup.sh --interval "30 2 * * *"

# Windows：注册任务计划
.\scripts\update.ps1 -SetupAuto -AutoTime "03:00"
```

> 支持企业微信 / 钉钉 / Slack 更新通知，详见 [`docs/deploy.md`](docs/deploy.md#更新与自动更新)

### 故障诊断与自动修复

如果 Ubuntu 服务器上原本已经部署成功，但现在页面打不开，可执行一键诊断修复脚本：

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/lsgoodlionel/Home-Library/main/scripts/doctor.sh)
```

如果脚本未能自动定位部署目录，手动指定项目目录：

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/lsgoodlionel/Home-Library/main/scripts/doctor.sh) /opt/Home-Library
```

脚本会检查 Docker、Compose、部署目录、`.env` 配置摘要、Git 版本、容器状态、健康接口和最近日志，并尝试非破坏性恢复运行状态：

- `docker compose up -d --remove-orphans`
- 健康检查失败后再执行 `docker compose up -d --build --remove-orphans`

脚本不会删除数据库、不会删除 Docker volume，执行过程会生成 `home-library-doctor-*.log` 日志文件，便于继续排查。

---

## 本地开发

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

### 4. 配置 Ollama（可选）

默认 AI 开关关闭，不影响登录、藏书、借阅、统计、备份等核心功能。本地开发可启动 Ollama：

```bash
ollama serve
ollama pull qwen3.5:4b
```

然后在 `.env` 设置 `OLLAMA_ENABLED=true` 和 `OLLAMA_BASE_URL=http://127.0.0.1:11434`。Docker 访问宿主机或 Compose profile 时改用 `DOCKER_OLLAMA_BASE_URL`。

远程模式当前默认地址为 `https://openclaw.lsgood.cn`。Cloudflare Access 的 Client ID/Secret 只允许写入服务器环境变量，禁止放入 `VITE_*`、前端设置或仓库；`OLLAMA_TRUSTED_BASE_URL` 独立限定可携带凭据的 HTTPS Origin，HTTP、本地名称和 IP 地址始终不携带凭据。`ollama.lsgood.cn` 当前不可作为默认地址。管理员可在“设置 > AI 模型配置”检查连接，生成测试需要再次确认。

只读远程连通性验证（仅访问 version/tags/ps，不触发生成）。脚本只在
`OLLAMA_BASE_URL` 与 `OLLAMA_TRUSTED_BASE_URL` 的规范化 Origin 完全一致时发送
Access headers：

```bash
bash scripts/ollama-cloudflare-smoke-test.sh
```

GitHub 的 `Build & Release` workflow 会先运行后端 pytest、前端 Vitest、类型检查、生产构建、脚本安全测试和普通 Compose 配置展开；全部通过后才构建并推送前后端 multi-arch GHCR 镜像。Release Git tag 必须是 `vMAJOR.MINOR.PATCH`，可带合法 prerelease；`prepare` 会去掉前导 `v`，例如将 `v1.2.3-rc.1` 映射为应用版本和 GHCR 镜像 tag `1.2.3-rc.1`，与 `VERSION=1.2.3-rc.1`、`update.sh --version 1.2.3-rc.1` 保持一致。两个镜像成功后才创建带部署资产的 Release。同一分支或 tag 的旧 run 会自动取消，不同 tag 互不影响。

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

当前分支验证结果：

| 检查项 | 结果 |
|---|---|
| 后端全量测试 | `361 passed, 0 failed`（2026-10-20） |
| AI 并发探针收尾 | 18 项回归通过：逐个探针失败、意外异常、调用方取消及取消清理异常；退出前取消并等待全部任务，取回异常 |
| AI 健康错误 traceback | 14 项真实客户端回归通过：检查函数及两个健康入口、全部 7 个探针失败位置；遍历任务结果、异常帧和 coroutine 引用，合成凭据与响应体标记不可达 |
| AI owner 取消 traceback | 16 项真实客户端回归通过：3/4 探针、单次/重复取消、清理正常/异常、owner 先取消/上游先失败后取消；全 frame locals、Task/Future、coroutine 和对象属性递归检查，runtime、client、Access headers/凭据不可达，缓存保持不变 |
| 前端类型检查 | 通过 |
| 前端构建 | 通过，仅 Vite chunk size warning |
| Vitest | `8 files / 42 tests passed` |
| 发布脚本测试 | AI 超时层级、smoke Origin 安全矩阵和 SemVer tag 解析通过 |
| Compose 配置 | 开发、生产配置均以临时 `.env` 普通展开通过 |
| Docker 隔离流程 | 2026-10-20 在当前交付代码的回环端口隔离 Compose 项目中通过 12 项真实 HTTP 验收：前端首页、公共健康、管理员登录/账号、图书列表、AI 配置脱敏、登录要求、AI 关闭降级、成员健康可见/管理员测试禁止，以及 AI 失败后核心健康与图书功能继续可用 |

2026-10-20 健康取消路径复验：持有敏感状态的内部函数完成取消与 drain 后，将原始取消转换为无敏感引用的安全标记；外层清除数据库和账号引用，再抛出无参、无原始异常链的 `CancelledError`。重复 owner 取消不会打断同一个受保护的 drain。预期上游错误仍使用既有中文分类与缓存逻辑；六个 AI 业务 route 的隔离回归通过。该结论覆盖已测的取消及预期上游失败路径，不代表任意 Python 反射和全局引用的形式化去敏证明；真实远程 Access 认证成功仍待凭据可用后验证。

Release workflow 不跳过测试或放宽业务断言。借阅测试使用相对日期，分类统计按图书直接所属分类精确计数，版本接口测试跟随动态应用版本，因此当前完整后端门禁为零失败。

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
| [部署与更新指南](docs/deploy.md) | 一键部署、自动更新、常见问题 |
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
