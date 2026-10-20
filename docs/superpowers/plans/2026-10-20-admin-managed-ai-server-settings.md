# 管理员前端管理 AI 服务器配置实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让管理员在系统设置页安全管理全局 AI/Ollama 服务器配置和 Cloudflare Access 凭据，保存后立即生效，同时保留账号级模型偏好与环境变量回退。

**Architecture:** 新增全局服务器 AI 配置及脱敏审计表，用由 `APP_SECRET_KEY` 派生的 AEAD 密钥加密 Access 凭据；独立服务负责数据库、环境变量和默认值的优先级解析。管理员 API 执行角色、双重密码、传输安全与事务校验，现有 AI 运行时统一读取该服务。前端新增独立服务器配置面板，现有账号配置保持原接口并在运行时变更后重新同步。

**Tech Stack:** FastAPI、SQLAlchemy 2、Alembic、Pydantic 2、`cryptography` AES-GCM/HKDF、pytest、Vue 3、TypeScript、Element Plus、Vitest、Docker Compose、Playwright。

**Spec:** `docs/superpowers/specs/2026-10-20-admin-managed-ai-server-settings-design.md`

## Global Constraints

- Access Client ID、Secret、管理员密码、升级专用密码、密文和派生密钥不得出现在 API 响应、日志、审计内容、测试输出、浏览器持久化或 Git 中。
- 服务器配置写操作只允许管理员，并且同一次请求必须验证当前管理员密码与服务器升级专用密码。
- 服务器数据库配置优先于环境变量和程序默认值；删除覆盖项后立即回退，不修改宿主机 `.env`，不执行 Docker 命令。
- 账号级地址和模型只能覆盖请求目标及模型，不能放宽 AI 总开关、可信 Origin、Access、TLS 或超时边界。
- Access headers 只发送到与可信 HTTPS Origin 规范化后严格同源的目标；HTTP、本地名称、IP、`.local` 及其他 Origin永不携带凭据。
- `APP_SECRET_KEY` 为默认、示例或低于生产强度时，拒绝保存数据库 Access 凭据；非敏感服务器配置仍可保存。
- 保存成功和健康检查是两个独立结果；连接失败不回滚已提交配置，也不影响任何非 AI 功能。
- 新依赖下载前必须在实际执行环境有界测速官方 PyPI 和可用候选镜像，使用当时最快且校验可用的源，仓库默认仍保留官方源。
- 所有行为变更遵循 RED → GREEN → REFACTOR；每个任务先观察目标测试因缺少功能而失败，再写最小实现。
- 同类失败连续两次无法解决时停止自动修复，保留诊断证据并移交人工或新任务，不进入第三轮或扩大范围。

## Review Focus

- `APP_SECRET_KEY` 轮换或密文篡改时必须安全禁用 Access，不能回退到部分数据库凭据或泄露异常内容；Task 1 的错误密钥和篡改测试覆盖。
- 空凭据、单项凭据、成对覆盖和显式清除的语义不能混淆；Task 3 的 API 事务测试覆盖。
- 反向代理后的 HTTPS 与本机回环 HTTP 必须可写，远程明文 HTTP 必须拒绝；Task 3 的传输边界测试覆盖。
- 多实例或并发请求观察到配置版本变化时不能继续使用旧密钥或半套配置；Task 2 的逐请求版本解析和事务可见性测试覆盖。
- 保存成功但自动健康检查失败时，页面必须明确显示“配置已保存、连接失败”，不能诱导重复提交敏感值；Task 6 的前端编排测试覆盖。

---

### Task 1: 全局配置模型、迁移与凭据加密

**Files:**
- Create: `backend/app/models/system_ai_setting.py`
- Create: `backend/app/models/system_config_audit.py`
- Create: `backend/app/services/credential_crypto.py`
- Create: `backend/app/tests/test_credential_crypto.py`
- Create: `backend/alembic/versions/0002_system_ai_settings.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/pyproject.toml`

