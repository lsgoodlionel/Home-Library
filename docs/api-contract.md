# Home Library API 契约

## 1. 总则

本文档定义 Home Library 前后端协作所需的 API 契约。后续后端实现应以本文档为最低标准，前端开发应以本文档作为请求和响应类型来源。

基础约定：

- API 前缀统一为 `/api`
- 请求和响应均使用 JSON，文件导入导出除外
- 时间字段统一使用 ISO 8601 字符串
- 后端字段使用 `snake_case`
- 前端类型可映射为 `camelCase`
- 所有受保护接口均需要 `Authorization: Bearer <token>`
- 分页默认 `page=1&page_size=20`
- 删除操作原则上使用软删除或删除保护，MVP 可先硬删除未关联数据

## 2. 通用响应

### 2.1 分页响应

```json
{
  "items": [],
  "total": 0,
  "page": 1,
  "page_size": 20
}
```

### 2.2 错误响应

```json
{
  "error": {
    "code": "BOOK_NOT_FOUND",
    "message": "图书不存在",
    "details": {}
  }
}
```

常用错误码：

| 错误码 | 含义 |
| --- | --- |
| `UNAUTHORIZED` | 未登录或 Token 无效 |
| `FORBIDDEN` | 权限不足 |
| `VALIDATION_ERROR` | 请求参数错误 |
| `NOT_FOUND` | 资源不存在 |
| `CONFLICT` | 资源冲突 |
| `EXTERNAL_SERVICE_ERROR` | 外部服务错误 |
| `AI_SERVICE_DISABLED` | AI 服务未启用 |
| `AI_ACCESS_DENIED` | Cloudflare Access 凭据缺失、无效或策略拒绝 |
| `AI_TUNNEL_UNAVAILABLE` | Cloudflare Tunnel 或远程 Origin 不可用 |
| `AI_CONNECT_TIMEOUT` | 连接 AI 服务超时 |
| `AI_RESPONSE_TIMEOUT` | 模型启动或生成超时 |
| `AI_MODEL_ERROR` | 模型配置或请求参数错误 |
| `AI_UPSTREAM_ERROR` | 上游连接/传输异常或其他 5xx；返回脱敏 reason、hostname 或 HTTP 状态 |
| `AI_RESPONSE_INVALID` | 模型响应无法安全解析 |
| `INTERNAL_ERROR` | 服务内部错误 |

## 3. 数据字典

### 3.1 用户角色

```text
admin
member
guest
```

### 3.2 用户状态

```text
active
disabled
```

### 3.3 图书状态

```text
available
borrowed
lost
pending
gifted
```

### 3.4 阅读状态

```text
unread
reading
read
paused
```

### 3.5 数据来源

```text
manual
isbn_lookup
title_search
ollama
import
```

## 4. 认证接口

### POST /api/auth/login

登录。

请求：

```json
{
  "username": "admin",
  "password": "password"
}
```

响应：

```json
{
  "access_token": "jwt-token",
  "token_type": "bearer",
  "expires_in": 86400,
  "user": {
    "id": 1,
    "username": "admin",
    "display_name": "管理员",
    "role": "admin"
  }
}
```

### POST /api/auth/logout

退出登录。MVP 可由前端删除 Token，后端返回成功。

响应：

```json
{
  "ok": true
}
```

### GET /api/auth/me

获取当前用户。

响应：

```json
{
  "id": 1,
  "username": "admin",
  "display_name": "管理员",
  "email": "",
  "role": "admin",
  "status": "active"
}
```

## 5. 用户接口

### GET /api/users

权限：管理员。

查询参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `page` | number | 页码 |
| `page_size` | number | 每页数量 |
| `keyword` | string | 用户名或显示名 |
| `role` | string | 角色 |
| `status` | string | 状态 |

响应：分页用户列表。

### POST /api/users

权限：管理员。

请求：

```json
{
  "username": "family",
  "password": "initial-password",
  "display_name": "家庭成员",
  "email": "",
  "role": "member",
  "status": "active"
}
```

### PATCH /api/users/{id}

权限：管理员。

请求：

```json
{
  "display_name": "新名称",
  "email": "",
  "role": "member",
  "status": "active"
}
```

### DELETE /api/users/{id}

权限：管理员。

说明：MVP 可禁用用户，不建议物理删除。

## 6. 图书接口

### GET /api/books

查询图书列表。

