# Home Library 远程 Ollama 与 Cloudflare Access 接入设计

## 1. 背景与目标

Home Library 已具备账号级 AI 模型配置、Ollama 模型列表、图书分类推荐、标签生成、内容推荐、摘要整理、重复检测和自然语言检索能力。现有实现面向本机或局域网 Ollama，使用同步 HTTP 客户端、单一请求超时和通用错误提示，尚未满足通过 Cloudflare Access 安全访问远程 Ollama 的要求。

本次升级目标是让 Home Library 后端能够安全调用 ssh08 上由 Cloudflare Access 保护的 Ollama，同时保留本地 Ollama 和账号级默认模型配置。Ollama 不可用时，只影响 AI 辅助功能，图书录入、外部书目检索、借阅、阅读记录、统计和备份等核心功能必须继续运行。

当前经运维任务验证的默认远程入口为 `https://openclaw.lsgood.cn`，默认建议模型为 `qwen3.5:4b`。`https://ollama.lsgood.cn` 当前返回 Access 403，不作为生产默认值。应用不得修改 ssh08、Cloudflare Tunnel 或 Access 策略。

## 2. 安全边界

Cloudflare Access Service Token 的 Client ID 和 Client Secret 只允许通过后端环境变量或服务器 Secret 管理系统注入：

- 不写入代码、数据库、README、日志或 Git。
- 不使用 `VITE_*` 环境变量，不返回给浏览器。
- 设置页只显示“已配置”或“未配置”。
- 后端日志和任务记录不得保存请求头或凭据值。
- Access 请求头只发送给服务器环境变量 `OLLAMA_TRUSTED_BASE_URL` 配置的可信 HTTPS Ollama Origin。账号或 Docker 把请求 Base URL 改为其他地址时，不得携带 Cloudflare 凭据，防止凭据被发送到任意主机。
- URL 比较以规范化后的 scheme、hostname 和有效端口为准；路径、查询参数和用户信息不能扩大可信范围。
- TLS 默认启用验证，仅允许通过服务器环境变量调整，前端不提供关闭 TLS 验证的操作。

现有账号级 Ollama Base URL 继续保留，用于本机、局域网或其他不需要 Cloudflare Access 的 Ollama。服务器环境变量提供默认远程地址，数据库中未显式保存地址的账号使用服务器默认值。

## 3. 配置设计

后端 `Settings` 增加以下配置：

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `OLLAMA_ENABLED` | `false` | 是否启用 Ollama AI 功能 |
| `OLLAMA_BASE_URL` | `https://openclaw.lsgood.cn` | 后端直接运行时的默认 Ollama 请求地址 |
| `OLLAMA_TRUSTED_BASE_URL` | `https://openclaw.lsgood.cn` | 允许携带 Access 凭据的独立 HTTPS 可信 Origin；HTTP、本地名称和 IP 地址不受信任 |
| `OLLAMA_DEFAULT_MODEL` | `qwen3.5:4b` | 默认模型 |
| `OLLAMA_CONNECT_TIMEOUT_SECONDS` | `20` | 建立连接超时 |
| `OLLAMA_READ_TIMEOUT_SECONDS` | `180` | 等待完整响应超时 |
| `OLLAMA_VERIFY_TLS` | `true` | 是否验证 TLS 证书 |
| `OLLAMA_CF_ACCESS_CLIENT_ID` | 空 | 后端专用 Access Client ID |
| `OLLAMA_CF_ACCESS_CLIENT_SECRET` | 空 | 后端专用 Access Client Secret |

保留读取旧的 `OLLAMA_TIMEOUT_SECONDS` 作为兼容兜底，但新配置和文档统一使用连接、读取两个独立超时。Docker 开发和生产 Compose 必须显式映射所有非敏感配置与两个后端 Secret 变量，前端构建参数不得出现凭据。

账号级设置继续保存 Active Provider、Base URL 和默认模型。Ollama 配置响应增加以下只读状态：

- AI 功能是否由服务器启用。
- 当前有效 Base URL 和默认模型。
- 连接超时、读取超时和 TLS 验证状态。
- Access Client ID 和 Client Secret 是否均已配置。
- 当前地址是否会使用 Cloudflare Access 认证。

