# Home Library 多供应商 AI 配置与运行状态设计

## 1. 背景

Home Library 当前已经提供账号级 AI 服务商配置表单，包含 Ollama、OpenAI、Google Gemini、DeepSeek、Kimi / Moonshot、通义千问和自定义兼容接口。现有调用层仍只实现 Ollama：模型列表、健康检查、连接测试、最小生成以及分类推荐等业务请求均固定使用 `OllamaClient`。

这导致以下问题：

- 非 Ollama 配置可以保存，但不能测试、发现模型或用于业务调用。
- 账号选择云服务商后，页面上方仍显示 Ollama 状态。
- 云模型名称可能被错误交给 Ollama，最终表现为模型不存在。
- Ollama 账号开关被前端禁用，后端运行时也不读取账号级 `enabled`。
- 服务器配置和运行状态重复展示地址、模型、TLS 和开关，配置值与实际生效值不易区分。
- 账号 API Key 当前保存在账号配置 JSON 中，正式接入云模型前必须升级为加密存储。

## 2. 目标

本次升级需要实现：

1. 建立统一供应商适配层，让已列出的服务商具备真实调用能力。
2. 增加账号级 AI 总开关，并允许账号自由启停 Ollama。
3. 让连接测试、模型列表、最小生成和运行状态跟随当前账号的实际服务商。
4. 保留服务器 Ollama 网关及 Cloudflare Access 安全边界。
5. 加密保存账号 API Key，保证接口、日志和任务记录不泄露凭据。
6. 保持现有 AI 业务接口和响应 Schema，避免破坏智能入库、藏书编辑和一键分类流程。
7. AI 配置错误或上游不可用时，只降级 AI 功能，不影响其他业务。

## 3. 非目标

本次不包含：

- 修改图书外部检索数据源、分类算法或分类体系。
- 自动选择价格最低或速度最快的模型。
- 账号之间共享云 API Key。
- 建立复杂的自动故障切换、供应商负载均衡或账单中心。
- 修改 Cloudflare Tunnel、Access Policy 或远程 Ollama 服务器配置。
- 在浏览器、日志、任务审计或 API 响应中返回凭据原值。

## 4. 配置层级

### 4.1 服务器 Ollama 网关

现有“服务器 AI 配置”调整为“服务器 Ollama 网关”，仅管理 Ollama 的服务器级能力：

- 服务器 Ollama 总开关。
- 默认 Ollama 服务地址。
- 允许携带 Access 凭据的可信 HTTPS Origin。
- Cloudflare Access Client ID 和 Client Secret。
- TLS 证书验证。
- 连接超时和读取超时。
- 服务器默认模型。

服务器 Ollama 网关继续使用“数据库覆盖 > 环境变量 > 程序默认值”的优先级。修改数据库配置仍要求管理员当前密码、服务器升级专用密码，以及 HTTPS 或受控本机来源。

“默认 Ollama 服务地址”是实际请求目标。“Access 可信 Origin”只限定 Access 凭据可以发送到哪个 `scheme + hostname + effective port`，不是备用地址。两者可相同，但必须独立保存。账号覆盖 Ollama 地址后，只有实际地址与可信 Origin 完全匹配才可携带 Access 凭据。

### 4.2 账号级 AI 配置

账号配置新增 `ai_enabled` 总开关，并继续保存：

- 当前服务商 `active_provider`。
- 当前默认模型。
- 每个供应商的启用状态、API 地址、默认模型和凭据状态。

约束如下：

- `ai_enabled=false` 时不得发起任何 AI 上游请求。
- `ai_enabled=true` 时必须存在一个已启用且配置有效的当前服务商。
- 已停用服务商不能成为当前服务商。
- 停用当前服务商时，必须同时切换到另一个已启用服务商，或者关闭账号 AI。
- Ollama 可自由停用，不再作为不可关闭的特殊项。
- Ollama 的账号地址和模型可覆盖服务器默认值，但不能修改 Access 可信 Origin、Access 凭据、TLS、超时或服务器总开关。
- 云供应商必须具备可解密的 API Key 和非空默认模型才可成为当前服务商。