**Interfaces:**
- Produces: `SystemAISetting` singleton model with non-sensitive values, versioned Client ID/Secret ciphertexts, `config_version`, `updated_by`, `created_at`, and `updated_at`.
- Produces: `SystemConfigAudit` append-only model with `action`, `changed_fields`, `config_version`, `created_by`, and `created_at`; it has no generic payload column.
- Produces: `CredentialCipher.from_secret_key(secret_key: str) -> CredentialCipher`, `encrypt(plaintext: str) -> str`, and `decrypt(ciphertext: str) -> str`.
- Produces: `is_production_secret_key(secret_key: str) -> bool`.

- [ ] **Step 1: Benchmark and select the dependency source**

Run bounded metadata/download probes for official PyPI and currently available candidate mirrors from the backend build environment. Record only timings and selected source in task notes; do not change repository defaults. Add `cryptography>=43.0.0` to `backend/pyproject.toml` and install from the fastest verified source with official PyPI fallback.

- [ ] **Step 2: Write failing crypto tests**

Add tests named:

```python
def test_credential_cipher_round_trips_without_exposing_plaintext(): ...
def test_credential_cipher_uses_unique_nonce_for_same_plaintext(): ...
def test_credential_cipher_rejects_tampering_and_wrong_secret_key(): ...
def test_production_secret_key_rejects_defaults_examples_and_short_values(): ...
```

Assert that ciphertexts are versioned, differ across encryptions, never contain plaintext, and decryption failure raises one sanitized domain exception whose text contains no key or ciphertext.

- [ ] **Step 3: Run the crypto tests and verify RED**

Run: `cd backend && pytest app/tests/test_credential_crypto.py -v`

Expected: FAIL because `credential_crypto` and its interfaces do not exist.

- [ ] **Step 4: Implement the minimal AEAD service**

Implement AES-GCM with a random 96-bit nonce and HKDF-SHA256 using a fixed application-purpose info label. Use a compact versioned encoding. Reject known repository defaults (`change-this-secret`, `dev-secret-change-me-in-production`), empty values and values shorter than 32 bytes in `is_production_secret_key`.

- [ ] **Step 5: Run the crypto tests and verify GREEN**

Run: `cd backend && pytest app/tests/test_credential_crypto.py -v`

Expected: all tests PASS without logging secret material.

- [ ] **Step 6: Add model metadata and migration tests**

Extend `test_credential_crypto.py` or create a focused metadata test that asserts `system_ai_settings` and `system_config_audits` are registered, the singleton row uses a fixed primary key, and audit storage has no unrestricted request/payload column.

- [ ] **Step 7: Implement models and Alembic revision**

Create revision `0002` with `down_revision = "0001"`. The upgrade creates both tables, foreign keys to `users`, and indexes on audit action/time; downgrade removes only these two tables. Import both models from `app.models` so `Base.metadata.create_all` and Alembic discover them.

- [ ] **Step 8: Verify task scope**

Run:

```bash
cd backend
pytest app/tests/test_credential_crypto.py -v
alembic -c alembic/alembic.ini upgrade head
alembic -c alembic/alembic.ini downgrade 0001
alembic -c alembic/alembic.ini upgrade head
```

Expected: tests PASS and migrations complete in both directions against a disposable database.

- [ ] **Step 9: Commit**

```bash
git add backend/app/models/system_ai_setting.py backend/app/models/system_config_audit.py backend/app/models/__init__.py backend/app/services/credential_crypto.py backend/app/tests/test_credential_crypto.py backend/alembic/versions/0002_system_ai_settings.py backend/pyproject.toml
git commit -m "feat: add encrypted AI server settings storage"
```

### Task 2: 服务器配置解析、优先级与事务服务

**Files:**
- Create: `backend/app/services/system_ai_setting_service.py`
- Create: `backend/app/tests/test_system_ai_setting_service.py`
- Modify: `backend/app/services/ai_setting_service.py`

