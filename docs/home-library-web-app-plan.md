# 家庭藏书管理系统 Web 应用开发方案

## 1. 项目定位

系统名称暂定为 **Home Library / 家藏书库**。

项目目标是开发一套面向家庭场景的轻量级藏书管理系统，用来记录家庭藏书的分类、名称、作者、ISBN、出版社、购买信息、阅读状态、借阅状态和实际摆放位置。系统参考《中国图书馆分类法》建立简化分类体系，并结合网络检索与本地 Ollama 模型完成图书信息补全、分类推荐、标签生成和自然语言查询。

系统定位不是大型公共图书馆系统，而是家庭版图书馆管理工具，设计重点是：

- 录入方便
- 查找快速
- 分类清晰
- 位置准确
- 数据可备份
- 本地智能辅助
- 易部署、易维护

## 2. 核心目标

1. 管理家庭藏书基础信息。
2. 按简化中图法和自定义分类管理书籍。
3. 精确记录书籍所在房间、书架、层数和具体位置。
4. 支持用户登录、角色和基础权限控制。
5. 支持 ISBN、书名、书名加作者联网检索书籍信息。
6. 支持调用本地 Ollama 模型辅助生成分类、标签、摘要和重复判断。
7. 支持借阅、归还、阅读记录和笔记。
8. 支持导入、导出、备份和恢复。
9. 支持后续扩展移动端、扫码、二维码标签和自然语言搜索。

## 3. 用户角色

### 3.1 管理员

- 创建、编辑、禁用用户
- 管理全部图书
- 管理分类体系
- 管理房间、书架和位置
- 配置外部检索数据源
- 配置 Ollama 地址和模型
- 导入、导出、备份、恢复数据
- 查看统计分析

### 3.2 普通家庭成员

- 查看藏书
- 搜索藏书
- 新增图书
- 编辑自己录入的图书
- 标记阅读状态
- 创建阅读笔记
- 标记借出、归还
- 收藏图书

### 3.3 访客

访客角色为可选设计。

- 只读查看允许公开的藏书
- 不允许新增、编辑、删除数据
- 不允许查看系统设置和用户管理

## 4. 权限模型

| 功能 | 管理员 | 普通用户 | 访客 |
| --- | --- | --- | --- |
| 查看藏书 | 是 | 是 | 可选 |
| 新增图书 | 是 | 是 | 否 |
| 编辑图书 | 是 | 自己录入或授权范围 | 否 |
| 删除图书 | 是 | 否 | 否 |
| 分类管理 | 是 | 否 | 否 |
| 位置管理 | 是 | 否 | 否 |
| 借阅管理 | 是 | 是 | 否 |
| 阅读笔记 | 是 | 是 | 否 |
| 用户管理 | 是 | 否 | 否 |
| 系统设置 | 是 | 否 | 否 |
| 数据导入导出 | 是 | 可选 | 否 |

## 5. 功能模块

### 5.1 用户登录与账户管理

功能范围：

- 登录
- 退出登录
- 获取当前用户
- 修改密码
- 管理员创建用户
- 管理员修改用户角色
- 用户启用、禁用
- 登录失败限流
- 会话过期处理

认证建议：

- MVP 阶段使用 JWT Bearer Token。
- 密码使用 `bcrypt` 或 `argon2` 哈希。
- 管理员初始账号首次登录强制修改密码。

### 5.2 图书基础信息管理

每本书建议包含以下信息。

基础书目信息：

- 图书 ID
- 书名
- 副标题
- 作者
- 译者
- 出版社
- 出版年份
- ISBN
- 语言
- 页数
- 定价
- 装帧
- 丛书名
- 版本信息
- 封面图片
- 内容简介
- 作者简介

家庭管理信息：

- 分类号
- 分类名称
- 标签
- 所在房间
- 所在书架
- 所在层
- 具体位置
- 入库日期
- 购买日期
- 购买渠道
- 购买价格
- 图书状态：在架、借出、遗失、待整理、已转赠
- 阅读状态：未读、阅读中、已读、暂停
- 是否重点收藏
- 评分
- 备注

系统信息：

- 创建人
- 创建时间
- 最后修改人
- 最后修改时间
- 数据来源：手动录入、ISBN 查询、书名检索、Ollama 生成、批量导入

### 5.3 简化中图法分类管理

系统内置一套简化中图法一级分类：

