# 并行开发协作规则

## 开发模式

本项目采用多窗口/多 AI 应用并行开发模式。每个子任务在独立窗口或独立分支中推进，由总控窗口统一汇总、集成和验收。

## 任务分工总览

| 任务 | 名称 | 主要范围 |
|---|---|---|
| A | 项目骨架与公共规范 | README、docs、.env.example |
| B | 后端基础框架 | FastAPI 启动、CORS、健康检查 |
| C | 数据库模型与迁移 | SQLAlchemy 模型、Pydantic schema、种子数据 |
| D | 认证与用户管理 | JWT、登录、权限依赖 |
| E | 图书 CRUD 后端 | 图书增删改查 API |
| F | 分类与位置后端 | 分类树、位置管理 API |
| G | 外部书籍检索后端 | Open Library、Google Books 接入 |
| H | Ollama 智能能力后端 | 分类推荐、标签生成、重复检测 |
| I | 借阅与阅读后端 | 借阅记录、阅读笔记 API |
| J | 统计后端 | 仪表盘统计接口 |
| K | 导入导出后端 | CSV / Excel / JSON 导入导出 |
| L | 前端基础框架 | Vue Router、Pinia、API client、主布局 |
| M | 前端图书管理界面 | 图书列表、详情、表单 |
| N | 前端分类与位置管理 | 分类树、位置管理页 |
| O | 前端智能检索与 AI 入库 | ISBN 检索、Ollama 推荐 |
| P | 前端借阅与阅读界面 | 借阅表单、阅读笔记编辑 |
| Q | 前端仪表盘与统计 | ECharts 图表、统计页 |
| R | 系统设置与用户管理前端 | 用户管理、系统设置页 |
| S | 部署与运维 | Docker Compose、备份脚本 |
| T | 测试与质量保障 | 后端测试、前端测试、E2E |

## 协作规则

### 1. 只改自己的范围

- 每个任务只修改 [`docs/parallel-development-plan.md`](parallel-development-plan.md) 中对应任务"负责范围"内的文件。
- 不得随意修改其他任务的文件。如确实需要跨范围修改，必须在汇报中明确说明，并等待总控窗口确认。

### 2. 接口契约优先

- 修改任何 API 路径、请求体、响应体格式前，必须先更新 [`docs/api-contract.md`](api-contract.md)。
- 后端实现以 `docs/api-contract.md` 为最低标准；前端以该文档作为请求和响应类型来源。
- 不能绕过接口文档直接与其他任务的实现耦合。

### 3. 命名约定

| 场景 | 风格 | 示例 |
|---|---|---|
| 数据库字段 | `snake_case` | `publish_year`, `created_at` |
| Python 变量/函数 | `snake_case` | `get_book_by_id` |
| TypeScript 变量/函数 | `camelCase` | `getBookById` |
| TypeScript 类型/接口 | `PascalCase` | `BookDetail` |
| API 响应 JSON 字段 | `snake_case` | `page_size` |
| Vue 组件文件名 | `PascalCase` | `BookCard.vue` |

### 4. 数据约定

- 时间字段：ISO 8601 含时区字符串（`2026-05-03T10:00:00+08:00`）
- 金额：后端存整数分（`price_cents: int`），前端展示时除以 100
- ISBN：保存清洗后的纯数字字符串（去掉连字符）
- 所有 AI 输出必须经过 JSON Schema 校验，不能直接信任模型文本

### 5. 分支策略

```text
main          生产就绪代码
dev           集成分支，总控窗口维护
feature/      各子任务功能分支
```

子任务建议在对应分支开发：

```text
feature/backend-foundation   任务 B
feature/db-models            任务 C
feature/auth                 任务 D
feature/books-crud           任务 E
feature/categories-locations 任务 F
feature/search-external      任务 G
feature/search-ai            任务 H
feature/borrow-reading       任务 I
feature/stats                任务 J
feature/import-export        任务 K
feature/frontend-foundation  任务 L
feature/frontend-books       任务 M
feature/frontend-categories  任务 N
feature/frontend-ai          任务 O
feature/frontend-borrow      任务 P
feature/frontend-stats       任务 Q
feature/frontend-settings    任务 R
feature/docker-deploy        任务 S
feature/tests                任务 T
```

### 6. 提交信息

格式：`<type>(<scope>): <summary>`

| type | 含义 |
|---|---|
| feat | 新功能 |
| fix | 修复 bug |
| docs | 文档 |
| chore | 构建、配置、依赖 |
| refactor | 重构（不改功能） |
| test | 测试 |

示例：
```
feat(books): add book CRUD endpoints
docs(readme): update development guide
chore(deps): add FastAPI dependency
```

### 7. 向总控窗口汇报

完成子任务后，使用以下模板汇报：

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

## 总控窗口职责

总控窗口不直接实现业务功能，负责：

1. 收集并审查各子任务输出
2. 检查接口变更是否与契约一致
3. 合并数据库迁移（防止版本冲突）
4. 合并各分支代码到 `dev`
5. 处理跨任务命名冲突
6. 运行全量测试
7. 维护 README 和文档索引
8. 生成下一批任务说明

## 并行启动顺序

```text
第一批（当前）：A（骨架）、B（后端框架）、C（数据库）、L（前端框架）
第二批：D（认证）、E（图书 CRUD）、F（分类位置）、M（前端图书）、N（前端分类位置）
第三批：G（外部检索）、H（Ollama AI）、O（前端 AI 入库）
第四批：I（借阅阅读）、J（统计）、K（导入导出）、P（前端借阅）、Q（前端统计）
第五批：R（前端设置）、S（部署）、T（测试）
```

每一批任务需等待前一批中依赖模块（数据库模型、认证框架、基础框架）完成后再启动。