**Interfaces:**
- Consumes: `SystemAISetting`, `SystemConfigAudit`, `CredentialCipher`, `is_production_secret_key` from Task 1.
- Produces: immutable `ServerAIConfig` and `ServerAICredentialState` dataclasses.
- Produces: immutable `ServerAIConfigUpdateValues(enabled: bool, default_base_url: str, trusted_base_url: str, default_model: str, connect_timeout_seconds: float, read_timeout_seconds: float, verify_tls: bool)`.
- Produces: immutable `CredentialUpdate(mode: Literal["preserve", "replace_pair", "clear_pair"], client_id: str = "", client_secret: str = "")` that rejects values inconsistent with its mode.
- Produces: `get_effective_server_ai_config(db: Session) -> ServerAIConfig`.
- Produces: `update_server_ai_config(db: Session, *, values: ServerAIConfigUpdateValues, credentials: CredentialUpdate, actor_id: int) -> ServerAIConfig`.
- Produces: `reset_server_ai_config(db: Session, *, actor_id: int) -> ServerAIConfig`.
- Produces: `get_ollama_runtime_config(db: Session, user: User | None) -> OllamaRuntimeConfig` using server config plus account overrides.

- [ ] **Step 1: Write failing precedence and transaction tests**

Add tests named:

```python
def test_server_config_falls_back_to_environment_then_defaults(): ...
def test_database_server_config_overrides_environment_and_increments_version(): ...
def test_reset_immediately_restores_environment_config(): ...
def test_empty_credentials_preserve_and_explicit_clear_removes_both(): ...
def test_partial_or_failed_encryption_rolls_back_the_entire_update(): ...
def test_changed_fields_audit_contains_names_only(): ...
def test_corrupt_credentials_fail_closed_without_secret_in_error(): ...
def test_account_target_and_model_override_server_defaults_without_overriding_security(): ...
def test_concurrent_reader_observes_only_complete_committed_versions(): ...
```

Use synthetic credentials with obvious markers and assert those markers are absent from serialized responses, audits and captured logs.

- [ ] **Step 2: Run service tests and verify RED**

Run: `cd backend && pytest app/tests/test_system_ai_setting_service.py -v`

Expected: FAIL because the server setting service and effective runtime integration do not exist.

- [ ] **Step 3: Implement environment/default normalization**

Implement exact conversion from `Settings` to `ServerAIConfig`, including `configuration_source`. Treat any recognized AI environment alias that is explicitly present as `environment`; otherwise report `default`. Keep URL normalization and Access Origin matching in existing shared helpers rather than duplicating string comparison.

- [ ] **Step 4: Implement atomic update/reset and audit**

Use one SQLAlchemy transaction for validation-ready values, encryption, singleton upsert/delete and audit append. Credential input has three explicit modes: `preserve`, `replace_pair`, `clear_pair`. Never accept or construct a one-sided pair.

- [ ] **Step 5: Route existing runtime resolution through the new service**

Change `get_ollama_runtime_config` so server-owned fields always come from `get_effective_server_ai_config(db)`, while account-owned URL/model overrides retain current compatibility. Query the singleton/version on each runtime resolution; do not retain decrypted credentials in a cross-request cache in this first implementation.

- [ ] **Step 6: Run focused tests and verify GREEN**

Run:

```bash
cd backend
pytest app/tests/test_system_ai_setting_service.py -v
pytest app/tests/test_ai.py -v
```

