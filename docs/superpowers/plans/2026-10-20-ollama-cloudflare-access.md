# Ollama Cloudflare Access Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade Home Library's Ollama integration to call local or Cloudflare Access-protected remote servers securely, with async requests, account-compatible configuration, Chinese diagnostics, administrator tests, and graceful degradation.

**Architecture:** A server-owned `OllamaRuntimeConfig` resolves environment-only credentials and account-level URL/model choices. A single async `OllamaClient` owns request headers, trusted-origin checks, timeout handling, response validation, and upstream error mapping; FastAPI routes and the settings UI consume sanitized schemas only. Existing AI business endpoints keep their response contracts, while health and administrator test endpoints expose non-sensitive operational status.

**Tech Stack:** Python 3.11, FastAPI, Pydantic 2, SQLAlchemy, httpx AsyncClient, pytest, Vue 3, TypeScript, Element Plus, Vitest, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-10-20-ollama-cloudflare-access-design.md`

## Global Constraints

- Cloudflare Client ID and Secret may only come from backend environment variables or server secret management.
- Never return, log, persist, document, or expose Cloudflare credentials through `VITE_*` variables.
- Access headers may only be sent when the effective request origin exactly matches the normalized server `OLLAMA_BASE_URL` origin.
- Defaults are `OLLAMA_ENABLED=false`, `OLLAMA_BASE_URL=https://openclaw.lsgood.cn`, `OLLAMA_DEFAULT_MODEL=qwen3.5:4b`, connect timeout `20`, read timeout `180`, and TLS verification enabled.
- Preserve account-level Ollama URL/model settings and existing AI business response schemas; no database migration.
- Ollama failures must not affect `/api/health` or non-AI book, search, borrow, reading, statistics, and backup operations.
- Do not change ssh08, Cloudflare Tunnel, or Cloudflare Access policies in this project.
- Use Chinese user-facing status and error text; never include full prompts, excerpts, upstream bodies, query strings, or secrets in errors and audit records.

## Review Focus

- A malicious account URL with the same hostname text in userinfo, subdomain, or query string must not receive Access headers; covered by Task 2 trusted-origin tests.
- Existing accounts with a saved local URL must continue using that URL without Access headers after the server default becomes remote; covered by Task 1 runtime-config tests.
- Cloudflare-branded 1033 responses may arrive with an HTTP status outside the usual 5xx mapping; covered by Task 2 upstream classification tests.
- A slow model must produce a read-timeout error without being mislabeled as a connection timeout; covered by Task 2 timeout tests.
- A member must be able to inspect health but must not invoke the administrator test endpoint; covered by Task 3 authorization tests.

---