## 4. 后端客户端架构

新增集中式异步 `OllamaClient`，所有业务接口只能通过该客户端调用 Ollama，不再自行拼接 URL、请求头或超时。

客户端职责：

- 使用 `httpx.AsyncClient`。
- 分别设置 connect、read、write 和 pool timeout；读取超时使用 `OLLAMA_READ_TIMEOUT_SECONDS`。
- 健康检查的 version、installed models、running models 独立探针并发执行；显式生成测试也与这些探针并发，端点预算不随探针数量顺序累加。
- 默认超时严格保持后端读取 `180s` < 前端健康/生成 `240s` < Nginx AI send/read `300s`。
- 为可信 Origin 自动添加 `CF-Access-Client-Id` 和 `CF-Access-Client-Secret`。
- 提供 `version()`、`list_models()`、`running_models()`、`generate_json()` 和非流式 `chat()` 方法。
- `/api/generate` 和 `/api/chat` 默认发送 `stream: false`。
- 对请求输入、系统提示和模型文本输出设置长度上限。
- 生成 JSON 必须经过现有 Pydantic Schema 和字段白名单校验，不能把任意模型字段直接写入图书记录。
- 只在尚未开始返回响应内容时允许有限重试；本次非流式调用最多重试一次瞬时连接错误，不重试 Access 401/403、模型 4xx 或格式错误。
- 不记录完整 Prompt、图书摘录、模型响应或请求头。AI 任务审计记录只保存受限长度的业务摘要和结构化结果。

现有 `OllamaService` 的业务接口逐步迁移到异步客户端。FastAPI AI 路由改为异步处理，保留既有 API 路径和响应 Schema，避免前端业务调用发生破坏性变化。

## 5. 错误分类与降级

后端建立明确异常类型并映射为稳定的 API 错误码和中文提示：

| 场景 | API 错误码 | HTTP 状态 | 中文语义 |
|---|---|---:|---|
| `OLLAMA_ENABLED=false` | `AI_SERVICE_DISABLED` | 503 | AI 服务尚未启用 |
| Access 401/403 | `AI_ACCESS_DENIED` | 502 | Cloudflare Access 凭据缺失、无效或策略不允许 |
| 502/503/1033 | `AI_TUNNEL_UNAVAILABLE` | 503 | Tunnel 或远程 Ollama Origin 不可用 |
| 建立连接超时 | `AI_CONNECT_TIMEOUT` | 504 | 无法在限定时间内连接 AI 服务 |
| 响应读取超时 | `AI_RESPONSE_TIMEOUT` | 504 | 模型启动或生成超时 |
| 模型不存在或 Ollama 4xx | `AI_MODEL_ERROR` | 502 | 模型配置或请求参数错误 |
| Ollama 其他 5xx | `AI_UPSTREAM_ERROR` | 502 | 上游 AI 服务异常 |
| 非法 JSON 或 Schema 不匹配 | `AI_RESPONSE_INVALID` | 502 | 模型返回内容不能安全使用 |

错误详情可以包含不敏感的 HTTP 状态、目标 hostname 和排障建议，但不得包含 Access 凭据、完整 URL 查询参数、完整 Prompt 或完整响应正文。

AI 请求失败继续写入现有 AI 任务审计记录，但只保存清理后的错误分类和受限输入摘要。失败不改变图书数据，也不阻止用户改为手工录入。

## 6. 健康检查与管理员接口

保留现有 `GET /api/ai/models`，改由异步客户端实现。新增：

- `GET /api/ai/health`：登录用户可读取当前有效配置的非敏感状态，并检查 `/api/version`、`/api/tags` 和 `/api/ps`。返回 Ollama 版本、模型数量、当前加载模型数量、检查时间、状态与中文消息。
- `POST /api/ai/test-connection`：仅管理员可调用。默认检查版本、模型列表和运行模型；请求体中显式传入 `generate=true` 时才使用当前默认模型执行最小生成，生成请求携带 `keep_alive=0`。