Expected: new service tests and all existing AI tests PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/system_ai_setting_service.py backend/app/services/ai_setting_service.py backend/app/tests/test_system_ai_setting_service.py
git commit -m "feat: resolve dynamic AI server configuration"
```

### Task 3: 管理员服务器配置 API、双重认证与传输边界

**Files:**
- Create: `backend/app/schemas/system_ai_setting.py`
- Create: `backend/app/api/routes/system_ai_settings.py`
- Create: `backend/app/tests/test_system_ai_settings_api.py`
- Modify: `backend/app/api/router.py`
- Modify: `backend/app/core/security.py`

**Interfaces:**
- Consumes: service interfaces from Task 2 and existing `verify_password`, `require_admin`, `Settings.upgrade_password`.
- Produces: `GET /api/system/ai-config`, `PUT /api/system/ai-config`, `DELETE /api/system/ai-config`, and `POST /api/system/ai-config/test` contracts from the spec.
- Produces: `require_secure_server_config_transport(request: Request) -> None` accepting HTTPS, trusted private-proxy `X-Forwarded-Proto=https`, or browser origins on `localhost`/`127.0.0.1`; it rejects remote plaintext submissions.
- Produces: Pydantic request models using `SecretStr` for every submitted password or credential.

- [ ] **Step 1: Write failing authorization, authentication and schema tests**

Add tests named:

```python
def test_server_ai_config_requires_admin_for_every_endpoint(): ...
def test_get_returns_only_sanitized_config_and_credential_state(): ...
def test_put_requires_current_admin_and_upgrade_password_atomically(): ...
def test_put_rejects_when_upgrade_password_is_not_configured(): ...
def test_put_preserves_blank_credentials_replaces_pair_and_rejects_partial_pair(): ...
def test_put_rejects_weak_app_secret_only_when_new_credentials_are_saved(): ...
def test_delete_requires_explicit_confirmation_and_restores_environment(): ...
def test_remote_plain_http_is_rejected_but_loopback_and_proxy_https_are_accepted(): ...
def test_api_validation_never_serializes_secret_values(): ...
```

- [ ] **Step 2: Run API tests and verify RED**

Run: `cd backend && pytest app/tests/test_system_ai_settings_api.py -v`

Expected: FAIL with missing schemas/routes.

- [ ] **Step 3: Implement schemas and shared verification helpers**

Define bounded URL/model/timeout fields, pair validation, `clear_access_credentials`, and explicit reset confirmation. Add `verify_admin_secondary_auth(current_user: User, admin_password: SecretStr, upgrade_password: SecretStr) -> None`; compare the upgrade password with `secrets.compare_digest` and expose only stable Chinese errors.

- [ ] **Step 4: Implement transport guard and API routes**

Accept proxy HTTPS only when the direct client IP is private/loopback; parse forwarded protocol without trusting forwarded client IP. Permit local development HTTP only when the browser Origin/Referer hostname is loopback. Call Task 2 services only after authorization, transport and both password checks pass.

- [ ] **Step 5: Implement persisted-config connection test**

The test endpoint calls the existing non-generating health probe only after reading persisted configuration. It does not accept an ad hoc URL or credentials in the request body and does not run generation.

- [ ] **Step 6: Run API and regression tests and verify GREEN**

Run:

```bash
cd backend
pytest app/tests/test_system_ai_settings_api.py -v
pytest app/tests/test_system.py app/tests/test_auth.py app/tests/test_ai.py -v
```

Expected: all tests PASS; captured responses/logs contain no synthetic secret markers.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/system_ai_setting.py backend/app/api/routes/system_ai_settings.py backend/app/api/router.py backend/app/core/security.py backend/app/tests/test_system_ai_settings_api.py
git commit -m "feat: expose secured AI server settings API"
```

### Task 4: AI 健康缓存和所有业务调用的动态配置接入

**Files:**
- Create: `backend/app/services/ai_health_status_cache.py`
- Create: `backend/app/tests/test_ai_runtime_reload.py`
- Modify: `backend/app/api/routes/ai.py`
- Modify: `backend/app/api/routes/system_ai_settings.py`
- Modify: `backend/app/tests/test_ai.py`

**Interfaces:**
- Consumes: dynamic `get_ollama_runtime_config` from Task 2.
- Produces: `AIHealthStatusCache.get(user_id: int, fingerprint: str) -> AIHealthResponse`, `put(user_id: int, fingerprint: str, status: AIHealthResponse) -> None`, `invalidate_user(user_id: int) -> None`, and `invalidate_all() -> None` with the existing bounded entry behavior and unchecked-response fallback.
- Guarantees: every model list, health, classification, content recommendation and natural-search path resolves the current server configuration before constructing `OllamaClient`.