### Task 1: Server and Account Runtime Configuration

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/schemas/ai_setting.py`
- Modify: `backend/app/services/ai_setting_service.py`
- Test: `backend/app/tests/test_ai.py`

**Interfaces:**
- Produces: `OllamaRuntimeConfig` with `enabled`, `base_url`, `trusted_base_url`, `default_model`, `connect_timeout_seconds`, `read_timeout_seconds`, `verify_tls`, `access_client_id`, and `access_client_secret`.
- Produces: `get_ollama_runtime_config(db: Session, user: User | None) -> OllamaRuntimeConfig`.
- Produces: sanitized `AISettingsResponse.ollama_runtime` fields `enabled`, `base_url`, `default_model`, `connect_timeout_seconds`, `read_timeout_seconds`, `verify_tls`, `access_configured`, and `uses_access`.

- [ ] **Step 1: Write failing configuration and account-compatibility tests**

Add tests named:

- `test_ollama_runtime_defaults_to_remote_disabled_configuration`
- `test_ollama_runtime_uses_saved_account_url_without_access_headers`
- `test_ai_config_exposes_access_status_without_credentials`
- `test_legacy_timeout_is_read_timeout_fallback`

Use literal expected values from the spec. Assert that serialized API responses contain no Client ID or Secret keys or values.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `cd backend && pytest app/tests/test_ai.py -k "runtime or access_status or legacy_timeout" -v`

Expected: FAIL because the new settings fields, runtime object, and sanitized response do not exist.

- [ ] **Step 3: Implement settings fields and runtime resolution**

Add the exact environment aliases from the spec to `Settings`. Define `OllamaRuntimeConfig` in `ai_setting_service.py` as an immutable dataclass. Replace the tuple-returning `get_ollama_runtime_config` with the dataclass and derive `access_configured`/`uses_access` without returning credential values in schemas.

- [ ] **Step 4: Run focused and existing AI configuration tests**

Run: `cd backend && pytest app/tests/test_ai.py -k "config or runtime or timeout" -v`

Expected: PASS with no credential value in captured output.

- [ ] **Step 5: Commit the configuration boundary**

```bash
git add backend/app/core/config.py backend/app/schemas/ai_setting.py backend/app/services/ai_setting_service.py backend/app/tests/test_ai.py
git commit -m "feat: add secure Ollama runtime configuration"
```

### Task 2: Central Async Ollama Client and Error Classification

**Files:**
- Create: `backend/app/services/ollama_client.py`
- Modify: `backend/app/services/ollama_service.py`
- Modify: `backend/app/schemas/ai.py`
- Create: `backend/app/tests/test_ollama_client.py`

**Interfaces:**
- Consumes: `OllamaRuntimeConfig` from Task 1.
- Produces: `OllamaClient(runtime: OllamaRuntimeConfig, transport: httpx.AsyncBaseTransport | None = None)`.
- Produces async methods: `version() -> OllamaVersionResponse`, `list_models() -> OllamaModelsResponse`, `running_models() -> OllamaRunningModelsResponse`, `generate_json(...) -> T`, and `chat(...) -> str`.
- Produces exceptions carrying safe metadata only: `OllamaDisabledError`, `OllamaAccessDeniedError`, `OllamaTunnelError`, `OllamaConnectTimeoutError`, `OllamaReadTimeoutError`, `OllamaModelError`, `OllamaUpstreamError`, and `OllamaResponseInvalidError`.

- [ ] **Step 1: Write failing trusted-origin and timeout tests**

Use `httpx.MockTransport` against the real `OllamaClient`. Add tests named:

- `test_trusted_origin_receives_access_headers`
- `test_untrusted_origin_never_receives_access_headers`
- `test_userinfo_subdomain_and_query_cannot_spoof_trusted_origin`
- `test_connect_timeout_and_read_timeout_are_distinct`

Assert observable request headers and exception types; do not assert that a mock was called.

- [ ] **Step 2: Run the focused client tests and verify RED**

Run: `cd backend && pytest app/tests/test_ollama_client.py -k "origin or timeout" -v`

Expected: FAIL because `OllamaClient` and exception types do not exist.

- [ ] **Step 3: Implement origin normalization, AsyncClient timeouts, and safe headers**

Normalize scheme, lowercase hostname, and effective port. Reject URL userinfo for Access matching. Attach both Access headers only when credentials are complete and effective origin equals `trusted_base_url` origin. Configure `httpx.Timeout(connect=..., read=..., write=..., pool=...)` and TLS verification from runtime configuration.

- [ ] **Step 4: Write failing upstream and response-validation tests**

Add table-driven tests named:

- `test_access_401_and_403_map_to_access_denied`
- `test_tunnel_502_503_and_1033_map_to_tunnel_error`
- `test_model_4xx_maps_to_model_error_without_body_leak`
- `test_upstream_5xx_maps_to_upstream_error_without_body_leak`
- `test_generate_json_rejects_invalid_json_and_schema`
- `test_disabled_runtime_never_sends_request`
- `test_transient_connect_failure_retries_once_before_response`

Use literal error categories and include a fake secret/upstream body marker that must not appear in `str(exc)`.

- [ ] **Step 5: Run the new tests and verify RED**

Run: `cd backend && pytest app/tests/test_ollama_client.py -k "access or tunnel or model or upstream or invalid or disabled or retries" -v`

Expected: FAIL on unimplemented classification and retry behavior.

- [ ] **Step 6: Implement health methods, generation, classification, validation, and retry**

Implement the interfaces above. Detect Cloudflare error code `1033` from a bounded response prefix without exposing the body. Retry one transient connect failure only before a response exists. Enforce bounded prompt and output lengths, `stream: false`, JSON format, and Pydantic validation. Keep prompt loading/parsing helpers in `ollama_service.py` if they remain business-oriented.

- [ ] **Step 7: Run the complete async-client suite**

Run: `cd backend && pytest app/tests/test_ollama_client.py -v`

Expected: PASS.

- [ ] **Step 8: Commit the client boundary**

```bash
git add backend/app/services/ollama_client.py backend/app/services/ollama_service.py backend/app/schemas/ai.py backend/app/tests/test_ollama_client.py
git commit -m "feat: add async Cloudflare-aware Ollama client"
```

### Task 3: Health and Administrator Test APIs

**Files:**
- Modify: `backend/app/schemas/ai.py`
- Modify: `backend/app/api/routes/ai.py`
- Test: `backend/app/tests/test_ai.py`

**Interfaces:**
- Consumes: Task 2 `OllamaClient` health methods and exceptions.
- Produces: `GET /api/ai/health` returning sanitized runtime status, version, installed/running model counts, timestamp, status, and Chinese message.
- Produces: `POST /api/ai/test-connection` accepting `{ "generate": bool }`; administrator-only; when true, performs a minimal generation with `keep_alive=0`.
- Produces: stable API error codes defined in the spec through `_ai_error_from_ollama`.

- [ ] **Step 1: Write failing health response and authorization tests**

Add tests named:

- `test_ai_health_returns_sanitized_version_and_model_counts`
- `test_ai_health_requires_login`
- `test_member_cannot_run_ai_connection_test`
- `test_admin_connection_test_does_not_generate_by_default`
- `test_admin_generation_test_requires_explicit_true_and_uses_keep_alive_zero`
- `test_health_failure_returns_chinese_classified_error_without_secret`

- [ ] **Step 2: Run endpoint tests and verify RED**

Run: `cd backend && pytest app/tests/test_ai.py -k "health or connection_test or generation_test" -v`

Expected: FAIL with 404 or missing response schema.

- [ ] **Step 3: Implement schemas, routes, permissions, and bounded last-health state**

Add Pydantic request/response schemas to `schemas/ai.py`. Use `get_current_user` for health and `require_admin` for test connection. Store only the latest sanitized status in a module-level bounded value; reset to “尚未检查” on process start. Do not change `/api/health`.

- [ ] **Step 4: Implement stable Chinese error mapping**

Map every Task 2 exception to the exact API error code and HTTP status from the spec. Details may include safe hostname/status/category only.

- [ ] **Step 5: Run focused endpoint tests**

Run: `cd backend && pytest app/tests/test_ai.py -k "health or connection_test or generation_test or access_denied or tunnel or timeout" -v`

Expected: PASS.

- [ ] **Step 6: Commit operational APIs**

```bash
git add backend/app/schemas/ai.py backend/app/api/routes/ai.py backend/app/tests/test_ai.py
git commit -m "feat: add Ollama health and admin test APIs"
```

### Task 4: Migrate Existing AI Workflows to the Async Client

**Files:**
- Modify: `backend/app/api/routes/ai.py`
- Modify: `backend/app/services/ai_task_service.py`
- Modify: `backend/app/tests/test_ai.py`

**Interfaces:**
- Consumes: Task 1 runtime config and Task 2 async `generate_json`.
- Preserves: existing `/models`, `/classify-book`, `/generate-tags`, `/recommend-book-content`, `/summarize-book`, `/detect-duplicate`, and `/natural-search` response schemas.
- Produces: `sanitize_ai_task_input(input_data: dict[str, Any]) -> dict[str, Any]` for bounded audit data.

- [ ] **Step 1: Convert test transport support and write failing audit-sanitization tests**

Update the existing Ollama test helper to use `httpx.AsyncClient` plus `MockTransport`. Add tests named:

- `test_ai_business_routes_use_account_runtime_and_default_model`
- `test_ai_task_input_truncates_long_summary_and_never_stores_headers`
- `test_ai_failure_does_not_modify_book_or_block_non_ai_health`

Retain all existing schema assertions for category, tags, content recommendation, summary, duplicates, and natural search.

- [ ] **Step 2: Run the full AI suite and verify RED**

Run: `cd backend && pytest app/tests/test_ai.py -v`

Expected: FAIL because routes still call the synchronous service and audit inputs are unbounded.

- [ ] **Step 3: Convert route helpers and endpoints to async**

Change `_run_json_task` and all Ollama-calling route functions to `async def` and `await OllamaClient`. Preserve endpoint paths and response models. Use the account runtime object consistently so the saved default model is not replaced by the first model returned from `/api/tags`.

- [ ] **Step 4: Bound AI task audit input and failure details**

Implement `sanitize_ai_task_input` in `ai_task_service.py` with field whitelisting and bounded strings/lists. Store structured output only after Pydantic validation. Store classified safe error text on failure.

- [ ] **Step 5: Run AI and non-AI regression tests**

Run: `cd backend && pytest app/tests/test_ai.py app/tests/test_books.py app/tests/test_search.py app/tests/test_system.py -v`

Expected: PASS.

- [ ] **Step 6: Commit workflow migration**

```bash
git add backend/app/api/routes/ai.py backend/app/services/ai_task_service.py backend/app/tests/test_ai.py
git commit -m "refactor: route AI workflows through async Ollama client"
```

### Task 5: Settings UI, Status Component, and Chinese Errors

**Files:**
- Modify: `frontend/src/types/settings.ts`
- Modify: `frontend/src/types/ai.ts`
- Modify: `frontend/src/api/settings.ts`
- Modify: `frontend/src/api/ai.ts`
- Create: `frontend/src/api/settings.spec.ts`
- Create: `frontend/src/components/ai/OllamaConnectionStatus.vue`
- Create: `frontend/src/components/ai/OllamaConnectionStatus.spec.ts`
- Create: `frontend/src/utils/aiErrors.ts`
- Create: `frontend/src/utils/aiErrors.spec.ts`
- Modify: `frontend/src/pages/settings/SettingsPage.vue`

**Interfaces:**
- Consumes: Task 1 runtime status and Task 3 health/test endpoints.
- Produces: `fetchAIHealth()`, `testAIConnection(generate: boolean)`, and `getAIErrorMessage(error: unknown) -> string`.
- Produces: `OllamaConnectionStatus` component props `status`, `isAdmin`, `loading`; emits `check`, `test`, and `test-generate`.

- [ ] **Step 1: Write failing API normalization and error mapping tests**

Add table-driven tests for every stable backend AI error code. Assert literal Chinese messages and that unknown errors use a bounded generic fallback. Add API normalization tests proving credential values are absent and `accessConfigured`/`usesAccess` booleans are retained.

- [ ] **Step 2: Run focused frontend tests and verify RED**

Run: `cd frontend && npm test -- src/utils/aiErrors.spec.ts src/api/settings.spec.ts`

Expected: FAIL because helpers and normalized health types do not exist.

- [ ] **Step 3: Implement frontend types, API methods, and Chinese error mapping**

Map snake_case API fields to camelCase. Use `API_TIMEOUTS.aiGeneration` for explicit generation tests. Keep both `aiHealth` and `aiGeneration` at 240 seconds so the backend 180-second read timeout expires first and the Nginx 300-second proxy timeout remains the outer limit. Never define Client ID or Secret fields in frontend types.

- [ ] **Step 4: Write failing status-component tests**

Mount the real component and add tests named:

- `shows_access_credentials_as_configured_status_only`
- `warns_when_current_url_does_not_use_access`
- `hides_admin_test_actions_for_members`
- `emits_separate_check_test_and_generate_actions_for_admin`

- [ ] **Step 5: Run component tests and verify RED**

Run: `cd frontend && npm test -- src/components/ai/OllamaConnectionStatus.spec.ts`

Expected: FAIL because the component does not exist.

- [ ] **Step 6: Implement the status component and integrate SettingsPage**

Render enabled state, effective URL/model, connect/read timeout, TLS state, Access configured status, Access-use warning, last health message, version, and model counts. Use `useAuthStore().isAdmin` for administrator actions. Require `ElMessageBox.confirm` before `generate=true`; model refresh and ordinary health checks must never generate.

- [ ] **Step 7: Run frontend tests, type check, and build**

Run: `cd frontend && npm test`

Run: `cd frontend && npm run typecheck`

Run: `cd frontend && npm run build`

Expected: all commands exit 0.

- [ ] **Step 8: Commit the settings UI**

```bash
git add frontend/src/types frontend/src/api frontend/src/components/ai frontend/src/utils frontend/src/pages/settings/SettingsPage.vue
git commit -m "feat: add Ollama connection status and admin tests"
```

### Task 6: Deployment Mapping, Documentation, and End-to-End Verification

**Files:**
- Modify: `.github/workflows/release.yml`
- Modify: `.env.example`
- Modify: `docker-compose.yml`
- Modify: `docker-compose.prod.yml`
- Create: `scripts/ollama-cloudflare-smoke-test.sh`
- Modify: `README.md`
- Modify: `backend/README.md`
- Modify: `docs/api-contract.md`
- Modify: `docs/deployment.md`
- Modify: `docs/development.md`
- Modify: `docs/home-library-web-app-plan.md`
- Modify: `docs/DOCS_INDEX.md`

**Interfaces:**
- Consumes: Tasks 1-5 environment names, endpoints, and UI behavior.
- Produces: development and production Compose mappings plus a read-only smoke script for `/api/version`, `/api/tags`, and `/api/ps`.
- Produces: GitHub tag-release automation that gates on backend tests and frontend tests/build, then publishes both multi-architecture GHCR images and creates the GitHub Release with deployment assets.

- [ ] **Step 1: Add environment and Compose mappings**

Document and map all spec variables. Keep secrets as empty placeholders. Do not add any `VITE_OLLAMA_*` or credential build arguments. Preserve the optional local Ollama Compose profile.

- [ ] **Step 2: Add the sanitized smoke script**

Adapt the verified handoff script so it reads credentials from environment, never echoes them, defaults to `https://openclaw.lsgood.cn`, checks version/tags/ps only, and does not generate unless a future separately reviewed change adds that behavior.

