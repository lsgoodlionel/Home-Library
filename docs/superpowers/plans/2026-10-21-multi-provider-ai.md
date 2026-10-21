# Multi-Provider AI Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade Home Library from an Ollama-only runtime with placeholder cloud settings to a secure account-scoped multi-provider AI runtime with provider-specific model discovery, testing, status, and generation.

**Architecture:** Keep the server-level Ollama gateway as the only owner of Cloudflare Access and Ollama transport policy. Add encrypted account provider credentials, a common `AIProviderClient` protocol with Ollama, OpenAI-compatible, and Gemini adapters, and resolve every AI operation through the account's validated active provider. Preserve existing business API paths and response schemas while replacing Ollama-specific settings and status UI with provider-aware components.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2, Alembic, Pydantic 2, httpx, cryptography/AES-GCM, pytest, Vue 3, TypeScript, Element Plus, Axios, Vitest, Playwright, Docker Compose

**Spec:** `docs/superpowers/specs/2026-10-21-multi-provider-ai-design.md`

## Global Constraints

- `ai_enabled=false` must prevent every account AI upstream request while leaving all non-AI routes available.
- An enabled account must select one enabled, valid provider; never silently fall back to Ollama or another provider.
- Server Ollama Access credentials may only be sent to the exact normalized trusted HTTPS Origin.
- Account API keys must be encrypted at rest and must never appear in API responses, logs, task audits, tracebacks, browser storage, or committed fixtures.
- Existing AI business paths and response schemas remain compatible.
- Cloud provider URLs default to HTTPS and reject protected network targets; Ollama retains its explicit local/LAN use case.
- `AI_PROVIDER_ALLOWED_PRIVATE_ORIGINS` is the server-only comma-separated exact-Origin allowlist for exceptional private cloud-compatible endpoints; it defaults to empty and is never editable by account settings.
- Model names are scoped to their provider; a cloud model must never be sent to Ollama and vice versa.
- Saving valid configuration and proving upstream connectivity are separate outcomes.
- Missing real cloud credentials must be reported as an unexecuted external acceptance item, never as a passing real test.
- Do not modify external book search, classification taxonomy, borrowing, statistics, or unrelated modules.

## Review Focus

1. **Partial credential updates:** leaving the API Key input empty must preserve the existing ciphertext; explicit clear must remove it. Task 1 and Task 2 pin both paths.
2. **Provider-switch races:** a late model-list response from the previous provider must not replace the current provider's options. Task 9 adds a stale-response test.
3. **SSRF through DNS or redirects:** a public-looking hostname resolving or redirecting to a protected address must be rejected before credentials are sent. Task 3 tests both cases.
4. **Provider/model mismatch:** changing `active_provider` while retaining another provider's model must fail validation rather than reach an upstream. Task 2 and Task 8 cover this.
5. **Non-canonical structured output:** fenced JSON, malformed JSON, and schema-invalid JSON must follow the same bounded parsing and safe error path for every provider. Tasks 4, 5, and 8 test these forms.

## File Map

- `backend/alembic/versions/0003_multi_provider_ai.py`: add account AI enablement and encrypted provider credential storage; transactionally migrate old plaintext keys.
- `backend/app/models/user_ai_provider_credential.py`: one encrypted credential row per user/provider.
- `backend/app/services/ai_provider_credential_service.py`: encrypt, decrypt, preserve, replace, clear, and summarize account API keys.
- `backend/app/services/ai_provider_url.py`: cloud provider URL and resolved-address safety validation.
- `backend/app/services/ai_providers/base.py`: common runtime, model, health, error, and client protocol types.
- `backend/app/services/ai_providers/openai_compatible.py`: OpenAI, DeepSeek, Moonshot, Qwen, and custom compatible transport.
- `backend/app/services/ai_providers/gemini.py`: Gemini-native transport and model mapping.
- `backend/app/services/ai_providers/ollama.py`: adapter over the existing `OllamaClient`.
- `backend/app/services/ai_provider_runtime.py`: account configuration validation, runtime resolution, client factory, and provider-scoped model cache.
- `backend/app/schemas/ai_provider.py`: provider-aware config, model, status, and test payloads.
- `backend/app/api/routes/ai_providers.py`: provider test, model-list, and generation-test endpoints.
- `backend/app/api/routes/ai.py`: retain public business paths while routing through the common runtime.
- `frontend/src/components/ai/CurrentAIStatus.vue`: provider-aware effective status.
- `frontend/src/components/ai/AIProviderSettingsPanel.vue`: account switch and per-provider controls.
- `frontend/src/pages/settings/SettingsPage.vue`: compose the new components and keep server Ollama administration separate.