查询参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `page` | number | 页码 |
| `page_size` | number | 每页数量 |
| `keyword` | string | 搜索书名、作者、ISBN、出版社 |
| `category_id` | number | 分类 |
| `location_id` | number | 位置 |
| `status` | string | 图书状态 |
| `read_status` | string | 阅读状态 |
| `is_favorite` | boolean | 是否重点收藏 |
| `publish_year_from` | number | 出版年份开始 |
| `publish_year_to` | number | 出版年份结束 |

响应：

```json
{
  "items": [
    {
      "id": 1,
      "title": "乡土中国",
      "subtitle": "",
      "author": "费孝通",
      "publisher": "生活·读书·新知三联书店",
      "publish_year": 2013,
      "isbn": "9787108045269",
      "cover_url": "",
      "category": {
        "id": 12,
        "code": "C91",
        "name": "社会学"
      },
      "location": {
        "id": 3,
        "full_path": "书房 / A 架 / 第 2 层 / 右侧"
      },
      "status": "available",
      "read_status": "read",
      "rating": 5,
      "is_favorite": true,
      "created_at": "2026-05-03T10:00:00+08:00",
      "updated_at": "2026-05-03T10:00:00+08:00"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

### GET /api/books/{id}

获取图书详情。

响应包含完整字段、标签、分类、位置、借阅状态和阅读笔记摘要。

### POST /api/books

创建图书。

请求：

```json
{
  "title": "乡土中国",
  "subtitle": "",
  "author": "费孝通",
  "translator": "",
  "publisher": "生活·读书·新知三联书店",
  "publish_year": 2013,
  "isbn": "9787108045269",
  "language": "zh-CN",
  "pages": 120,
  "price_cents": 2800,
  "binding": "平装",
  "series": "",
  "cover_url": "",
  "summary": "",
  "author_intro": "",
  "category_id": 12,
  "location_id": 3,
  "tag_names": ["社会学", "中国乡村"],
  "status": "available",
  "read_status": "read",
  "rating": 5,
  "is_favorite": true,
  "note": ""
}
```

### PATCH /api/books/{id}

编辑图书。请求体允许传部分字段。

### DELETE /api/books/{id}

删除图书。若存在未归还借阅记录，返回 `CONFLICT`。

### POST /api/books/batch-update

批量更新分类、位置、状态或标签。

请求：

```json
{
  "book_ids": [1, 2, 3],
  "updates": {
    "category_id": 12,
    "location_id": 3,
    "status": "available"
  }
}
```

## 7. 分类接口

### GET /api/categories

返回分类树。

响应：

```json
[
  {
    "id": 1,
    "code": "I",
    "name": "文学",
    "parent_id": null,
    "description": "",
    "sort_order": 90,
    "is_system": true,
    "children": []
  }
]
```

### POST /api/categories

权限：管理员。

请求：

```json
{
  "code": "I247",
  "name": "中国当代小说",
  "parent_id": 9,
  "description": "",
  "sort_order": 1
}
```

### PATCH /api/categories/{id}

权限：管理员。

### DELETE /api/categories/{id}

权限：管理员。系统分类或已被图书使用的分类不能删除。

## 8. 位置接口

### GET /api/locations

查询位置列表。

响应：

```json
[
  {
    "id": 1,
    "room": "书房",
    "shelf": "A 架",
    "layer": "第 2 层",
    "position": "右侧",
    "full_path": "书房 / A 架 / 第 2 层 / 右侧",
    "description": "",
    "sort_order": 1
  }
]
```

### POST /api/locations

权限：管理员。

请求：

```json
{
  "room": "书房",
  "shelf": "A 架",
  "layer": "第 2 层",
  "position": "右侧",
  "description": "",
  "sort_order": 1
}
```

### PATCH /api/locations/{id}

权限：管理员。

### DELETE /api/locations/{id}

权限：管理员。已被图书使用的位置不能删除。

## 9. 外部书籍检索接口

### GET /api/search/books

按书名、作者或混合关键词搜索。

查询参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `query` | string | 检索词 |
| `limit` | number | 返回数量 |

响应：

```json
{
  "items": [
    {
      "source": "open_library",
      "source_id": "OL123",
      "title": "乡土中国",
      "subtitle": "",
      "author": "费孝通",
      "publisher": "三联书店",
      "publish_year": 2013,
      "isbn": "9787108045269",
      "cover_url": "",
      "summary": "",
      "raw": {}
    }
  ]
}
```

### GET /api/search/isbn/{isbn}

按 ISBN 检索，响应结构同上。

### POST /api/search/import-result

把外部检索结果导入为图书草稿或直接入库。

请求：

```json
{
  "result": {},
  "category_id": 12,
  "location_id": 3,
  "import_mode": "draft"
}
```

## 10. AI 接口

除管理员专用的连接测试外，本节所有 AI 接口均要求登录；匿名请求统一返回
HTTP 401。AI 任务审计按当前账号记录，成功输出使用严格标准 JSON，并限制为
UTF-8 编码最大 64 KiB。

### 服务器全局配置 `/api/system/ai-config`

所有操作要求管理员。`GET` 返回 `enabled`、`default_base_url`、`trusted_base_url`、`default_model`、`connect_timeout_seconds`、`read_timeout_seconds`、`verify_tls`、`configuration_source`、`config_version` 和 `credential_state`。来源为 `database` / `environment` / `default`；凭据状态仅含 `access_client_id_configured`、`access_client_secret_configured`、`credentials_usable` 和 `source`，不含任何凭据值或密文。

`PUT` 提交全部运行参数以及 `admin_password`、`upgrade_password`。密码只用于本次验证。`access_client_id` 与 `access_client_secret` 必须成对提交；均省略或为空表示保留现有凭据。`clear_access_credentials=true` 显式清除，不能同时提供新凭据。`verify_tls=false` 必须另传 `confirm_insecure_tls=true`。连接超时须大于 0、不超过 60 且小于读取超时；读取超时必须小于 300 秒。可信地址须为公开域名 HTTPS URL。未知字段被拒绝。

`DELETE` 请求体为 `admin_password`、`upgrade_password`、`confirm_reset: true`，删除全局覆盖，返回环境或默认配置，不删除账号偏好。PUT/DELETE 要求 HTTPS，或来自精确可信代理且 `X-Forwarded-Proto: https`，或直连回环且浏览器 Origin/Referer 也为回环；普通 Docker HTTP 代理不满足此条件。

`POST /api/system/ai-config/test` 不接受待保存配置或凭据，只对当前生效配置及当前账号目标执行只读 version/tags/ps 检查。保存与健康检测是独立操作：保存 HTTP 200 后，测试可能返回 HTTP 502 / `AI_ACCESS_DENIED` / `access_denied`（上游 401/403），或连接/读取超时等既有稳定分类。测试失败不回滚保存。`AI_UPSTREAM_ERROR.details` 只允许安全诊断字段：`reason=connection_failed|request_failed`、规范化 hostname 和数字 HTTP 状态；前端据此区分“未收到 HTTP 响应”“传输失败”和“上游返回 HTTP 状态”，不透传原始异常或响应正文。

PUT/DELETE 成功后才失效全部健康缓存。并发版本冲突（包含首次创建竞争）返回 HTTP 409 / `AI_SERVER_CONFIG_CONFLICT`，提示“服务器 AI 配置已被其他请求修改，请刷新后重试”；失败方不修改配置、凭据或审计。数据库写入故障返回 HTTP 500 / `AI_SERVER_CONFIG_WRITE_FAILED` 与稳定中文提示，不包含 SQL、参数、明文或密文。升级密码按 UTF-8 bytes 恒定时间比较，支持 Unicode；错误或无法编码的输入稳定返回 403。

`GET/PUT /api/ai/config` 管理登录账号的 `ai_enabled`、`active_provider`、默认模型和 provider 列表，不能改变服务器凭据和安全参数。provider 标识为 `ollama`、`openai`、`gemini`、`deepseek`、`moonshot`、`qwen`、`custom`。读取只返回 `has_api_key` 与 `credential_state=missing|configured|unusable`；Key 留空表示保留，`clear_api_key=true` 表示清除。AI 开启时 active provider 必须已启用且配置有效；关闭后保留选择，重新开启继续使用。保存会失效账号 provider health/model cache，使下一请求从数据库重载。

配置层级为服务器 Ollama 安全边界与默认值、账号 provider 持久配置、单次诊断草稿。账号/草稿不能修改 TLS、超时、Cloudflare Access、可信 Origin 或 `AI_PROVIDER_ALLOWED_PRIVATE_ORIGINS`。

Provider 诊断接口为 `POST /api/ai/providers/{provider}/test`、`POST /api/ai/providers/{provider}/models` 和 `POST /api/ai/providers/{provider}/generate-test`。三者均要求登录，可使用保存配置或临时 `base_url`、`model`、`api_key` 草稿；草稿不持久化。`test` 只验证连接，`models` 返回模型及 capability，不支持枚举时返回稳定 unsupported 说明，`generate-test` 执行最小生成且前端必须二次确认。响应只包含安全 Base URL、有效模型、凭据状态和脱敏错误。

### GET /api/ai/models

返回 Ollama 可用模型列表。

### GET /api/ai/health

权限：登录用户。默认 `refresh=false` 只读取当前账号且 runtime fingerprint
一致的进程内脱敏状态；没有匹配缓存时返回“尚未检查”。`refresh=true` 会并发检查
Ollama `version`、已安装模型和运行中模型。保存该账号的 AI 设置会立即失效其健康
缓存。响应只包含状态、中文消息、检查时间、版本、模型数量和脱敏 runtime，不包含
Access 凭据。带 path 的 Ollama Base URL 会原样参与请求与缓存匹配；Base URL 不接受
query 或 fragment。

### POST /api/ai/test-connection

权限：管理员。

```json
{
  "generate": false
}
```

默认只检查只读端点。只有严格 JSON 布尔值 `true` 才执行最小生成测试，并使用 `keep_alive=0`；前端操作前需要二次确认。

AI 错误使用上表稳定代码和中文消息。服务器配置保存后的自动测试与手动测试使用相同的脱敏错误映射；不返回 Prompt、图书全文、请求头、上游响应正文或凭据。AI 服务关闭、Access/Tunnel 故障或超时时，登录、藏书、检索、借阅、阅读、统计和备份接口仍保持可用。

### POST /api/ai/classify-book

请求：

```json
{
  "title": "乡土中国",
  "author": "费孝通",
  "publisher": "三联书店",
  "summary": "",
  "model": "qwen3.5:4b"
}
```

响应：

```json
{
  "category_code": "C91",
  "category_name": "社会学",
  "confidence": 0.86,
  "tags": ["社会学", "中国乡村", "经典著作"],
  "reason": "该书主要讨论乡村社会结构与社会关系。",
  "model": "qwen3.5:4b"
}
```

### POST /api/ai/generate-tags

生成标签。

### POST /api/ai/summarize-book

整理简介。

### POST /api/ai/detect-duplicate

判断两本书是否重复。

### POST /api/ai/natural-search

把自然语言转为搜索条件。

## 11. 借阅接口

### POST /api/borrow

请求：

```json
{
  "book_id": 1,
  "borrower_name": "张三",
  "borrower_contact": "",
  "borrowed_at": "2026-05-03",
  "due_at": "2026-06-03",
  "note": ""
}
```

### POST /api/borrow/{id}/return

请求：

```json
{
  "returned_at": "2026-05-20",
  "note": ""
}
```

### GET /api/borrow/records

借阅历史。

### GET /api/borrow/active

当前借出。

## 12. 阅读笔记接口

### GET /api/books/{id}/notes

获取某本书的笔记。

### POST /api/books/{id}/notes

请求：

```json
{
  "title": "第一章笔记",
  "content": "Markdown 内容",
  "progress": 35,
  "rating": 5,
  "started_at": "2026-05-03",
  "finished_at": null
}
```

### PATCH /api/notes/{id}

编辑笔记。

### DELETE /api/notes/{id}

删除笔记。

## 13. 统计接口

### GET /api/stats/overview

响应：

```json
{
  "total_books": 120,
  "available_books": 110,
  "borrowed_books": 3,
  "read_books": 42,
  "unread_books": 78,
  "favorite_books": 12,
  "recent_books": [],
  "active_borrows": []
}
```

### GET /api/stats/categories

分类分布。按图书直接所属分类精确计数，不把子类图书汇总到父类；返回所有有书的层级分类及未分类数量。每项包含 `id`、`code`、`name`、`count`，同名分类仍通过 `id` 和 `code` 区分，结果按数量及分类稳定顺序排列。前端分类图以 `id`、其次 `code` 生成稳定 segment key，并显示为“`code name`”；未分类保持显示“未分类”。

### GET /api/stats/locations

位置分布。

### GET /api/stats/reading

阅读状态统计。

### GET /api/stats/timeline

入库、阅读时间趋势。

## 14. 导入导出接口

### POST /api/books/import/preview

上传文件并预览。

请求：`multipart/form-data`

字段：

- `file`
- `format`: `csv`、`xlsx`、`json`

### POST /api/books/import

确认导入。

### GET /api/books/export

查询参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `format` | string | `csv`、`xlsx`、`json` |

响应：文件下载。