健康检查和管理员测试不得返回原始上游响应。健康状态保留在当前后端进程的有界内存中，设置页显示最近一次结果；应用重启后状态为“尚未检查”，不为此增加数据库迁移。

公开的应用健康接口 `/api/health` 不依赖 Ollama，避免远程 AI 故障导致 Docker 将整个 Home Library 判定为不健康。

## 7. 前端设置与业务接入

系统设置中的“AI 模型配置”继续使用账号级持久化，增加：

- 服务器 AI 功能启用状态。
- 当前有效 Base URL。
- 默认模型。
- 连接与读取超时。
- TLS 验证状态。
- Cloudflare Access 凭据“已配置/未配置”。
- 当前地址是否使用 Access 认证。
- 最近健康状态、Ollama 版本和可用模型数量。
- “检查健康状态”和仅管理员可见的“测试连接”按钮。
- 管理员测试生成使用单独确认，不在普通刷新模型操作中触发模型加载。

页面不显示、不编辑 Access Client ID 或 Secret。账号可以继续调整 Ollama Base URL 和默认模型；当地址不是服务器可信 Origin 时，页面提示“此地址不会携带服务器 Cloudflare Access 凭据”。

智能入库、藏书编辑、一键分类和其他 AI 操作沿用现有接口。前端根据稳定错误码显示中文提示，并允许继续手工处理；不得因为健康检查失败锁死保存图书、检索书目或其他非 AI 操作。

## 8. 兼容性与迁移

- 不修改现有数据库表结构，新的服务器状态由环境变量和运行时响应提供。
- 已保存的账号级 Ollama 地址和模型继续生效。
- 旧 `OLLAMA_TIMEOUT_SECONDS` 仅作为没有设置新读取超时时的兼容兜底。
- 本地 Ollama 仍可使用 `http://localhost:11434` 或 Docker 宿主机地址；本地地址不会携带 Cloudflare Access 凭据。
- `OLLAMA_ENABLED=false` 时 AI 接口返回明确错误，应用其他模块正常运行。
- 不改变现有 AI 业务响应字段，前端已有分类、标签和内容推荐流程保持兼容。

## 9. 测试与验收

后端自动化测试至少覆盖：

- 可信 Origin 请求携带 Access headers，其他 Origin 不携带。
- API 和日志中不暴露凭据。
- connect/read timeout 分离并映射到不同错误码。
- delivery 契约同时解析后端默认值、前端健康/生成值和 Nginx send/read 值，并验证严格大小关系。
- Access 401/403、Tunnel 502/503/1033、模型 4xx/5xx和非法 JSON 的分类。
- 停用 AI 时的安全降级。
- 健康检查结果结构与管理员测试权限。
- 显式确认前不执行最小生成，生成时使用 `keep_alive=0`。
- 账号级 Base URL 和默认模型兼容。
- 所有现有 AI 业务 Schema 校验继续有效。

前端测试和构建至少覆盖：

- 非敏感状态字段映射。
- Access 凭据只显示配置状态。
- 中文错误映射和非 AI 操作不受影响。
- 管理员连接测试与生成确认交互。
- TypeScript 类型检查和生产构建。

部署验证包括：

- `docker compose config` 和生产 Compose 配置展开成功。
- 无凭据环境返回明确的停用或 Access 错误，不泄露配置值。
- 已注入凭据的环境执行 `/api/version`、`/api/tags`、`/api/ps` 真实烟雾测试。
- 只有在用户明确选择管理员测试生成时执行最小生成。

若真实验证发现 ssh08、Cloudflare Tunnel 或 Access Policy 问题，只记录不敏感诊断并移交 ssh08 运维任务，不在本项目修改服务器策略。

## 10. 文档与交付

完成实现后更新现有 README、部署文档、开发文档、API 合约和项目路线图中与 AI/Ollama 状态有关的段落。文档只提供变量名和占位值，不记录任何真实凭据。

交付前运行后端完整测试、前端完整测试、类型检查、生产构建、Compose 配置检查和可执行的真实接口烟雾测试。只提交本任务文件，使用普通提交和普通推送，不使用 force push。