---

### Task 1: Encrypted Account Provider Credentials and Schema Migration

**Files:**
- Create: `backend/alembic/versions/0003_multi_provider_ai.py`
- Create: `backend/app/models/user_ai_provider_credential.py`
- Create: `backend/app/services/ai_provider_credential_service.py`
- Modify: `backend/app/models/user_ai_setting.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/services/credential_crypto.py`
- Test: `backend/app/tests/test_ai_provider_credential_migration.py`
- Test: `backend/app/tests/test_ai_provider_credential_service.py`

**Interfaces:**
- Produces: `ProviderCredentialState = Literal["missing", "configured", "unusable"]`.
- Produces: `get_provider_api_key(db: Session, user_id: int, provider: str) -> str`.
- Produces: `set_provider_api_key(db: Session, user_id: int, provider: str, api_key: str) -> None`.
- Produces: `clear_provider_api_key(db: Session, user_id: int, provider: str) -> None`.
- Produces: `get_provider_credential_state(db: Session, user_id: int, provider: str) -> ProviderCredentialState`.

- [ ] **Step 1: Write migration RED tests**

Add tests named `test_upgrade_adds_ai_enabled_and_provider_credentials`, `test_upgrade_encrypts_and_removes_plaintext_provider_keys`, and `test_upgrade_rolls_back_plaintext_cleanup_when_encryption_fails`. Assert existing accounts default to enabled, ciphertext uses the versioned prefix without containing the source key, and failed migration leaves the original JSON unchanged.

- [ ] **Step 2: Run migration tests and verify RED**

Run: `cd backend && pytest app/tests/test_ai_provider_credential_migration.py -v`

Expected: FAIL because revision `0003`, `ai_enabled`, and the credential table do not exist.

- [ ] **Step 3: Implement migration and model**

Add `UserAISetting.ai_enabled: bool` with database default true. Add `UserAIProviderCredential(id, user_id, provider, api_key_ciphertext, created_at, updated_at)` with a unique constraint on `(user_id, provider)`. Generalize `CredentialCipher` to accept a purpose while preserving the current server-credential purpose as its default; use a distinct `home-library:user-ai-provider-key:v1` purpose for account keys.

- [ ] **Step 4: Write credential service RED tests**

Cover preserve-on-empty, replace, explicit clear, wrong-key `unusable`, user/provider isolation, and response/log exception text containing no plaintext or ciphertext.

- [ ] **Step 5: Implement credential service and make migration transactional**

Implement the five produced interfaces. In revision `0003`, parse each `provider_configs` JSON value, encrypt non-empty legacy `api_key` values, verify decryption, then remove plaintext and update both tables in the same database transaction. When legacy keys exist and the application key cannot safely encrypt them, abort without cleanup.

- [ ] **Step 6: Verify Task 1**

Run: `cd backend && pytest app/tests/test_ai_provider_credential_migration.py app/tests/test_ai_provider_credential_service.py app/tests/test_credential_crypto.py -v`

Expected: PASS.

- [ ] **Step 7: Commit Task 1**

```bash
git add backend/alembic/versions/0003_multi_provider_ai.py backend/app/models backend/app/services/credential_crypto.py backend/app/services/ai_provider_credential_service.py backend/app/tests/test_ai_provider_credential_migration.py backend/app/tests/test_ai_provider_credential_service.py
git commit -m "feat: encrypt account AI provider credentials"
```

### Task 2: Account AI Configuration Contract and Validation

**Files:**
- Modify: `backend/app/schemas/ai_setting.py`
- Modify: `backend/app/services/ai_setting_service.py`
- Test: `backend/app/tests/test_ai.py`
- Test: `backend/app/tests/test_ai_setting_service.py`

**Interfaces:**
- Consumes: Task 1 credential service.
- Produces: `AISettingsResponse.ai_enabled: bool`.
- Produces: `AIProviderConfig.credential_state: ProviderCredentialState` and `clear_api_key: bool` on updates.
- Produces: `validate_account_ai_selection(ai_enabled: bool, active_provider: str, configs: dict[str, dict[str, Any]], credential_states: dict[str, ProviderCredentialState]) -> None`.