- [ ] **Step 1: Write failing runtime reload tests**

Add tests named:

```python
def test_server_save_invalidates_all_cached_health_states(): ...
def test_server_reset_changes_next_ai_request_without_process_restart(): ...
def test_saved_disabled_state_prevents_ollama_client_construction(): ...
def test_account_runtime_fingerprint_changes_when_server_security_config_changes(): ...
def test_non_ai_health_and_book_api_survive_server_ai_failure(): ...
```

- [ ] **Step 2: Run reload tests and verify RED**

Run: `cd backend && pytest app/tests/test_ai_runtime_reload.py -v`

Expected: FAIL because server config mutations do not yet have a public cache invalidation boundary.

- [ ] **Step 3: Extract the bounded health cache**

Move cache locking, bounded eviction, user invalidation and fingerprint lookup from `routes/ai.py` into `AIHealthStatusCache`. Preserve cancellation and secret-lifetime behavior covered by existing AI tests.

- [ ] **Step 4: Invalidate globally after committed server changes**

Call `.invalidate_all()` only after Task 2 update/reset commits successfully. Failed validation, authentication, encryption or database writes must leave cache and effective configuration unchanged.

- [ ] **Step 5: Verify every AI entry point resolves dynamically**

Review all `OllamaClient` construction sites and route them through the dynamic runtime service. Do not refactor prompt behavior or response schemas.

- [ ] **Step 6: Run focused and complete backend tests**

Run:

```bash
cd backend
pytest app/tests/test_ai_runtime_reload.py app/tests/test_ai.py app/tests/test_ollama_client.py -v
pytest -v
```

Expected: complete backend suite PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/ai_health_status_cache.py backend/app/api/routes/ai.py backend/app/api/routes/system_ai_settings.py backend/app/tests/test_ai_runtime_reload.py backend/app/tests/test_ai.py
git commit -m "feat: reload AI runtime settings without restart"
```

### Task 5: 前端服务器配置类型、API 与独立面板

**Files:**
- Create: `frontend/src/components/ai/ServerAISettingsPanel.vue`
- Create: `frontend/src/components/ai/ServerAISettingsPanel.spec.ts`
- Modify: `frontend/src/types/settings.ts`
- Modify: `frontend/src/api/settings.ts`
- Modify: `frontend/src/api/settings.spec.ts`

**Interfaces:**
- Consumes: Task 3 API contracts.
- Produces: `SystemAIConfig`, `SystemAICredentialState`, `SystemAIConfigUpdate`, and `SystemAIAuth` TypeScript interfaces.
- Produces: `fetchSystemAIConfig()`, `saveSystemAIConfig(input)`, `resetSystemAIConfig(auth)`, and `testSystemAIConfig()`.
- Produces: `<ServerAISettingsPanel @runtime-changed="..." />`; the emitted event contains no credential or password fields.

- [ ] **Step 1: Write failing API normalization tests**

Extend `frontend/src/api/settings.spec.ts` with tests that assert snake_case mapping, DELETE body semantics, absent credential values, configured/usable status, and stable omission of secret fields.

- [ ] **Step 2: Run API tests and verify RED**

Run: `cd frontend && npm test -- src/api/settings.spec.ts`

Expected: FAIL because the new types and functions do not exist.

- [ ] **Step 3: Implement types and API adapters**

Keep wire-format interfaces private to `settings.ts`. Public TypeScript types use camelCase and never define a field representing saved credential plaintext.

- [ ] **Step 4: Write failing panel interaction tests**

Add tests named:

```typescript
it('renders source status and never renders saved credential values', ...)
it('requires both passwords before server save', ...)
it('preserves blank credentials and sends explicit clear only when selected', ...)
it('requires an extra warning before disabling TLS verification', ...)
it('clears every sensitive ref after success failure and dialog close', ...)
it('requires confirmation and both passwords before environment reset', ...)
it('emits runtime-changed after save even when follow-up health fails', ...)
```

- [ ] **Step 5: Run panel tests and verify RED**

Run: `cd frontend && npm test -- src/components/ai/ServerAISettingsPanel.spec.ts`

Expected: FAIL because the panel does not exist.

- [ ] **Step 6: Implement the panel**

Use switches for `enabled` and `verifyTls`, numeric inputs for timeouts, password inputs for credentials/authentication, and explicit buttons for save, test and restore. Keep dimensions stable and Chinese labels concise. Use one dedicated authentication dialog and clear its reactive object in `finally` plus dialog close hooks.

- [ ] **Step 7: Verify Task 5**

Run:

```bash
cd frontend
npm test -- src/api/settings.spec.ts src/components/ai/ServerAISettingsPanel.spec.ts
npm run typecheck
```

Expected: tests and typecheck PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/types/settings.ts frontend/src/api/settings.ts frontend/src/api/settings.spec.ts frontend/src/components/ai/ServerAISettingsPanel.vue frontend/src/components/ai/ServerAISettingsPanel.spec.ts
git commit -m "feat: add admin AI server settings panel"
```