配置无效时系统进入明确的“配置无效”状态，不自动切换到其他供应商，也不静默回退到 Ollama。

## 5. 供应商适配层

### 5.1 通用接口

新增内部 `AIProviderClient` 协议，统一定义：

- `test_connection()`：验证地址、TLS、认证和基础接口，不执行文本生成。
- `list_models()`：返回规范化模型列表；供应商不支持时返回明确能力状态。
- `generate_text()`：执行非流式文本生成。
- `generate_json()`：执行生成并通过现有 Pydantic Schema 校验结构化结果。

所有适配器返回统一的模型、健康和异常类型。业务路由不再直接构造 `OllamaClient`，而是通过供应商工厂根据当前账号有效配置解析客户端。

### 5.2 Ollama 适配器

`OllamaProviderClient` 复用现有集中式 `OllamaClient`，继续支持：

- `/api/version`
- `/api/tags`
- `/api/ps`
- `/api/generate`
- `/api/chat`
- Cloudflare Access 请求头安全限制
- `Accept-Encoding: identity`
- 独立 connect/read timeout
- 现有 Ollama 错误分类

Ollama 特有状态包括版本、已安装模型数量、正在运行模型数量和是否使用 Access。

### 5.3 OpenAI-compatible 适配器

`OpenAICompatibleProviderClient` 覆盖：

- OpenAI
- DeepSeek
- Kimi / Moonshot
- 通义千问兼容模式
- 自定义 OpenAI-compatible 接口

默认使用 Bearer API Key。模型发现优先调用兼容 `/models`，生成优先使用非流式 Chat Completions；若某个官方供应商需要不同路径或响应映射，由供应商配置描述覆盖，不在业务路由中增加条件分支。

结构化生成仍以现有 Pydantic Schema 为最终边界。供应商原生结构化输出可作为能力优化，但不能绕过本地 JSON 解析、字段白名单和 Schema 校验。

### 5.4 Gemini 适配器

`GeminiProviderClient` 独立处理 Google Gemini API：

- 使用 Gemini 的认证方式、模型列表和生成接口。
- 模型列表只保留支持内容生成的模型。
- 将 Gemini 响应映射为统一文本或 JSON 结果。
- 不把 Gemini 强行伪装成 OpenAI-compatible 请求。

## 6. 运行时解析

新增通用 `AIProviderRuntime`，至少包含：

- `provider`
- `enabled`
- `base_url`
- `default_model`
- `credential_state`
- 供应商特有的安全和超时配置

运行时解析顺序：

1. 读取账号 AI 总开关。
2. 读取账号当前服务商及该服务商配置。
3. 验证服务商已启用、地址合法、模型非空且凭据可用。
4. Ollama 额外叠加服务器网关配置和 Access 安全边界。
5. 创建对应的供应商适配器。

前端业务请求可以继续传递可选模型名称用于现有流程兼容，但后端必须验证该模型属于当前服务商，不能借此切换供应商。最终默认值始终来源于账号当前服务商配置。

## 7. API 合约

### 7.1 保持兼容的业务接口

以下路径和响应 Schema 保持不变：

```text
POST /api/ai/classify-book
POST /api/ai/generate-tags
POST /api/ai/recommend-book-content
POST /api/ai/summarize-book
POST /api/ai/detect-duplicate
POST /api/ai/natural-search
```

内部实现改为根据账号当前服务商调用统一适配器。

### 7.2 配置接口

```text
GET /api/ai/config
PUT /api/ai/config
```

配置响应新增账号 AI 总开关和各供应商凭据状态，不返回 API Key 原值。更新接口支持：

- 留空保持已有 Key。
- 提交新 Key 覆盖旧值。
- 显式 `clear_api_key=true` 删除旧值。

### 7.3 供应商操作接口

```text
GET  /api/ai/health
POST /api/ai/providers/{provider}/test
POST /api/ai/providers/{provider}/models
POST /api/ai/providers/{provider}/generate-test
```