- [ ] **Step 1: Write configuration RED tests**

Add tests for account AI off with all providers disabled, enabled account with disabled active provider, cloud active provider without a usable key, empty model, provider/model mismatch, Ollama disable after switching provider, API Key preserve/replace/clear, and no automatic fallback.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `cd backend && pytest app/tests/test_ai_setting_service.py app/tests/test_ai.py -k "config or provider or api_key or disabled" -v`

Expected: FAIL on missing `ai_enabled`, credential state, clear semantics, and validation.

- [ ] **Step 3: Implement schema and persistence changes**

Remove API Key values from `provider_configs`; read and write them only through Task 1. Return credential state without ciphertext. Keep `has_api_key` as a response compatibility alias until the frontend migration is complete, but derive it from `credential_state == "configured"`.

- [ ] **Step 4: Implement selection validation**

Reject an enabled account when the active provider is disabled, has an empty model, or is a cloud provider without usable credentials. Permit all providers disabled only when `ai_enabled=false`. Do not infer or auto-select another provider.

- [ ] **Step 5: Verify Task 2**

Run: `cd backend && pytest app/tests/test_ai_setting_service.py app/tests/test_ai.py -k "config or provider or api_key or disabled" -v`

Expected: PASS with stable Chinese validation errors and no secret values.

- [ ] **Step 6: Commit Task 2**

```bash
git add backend/app/schemas/ai_setting.py backend/app/services/ai_setting_service.py backend/app/tests/test_ai.py backend/app/tests/test_ai_setting_service.py
git commit -m "feat: validate account AI provider settings"
```

### Task 3: Provider Protocol, Safe URL Policy, and Error Taxonomy

**Files:**
- Create: `backend/app/services/ai_providers/__init__.py`
- Create: `backend/app/services/ai_providers/base.py`
- Create: `backend/app/services/ai_provider_url.py`
- Create: `backend/app/schemas/ai_provider.py`
- Modify: `backend/app/core/config.py`
- Test: `backend/app/tests/test_ai_provider_base.py`
- Test: `backend/app/tests/test_ai_provider_url.py`

**Interfaces:**
- Produces: `AIProviderRuntime`, `AIProviderModel`, `AIProviderHealth`, and `AIProviderClient` protocol.
- `AIProviderClient` defines async `test_connection()`, `list_models()`, `generate_text(prompt: str, model: str | None = None)`, and `generate_json(prompt: str, response_model: type[BaseModel], model: str | None = None)`.
- Produces sanitized exceptions: disabled, invalid configuration, authentication, quota, rate limit, model, connect timeout, read timeout, upstream, and invalid response.
- Produces: `validate_cloud_provider_url(url: str, *, allowed_private_origins: set[str]) -> str`.

- [ ] **Step 1: Write protocol and URL-policy RED tests**

Test HTTPS normalization, user-info rejection, loopback/link-local/private/metadata IP rejection, hostname resolution to protected IP rejection, explicit admin allowlist, redirect-to-private rejection contract, and exception-to-safe-error mapping.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `cd backend && pytest app/tests/test_ai_provider_base.py app/tests/test_ai_provider_url.py -v`

Expected: FAIL because the protocol and URL policy do not exist.

- [ ] **Step 3: Implement common types and safe errors**

Use immutable dataclasses for runtime/model/health and a runtime-checkable protocol for clients. Store only provider, safe base URL, model, timeout, TLS, and an in-memory credential value; repr and exception messages must exclude the credential.

- [ ] **Step 4: Implement URL validation**

Normalize cloud URLs, require HTTPS, resolve all A/AAAA results before requests, reject any protected result unless its exact Origin is present in `AI_PROVIDER_ALLOWED_PRIVATE_ORIGINS`, and disable automatic redirects in cloud clients. Parse the allowlist as comma-separated normalized Origins, reject entries containing paths, queries, fragments, or user information, and default to an empty set. Validate each explicit redirect target before following it; do not forward Authorization across Origin changes.

- [ ] **Step 5: Verify Task 3**

Run: `cd backend && pytest app/tests/test_ai_provider_base.py app/tests/test_ai_provider_url.py -v`

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