### Task 6: 系统设置页编排、状态同步与真实浏览器流程

**Files:**
- Modify: `frontend/src/pages/settings/SettingsPage.vue`
- Modify: `frontend/src/pages/settings/SettingsPage.spec.ts`
- Modify: `frontend/src/components/ai/OllamaConnectionStatus.vue`
- Modify: `frontend/src/components/ai/OllamaConnectionStatus.spec.ts`
- Create: `e2e/system-ai-settings.spec.ts`

**Interfaces:**
- Consumes: `<ServerAISettingsPanel>` and existing account AI/health APIs.
- Produces: page sections “服务器 AI 配置”“当前运行状态”“当前账号 AI 偏好”.
- Guarantees: server runtime changes trigger account settings reload, old health state removal, then one non-generating refresh; save success and health failure remain distinct UI outcomes.

- [ ] **Step 1: Write failing page orchestration tests**

Add tests named:

```typescript
it('separates_server_settings_runtime_status_and_account_preferences', ...)
it('reloads_account_runtime_and_clears_stale_health_after_server_change', ...)
it('shows_saved_but_connection_failed_without_reopening_sensitive_dialog', ...)
it('keeps_non_ai_settings_usable_when_server_config_load_fails', ...)
```

- [ ] **Step 2: Run page tests and verify RED**

Run: `cd frontend && npm test -- src/pages/settings/SettingsPage.spec.ts`

Expected: FAIL because the server panel and orchestration are not mounted.

- [ ] **Step 3: Integrate the three page sections**

Mount the server panel above the existing account provider editor, rename account copy to make ownership explicit, and keep the current `OllamaConnectionStatus` as the single runtime-status display. Avoid nested cards; use full-width sections/dividers inside the existing AI configuration surface.

- [ ] **Step 4: Implement runtime-change orchestration**

On `runtime-changed`, reload `/ai/config`, clear the stale status, then perform `fetchAIHealth(true)`. Preserve the save result toast before any health error toast. Do not automatically call generation or model loading.

- [ ] **Step 5: Write and run browser E2E**

Cover admin login, server config status visibility, double-auth dialog, validation without sending secrets, synthetic save, persisted reload, explicit reset, and continued access to the books page after a forced AI connection failure. Use synthetic credentials and a controlled test upstream; never capture entered values in screenshots or traces.

Run: `cd frontend && npm run test:e2e -- ../e2e/system-ai-settings.spec.ts`

Expected: E2E PASS in the isolated test environment.

- [ ] **Step 6: Run complete frontend verification**

Run:

```bash
cd frontend
npm test
npm run typecheck
npm run build
```