`test` 和 `models` 可使用已保存配置，也可在设置页提交尚未保存的临时地址和新 Key。临时凭据只存在于单次请求内存中，不写日志、数据库或任务审计。

`generate-test` 使用指定供应商的当前表单模型执行最小非流式生成。前端必须二次确认可能产生费用。

通用响应至少包含：

- `provider`
- `status`
- `message`
- `checked_at`
- `effective_model`
- `safe_base_url`
- `credential_state`
- `models`
- `details`

`details` 只包含非敏感供应商特有信息。原 `GET /api/ai/models` 暂时保留，内部转发到当前服务商模型接口并在文档中标记兼容用途。

## 8. 前端设计

### 8.1 服务器 Ollama 网关

仅管理员可见。保留管理员配置表单、配置来源、凭据状态和保存/恢复结果，移除与运行状态重复的静态摘要。字段名称使用：

- 默认 Ollama 服务地址
- 允许携带 Access 凭据的可信 Origin

可信 Origin 下方明确说明“该地址不是备用服务地址，只用于限制 Access 凭据发送目标”。

### 8.2 当前 AI 运行状态

原“Ollama 运行状态”改为“当前 AI 运行状态”，根据账号实际服务商显示：

- 账号 AI 是否启用。
- 当前服务商和当前模型。
- 脱敏有效地址。
- 凭据配置状态。
- 最近检查时间、连接结果和最小生成结果。

Ollama 激活时额外显示版本、已安装模型、正在运行模型和 Access 使用状态。云供应商激活时不得继续显示 Ollama 版本和模型数量。

账号 AI 停用时显示“当前账号未启用 AI”，不自动发起健康检查。

### 8.3 当前账号 AI 配置

顶部增加账号 AI 总开关和当前服务商选择。服务商下拉框只允许选择已启用且满足基本配置的项。

每个供应商面板提供：

- 启用/停用。
- API 地址。
- API Key 状态及显式清除操作。
- 服务商默认模型。
- 测试连接。
- 刷新模型。
- 生成测试。

保存配置和测试连接是两个独立结果。供应商临时故障不能阻止保存合法配置。

## 9. 模型列表与测试

### 9.1 模型发现

- Ollama 调用 `/api/tags`。
- OpenAI-compatible 供应商优先调用 `/models`。
- Gemini 调用其模型列表接口并过滤生成能力。
- 不支持枚举、权限不足或模型接口不可用时，允许手工输入模型名。

每个供应商分别维护短时内存缓存。切换供应商时不得混用模型列表。刷新列表不自动改变默认模型；当前模型不存在时显示警告，由用户确认修改。

### 9.2 测试层级

- “测试连接”不产生生成费用。
- “刷新模型”只读取模型列表。
- “生成测试”执行一次最小请求，并在前端二次确认。

错误统一映射为中文稳定分类：

- 服务未启用。
- 配置无效。
- 认证失败。
- 地址或 TLS 错误。
- 额度不足。
- 请求限流。
- 模型不存在或无权访问。
- 连接超时。
- 响应超时。
- 供应商异常。
- 响应格式异常。

错误详情可包含脱敏 hostname、HTTP 状态和供应商错误类别，不得包含 Key、Authorization Header、完整查询参数、完整 Prompt 或完整原始响应。

## 10. 凭据加密与网络安全

### 10.1 API Key 加密

账号 API Key 使用后端凭据加密服务保存，并由稳定 `APP_SECRET_KEY` 派生密钥。API 只返回：

- 是否已配置。
- 是否可解密。
- 是否需要重新录入。

管理员不能通过 API 读取其他账号的 Key 原值。`APP_SECRET_KEY` 变更造成旧值无法解密时，不尝试猜测或静默清除，页面明确要求重新录入。

### 10.2 明文迁移

增加数据库迁移所需的加密字段或独立凭据表。迁移按以下顺序执行：

1. 读取旧账号配置中的非空明文 Key。
2. 使用当前稳定密钥加密并写入新字段。
3. 验证密文可解密且内容一致。
4. 清除旧 JSON 中的明文 Key。