```bash
git add backend/app/services/ai_providers backend/app/services/ai_provider_url.py backend/app/schemas/ai_provider.py backend/app/core/config.py backend/app/tests/test_ai_provider_base.py backend/app/tests/test_ai_provider_url.py
git commit -m "feat: define secure AI provider protocol"
```

### Task 4: OpenAI-Compatible Provider Client

**Files:**
- Create: `backend/app/services/ai_providers/openai_compatible.py`
- Test: `backend/app/tests/test_openai_compatible_provider.py`

**Interfaces:**
- Consumes: Task 3 protocol, runtime, URL policy, and errors.
- Produces: `OpenAICompatibleProviderClient(runtime: AIProviderRuntime)` implementing all protocol methods.
- Produces provider descriptors for `openai`, `deepseek`, `moonshot`, `qwen`, and `custom` with exact default generation paths and an explicit model-list capability flag.

- [ ] **Step 1: Write request/response RED tests**

Using `httpx.MockTransport`, assert Bearer authentication, `Accept-Encoding: identity`, non-streaming chat payloads, provider-scoped model mapping, no redirects, bounded inputs, and no credentials in exceptions. OpenAI and DeepSeek fixtures must exercise their documented `/models` response. A descriptor without model-list support, or a compatible endpoint returning 404/405 for model enumeration, must return an explicit `unsupported` capability so the UI keeps manual model entry available.

- [ ] **Step 2: Write failure and structured-output RED tests**

Cover 401/403, 429, quota error bodies, unknown model 4xx, connect/read timeout, 5xx, fenced JSON, malformed JSON, and schema-invalid JSON. Assertions use stable sanitized exception classes rather than raw provider messages.

- [ ] **Step 3: Run tests and verify RED**

Run: `cd backend && pytest app/tests/test_openai_compatible_provider.py -v`

Expected: FAIL because the client does not exist.

- [ ] **Step 4: Implement the client**

Use `httpx.AsyncClient` with explicit connect/read/write/pool timeouts, `follow_redirects=False`, and Task 3 URL validation before every target. Centralize compatible response extraction and reuse one bounded JSON parser for `generate_json`.

- [ ] **Step 5: Verify Task 4**

Run: `cd backend && pytest app/tests/test_openai_compatible_provider.py -v`

Expected: PASS for all five compatible provider descriptors.

- [ ] **Step 6: Commit Task 4**

```bash
git add backend/app/services/ai_providers/openai_compatible.py backend/app/tests/test_openai_compatible_provider.py
git commit -m "feat: add OpenAI-compatible AI providers"
```

### Task 5: Gemini Provider Client

**Files:**
- Create: `backend/app/services/ai_providers/gemini.py`
- Test: `backend/app/tests/test_gemini_provider.py`

**Interfaces:**
- Consumes: Task 3 protocol, runtime, URL policy, errors, and bounded JSON parsing contract.
- Produces: `GeminiProviderClient(runtime: AIProviderRuntime)` implementing all protocol methods.

- [ ] **Step 1: Write Gemini RED tests**

Assert native authentication, `models` mapping filtered to `generateContent`, non-streaming `generateContent`, model-name normalization, safe URL enforcement, and text extraction from valid candidates.

- [ ] **Step 2: Add Gemini error and JSON tests**

Cover authentication, quota/rate limit, unavailable model, empty candidates, safety-blocked output, timeout, 5xx, fenced JSON, malformed JSON, and schema-invalid JSON.

- [ ] **Step 3: Run tests and verify RED**

Run: `cd backend && pytest app/tests/test_gemini_provider.py -v`

Expected: FAIL because the Gemini adapter does not exist.

- [ ] **Step 4: Implement Gemini adapter**

Keep Gemini paths and payload mapping inside this adapter; do not route Gemini through the OpenAI-compatible client. Send the API key in the `x-goog-api-key` header, paginate `GET /v1beta/models`, retain only models whose advertised actions include `generateContent`, and use `/v1beta/models/{model}:generateContent` for non-streaming generation. Reuse common limits and sanitized errors.

- [ ] **Step 5: Verify Task 5**

Run: `cd backend && pytest app/tests/test_gemini_provider.py -v`

Expected: PASS.

- [ ] **Step 6: Commit Task 5**

```bash
git add backend/app/services/ai_providers/gemini.py backend/app/tests/test_gemini_provider.py
git commit -m "feat: add Gemini AI provider"
```