- [ ] **Step 3: Update existing documentation and roadmap**

Replace local-only wording with local-or-remote behavior, list new variables and endpoints, document Chinese error categories and core-feature degradation, and state that `ollama.lsgood.cn` is not the current default. Add the spec and plan to `DOCS_INDEX.md`; do not create another top-level status document.

- [ ] **Step 4: Gate GitHub Release image generation on backend and frontend validation**

Extend the existing `.github/workflows/release.yml` instead of creating another workflow. For `v*` tags, require successful backend pytest plus frontend Vitest and production build before publishing both `home-library-backend` and `home-library-frontend` multi-architecture GHCR images. Create the GitHub Release only after both images succeed, retaining generated release notes and the existing production Compose, environment template, deploy script, and update script assets. Main-branch image publishing may remain for `latest`, but a failed validation must block image publication.

- [ ] **Step 5: Validate shell, Compose, and workflow files**

Run: `bash -n scripts/ollama-cloudflare-smoke-test.sh`

Run: `docker compose config --quiet`

Run: `docker compose -f docker-compose.prod.yml config --quiet`

Expected: all commands exit 0 and rendered Compose contains no non-empty credential value from tracked files.

- [ ] **Step 6: Run complete backend and frontend verification**

Run: `cd backend && pytest -v`