| 分类号 | 分类名称 |
| --- | --- |
| A | 马克思主义、列宁主义、毛泽东思想、邓小平理论 |
| B | 哲学、宗教 |
| C | 社会科学总论 |
| D | 政治、法律 |
| E | 军事 |
| F | 经济 |
| G | 文化、科学、教育、体育 |
| H | 语言、文字 |
| I | 文学 |
| J | 艺术 |
| K | 历史、地理 |
| N | 自然科学总论 |
| O | 数理科学和化学 |
| P | 天文学、地球科学 |
| Q | 生物科学 |
| R | 医药、卫生 |
| S | 农业科学 |
| T | 工业技术 |
| U | 交通运输 |
| V | 航空、航天 |
| X | 环境科学、安全科学 |
| Z | 综合性图书 |

建议内置常用二级分类：

| 分类号 | 分类名称 |
| --- | --- |
| B2 | 中国哲学 |
| B5 | 西方哲学 |
| C91 | 社会学 |
| D9 | 法律 |
| F0 | 经济学 |
| F8 | 金融、投资 |
| G4 | 教育 |
| G6 | 儿童教育 |
| H3 | 外语学习 |
| I2 | 中国文学 |
| I3 | 亚洲文学 |
| I5 | 欧洲文学 |
| I7 | 美洲文学 |
| J2 | 绘画 |
| J6 | 音乐 |
| K2 | 中国历史 |
| K5 | 世界历史 |
| O1 | 数学 |
| Q | 生物科学 |
| R2 | 中医 |
| R4 | 临床医学 |
| T9 | 计算机技术 |
| Z1 | 丛书、文库 |

分类功能：

- 分类树展示
- 新增分类
- 编辑分类
- 删除未使用分类
- 合并分类
- 分类排序
- 系统分类锁定
- 自定义分类扩展
- 批量修改图书分类
- Ollama 推荐分类

### 5.4 位置管理

家庭藏书管理的核心是找得到书。

位置模型建议采用四层结构：

```text
房间 / 书架 / 层数 / 具体位置
```

示例：

```text
书房 / A 架 / 第 3 层 / 右侧
客厅 / 电视柜 / 第 1 层 / 左侧
儿童房 / 绘本架 / 第 2 层 / 中间
```

功能：

- 房间管理
- 书架管理
- 层位管理
- 具体位置说明
- 位置完整路径自动生成
- 按位置筛选图书
- 批量移动图书
- 位置变更记录

后续扩展：

- 位置二维码
- 图书二维码标签
- 手机扫码定位
- 盘点模式

### 5.5 图书录入

#### 手动录入

用户填写书名、作者、分类、位置等字段。

适合：

- 旧书
- 内部资料
- 无 ISBN 图书
- 影印本
- 手稿、资料册

#### ISBN 录入

输入 ISBN 后，系统自动联网查询：

- 书名
- 作者
- 出版社
- 出版日期
- ISBN
- 封面
- 简介
- 页数
- 定价

#### 书名检索录入

用户输入：

```text
乡土中国
```

或：

```text
乡土中国 费孝通
```

系统返回候选图书列表，用户选择正确版本后导入。

#### 批量导入

支持 CSV、Excel、JSON。

CSV 示例：

```csv
书名,作者,ISBN,分类号,房间,书架,层数,备注
乡土中国,费孝通,9787108069425,C91,书房,A架,第2层,社会学经典
```

### 5.6 网络检索与信息补全

检索输入：

- ISBN
- 书名
- 书名 + 作者
- 书名 + 出版社

可接入数据源：

- Open Library API
- Google Books API
- 出版社官网
- 国家图书馆或公开 ISBN 数据源
- 普通搜索引擎结果摘要
- 豆瓣读书页面检索，需注意合规和访问限制

推荐流程：

1. 用户输入查询词。
2. 后端调用多个数据源。
3. 统一归一化字段。
4. 返回候选书籍。
5. 用户选择版本。
6. 系统导入并补全字段。
7. Ollama 生成分类、标签和简介整理建议。

候选结果字段：

- 封面
- 书名
- 作者
- 出版社
- 出版年份
- ISBN
- 简介摘要
- 数据来源

### 5.7 Ollama 本地模型集成

后端通过 HTTP 调用本地 Ollama：

```text
POST http://localhost:11434/api/chat
POST http://localhost:11434/api/generate
GET  http://localhost:11434/api/tags
```

推荐模型：

- `qwen2.5`
- `qwen3`
- `llama3.1`
- `gemma`
- `deepseek-r1`
- `mistral`

中文书籍分类优先推荐 Qwen 系列。

Ollama 任务：

- 简化中图法分类推荐
- 标签生成
- 内容简介整理
- 作者信息整理
- 重复图书判断
- 自然语言搜索解析
- 摆放位置建议
- 相关书推荐