### Task 6: Ollama Adapter, Runtime Resolver, Factory, and Model Cache

**Files:**
- Create: `backend/app/services/ai_providers/ollama.py`
- Create: `backend/app/services/ai_provider_runtime.py`
- Modify: `backend/app/services/ai_health_status_cache.py`
- Test: `backend/app/tests/test_ai_provider_runtime.py`
- Test: `backend/app/tests/test_ollama_provider.py`

**Interfaces:**
- Consumes: Tasks 1-5 plus existing `OllamaClient` and server AI state.
- Produces: `resolve_ai_provider_runtime(db: Session, user: User) -> AIProviderRuntime`.
- Produces: `create_ai_provider_client(runtime: AIProviderRuntime) -> AIProviderClient`.
- Produces: `provider_model_cache.get(user_id: int, provider: str, fingerprint: str)` and `.put(...)` with a 300-second TTL.

- [ ] **Step 1: Write runtime RED tests**

Cover account AI off, invalid active provider, cloud credential decryption, provider/model mismatch, Ollama server disabled, account Ollama override, exact trusted Access Origin, and no cloud API Key copied into repr/status/audit inputs.

- [ ] **Step 2: Write Ollama adapter RED tests**

Assert mapping of version/models/running/generation and every existing Ollama error to Task 3 common types without changing Access-header behavior.

- [ ] **Step 3: Write cache isolation RED tests**

Assert entries are isolated by user, provider, and config fingerprint; expire at 300 seconds; and are invalidated on account or server setting updates.

- [ ] **Step 4: Run tests and verify RED**

Run: `cd backend && pytest app/tests/test_ai_provider_runtime.py app/tests/test_ollama_provider.py -v`

Expected: FAIL because resolver, adapter, factory, and provider cache do not exist.

- [ ] **Step 5: Implement runtime and factory**

Resolve exactly one account provider. For Ollama, compose account address/model with server enablement, Access, TLS, and timeouts. For cloud providers, use the encrypted account key and validated cloud URL. Instantiate only the matching adapter.

- [ ] **Step 6: Implement provider model cache**

Use a bounded in-memory cache keyed by user/provider/fingerprint. Never cache credentials or raw upstream responses.

- [ ] **Step 7: Verify Task 6 and existing Ollama regression**

Run: `cd backend && pytest app/tests/test_ai_provider_runtime.py app/tests/test_ollama_provider.py app/tests/test_ollama_client.py app/tests/test_system_ai_setting_service.py -v`

Expected: PASS.

- [ ] **Step 8: Commit Task 6**

```bash
git add backend/app/services/ai_providers/ollama.py backend/app/services/ai_provider_runtime.py backend/app/services/ai_health_status_cache.py backend/app/tests/test_ai_provider_runtime.py backend/app/tests/test_ollama_provider.py
git commit -m "feat: resolve effective AI provider runtime"
```

### Task 7: Provider-Aware Health, Models, and Test APIs

**Files:**
- Create: `backend/app/api/routes/ai_providers.py`
- Modify: `backend/app/api/router.py`
- Modify: `backend/app/api/routes/ai.py`
- Modify: `backend/app/schemas/ai.py`
- Modify: `backend/app/schemas/ai_provider.py`
- Test: `backend/app/tests/test_ai_provider_api.py`
- Modify: `backend/app/tests/test_ai.py`

**Interfaces:**
- Consumes: Task 6 resolver, factory, cache, and Task 3 response types.
- Produces: `POST /api/ai/providers/{provider}/test`.
- Produces: `POST /api/ai/providers/{provider}/models`.
- Produces: `POST /api/ai/providers/{provider}/generate-test`.
- Upgrades: `GET /api/ai/health` and compatibility `GET /api/ai/models` to the active provider.

- [ ] **Step 1: Write endpoint RED tests**

Test saved configuration, unsaved draft configuration, empty-Key-preserves-saved behavior, explicit provider mismatch, member/admin permissions, account AI off, provider-specific status details, model cache use, and generation confirmation payload.

- [ ] **Step 2: Write safe failure RED tests**

For each common error class, assert stable HTTP status/code/Chinese message and that response JSON, logs, tasks, exception chain, and cache contain none of the synthetic key/header/prompt markers.

- [ ] **Step 3: Run tests and verify RED**

Run: `cd backend && pytest app/tests/test_ai_provider_api.py app/tests/test_ai.py -k "health or models or test_connection" -v`