Expected: all Vitest suites, typecheck and production build PASS; only previously documented bundle-size warning may remain.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/settings/SettingsPage.vue frontend/src/pages/settings/SettingsPage.spec.ts frontend/src/components/ai/OllamaConnectionStatus.vue frontend/src/components/ai/OllamaConnectionStatus.spec.ts e2e/system-ai-settings.spec.ts
git commit -m "feat: manage AI server settings from system page"
```

### Task 7: 文档、Docker 验收、安全扫描与交付闭环

**Files:**
- Modify: `README.md`
- Modify: `backend/README.md`
- Modify: `docs/api-contract.md`
- Modify: `docs/deployment.md`
- Modify: `docs/development.md`
- Modify: `docs/frontend-spec.md`
- Modify: `docs/home-library-web-app-plan.md`
- Modify: `docs/superpowers/specs/2026-10-20-admin-managed-ai-server-settings-design.md` only if implementation evidence requires an explicit correction
- Modify: Obsidian project overview outside the repository after push

**Interfaces:**
- Consumes: all completed behavior and verification evidence from Tasks 1–6.
- Produces: operator guidance that distinguishes bootstrap environment settings from database overrides and never contains real credentials.

- [ ] **Step 1: Update documentation from verified behavior**

Document the page workflow, configuration precedence, double authentication, HTTPS/local transport rule, weak `APP_SECRET_KEY` behavior, encrypted credential recovery limits, environment reset, and non-AI degradation. Use placeholders only for secrets.

- [ ] **Step 2: Run repository-level security scans**

Search tracked files and generated logs for synthetic secret markers, non-empty real Access variables, `.env`, private keys and credential headers. Verify API responses, audit rows, test artifacts and browser traces do not retain entered values.

- [ ] **Step 3: Run complete automated gates**

Run:

```bash
cd backend && pytest -v
cd ../frontend && npm test && npm run typecheck && npm run build
cd .. && docker compose config >/dev/null
docker compose -f docker-compose.prod.yml config >/dev/null
```

Expected: all commands PASS.

- [ ] **Step 4: Build and test Docker after bounded source benchmarking**

Before dependency/image downloads, benchmark official and available candidate sources from the Docker environment, select the fastest verified source for this build, and retain official fallback. Rebuild the application with isolated test volumes and ports, apply Alembic migration, and verify health, login, books and settings APIs.

- [ ] **Step 5: Execute three credential-state acceptance paths**

Verify with controlled upstreams:

1. no credentials → sanitized Access-denied/disabled status;
2. wrong synthetic credentials → sanitized 401/403 classification;
3. valid synthetic credentials → version/tags/ps and model list succeed.

If real Cloudflare Service Token is available through the deployment secret store, additionally run a read-only remote smoke without printing values. If unavailable, report that external smoke as not executed rather than inventing success.

- [ ] **Step 6: Perform full browser acceptance**

From login, verify server configuration save, page reload persistence, connection status, model refresh, account preference preservation, explicit credential clear/reset, and navigation to every non-AI module. Save sanitized screenshots that contain no passwords or credentials.

- [ ] **Step 7: Request independent code review and repair only validated findings**

Use a fresh reviewer for the complete branch. Apply only in-scope findings, rerun affected tests, and stop under the repeated-failure rule if the same issue fails twice.

- [ ] **Step 8: Update versioned docs and commit**

```bash
git add README.md backend/README.md docs/api-contract.md docs/deployment.md docs/development.md docs/frontend-spec.md docs/home-library-web-app-plan.md
git commit -m "docs: document managed AI server settings"
```

- [ ] **Step 9: Final verification, normal push and Obsidian sync**

Confirm the working tree contains only intended changes, push the current registered branch to `origin` without force, then update the Home Library Obsidian project overview with date, branch, commits, tests, Docker/browser evidence, remaining external constraints and GitHub links.

Expected: repository, GitHub and Obsidian all reference the same delivered commit; no required gate remains unreported.