Run: `cd frontend && npm test`

Run: `cd frontend && npm run typecheck`

Run: `cd frontend && npm run build`

Expected: all commands exit 0 with zero failed tests.

- [ ] **Step 7: Run Docker application verification**

Run: `docker compose up -d --build`

Verify `/api/health`, login, non-AI book listing, AI config sanitization, disabled/no-credential degradation, and the health/test authorization behavior through the running stack. Do not display credentials in command output.

- [ ] **Step 8: Run the real remote smoke test when credentials are present**

First check only whether both credential environment variables are present, without printing values. If present, run `scripts/ollama-cloudflare-smoke-test.sh` and require HTTP 200 for version/tags/ps. If absent, record that authenticated real-interface verification was not executable; an unauthenticated 401/403 check may confirm Access protection but does not count as success.

- [ ] **Step 9: Review the complete diff for secret leakage and scope**

Run: `git diff --check`

Run a secret-name and suspicious-value scan across tracked changes, report only filenames/findings, and confirm no unrelated files are staged.

- [ ] **Step 10: Commit deployment, release automation, and documentation**

```bash
git add .github/workflows/release.yml .env.example docker-compose.yml docker-compose.prod.yml scripts/ollama-cloudflare-smoke-test.sh README.md backend/README.md docs
git commit -m "ci: gate Ollama release images and document deployment"
```

- [ ] **Step 11: Final review, repository sync, and project record**

Use `superpowers:requesting-code-review` for a fresh whole-branch review, then rerun any verification affected by fixes. Before push, re-read `~/.codex/memories/claude-code-migration/github-repositories.md`; push only if Home-Library is registered and the branch can be updated by ordinary push. After push, update the existing Obsidian Home-Library project overview with date, branch, commits, test evidence, completed scope, remaining real-credential validation, and GitHub traceability.