Expected: FAIL on missing routes and Ollama-specific health shape.

- [ ] **Step 4: Implement provider operation routes**

Accept a provider-scoped draft containing address, model, and optional replacement key. Build an ephemeral runtime without persisting the draft. Return the common safe response with provider-specific `details`.

- [ ] **Step 5: Upgrade compatibility endpoints**

Make `/ai/health` and `/ai/models` resolve the account active provider. Keep server-only `/system/ai-config/test` and `/system/ai-config/models` Ollama-specific.

- [ ] **Step 6: Verify Task 7**

Run: `cd backend && pytest app/tests/test_ai_provider_api.py app/tests/test_ai.py -k "health or models or test_connection" -v`

Expected: PASS.

- [ ] **Step 7: Commit Task 7**

```bash
git add backend/app/api backend/app/schemas/ai.py backend/app/schemas/ai_provider.py backend/app/tests/test_ai_provider_api.py backend/app/tests/test_ai.py
git commit -m "feat: expose provider-aware AI diagnostics"
```

### Task 8: Route All AI Business Operations Through the Active Provider

**Files:**
- Modify: `backend/app/api/routes/ai.py`
- Modify: `backend/app/services/ai_task_service.py`
- Test: `backend/app/tests/test_ai.py`
- Test: `backend/app/tests/test_ai_provider_business_routes.py`

**Interfaces:**
- Consumes: Task 6 `resolve_ai_provider_runtime` and `create_ai_provider_client`.
- Preserves: all existing classify, tags, content recommendation, summarize, duplicate, and natural-search API paths and response schemas.
- Produces task audits with provider and model but no credentials, full prompt, or raw model response.

- [ ] **Step 1: Write cross-provider business RED tests**

Parameterize all six business operations across Ollama, OpenAI-compatible, and Gemini fake clients. Assert the selected provider receives the expected model and prompt, response Schema remains unchanged, and `ai_enabled=false` performs zero upstream calls.

- [ ] **Step 2: Add mismatch and structured-output tests**

Assert a request model belonging to another provider is rejected before transport. Test canonical JSON, fenced JSON, malformed JSON, and schema-invalid JSON through representative business routes.

- [ ] **Step 3: Run tests and verify RED**

Run: `cd backend && pytest app/tests/test_ai_provider_business_routes.py app/tests/test_ai.py -k "classify or tags or recommend or summarize or duplicate or natural" -v`

Expected: FAIL because routes still construct `OllamaClient`.

- [ ] **Step 4: Replace route-local Ollama runtime use**

Create one common `_run_provider_json_task(...)` path that resolves the active runtime, validates an optional requested model against that provider, calls `generate_json`, maps safe errors, and writes bounded audit metadata.

- [ ] **Step 5: Remove obsolete Ollama-only business helpers**

Retain only Ollama-specific server diagnostics in their existing server route. Do not change prompt templates or business response models.

- [ ] **Step 6: Verify Task 8 and full backend suite**

Run: `cd backend && pytest app/tests/test_ai_provider_business_routes.py app/tests/test_ai.py -v`

Then run: `cd backend && pytest`

Expected: all tests PASS; only previously documented dependency/time deprecation warnings may remain.

- [ ] **Step 7: Commit Task 8**

```bash
git add backend/app/api/routes/ai.py backend/app/services/ai_task_service.py backend/app/tests/test_ai.py backend/app/tests/test_ai_provider_business_routes.py
git commit -m "feat: use active provider for AI workflows"
```

### Task 9: Frontend Provider API, Types, and Current Status

**Files:**
- Modify: `frontend/src/types/ai.ts`
- Modify: `frontend/src/types/settings.ts`
- Modify: `frontend/src/api/ai.ts`
- Modify: `frontend/src/api/settings.ts`
- Modify: `frontend/src/api/ai.spec.ts`
- Create: `frontend/src/components/ai/CurrentAIStatus.vue`
- Create: `frontend/src/components/ai/CurrentAIStatus.spec.ts`
- Modify: `frontend/src/api/settings.spec.ts`

**Interfaces:**
- Produces: provider-aware `AIHealthStatus`, `AIProviderModel`, `AIProviderCredentialState`, and `AIModelSettings.aiEnabled`.
- Produces frontend calls `testAIProvider`, `fetchAIProviderModels`, and `generateAIProviderTest` with draft config support.
- Replaces account use of `OllamaConnectionStatus` with `CurrentAIStatus`; the old component remains only until Task 10 removes unused imports/tests.