分类推荐输出：

```json
{
  "categoryCode": "C91",
  "categoryName": "社会学",
  "confidence": 0.86,
  "tags": ["社会学", "中国乡村", "人类学", "经典著作"],
  "reason": "该书主要讨论乡村社会结构与社会关系，适合归入社会学。"
}
```

### 5.8 搜索功能

普通搜索字段：

- 书名
- 作者
- ISBN
- 出版社
- 标签
- 分类
- 位置
- 备注

高级筛选：

- 分类
- 作者
- 出版年份
- 入库时间
- 是否已读
- 是否借出
- 所在房间
- 所在书架
- 是否重点收藏

自然语言搜索示例：

```text
找一下家里关于中国社会学的书
费孝通写的书在哪里？
有没有儿童心理学相关的书？
```

MVP 阶段可使用数据库关键词检索和 SQLite FTS5。后续可加入向量检索。

### 5.9 借阅管理

功能：

- 标记借出
- 标记归还
- 查看当前借出
- 查看历史借阅
- 超期提醒
- 借阅备注

字段：

- 图书
- 借阅人
- 联系方式
- 借出日期
- 预计归还日期
- 实际归还日期
- 状态
- 备注

### 5.10 阅读记录与笔记

功能：

- 标记未读、阅读中、已读、暂停
- 阅读开始日期
- 阅读完成日期
- 阅读进度
- 评分
- 摘录
- 阅读笔记
- 读后感
- Markdown 笔记

后续扩展：

- 图片笔记
- 引文管理
- 电子书文件关联
- 年度阅读报告

### 5.11 统计分析

统计项：

- 总藏书数量
- 分类分布
- 作者排行
- 出版年代分布
- 房间分布
- 书架分布
- 已读数量
- 未读数量
- 借出数量
- 年度购书数量
- 年度阅读数量
- 重点收藏数量

图表：

- 分类饼图
- 年份柱状图
- 书架分布图
- 阅读趋势折线图
- 作者排行条形图

### 5.12 导入导出、备份恢复

导入：

- CSV
- Excel
- JSON

导入流程：

1. 上传文件
2. 字段映射
3. 数据预览
4. 重复检测
5. 错误提示
6. 确认导入

导出：

- CSV
- Excel
- JSON
- PDF 书单，后续扩展

备份包结构：

```text
backup-2026-05-03.zip
  database.sqlite
  covers/
  config.json
  export-books.json
```

## 6. 页面结构

1. 登录页
2. 首页仪表盘
3. 图书列表页
4. 图书详情页
5. 新增、编辑图书页
6. 智能检索入库页
7. 分类管理页
8. 位置管理页
9. 借阅管理页
10. 阅读笔记页
11. 统计分析页
12. 用户管理页
13. 系统设置页

## 7. 技术架构

推荐技术栈：

```text
前端：Vue 3 + TypeScript + Vite + Element Plus
后端：FastAPI + SQLAlchemy + Pydantic
数据库：SQLite，后续可切换 PostgreSQL
认证：JWT
AI：Ollama HTTP API
搜索：SQLite FTS5，后续可扩展向量检索
部署：Docker Compose
```

整体架构：

```text
Vue Web 前端
  |
FastAPI 后端服务
  |
SQLite / PostgreSQL
  |
外部书籍信息 API
  |
本地 Ollama 服务
```

## 8. 数据库设计

### users

```text
id
username
password_hash
display_name
role
email
status
created_at
updated_at
last_login_at
```

### books

```text
id
title
subtitle
author
translator
publisher
publish_year
isbn
language
pages
price
binding
series
cover_url
summary
author_intro
category_id
location_id
status
read_status
rating
is_favorite
source
created_by
created_at
updated_at
```

### categories

```text
id
code
name
parent_id
description
sort_order
is_system
created_at
updated_at
```

### locations

```text
id
room
shelf
layer
position
description
sort_order
created_at
updated_at
```

### tags

```text
id
name
color
created_at
```

### book_tags

```text
book_id
tag_id
```

### borrow_records

```text
id
book_id
borrower_name
borrower_contact
borrowed_at
due_at
returned_at
status
note
created_by
created_at
updated_at
```

### reading_notes

```text
id
book_id
user_id
title
content
progress
rating
started_at
finished_at
created_at
updated_at
```

### external_book_results

```text
id
query
source
raw_data
normalized_data
created_at
```

### ai_tasks

```text
id
task_type
input
output
model
status
created_at
updated_at
```

## 9. API 设计