任一步失败都回滚该账号迁移，不删除旧值，并只记录不敏感错误类别。应用读取阶段可在受限过渡期兼容旧字段，但写入必须只使用新加密存储；兼容读取应在迁移稳定后的后续版本移除。

### 10.3 SSRF 防护

云供应商默认只允许 HTTPS。地址解析和连接前必须拒绝：

- 环回地址。
- 链路本地地址。
- 云元数据地址。
- 未经允许的私有网络地址。
- URL 用户信息和非法端口。
- DNS 解析后落入受保护地址的目标。

Ollama 继续支持明确的本机和局域网场景，并沿用 Access Origin 安全限制。自定义兼容接口如需访问内网，必须由服务器管理员通过明确允许列表授权，账号不能自行突破。

## 11. 迁移与兼容策略

- 现有账号默认迁移为 `ai_enabled=true`，当前服务商保持 Ollama。
- 已保存的 Ollama 地址和模型继续生效。
- 服务器 Cloudflare Access 配置不迁移、不删除。
- 已保存的非 Ollama 地址、模型和启用状态继续保留。
- API Key 只有在加密迁移成功后才从旧位置清除。
- 当前服务商停用、模型为空或凭据不可用时，账号进入配置无效状态，不自动回退。
- AI 配置错误只影响 AI 路由，图书录入、外部检索、借阅、统计和备份继续运行。

## 12. 测试与验收

### 12.1 后端自动化测试

- 账号 AI 总开关和服务商启停约束。
- 当前服务商、模型和客户端不会错配。
- Ollama Cloudflare Access 请求头安全边界继续成立。
- OpenAI、DeepSeek、Kimi、通义和自定义兼容请求格式。
- Gemini 独立请求和响应格式。
- 各供应商模型发现、连接测试和最小生成。
- API Key 加密、明文迁移、清除、换钥不可解密状态和权限隔离。
- SSRF 地址和 DNS 解析限制。
- 401/403、429、额度不足、模型错误、超时、5xx 和非法响应分类。
- 日志、任务记录、异常链和 API 响应不包含合成敏感标记。
- 现有 AI 业务 Schema 和非 AI 降级行为保持兼容。

### 12.2 前端自动化测试

- 账号 AI 总开关。
- 不能选择已停用或无效供应商。
- 供应商切换后状态和模型列表隔离。
- Ollama 与云供应商特有状态按条件显示。
- Key 保留、覆盖、清除和不可解密提示。
- 三种测试操作的独立状态和生成确认。
- 中文错误映射、TypeScript 类型检查和生产构建。

### 12.3 真实浏览器验收

1. 登录管理员账号。
2. 验证服务器 Ollama 网关和 Cloudflare Access 远程模型。
3. 逐个保存并测试 OpenAI、Gemini、DeepSeek、Kimi 和通义千问配置。
4. 分别刷新模型并选择默认模型。
5. 切换当前服务商，确认顶部运行状态同步变化。
6. 对每个可用供应商执行最小生成测试。
7. 对每个可用供应商至少执行一次 AI 分类推荐。
8. 停用 Ollama 并切换到云服务商。
9. 关闭账号 AI，确认 AI 操作明确降级且非 AI 功能正常。
10. 重新启用 Ollama，确认远程 Access 和原有模型恢复。

若某个供应商没有可用的真实测试凭据，应使用受控 mock 完成自动化验收，并把真实验证标记为待人工凭据测试，不伪造通过结论。

## 13. 交付边界

实施严格限制在：

- AI 配置模型和迁移。
- 供应商客户端与运行时解析。
- 凭据安全和网络安全。
- AI 设置与状态页面。
- AI 路由接入。
- 相关自动化测试、README、部署文档和项目进度记录。

不顺带重构图书检索、分类、借阅、统计或其他模块。实施完成后执行后端完整测试、前端完整测试、类型检查、生产构建、Compose 验证和可执行的真实接口烟雾测试，再按仓库交付约定提交、推送并同步 Obsidian。