- [ ] **Step 1: Write API normalization RED tests**

Test snake_case mapping, credential states, provider-specific details, key omission, clear flag, AI disabled status, and independent provider model responses.

- [ ] **Step 2: Write current-status RED tests**

Assert Ollama-only fields appear only for Ollama, cloud providers show provider/model/credential state without Ollama version, AI-off performs no automatic check, and Chinese safe errors render.

- [ ] **Step 3: Run tests and verify RED**

Run: `cd frontend && npm test -- src/api/ai.spec.ts src/api/settings.spec.ts src/components/ai/CurrentAIStatus.spec.ts`

Expected: FAIL on missing provider-aware types and component.

- [ ] **Step 4: Implement types, API client, and status component**

Keep account and server Ollama response normalizers separate. Never persist draft keys in local storage. Use stable provider labels from one exported map.

- [ ] **Step 5: Add stale-response test and guard**

Start model requests for provider A then B, resolve A last, and assert only B's models remain visible. Implement a request sequence token or abort controller scoped to the selected provider.

- [ ] **Step 6: Verify Task 9**

Run: `cd frontend && npm test -- src/api/ai.spec.ts src/api/settings.spec.ts src/components/ai/CurrentAIStatus.spec.ts`

Expected: PASS.

- [ ] **Step 7: Commit Task 9**

```bash
git add frontend/src/types frontend/src/api frontend/src/components/ai/CurrentAIStatus.vue frontend/src/components/ai/CurrentAIStatus.spec.ts
git commit -m "feat: add provider-aware AI status client"
```

### Task 10: Account Provider Settings and Server Ollama Page Composition

**Files:**
- Create: `frontend/src/components/ai/AIProviderSettingsPanel.vue`
- Create: `frontend/src/components/ai/AIProviderSettingsPanel.spec.ts`
- Modify: `frontend/src/components/ai/ServerAISettingsPanel.vue`
- Modify: `frontend/src/components/ai/ServerAISettingsPanel.spec.ts`
- Modify: `frontend/src/pages/settings/SettingsPage.vue`
- Modify: `frontend/src/pages/settings/SettingsPage.spec.ts`
- Delete: `frontend/src/components/ai/OllamaConnectionStatus.vue`
- Delete: `frontend/src/components/ai/OllamaConnectionStatus.spec.ts`

**Interfaces:**
- Consumes: Task 9 types, API calls, and `CurrentAIStatus`.
- Produces: account AI switch, valid active-provider selection, per-provider enable/address/key/model controls, test/models/generate actions, and explicit clear-key behavior.

- [ ] **Step 1: Write account-panel RED tests**

Cover AI master off, Ollama toggle enabled for editing, disabling active provider blocked unless switching/off, invalid providers excluded from active selection, key preserve/replace/clear, model-list isolation, save independent from test, and generation confirmation.

- [ ] **Step 2: Write settings-page RED tests**

Assert section order is “服务器 Ollama 网关” (admin only), “当前 AI 运行状态”, then “当前账号 AI 配置”; remove duplicated static runtime rows; and confirm non-admin accounts retain full account controls without server controls.

- [ ] **Step 3: Run tests and verify RED**

Run: `cd frontend && npm test -- src/components/ai/AIProviderSettingsPanel.spec.ts src/components/ai/ServerAISettingsPanel.spec.ts src/pages/settings/SettingsPage.spec.ts`

Expected: FAIL because the new panel and composition do not exist.

- [ ] **Step 4: Implement account provider panel**

Use switches for account/provider enablement, a select for active provider/model, credential-state text plus explicit clear checkbox, and separate icon/text actions for test, model refresh, and confirmed generation. Keep provider draft state until save succeeds.

- [ ] **Step 5: Refine server Ollama panel**

Rename headings and labels, add the trusted-Origin explanation, retain double authentication and server-only model refresh, and remove repeated runtime summary values now owned by `CurrentAIStatus`.

- [ ] **Step 6: Compose SettingsPage and remove old component**

Move account save orchestration into `AIProviderSettingsPanel`, preserve external-search save behavior, and ensure one provider operation does not reset another provider's form or status.

- [ ] **Step 7: Verify Task 10 and frontend gates**