### 认证与用户

```text
POST /api/auth/login
POST /api/auth/logout
GET  /api/auth/me
POST /api/users
GET  /api/users
PATCH /api/users/{id}
DELETE /api/users/{id}
```

### 图书

```text
GET    /api/books
GET    /api/books/{id}
POST   /api/books
PATCH  /api/books/{id}
DELETE /api/books/{id}
POST   /api/books/batch-update
POST   /api/books/import
GET    /api/books/export
```

### 分类

```text
GET    /api/categories
POST   /api/categories
PATCH  /api/categories/{id}
DELETE /api/categories/{id}
```

### 位置

```text
GET    /api/locations
POST   /api/locations
PATCH  /api/locations/{id}
DELETE /api/locations/{id}
```

### 外部检索

```text
GET  /api/search/books?query=
GET  /api/search/isbn/{isbn}
POST /api/search/import-result
```

### AI

```text
POST /api/ai/classify-book
POST /api/ai/generate-tags
POST /api/ai/summarize-book
POST /api/ai/detect-duplicate
POST /api/ai/natural-search
```

### 借阅

```text
POST /api/borrow
POST /api/borrow/{id}/return
GET  /api/borrow/records
GET  /api/borrow/active
```

### 统计

```text
GET /api/stats/overview
GET /api/stats/categories
GET /api/stats/locations
GET /api/stats/reading
GET /api/stats/timeline
```

## 10. Ollama Prompt 设计

### 分类推荐

```text
你是一个家庭藏书管理系统的图书分类助手。
请参考中国图书馆分类法的简化分类体系，为下面这本书推荐一个分类。

书名：{title}
作者：{author}
出版社：{publisher}
简介：{summary}

请返回 JSON：
{
  "categoryCode": "",
  "categoryName": "",
  "confidence": 0-1,
  "tags": [],
  "reason": ""
}

要求：
1. 分类尽量使用简化中图法。
2. 如果无法判断，请给出最可能的分类，并降低 confidence。
3. 不要输出 JSON 之外的解释。
```

### 重复检测

```text
请判断以下两条图书记录是否可能是同一本书的不同版本。

图书 A：
{bookA}

图书 B：
{bookB}

返回 JSON：
{
  "isDuplicate": true/false,
  "confidence": 0-1,
  "reason": ""
}
```

### 自然语言搜索解析

```text
请将用户的自然语言查询转换为图书数据库查询条件。

用户输入：
{query}

可用字段：
title, author, publisher, category, tags, location, read_status, status, publish_year

返回 JSON：
{
  "keywords": [],
  "filters": {},
  "intent": ""
}
```

## 11. 部署方案

### 本地单机部署

```text
前端：Vite build 后静态文件
后端：FastAPI
数据库：SQLite
Ollama：本机运行
```

### 家庭 NAS 部署

```text
Docker Compose
Nginx
FastAPI
PostgreSQL
Ollama，可单独部署
```

建议 Docker Compose 服务：

```text
web
api
db
ollama
nginx
```

## 12. 安全设计

- 密码使用 bcrypt 或 argon2 哈希
- 登录接口限流
- JWT 或 Session 认证
- 管理接口权限校验
- 防止 SQL 注入
- 上传文件类型限制
- 外部 URL 图片代理或白名单
- 定期备份数据库
- 不在日志中记录密码和 Token
- 默认不暴露公网
- 如需公网访问必须使用 HTTPS

## 13. 开发阶段

### 第一阶段：MVP

- 用户登录
- 图书增删改查
- 分类管理
- 位置管理
- 基础搜索
- 图书详情
- SQLite 数据库
- 简单统计

### 第二阶段：智能录入

- ISBN 查询
- 书名联网搜索
- 候选图书导入
- Ollama 分类推荐
- 标签生成
- 简介整理

### 第三阶段：家庭管理增强

- 借阅管理
- 阅读记录
- 阅读笔记
- 批量导入导出
- 重复检测
- 书架位置优化

### 第四阶段：体验优化

- 手机端适配
- 二维码标签
- 扫码入库
- 封面墙
- 高级统计
- 自然语言搜索

### 第五阶段：部署与维护

- Docker 部署
- 自动备份
- 系统设置页
- 多模型配置
- 日志查看
- 数据迁移工具

## 14. MVP 范围建议

第一版建议优先实现：

- 登录
- 图书管理
- 分类管理
- 位置管理
- 基础搜索
- ISBN / 书名检索
- Ollama 分类推荐
- 导入导出
- 基础统计

这能让系统快速可用，同时保留后续扩展空间。