Run: `cd frontend && npm test`

Run: `cd frontend && npm run typecheck`

Run: `cd frontend && npm run build`

Expected: all tests and typecheck PASS; build PASS with only the existing chunk-size warning if still present.

- [ ] **Step 8: Commit Task 10**

```bash
git add frontend/src/components/ai frontend/src/pages/settings/SettingsPage.vue frontend/src/pages/settings/SettingsPage.spec.ts
git commit -m "feat: manage account AI providers in settings"
```

### Task 11: Integration, Migration, Documentation, and Delivery Verification

**Files:**
- Modify: `backend/app/tests/test_ai.py`
- Create: `frontend/e2e/settings-ai-providers.spec.ts`
- Modify: `README.md`
- Modify: `docs/development.md`
- Modify: `docs/deployment.md`
- Modify: existing API/reference or roadmap documents that already track AI configuration
- Modify: `.env.example`
- Modify: `docker-compose.yml`
- Modify: `docker-compose.prod.yml`
- Modify: existing delivery configuration test script covering Compose environment propagation

**Interfaces:**
- Consumes: Tasks 1-10.
- Produces: verified migration from revision `0002` to `0003`, documented provider behavior, and reproducible local/Docker/browser evidence.

- [ ] **Step 1: Add migration and workflow integration tests**

Create a revision-`0002` database containing an Ollama account plus synthetic cloud provider keys, upgrade to head, and assert encrypted migration, configuration reload, provider switching, AI off/on, and non-AI route availability.

- [ ] **Step 2: Add browser workflow tests**

Cover login, server Ollama panel visibility, account AI off/on, provider configuration, model refresh, connection test, generation confirmation, status switching, Ollama disable/cloud enable, and restoration to Ollama. Use mocked cloud upstreams for deterministic CI.

- [ ] **Step 3: Run full local quality gates**

Run: `cd backend && pytest`

Run: `cd frontend && npm test && npm run typecheck && npm run build`

Run: the repository's delivery script tests and `docker compose config --quiet` for development and production configurations.

Expected: zero failures. Do not weaken existing assertions or skip security tests.

- [ ] **Step 4: Build Docker only after bounded source-speed checks**

From the actual Docker build environment, compare the official dependency/image sources with currently configured candidate mirrors using bounded manifest/download probes. Use the fastest verified source for this build while retaining the official production default and fallback; do not globally hard-code a regional mirror from one measurement.

- [ ] **Step 5: Run isolated Docker and browser acceptance**

Use isolated project name, ports, database, volumes, and synthetic provider credentials. Verify migration, backend/frontend health, account settings, all provider mock paths, AI-off degradation, and unchanged book/search/borrow/statistics availability. Capture only sanitized evidence.

- [ ] **Step 6: Run authorized real-provider smoke tests**

Always test the already authorized remote Ollama flow. Test OpenAI, Gemini, DeepSeek, Kimi, and Qwen only when the user has supplied valid credentials for this test; record each as PASS, FAIL with sanitized reason, or NOT RUN because no credential was available.

- [ ] **Step 7: Update documentation and project records**

Document configuration hierarchy, supported providers, connection/model/generation tests, encrypted credential migration, `APP_SECRET_KEY` stability, `AI_PROVIDER_ALLOWED_PRIVATE_ORIGINS` exact-Origin syntax and default-empty behavior, error meanings, rollback, and upgrade commands. Map the allowlist through development and production Compose and pin that propagation in the existing delivery configuration test. Update the existing roadmap/status record rather than creating duplicate top-level status files.

- [ ] **Step 8: Request whole-branch review and close findings**

Use a fresh reviewer on the complete branch. Fix only validated findings within this specification, rerun affected gates, then rerun strict final gates on the final commit.

- [ ] **Step 9: Commit delivery updates**

```bash
git add README.md docs .env.example docker-compose.yml docker-compose.prod.yml scripts backend/app/tests frontend/e2e/settings-ai-providers.spec.ts
git commit -m "docs: document multi-provider AI configuration"
```

- [ ] **Step 10: Final repository delivery**

Confirm a clean worktree, ordinary push to the registered `Home-Library` remote and current branch, successful GitHub Actions, and Obsidian project overview updated with date, branch, commits, exact test evidence, real-provider statuses, residual risks, and next step. Do not force push, merge, tag, or create a Release without separate authorization.
