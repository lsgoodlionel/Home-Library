from __future__ import annotations

import asyncio
import gc
import json
import math
import threading
from collections import OrderedDict
from collections.abc import Callable
from types import CoroutineType, FrameType, FunctionType, ModuleType, SimpleNamespace, TracebackType
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.config import Settings, get_settings
from app.models import AITask, Book
from app.models.user import User
from app.schemas.ai import (
    ClassifyBookRequest,
    DetectDuplicateRequest,
    GenerateTagsRequest,
    NaturalSearchRequest,
    RecommendBookContentRequest,
    SummarizeBookRequest,
)
from app.schemas.ai_setting import OllamaRuntimeStatus
from app.services.ai_setting_service import (
    OllamaRuntimeConfig,
    get_effective_ai_settings,
    get_ollama_runtime_config,
)
from app.services.ai_health_status_cache import AIHealthStatusCache
from app.services.ai_task_service import create_ai_task, sanitize_ai_task_input
from app.services.ollama_client import (
    OllamaAccessDeniedError,
    OllamaClient,
    OllamaConnectTimeoutError,
    OllamaDisabledError,
    OllamaModelError,
    OllamaReadTimeoutError,
    OllamaResponseInvalidError,
    OllamaTunnelError,
    OllamaUpstreamError,
)


OLLAMA_ENVIRONMENT_VARIABLES = (
    "HOME_LIBRARY_OLLAMA_ENABLED",
    "OLLAMA_ENABLED",
    "HOME_LIBRARY_OLLAMA_BASE_URL",
    "OLLAMA_BASE_URL",
    "HOME_LIBRARY_OLLAMA_TRUSTED_BASE_URL",
    "OLLAMA_TRUSTED_BASE_URL",
    "HOME_LIBRARY_OLLAMA_DEFAULT_MODEL",
    "OLLAMA_DEFAULT_MODEL",
    "HOME_LIBRARY_OLLAMA_CONNECT_TIMEOUT_SECONDS",
    "OLLAMA_CONNECT_TIMEOUT_SECONDS",
    "HOME_LIBRARY_OLLAMA_READ_TIMEOUT_SECONDS",
    "OLLAMA_READ_TIMEOUT_SECONDS",
    "HOME_LIBRARY_OLLAMA_TIMEOUT_SECONDS",
    "OLLAMA_TIMEOUT_SECONDS",
    "HOME_LIBRARY_OLLAMA_VERIFY_TLS",
    "OLLAMA_VERIFY_TLS",
    "HOME_LIBRARY_OLLAMA_CF_ACCESS_CLIENT_ID",
    "OLLAMA_CF_ACCESS_CLIENT_ID",
    "HOME_LIBRARY_OLLAMA_CF_ACCESS_CLIENT_SECRET",
    "OLLAMA_CF_ACCESS_CLIENT_SECRET",
)


def _clear_ollama_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in OLLAMA_ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()


def _mock_ollama(monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response]) -> None:
    monkeypatch.setenv("OLLAMA_ENABLED", "true")
    get_settings.cache_clear()
    _mock_async_ollama(monkeypatch, handler)


def _mock_async_ollama(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        "app.api.routes.ai.OllamaClient",
        lambda runtime: OllamaClient(runtime, transport=transport),
    )


def test_ollama_client_requests_identity_encoding_for_cloudflare_responses() -> None:
    runtime = OllamaRuntimeConfig(
        enabled=True,
        base_url="https://ollama.example.test",
        trusted_base_url="https://ollama.example.test",
        default_model="qwen3:8b",
        connect_timeout_seconds=20,
        read_timeout_seconds=180,
        verify_tls=True,
        access_client_id="client-id",
        access_client_secret="client-secret",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["accept-encoding"] == "identity"
        return httpx.Response(200, json={"models": []})

    client = OllamaClient(runtime, transport=httpx.MockTransport(handler))
    response = asyncio.run(client.list_models())

    assert response.models == []


@pytest.fixture
def enabled_ollama_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_ollama_environment(monkeypatch)
    monkeypatch.setenv("OLLAMA_ENABLED", "true")
    monkeypatch.setenv("OLLAMA_BASE_URL", "https://ollama.example.test")
    monkeypatch.setenv("OLLAMA_DEFAULT_MODEL", "qwen3:8b")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def reset_ai_health_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api.routes import ai as ai_routes

    ai_routes._health_status_cache.invalidate_all()


def _future_result_or_error(future: asyncio.Future[Any]) -> Any:
    # Keep graph-walker markers and queues out of tracebacks added by result().
    try:
        return future.result()
    except BaseException as error:
        return error


def _assert_route_exception_graph_excludes(
    exc: BaseException,
    *markers: str,
    forbidden_types: tuple[type, ...] = (),
    include_test_frames: bool = False,
) -> None:
    assert exc.__cause__ is None
    assert exc.__context__ is None

    pending: list[Any] = [exc]
    seen: set[int] = set()
    while pending:
        value = pending.pop()
        if value is None or id(value) in seen:
            continue
        seen.add(id(value))
        assert not isinstance(value, forbidden_types), "sensitive object remains reachable"

        if isinstance(value, bytes):
            text = value.decode("utf-8", errors="replace")
            assert all(marker not in text for marker in markers)
            continue
        if isinstance(value, str):
            assert all(marker not in value for marker in markers)
            continue
        if isinstance(value, dict):
            pending.extend(value.keys())
            pending.extend(value.values())
            continue
        if isinstance(value, (list, tuple, set, frozenset)):
            pending.extend(value)
            continue
        if isinstance(value, asyncio.Future):
            if value.done():
                pending.append(_future_result_or_error(value))
            if isinstance(value, asyncio.Task):
                pending.append(value.get_coro())
            for attribute in ("_children", "_result", "_exception", "_cancel_message"):
                pending.append(getattr(value, attribute, None))
            continue
        if isinstance(value, CoroutineType):
            pending.extend([value.cr_frame, value.cr_await])
            continue
        if isinstance(value, BaseException):
            pending.extend(value.args)
            pending.extend([value.__cause__, value.__context__, value.__traceback__])
        if isinstance(value, TracebackType):
            pending.extend([value.tb_frame, value.tb_next])
            continue
        if isinstance(value, FrameType):
            filename = value.f_code.co_filename
            if include_test_frames or ("/app/" in filename and "/app/tests/" not in filename):
                pending.append(value.f_locals)
            continue
        if not isinstance(value, (type, FunctionType, ModuleType)):
            try:
                pending.append(vars(value))
            except TypeError:
                pass
            for cls in type(value).__mro__:
                slots = cls.__dict__.get("__slots__", ())
                if isinstance(slots, str):
                    slots = (slots,)
                for slot in slots:
                    if slot not in {"__dict__", "__weakref__"}:
                        pending.append(getattr(value, slot, None))


def _generate_response(payload: dict) -> dict:
    return {"response": json.dumps(payload, ensure_ascii=False)}


def _classify_payload() -> dict:
    return {
        "title": "乡土中国",
        "author": "费孝通",
        "publisher": "三联书店",
        "summary": "社会学经典作品",
        "model": "qwen2.5",
    }


def test_ai_health_returns_unchecked_cache_without_refresh(
    client: TestClient,
    member_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def client_must_not_be_created(runtime):
        raise AssertionError("cached health read created an Ollama client")

    monkeypatch.setattr("app.api.routes.ai.OllamaClient", client_must_not_be_created)

    response = client.get("/api/ai/health", headers=member_headers)

    assert response.status_code == 200
    assert response.json() == {
        "status": "unchecked",
        "message": "尚未检查",
        "checked_at": None,
        "version": None,
        "installed_model_count": 0,
        "running_model_count": 0,
        "generated": False,
        "ollama_runtime": None,
    }


def test_ai_health_returns_sanitized_version_and_model_counts(
    client: TestClient,
    member_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    enabled_ollama_runtime: None,
) -> None:
    del enabled_ollama_runtime
    response_marker = "upstream-response-secret-marker"
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.6.2", "ignored": response_marker})
        if request.url.path == "/api/tags":
            return httpx.Response(
                200,
                json={"models": [{"name": "qwen3:8b"}, {"name": "nomic-embed-text"}]},
            )
        if request.url.path == "/api/ps":
            return httpx.Response(200, json={"models": [{"name": "qwen3:8b"}]})
        raise AssertionError(f"unexpected path: {request.url.path}")

    _mock_async_ollama(monkeypatch, handler)

    response = client.get("/api/ai/health?refresh=true", headers=member_headers)
    requested_paths_after_refresh = requested_paths.copy()
    cached = client.get("/api/ai/health", headers=member_headers)

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "message": "AI 服务连接正常",
        "checked_at": response.json()["checked_at"],
        "version": "0.6.2",
        "installed_model_count": 2,
        "running_model_count": 1,
        "generated": False,
        "ollama_runtime": {
            "enabled": True,
            "base_url": "https://ollama.example.test",
            "default_model": "qwen3:8b",
            "connect_timeout_seconds": 20.0,
            "read_timeout_seconds": 180.0,
            "verify_tls": True,
            "access_configured": False,
            "uses_access": False,
        },
    }
    assert response.json()["checked_at"]
    assert cached.status_code == 200
    assert cached.json() == response.json()
    assert requested_paths_after_refresh == ["/api/version", "/api/tags", "/api/ps"]
    assert requested_paths == requested_paths_after_refresh
    assert response_marker not in response.text


def test_ai_health_requires_login(client: TestClient) -> None:
    response = client.get("/api/ai/health")

    assert response.status_code == 401


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("get", "/api/ai/models", None),
        ("post", "/api/ai/classify-book", {"title": "乡土中国"}),
        ("post", "/api/ai/generate-tags", {"title": "乡土中国"}),
        (
            "post",
            "/api/ai/recommend-book-content",
            {"current": {"title": "乡土中国"}, "candidates": [], "missing_fields": []},
        ),
        ("post", "/api/ai/summarize-book", {"title": "乡土中国"}),
        (
            "post",
            "/api/ai/detect-duplicate",
            {"first": {"title": "乡土中国"}, "second": {"title": "乡土中国"}},
        ),
        ("post", "/api/ai/natural-search", {"query": "乡土社会"}),
    ],
)
def test_ai_business_routes_require_login(
    client: TestClient,
    method: str,
    path: str,
    payload: dict | None,
) -> None:
    response = client.request(method, path, json=payload)

    assert response.status_code == 401


@pytest.mark.parametrize(
    ("route_name", "payload", "template"),
    [
        (
            "classify_book",
            ClassifyBookRequest(title="payload-sensitive-marker"),
            "prompt-sensitive-marker {title} {author} {publisher} {summary} {categories}",
        ),
        (
            "generate_tags",
            GenerateTagsRequest(title="payload-sensitive-marker"),
            (
                "prompt-sensitive-marker {title} {author} {publisher} {category_name} "
                "{summary} {existing_tags}"
            ),
        ),
        (
            "recommend_book_content",
            RecommendBookContentRequest(
                current={"title": "payload-sensitive-marker"},
                candidates=[],
                missing_fields=[],
            ),
            "prompt-sensitive-marker {current} {candidates} {missing_fields}",
        ),
        (
            "summarize_book",
            SummarizeBookRequest(title="payload-sensitive-marker"),
            "prompt-sensitive-marker {title} {author} {publisher} {raw_summary} {raw_author_intro}",
        ),
        (
            "detect_duplicate",
            DetectDuplicateRequest(
                first={"title": "payload-sensitive-marker"},
                second={"title": "other"},
            ),
            "prompt-sensitive-marker {first} {second}",
        ),
        (
            "natural_search",
            NaturalSearchRequest(query="payload-sensitive-marker"),
            "prompt-sensitive-marker {query}",
        ),
    ],
)
def test_business_route_api_error_traceback_drops_sensitive_locals(
    monkeypatch: pytest.MonkeyPatch,
    route_name: str,
    payload: Any,
    template: str,
) -> None:
    from app.api.routes import ai as ai_routes

    runtime = OllamaRuntimeConfig(
        enabled=True,
        base_url="https://ollama.example.test",
        trusted_base_url="https://ollama.example.test",
        default_model="qwen3:8b",
        connect_timeout_seconds=20,
        read_timeout_seconds=180,
        verify_tls=True,
        access_client_id="client-id",
        access_client_secret="access-secret-marker",
    )

    class FailingClient:
        def __init__(self, configured_runtime: OllamaRuntimeConfig) -> None:
            self.runtime = configured_runtime

        async def generate_json(self, **kwargs: Any) -> None:
            raise OllamaUpstreamError("safe upstream failure")

    monkeypatch.setattr(ai_routes, "OllamaClient", FailingClient)
    monkeypatch.setattr(ai_routes, "_record_failure", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        ai_routes,
        "_prepare_runtime_and_template",
        lambda *args: (runtime, template),
    )
    monkeypatch.setattr(
        ai_routes,
        "_prepare_classify_context",
        lambda *args: (runtime, "categories", template),
    )

    route = getattr(ai_routes, route_name)
    with pytest.raises(ApiError) as caught:
        asyncio.run(route(payload, object(), SimpleNamespace(id=7)))

    _assert_route_exception_graph_excludes(
        caught.value,
        "access-secret-marker",
        "prompt-sensitive-marker",
        "payload-sensitive-marker",
    )


@pytest.mark.parametrize(("generate", "probe_count"), [(False, 3), (True, 4)])
def test_health_probes_run_concurrently_within_one_backend_timeout(
    monkeypatch: pytest.MonkeyPatch,
    generate: bool,
    probe_count: int,
) -> None:
    from app.api.routes import ai as ai_routes

    runtime = OllamaRuntimeConfig(
        enabled=True,
        base_url="https://ollama.example.test",
        trusted_base_url="https://ollama.example.test",
        default_model="qwen3:8b",
        connect_timeout_seconds=20,
        read_timeout_seconds=180,
        verify_tls=True,
        access_client_id="",
        access_client_secret="",
    )
    safe_runtime = OllamaRuntimeStatus(
        enabled=True,
        base_url=runtime.base_url,
        default_model=runtime.default_model,
        connect_timeout_seconds=20,
        read_timeout_seconds=180,
        verify_tls=True,
        access_configured=False,
        uses_access=False,
    )
    started: set[str] = set()
    all_started = asyncio.Event()

    async def probe(name: str, result: Any) -> Any:
        started.add(name)
        if len(started) == probe_count:
            all_started.set()
        await asyncio.wait_for(all_started.wait(), timeout=0.2)
        return result

    class ConcurrentProbeClient:
        def __init__(self, configured_runtime: OllamaRuntimeConfig) -> None:
            del configured_runtime

        async def version(self) -> Any:
            return await probe("version", SimpleNamespace(version="0.6.2"))

        async def list_models(self) -> Any:
            return await probe("models", SimpleNamespace(models=[]))

        async def running_models(self) -> Any:
            return await probe("running", SimpleNamespace(models=[]))

        async def generate_text(self, **kwargs: Any) -> str:
            return await probe("generate", "OK")

    monkeypatch.setattr(ai_routes, "OllamaClient", ConcurrentProbeClient)
    monkeypatch.setattr(
        ai_routes,
        "_load_health_context",
        lambda *args: (runtime, safe_runtime),
    )

    response = asyncio.run(
        asyncio.wait_for(
            ai_routes._check_ollama(object(), SimpleNamespace(id=11), generate=generate),
            timeout=0.5,
        )
    )

    assert response.status == "healthy"
    assert len(started) == probe_count


@pytest.mark.parametrize(
    ("generate", "failed_probe"),
    [(False, name) for name in ("version", "models", "running", None)]
    + [(True, name) for name in ("version", "models", "running", "generate", None)],
)
@pytest.mark.parametrize("unexpected_failure", [False, True])
def test_health_probe_failure_or_cancellation_drains_all_tasks(
    monkeypatch: pytest.MonkeyPatch,
    generate: bool,
    failed_probe: str | None,
    unexpected_failure: bool,
) -> None:
    from app.api.routes import ai as ai_routes

    runtime = OllamaRuntimeConfig(
        enabled=True,
        base_url="https://ollama.example.test",
        trusted_base_url="https://ollama.example.test",
        default_model="qwen3:8b",
        connect_timeout_seconds=20,
        read_timeout_seconds=180,
        verify_tls=True,
        access_client_id="",
        access_client_secret="",
    )
    safe_runtime = OllamaRuntimeStatus(
        enabled=True,
        base_url=runtime.base_url,
        default_model=runtime.default_model,
        connect_timeout_seconds=20,
        read_timeout_seconds=180,
        verify_tls=True,
        access_configured=False,
        uses_access=False,
    )

    async def exercise() -> None:
        probe_count = 4 if generate else 3
        started: set[str] = set()
        finished: set[str] = set()
        probe_tasks: list[asyncio.Task[Any]] = []
        all_started = asyncio.Event()
        blocked = asyncio.Event()
        unhandled: list[dict[str, Any]] = []
        loop = asyncio.get_running_loop()
        previous_handler = loop.get_exception_handler()
        loop.set_exception_handler(lambda _loop, context: unhandled.append(context))

        async def probe(name: str) -> None:
            task = asyncio.current_task()
            assert task is not None
            probe_tasks.append(task)
            started.add(name)
            if len(started) == probe_count:
                all_started.set()
            try:
                await all_started.wait()
                if name == failed_probe:
                    if unexpected_failure:
                        raise RuntimeError("unexpected probe failure")
                    raise OllamaUpstreamError("safe upstream failure")
                await blocked.wait()
            except asyncio.CancelledError:
                # Cleanup may yield and itself fail; the owner must await it
                # and retrieve this exception before returning to the caller.
                await asyncio.sleep(0)
                raise OllamaUpstreamError("safe cleanup failure") from None
            finally:
                finished.add(name)

        class ProbeClient:
            def __init__(self, configured_runtime: OllamaRuntimeConfig) -> None:
                del configured_runtime

            async def version(self) -> None:
                await probe("version")

            async def list_models(self) -> None:
                await probe("models")

            async def running_models(self) -> None:
                await probe("running")

            async def generate_text(self, **kwargs: Any) -> None:
                await probe("generate")

        monkeypatch.setattr(ai_routes, "OllamaClient", ProbeClient)
        monkeypatch.setattr(ai_routes, "_load_health_context", lambda *args: (runtime, safe_runtime))
        owner = asyncio.create_task(
            ai_routes._check_ollama(object(), SimpleNamespace(id=11), generate=generate)
        )
        try:
            await asyncio.wait_for(all_started.wait(), timeout=1)
            if failed_probe is None:
                owner.cancel()
                expected_error = asyncio.CancelledError
            else:
                expected_error = RuntimeError if unexpected_failure else ApiError
            with pytest.raises(expected_error):
                await asyncio.wait_for(owner, timeout=1)

            assert finished == started
            assert all(task.done() for task in probe_tasks)
            assert not [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
            # A probe exception not retrieved by its owner is reported when
            # its task is released, even if the task has already completed.
            probe_tasks.clear()
            await asyncio.sleep(0)
            assert not unhandled
        finally:
            # Test cleanup must not hide unfinished tasks at the assertions.
            for task in [owner, *probe_tasks]:
                if not task.done():
                    task.cancel()
            await asyncio.gather(owner, *probe_tasks, return_exceptions=True)
            loop.set_exception_handler(previous_handler)

    asyncio.run(exercise())


@pytest.mark.parametrize(
    ("generate", "failed_path"),
    [(False, path) for path in ("/api/version", "/api/tags", "/api/ps")]
    + [(True, path) for path in ("/api/version", "/api/tags", "/api/ps", "/api/generate")],
)
@pytest.mark.parametrize("via_route", [False, True])
def test_health_api_error_graph_drops_completed_probe_secrets(
    monkeypatch: pytest.MonkeyPatch,
    generate: bool,
    failed_path: str,
    via_route: bool,
) -> None:
    from app.api.routes import ai as ai_routes

    runtime = OllamaRuntimeConfig(
        enabled=True,
        base_url="https://ollama.example.test",
        trusted_base_url="https://ollama.example.test",
        default_model="qwen3:8b",
        connect_timeout_seconds=20,
        read_timeout_seconds=180,
        verify_tls=True,
        access_client_id="health-client-id-marker",
        access_client_secret="health-access-secret-marker",
    )
    safe_runtime = OllamaRuntimeStatus(
        enabled=True,
        base_url=runtime.base_url,
        default_model=runtime.default_model,
        connect_timeout_seconds=20,
        read_timeout_seconds=180,
        verify_tls=True,
        access_configured=True,
        uses_access=True,
    )

    async def exercise() -> ApiError:
        started: set[str] = set()
        finished: set[str] = set()
        all_started = asyncio.Event()
        blocked = asyncio.Event()

        async def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            started.add(path)
            if len(started) == (4 if generate else 3):
                all_started.set()
            try:
                await all_started.wait()
                if path == failed_path:
                    return httpx.Response(503, text="health-response-body-marker")
                await blocked.wait()
                raise AssertionError("blocked probe unexpectedly completed")
            finally:
                finished.add(path)

        transport = httpx.MockTransport(handler)
        monkeypatch.setattr(
            ai_routes, "OllamaClient", lambda config: OllamaClient(config, transport=transport)
        )
        monkeypatch.setattr(ai_routes, "_load_health_context", lambda *args: (runtime, safe_runtime))
        db, user = object(), SimpleNamespace(id=11)
        if via_route and generate:
            check = ai_routes.test_ai_connection(
                ai_routes.AIConnectionTestRequest(generate=True), db, user
            )
        elif via_route:
            check = ai_routes.get_ai_health(db, user, refresh=True)
        else:
            check = ai_routes._check_ollama(db, user, generate=generate)
        with pytest.raises(ApiError) as caught:
            await asyncio.wait_for(check, timeout=1)
        assert finished == started
        return caught.value

    error = asyncio.run(exercise())
    _assert_route_exception_graph_excludes(
        error,
        "health-client-id-marker",
        "health-access-secret-marker",
        "health-response-body-marker",
    )


async def _observe_health_owner_cancellation(owner: asyncio.Task[Any]) -> BaseException:
    # Return the exception as a value: setup fixtures never enter its traceback.
    try:
        await owner
    except asyncio.CancelledError as error:
        return error
    raise AssertionError("health owner did not preserve cancellation")


@pytest.mark.parametrize("generate", [False, True])
@pytest.mark.parametrize("repeat_cancel", [False, True])
@pytest.mark.parametrize("cleanup_failure", [False, True])
@pytest.mark.parametrize("upstream_failure_first", [False, True])
def test_health_owner_cancellation_graph_and_complete_drain(
    monkeypatch: pytest.MonkeyPatch,
    generate: bool,
    repeat_cancel: bool,
    cleanup_failure: bool,
    upstream_failure_first: bool,
) -> None:
    from app.api.routes import ai as ai_routes

    runtime = OllamaRuntimeConfig(
        enabled=True,
        base_url="https://ollama.example.test",
        trusted_base_url="https://ollama.example.test",
        default_model="qwen3:8b",
        connect_timeout_seconds=20,
        read_timeout_seconds=180,
        verify_tls=True,
        access_client_id="cancel-client-id-marker",
        access_client_secret="cancel-access-secret-marker",
    )
    safe_runtime = OllamaRuntimeStatus(
        enabled=True, base_url=runtime.base_url, default_model=runtime.default_model,
        connect_timeout_seconds=20, read_timeout_seconds=180, verify_tls=True,
        access_configured=True, uses_access=True,
    )

    async def exercise() -> None:
        count = 4 if generate else 3
        started: set[str] = set()
        cleaned: set[str] = set()
        cleaning: set[str] = set()
        all_started = asyncio.Event()
        all_cleaning = asyncio.Event()
        release_cleanup = asyncio.Event()
        blocked = asyncio.Event()
        unhandled: list[dict[str, Any]] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            started.add(path)
            if len(started) == count:
                all_started.set()
            try:
                await all_started.wait()
                if upstream_failure_first and path == "/api/version":
                    cleaned.add(path)
                    return httpx.Response(503, text="synthetic upstream failure")
                await blocked.wait()
            except asyncio.CancelledError:
                cleaning.add(path)
                if len(cleaning) == count - int(upstream_failure_first):
                    all_cleaning.set()
                await release_cleanup.wait()
                cleaned.add(path)
                if cleanup_failure:
                    raise RuntimeError("synthetic cleanup failure") from None
                raise
            raise AssertionError("blocked probe unexpectedly completed")

        class TrackedTransport(httpx.MockTransport):
            closed = 0

            async def aclose(self) -> None:
                self.closed += 1
                await super().aclose()

        transport = TrackedTransport(handler)
        monkeypatch.setattr(
            ai_routes, "OllamaClient", lambda config: OllamaClient(config, transport=transport)
        )
        monkeypatch.setattr(ai_routes, "_load_health_context", lambda *args: (runtime, safe_runtime))
        user_id = 17
        fingerprint = ai_routes._runtime_fingerprint(runtime)
        cached = ai_routes.AIHealthResponse(status="healthy", message="existing cached status")
        ai_routes._health_status_cache.put(user_id, fingerprint, cached)
        loop = asyncio.get_running_loop()
        previous_handler = loop.get_exception_handler()
        loop.set_exception_handler(lambda _loop, context: unhandled.append(context))
        owner = asyncio.create_task(
            ai_routes._check_ollama(object(), SimpleNamespace(id=17), generate=generate)
        )
        observer = asyncio.create_task(_observe_health_owner_cancellation(owner))
        try:
            await asyncio.wait_for(all_started.wait(), 1)
            if upstream_failure_first:
                # Let the upstream error, rather than owner cancellation,
                # start drain before injecting the external cancellation.
                await asyncio.wait_for(all_cleaning.wait(), 1)
            owner.cancel("cancel-message-marker")
            await asyncio.wait_for(all_cleaning.wait(), 1)
            if repeat_cancel:
                for _ in range(3):
                    owner.cancel("repeat-cancel-message-marker")
                    await asyncio.sleep(0)
                    await asyncio.sleep(0)
                    assert not owner.done(), "repeated cancellation interrupted drain"
            release_cleanup.set()
            error = await asyncio.wait_for(observer, 1)
            assert cleaned == started
            assert transport.closed == count
            assert owner.cancelled()
            assert ai_routes._health_status_cache.get(user_id, fingerprint) is cached
            assert not [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
            _assert_route_exception_graph_excludes(
                error,
                "cancel-client-id-marker", "cancel-access-secret-marker",
                "cancel-message-marker", "repeat-cancel-message-marker",
                "CF-Access-Client-Id", "CF-Access-Client-Secret",
                "cf-access-client-id", "cf-access-client-secret",
                forbidden_types=(OllamaRuntimeConfig, OllamaClient),
                include_test_frames=True,
            )
            del error, owner, observer
            gc.collect()
            await asyncio.sleep(0)
            assert not unhandled
        finally:
            release_cleanup.set()
            # Only the failing test's cleanup may recover unfinished tasks.
            if "owner" in locals():
                if not owner.done():
                    owner.cancel()
                await asyncio.gather(owner, observer, return_exceptions=True)
            loop.set_exception_handler(previous_handler)

    asyncio.run(exercise())


def test_health_cache_operations_hold_lock_during_mutation_and_iteration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes import ai as ai_routes

    class TrackingLock:
        held = False
        entries = 0

        def __enter__(self) -> None:
            assert not self.held
            self.held = True
            self.entries += 1

        def __exit__(self, *args: Any) -> None:
            self.held = False

    lock = TrackingLock()

    class GuardedCache(OrderedDict):
        def _assert_locked(self) -> None:
            assert lock.held

        def __setitem__(self, key: Any, value: Any) -> None:
            self._assert_locked()
            super().__setitem__(key, value)

        def get(self, key: Any, default: Any = None) -> Any:
            self._assert_locked()
            return super().get(key, default)

        def __iter__(self):
            self._assert_locked()
            return super().__iter__()

        def __delitem__(self, key: Any) -> None:
            self._assert_locked()
            super().__delitem__(key)

        def move_to_end(self, key: Any, last: bool = True) -> None:
            self._assert_locked()
            super().move_to_end(key, last)

        def popitem(self, last: bool = True) -> tuple[Any, Any]:
            self._assert_locked()
            return super().popitem(last)

    cache = AIHealthStatusCache(max_entries=1)
    monkeypatch.setattr(cache, "_lock", lock)
    monkeypatch.setattr(cache, "_entries", GuardedCache())
    status = ai_routes.AIHealthResponse(status="healthy")

    cache.put(1, "one", status)
    cache.put(1, "two", status)
    assert cache.get(1, "two") is status
    cache.invalidate_user(1)

    assert lock.entries == 4


def test_ai_health_cache_isolated_by_account(
    client: TestClient,
    admin_headers: dict[str, str],
    member_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    enabled_ollama_runtime: None,
) -> None:
    del enabled_ollama_runtime

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.6.2"})
        return httpx.Response(200, json={"models": []})

    _mock_async_ollama(monkeypatch, handler)

    refreshed = client.get("/api/ai/health?refresh=true", headers=admin_headers)
    other_account = client.get("/api/ai/health", headers=member_headers)

    assert refreshed.status_code == 200
    assert refreshed.json()["status"] == "healthy"
    assert other_account.status_code == 200
    assert other_account.json()["status"] == "unchecked"


def test_ai_health_cache_matches_runtime_with_base_path(
    client: TestClient,
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    enabled_ollama_runtime: None,
) -> None:
    del enabled_ollama_runtime
    configured = client.put(
        "/api/ai/config",
        headers=admin_headers,
        json={
            "active_provider": "ollama",
            "default_model": "path-model",
            "providers": [
                {
                    "provider": "ollama",
                    "enabled": True,
                    "base_url": "https://ollama.example.test/team-a/ollama",
                    "default_model": "path-model",
                }
            ],
        },
    )
    assert configured.status_code == 200
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        if request.url.path.endswith("/api/version"):
            return httpx.Response(200, json={"version": "0.6.2"})
        return httpx.Response(200, json={"models": []})

    _mock_async_ollama(monkeypatch, handler)

    refreshed = client.get("/api/ai/health?refresh=true", headers=admin_headers)
    cached = client.get("/api/ai/health", headers=admin_headers)

    assert refreshed.status_code == 200
    assert refreshed.json()["ollama_runtime"]["base_url"] == (
        "https://ollama.example.test/team-a/ollama"
    )
    assert cached.json() == refreshed.json()
    assert requested_paths == [
        "/team-a/ollama/api/version",
        "/team-a/ollama/api/tags",
        "/team-a/ollama/api/ps",
    ]


def test_ai_settings_save_invalidates_current_user_health_cache(
    client: TestClient,
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    enabled_ollama_runtime: None,
) -> None:
    del enabled_ollama_runtime

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.6.2"})
        return httpx.Response(200, json={"models": []})

    _mock_async_ollama(monkeypatch, handler)
    refreshed = client.get("/api/ai/health?refresh=true", headers=admin_headers)
    assert refreshed.status_code == 200

    current = client.get("/api/ai/config", headers=admin_headers).json()
    saved = client.put(
        "/api/ai/config",
        headers=admin_headers,
        json={
            "active_provider": current["active_provider"],
            "default_model": current["default_model"],
            "providers": current["providers"],
        },
    )
    cached = client.get("/api/ai/health", headers=admin_headers)

    assert saved.status_code == 200
    assert cached.status_code == 200
    assert cached.json()["status"] == "unchecked"


def test_member_cannot_run_ai_connection_test(
    client: TestClient,
    member_headers: dict[str, str],
) -> None:
    response = client.post(
        "/api/ai/test-connection",
        headers=member_headers,
        json={"generate": False},
    )

    assert response.status_code == 403


def test_admin_connection_test_does_not_generate_by_default(
    client: TestClient,
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    enabled_ollama_runtime: None,
) -> None:
    del enabled_ollama_runtime
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.6.2"})
        if request.url.path in {"/api/tags", "/api/ps"}:
            return httpx.Response(200, json={"models": []})
        raise AssertionError(f"unexpected path: {request.url.path}")

    _mock_async_ollama(monkeypatch, handler)

    response = client.post(
        "/api/ai/test-connection",
        headers=admin_headers,
        json={},
    )

    assert response.status_code == 200
    assert response.json()["generated"] is False
    assert requested_paths == ["/api/version", "/api/tags", "/api/ps"]
    cached = client.get("/api/ai/health", headers=admin_headers)
    assert cached.json() == response.json()
    assert requested_paths == ["/api/version", "/api/tags", "/api/ps"]


def test_admin_generation_test_requires_explicit_true_and_uses_keep_alive_zero(
    client: TestClient,
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    enabled_ollama_runtime: None,
) -> None:
    del enabled_ollama_runtime
    generation_payloads: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.6.2"})
        if request.url.path in {"/api/tags", "/api/ps"}:
            return httpx.Response(200, json={"models": []})
        if request.url.path == "/api/generate":
            generation_payloads.append(json.loads(request.content))
            return httpx.Response(200, json={"response": '{"ok":true}'})
        raise AssertionError(f"unexpected path: {request.url.path}")

    _mock_async_ollama(monkeypatch, handler)

    disabled = client.post(
        "/api/ai/test-connection",
        headers=admin_headers,
        json={"generate": False},
    )
    enabled = client.post(
        "/api/ai/test-connection",
        headers=admin_headers,
        json={"generate": True},
    )

    assert disabled.status_code == 200
    assert disabled.json()["generated"] is False
    assert enabled.status_code == 200
    assert enabled.json()["generated"] is True
    assert generation_payloads == [
        {
            "model": "qwen3:8b",
            "prompt": "请回复 OK",
            "stream": False,
            "keep_alive": 0,
        }
    ]


@pytest.mark.parametrize("invalid_generate", ["true", "yes", 1])
def test_admin_connection_test_rejects_non_boolean_generate_without_request(
    client: TestClient,
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    invalid_generate: object,
) -> None:
    def client_must_not_be_created(runtime):
        raise AssertionError("invalid generate value created an Ollama client")

    monkeypatch.setattr("app.api.routes.ai.OllamaClient", client_must_not_be_created)

    response = client.post(
        "/api/ai/test-connection",
        headers=admin_headers,
        json={"generate": invalid_generate},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_admin_connection_failure_updates_health_cache(
    client: TestClient,
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    enabled_ollama_runtime: None,
) -> None:
    del enabled_ollama_runtime

    class FailingOllamaClient:
        async def version(self):
            raise OllamaTunnelError("safe", status_code=503)

        async def list_models(self):
            return SimpleNamespace(models=[])

        async def running_models(self):
            return SimpleNamespace(models=[])

    monkeypatch.setattr(
        "app.api.routes.ai.OllamaClient",
        lambda runtime: FailingOllamaClient(),
    )

    failed = client.post(
        "/api/ai/test-connection",
        headers=admin_headers,
        json={"generate": False},
    )
    cached = client.get("/api/ai/health", headers=admin_headers)

    assert failed.status_code == 503
    assert cached.status_code == 200
    assert cached.json()["status"] == "error"
    assert cached.json()["message"] == "Tunnel 或远程 Ollama Origin 不可用"
    assert cached.json()["checked_at"]


@pytest.mark.parametrize(
    ("error", "expected_code", "expected_status", "expected_message"),
    [
        pytest.param(
            OllamaDisabledError("safe"),
            "AI_SERVICE_DISABLED",
            503,
            "AI 服务尚未启用",
            id="disabled",
        ),
        pytest.param(
            OllamaAccessDeniedError("safe", status_code=403),
            "AI_ACCESS_DENIED",
            502,
            "Cloudflare Access 凭据缺失、无效或策略不允许",
            id="access_denied",
        ),
        pytest.param(
            OllamaTunnelError("safe", status_code=503),
            "AI_TUNNEL_UNAVAILABLE",
            503,
            "Tunnel 或远程 Ollama Origin 不可用",
            id="tunnel",
        ),
        pytest.param(
            OllamaConnectTimeoutError("safe"),
            "AI_CONNECT_TIMEOUT",
            504,
            "无法在限定时间内连接 AI 服务",
            id="connect_timeout",
        ),
        pytest.param(
            OllamaReadTimeoutError("safe"),
            "AI_RESPONSE_TIMEOUT",
            504,
            "模型启动或生成超时",
            id="read_timeout",
        ),
        pytest.param(
            OllamaModelError("safe", status_code=400),
            "AI_MODEL_ERROR",
            502,
            "模型配置或请求参数错误",
            id="model",
        ),
        pytest.param(
            OllamaUpstreamError("safe", reason="connection_failed"),
            "AI_UPSTREAM_ERROR",
            502,
            "未收到上游 HTTP 响应，无法建立连接（ollama.example.test）",
            id="upstream",
        ),
        pytest.param(
            OllamaResponseInvalidError("safe"),
            "AI_RESPONSE_INVALID",
            502,
            "模型返回内容不能安全使用",
            id="response_invalid",
        ),
    ],
)
def test_health_failure_returns_chinese_classified_error_without_secret(
    client: TestClient,
    member_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    expected_code: str,
    expected_status: int,
    expected_message: str,
) -> None:
    secret_marker = "access-secret-route-marker"
    _clear_ollama_environment(monkeypatch)
    monkeypatch.setenv("OLLAMA_ENABLED", "true")
    monkeypatch.setenv("OLLAMA_BASE_URL", "https://ollama.example.test/path")
    monkeypatch.setenv("OLLAMA_CF_ACCESS_CLIENT_ID", "client-id-route-marker")
    monkeypatch.setenv("OLLAMA_CF_ACCESS_CLIENT_SECRET", secret_marker)
    get_settings.cache_clear()

    class FailingOllamaClient:
        async def version(self):
            raise error

        async def list_models(self):
            return SimpleNamespace(models=[])

        async def running_models(self):
            return SimpleNamespace(models=[])

    monkeypatch.setattr(
        "app.api.routes.ai.OllamaClient",
        lambda runtime: FailingOllamaClient(),
    )

    response = client.get("/api/ai/health?refresh=true", headers=member_headers)
    cached = client.get("/api/ai/health", headers=member_headers)
    get_settings.cache_clear()

    assert response.status_code == expected_status
    assert response.json()["error"]["code"] == expected_code
    assert response.json()["error"]["message"] == expected_message
    assert response.json()["error"]["details"]["hostname"] == "ollama.example.test"
    assert response.json()["error"]["details"]["category"] == getattr(error, "category")
    if getattr(error, "reason", None):
        assert response.json()["error"]["details"]["reason"] == error.reason
    assert cached.status_code == 200
    assert cached.json()["status"] == "error"
    assert cached.json()["message"] == expected_message
    assert cached.json()["checked_at"]
    assert secret_marker not in response.text
    assert secret_marker not in cached.text
    assert "client-id-route-marker" not in response.text


def test_ollama_runtime_defaults_to_remote_disabled_configuration(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_ollama_environment(monkeypatch)

    runtime = get_ollama_runtime_config(db, None)
    get_settings.cache_clear()

    assert runtime.enabled is False
    assert runtime.base_url == "https://openclaw.lsgood.cn"
    assert runtime.trusted_base_url == "https://openclaw.lsgood.cn"
    assert runtime.default_model == "qwen3.5:4b"
    assert runtime.connect_timeout_seconds == 20.0
    assert runtime.read_timeout_seconds == 180.0
    assert runtime.verify_tls is True
    assert runtime.access_client_id == ""
    assert runtime.access_client_secret == ""


def test_ollama_runtime_uses_saved_account_url_without_access_headers(
    client: TestClient,
    db: Session,
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_ollama_environment(monkeypatch)
    monkeypatch.setenv("OLLAMA_ENABLED", "true")
    monkeypatch.setenv("OLLAMA_CF_ACCESS_CLIENT_ID", "runtime-client-id")
    monkeypatch.setenv("OLLAMA_CF_ACCESS_CLIENT_SECRET", "runtime-client-secret")

    response = client.put(
        "/api/ai/config",
        headers=admin_headers,
        json={
            "active_provider": "ollama",
            "default_model": "saved-model",
            "providers": [
                {
                    "provider": "ollama",
                    "enabled": True,
                    "base_url": "http://remote-ollama.local:11434",
                    "default_model": "saved-model",
                    "note": "account ollama",
                }
            ],
        },
    )
    user = db.query(User).one()
    runtime = get_ollama_runtime_config(db, user)
    get_settings.cache_clear()

    assert response.status_code == 200
    assert runtime.base_url == "http://remote-ollama.local:11434"
    assert runtime.default_model == "saved-model"
    assert response.json()["ollama_runtime"]["uses_access"] is False


def test_ollama_runtime_keeps_remote_trust_anchor_when_default_target_is_local(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_ollama_environment(monkeypatch)
    monkeypatch.setenv("OLLAMA_ENABLED", "true")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
    monkeypatch.setenv("OLLAMA_TRUSTED_BASE_URL", "https://openclaw.lsgood.cn")
    monkeypatch.setenv("OLLAMA_CF_ACCESS_CLIENT_ID", "runtime-client-id")
    monkeypatch.setenv("OLLAMA_CF_ACCESS_CLIENT_SECRET", "runtime-client-secret")
    get_settings.cache_clear()

    runtime = get_ollama_runtime_config(db, None)
    effective = get_effective_ai_settings(db, None)
    get_settings.cache_clear()

    assert runtime.base_url == "http://host.docker.internal:11434"
    assert runtime.trusted_base_url == "https://openclaw.lsgood.cn"
    assert effective.ollama_runtime.access_configured is True
    assert effective.ollama_runtime.uses_access is False


def test_ai_config_exposes_access_status_without_credentials(
    client: TestClient,
    db: Session,
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_ollama_environment(monkeypatch)
    monkeypatch.setenv("OLLAMA_ENABLED", "true")
    monkeypatch.setenv("OLLAMA_CF_ACCESS_CLIENT_ID", "client-id-test-only")
    monkeypatch.setenv("OLLAMA_CF_ACCESS_CLIENT_SECRET", "client-secret-test-only")

    response = client.get("/api/ai/config", headers=admin_headers)
    get_settings.cache_clear()

    assert response.status_code == 200
    runtime = response.json()["ollama_runtime"]
    assert runtime == {
        "enabled": True,
        "base_url": "https://openclaw.lsgood.cn",
        "default_model": "qwen3.5:4b",
        "connect_timeout_seconds": 20.0,
        "read_timeout_seconds": 180.0,
        "verify_tls": True,
        "access_configured": True,
        "uses_access": True,
    }
    serialized = response.text
    assert "access_client_id" not in serialized
    assert "access_client_secret" not in serialized
    assert "client-id-test-only" not in serialized
    assert "client-secret-test-only" not in serialized

    monkeypatch.setenv("OLLAMA_BASE_URL", "https://user@openclaw.lsgood.cn")
    get_settings.cache_clear()
    invalid_origin = get_effective_ai_settings(db, None)
    get_settings.cache_clear()

    assert invalid_origin.ollama_runtime.uses_access is False


def test_legacy_timeout_is_read_timeout_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_ollama_environment(monkeypatch)
    monkeypatch.setenv("OLLAMA_TIMEOUT_SECONDS", "75")

    settings = Settings(_env_file=None)

    assert settings.ollama_read_timeout_seconds == 75.0


def test_models_reads_ollama_tags(
    client: TestClient,
    member_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": [{"name": "qwen2.5", "size": 123}]})

    _mock_ollama(monkeypatch, handler)

    response = client.get("/api/ai/models", headers=member_headers)

    assert response.status_code == 200
    assert response.json()["models"][0]["name"] == "qwen2.5"


def test_ai_config_is_persisted_per_account(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.get("/api/ai/config", headers=admin_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["active_provider"] == "ollama"
    assert any(provider["provider"] == "openai" for provider in data["providers"])

    updated = client.put(
        "/api/ai/config",
        headers=admin_headers,
        json={
            "active_provider": "ollama",
            "default_model": "remote-qwen",
            "providers": [
                {
                    "provider": "ollama",
                    "enabled": True,
                    "base_url": "http://192.168.1.10:11434",
                    "default_model": "remote-qwen",
                    "note": "remote ollama",
                },
                {
                    "provider": "openai",
                    "enabled": True,
                    "base_url": "https://api.openai.com/v1",
                    "api_key": "sk-test",
                    "default_model": "gpt-test",
                    "note": "openai placeholder",
                },
            ],
        },
    )

    assert updated.status_code == 200
    saved = updated.json()
    assert saved["default_model"] == "remote-qwen"
    ollama = next(provider for provider in saved["providers"] if provider["provider"] == "ollama")
    assert ollama["base_url"] == "http://192.168.1.10:11434"
    openai = next(provider for provider in saved["providers"] if provider["provider"] == "openai")
    assert openai["api_key"] == ""
    assert openai["has_api_key"] is True


@pytest.mark.parametrize(
    "base_url",
    [
        "http://[",
        "http://\nexample.com",
        "http://\texample.com",
        "http://\rexample.com",
        "http://example.com\x85path",
        " http://example.com",
        "http://example.com ",
        "ftp://ollama.example.com",
        "localhost:11434",
        "http:///missing-host",
        "https://ollama.example.com@evil.example",
        "https://ollama.example.com/path?token=secret",
        "https://ollama.example.com/path?",
        "https://ollama.example.com/path#fragment",
        "https://ollama.example.com/path#",
    ],
)
def test_ai_config_rejects_invalid_or_unsupported_base_url(
    client: TestClient,
    admin_headers: dict[str, str],
    base_url: str,
) -> None:
    response = client.put(
        "/api/ai/config",
        headers=admin_headers,
        json={
            "active_provider": "ollama",
            "default_model": "qwen3:8b",
            "providers": [
                {
                    "provider": "ollama",
                    "enabled": True,
                    "base_url": base_url,
                    "default_model": "qwen3:8b",
                }
            ],
        },
    )

    assert response.status_code == 422
    saved = client.get("/api/ai/config", headers=admin_headers).json()
    ollama = next(item for item in saved["providers"] if item["provider"] == "ollama")
    assert ollama["base_url"] != base_url


@pytest.mark.parametrize(
    "base_url",
    [
        "http://localhost:11434",
        "http://127.0.0.1:11434",
        "http://[::1]:11434",
        "https://ollama.example.com/ollama/api",
    ],
)
def test_ai_config_accepts_safe_http_base_urls(
    client: TestClient,
    admin_headers: dict[str, str],
    base_url: str,
) -> None:
    response = client.put(
        "/api/ai/config",
        headers=admin_headers,
        json={
            "active_provider": "ollama",
            "default_model": "qwen3:8b",
            "providers": [
                {
                    "provider": "ollama",
                    "enabled": True,
                    "base_url": base_url,
                    "default_model": "qwen3:8b",
                }
            ],
        },
    )

    assert response.status_code == 200
    ollama = next(item for item in response.json()["providers"] if item["provider"] == "ollama")
    assert ollama["base_url"] == base_url


def test_models_use_account_ollama_base_url(
    client: TestClient,
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client.put(
        "/api/ai/config",
        headers=admin_headers,
        json={
            "active_provider": "ollama",
            "default_model": "remote-qwen",
            "providers": [
                {
                    "provider": "ollama",
                    "enabled": True,
                    "base_url": "http://remote-ollama.local:11434",
                    "default_model": "remote-qwen",
                    "note": "remote ollama",
                }
            ],
        },
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith("http://remote-ollama.local:11434")
        return httpx.Response(200, json={"models": [{"name": "remote-qwen"}]})

    _mock_ollama(monkeypatch, handler)

    response = client.get("/api/ai/models", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["models"][0]["name"] == "remote-qwen"


def test_models_fallback_to_docker_host_for_localhost_ollama(
    client: TestClient,
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client.put(
        "/api/ai/config",
        headers=admin_headers,
        json={
            "active_provider": "ollama",
            "default_model": "local-qwen",
            "providers": [
                {
                    "provider": "ollama",
                    "enabled": True,
                    "base_url": "http://localhost:11434",
                    "default_model": "local-qwen",
                    "note": "local ollama",
                }
            ],
        },
    )

    requested_hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_hosts.append(request.url.host or "")
        if request.url.host == "localhost":
            raise httpx.ConnectError("connection refused", request=request)
        assert request.url.host == "host.docker.internal"
        return httpx.Response(200, json={"models": [{"name": "local-qwen"}]})

    _mock_ollama(monkeypatch, handler)

    response = client.get("/api/ai/models", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["models"][0]["name"] == "local-qwen"
    assert requested_hosts == ["localhost", "host.docker.internal"]


def test_ai_business_routes_use_account_runtime_and_default_model(
    client: TestClient,
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured = client.put(
        "/api/ai/config",
        headers=admin_headers,
        json={
            "active_provider": "ollama",
            "default_model": "saved-default-model",
            "providers": [
                {
                    "provider": "ollama",
                    "enabled": True,
                    "base_url": "http://account-ollama.local:11434",
                    "default_model": "saved-default-model",
                    "note": "account runtime",
                }
            ],
        },
    )
    assert configured.status_code == 200

    generated_payloads = iter(
        [
            {
                "category_code": "C91",
                "category_name": "社会学",
                "confidence": 0.9,
                "tags": ["社会学"],
                "reason": "分类结果",
            },
            {"tags": ["社会学"], "reason": "标签结果"},
            {
                "recommended": {"publisher": "三联书店"},
                "source_summary": "候选来源",
                "confidence": 0.8,
                "reason": "内容结果",
            },
            {"summary": "整理后的简介", "author_intro": "作者简介"},
            {"is_duplicate": True, "confidence": 0.95, "reason": "书目信息一致"},
            {"keyword": "乡土", "tags": ["社会学"]},
        ]
    )
    requested_models: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "account-ollama.local"
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "first-listed-model"}]})
        assert request.url.path == "/api/generate"
        body = json.loads(request.content)
        requested_models.append(body["model"])
        return httpx.Response(200, json=_generate_response(next(generated_payloads)))

    _mock_ollama(monkeypatch, handler)

    assert client.get("/api/ai/models", headers=admin_headers).status_code == 200
    responses = [
        client.post(
            "/api/ai/classify-book",
            headers=admin_headers,
            json={"title": "乡土中国", "author": "费孝通"},
        ),
        client.post(
            "/api/ai/generate-tags",
            headers=admin_headers,
            json={"title": "乡土中国", "summary": "社会学经典"},
        ),
        client.post(
            "/api/ai/recommend-book-content",
            headers=admin_headers,
            json={
                "current": {"title": "乡土中国"},
                "candidates": [{"source": "openlibrary", "publisher": "三联书店"}],
                "missing_fields": ["publisher"],
            },
        ),
        client.post(
            "/api/ai/summarize-book",
            headers=admin_headers,
            json={"title": "乡土中国", "raw_summary": "待整理简介"},
        ),
        client.post(
            "/api/ai/detect-duplicate",
            headers=admin_headers,
            json={"first": {"title": "乡土中国"}, "second": {"title": "乡土中国"}},
        ),
        client.post(
            "/api/ai/natural-search",
            headers=admin_headers,
            json={"query": "找乡土社会学图书"},
        ),
    ]

    assert [response.status_code for response in responses] == [200] * 6
    assert responses[0].json()["category_code"] == "C91"
    assert responses[1].json()["tags"] == ["社会学"]
    assert responses[2].json()["recommended"]["publisher"] == "三联书店"
    assert responses[3].json()["summary"] == "整理后的简介"
    assert responses[4].json()["is_duplicate"] is True
    assert responses[5].json()["keyword"] == "乡土"
    assert requested_models == ["saved-default-model"] * 6


def test_ai_task_input_truncates_long_summary_and_never_stores_headers(
    client: TestClient,
    db: Session,
    member_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_generate_response(
                {
                    "recommended": {"publisher": "人民出版社"},
                    "source_summary": "已核对",
                    "confidence": 0.8,
                    "reason": "候选信息一致",
                }
            ),
        )

    _mock_ollama(monkeypatch, handler)
    secret = "must-never-be-audited"
    response = client.post(
        "/api/ai/recommend-book-content",
        headers=member_headers,
        json={
            "current": {"title": "资本论", "summary": "长" * 5000},
            "candidates": [
                {
                    "source": "openlibrary",
                    "summary": "候选" * 1000,
                    "raw": {"headers": {"Authorization": secret}, "response": secret},
                }
            ],
            "missing_fields": [f"field-{index}" for index in range(30)],
        },
    )

    assert response.status_code == 200
    audit = json.loads(db.query(AITask).one().input_data)
    assert len(audit["current"]["summary"]) <= 512
    assert len(audit["candidates"][0]["summary"]) <= 512
    assert len(audit["missing_fields"]) == 20
    serialized = json.dumps(audit, ensure_ascii=False).lower()
    assert "headers" not in serialized
    assert "authorization" not in serialized
    assert secret not in serialized


def test_sanitize_ai_task_input_bounds_cycles_depth_nodes_and_json_bytes() -> None:
    cyclic: dict[str, object] = {"title": "保留标题"}
    cyclic["current"] = cyclic

    deep: dict[str, object] = {"title": "最深层"}
    for _ in range(20):
        deep = {"title": "层级", "current": deep}

    branch: dict[str, object] = {
        "title": "节点" * 300,
        "summary": "摘要" * 300,
    }
    for _ in range(5):
        branch = {"title": "根", "candidates": [branch] * 20, "current": branch}

    sanitized = sanitize_ai_task_input(
        {"title": "审计根", "current": cyclic, "first": deep, "candidates": [branch] * 20}
    )
    encoded = json.dumps(sanitized, ensure_ascii=False).encode("utf-8")

    assert sanitized["title"] == "审计根"
    assert sanitized["current"]["title"] == "保留标题"
    assert len(encoded) <= 16_384

    def count_nodes(value: object) -> int:
        if isinstance(value, dict):
            return 1 + sum(count_nodes(item) for item in value.values())
        if isinstance(value, list):
            return 1 + sum(count_nodes(item) for item in value)
        return 1

    assert count_nodes(sanitized) <= 256

    depth = 0
    cursor = sanitized.get("first")
    while isinstance(cursor, dict) and "current" in cursor:
        depth += 1
        cursor = cursor["current"]
    assert depth <= 6


def test_ai_task_persists_one_compact_bounded_json_document(db: Session) -> None:
    # This shape previously measured at the compact limit and then exceeded it
    # when create_ai_task serialized it again with spaced separators.
    candidates = [
        {
            "title": f"候选-{index}",
            "summary": "中" * 512,
            "author_intro": "介" * 512,
            "note": "注" * 512,
        }
        for index in range(20)
    ]
    cyclic: dict[str, object] = {"title": "循环保留"}
    cyclic["current"] = cyclic
    deep: dict[str, object] = {"title": "底层"}
    for _ in range(20):
        deep = {"title": "深层", "current": deep}

    task = create_ai_task(
        db,
        task_type="review-boundary",
        model="qwen3:8b",
        input_data={
            "title": "资本论",
            "summary": "正常中文",
            "pages": math.nan,
            "publish_year": math.inf,
            "note": "孤立代理:\ud800",
            "current": cyclic,
            "first": deep,
            "candidates": candidates,
        },
        status="failed",
        error_message="model",
    )

    persisted = db.query(AITask).filter(AITask.id == task.id).one().input_data
    decoded = json.loads(persisted)

    assert len(persisted.encode("utf-8")) <= 16_384
    assert json.dumps(decoded, ensure_ascii=False, separators=(",", ":"), allow_nan=False) == persisted
    assert decoded["title"] == "资本论"
    assert decoded["summary"] == "正常中文"
    assert "pages" not in decoded
    assert "publish_year" not in decoded
    assert "\ud800" not in persisted
    assert decoded["current"]["title"] == "循环保留"


def test_ai_task_persists_exact_16384_byte_compact_boundary(db: Session) -> None:
    candidates = [{"summary": ""} for _ in range(19)] + [""]
    candidates[0]["note"] = ""
    payload = {"title": "", "candidates": candidates}
    slots = [(payload, "title"), *[(item, "summary") for item in candidates[:-1]]]
    slots.append((candidates[0], "note"))

    empty_size = len(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode(
            "utf-8"
        )
    )
    remaining = 16_384 - empty_size
    for mapping, key in slots:
        if remaining > 1_536:
            mapping[key] = "中" * 512
            remaining -= 1_536
            continue
        if remaining <= 512:
            mapping[key] = "x" * remaining
        else:
            chinese_count = (remaining - 512 + 1) // 2
            mapping[key] = ("中" * chinese_count) + ("x" * (remaining - 3 * chinese_count))
        remaining = 0
        break

    compact = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    old_persisted = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    assert remaining == 0
    assert len(compact.encode("utf-8")) == 16_384
    assert len(old_persisted.encode("utf-8")) == 16_427

    task = create_ai_task(
        db,
        task_type="review-exact-boundary",
        model="qwen3:8b",
        input_data=payload,
        status="success",
    )

    persisted = db.query(AITask).filter(AITask.id == task.id).one().input_data
    assert persisted == compact
    assert len(persisted.encode("utf-8")) == 16_384
    assert json.loads(persisted) == payload


def test_success_ai_task_output_is_strict_json_bounded_to_64_kib(db: Session) -> None:
    task = create_ai_task(
        db,
        task_type="bounded-output",
        model="qwen3:8b",
        input_data={"title": "资本论"},
        output_data={
            "summary": "中" * 100_000,
            "confidence": math.nan,
            "reason": "孤立代理:\ud800",
        },
        status="success",
    )

    persisted = db.query(AITask).filter(AITask.id == task.id).one().output_data
    assert persisted is not None
    assert len(persisted.encode("utf-8")) <= 65_536
    decoded = json.loads(
        persisted,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
    )
    assert json.dumps(
        decoded,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ) == persisted
    assert "\ud800" not in persisted


@pytest.mark.parametrize(
    "invalid_base_url",
    [
        "http://[sensitive-invalid-url",
        "http://\nsensitive.example",
        "http://\tsensitive.example",
        "http://\rsensitive.example",
    ],
)
def test_invalid_runtime_is_audited_and_returns_stable_ai_error(
    client: TestClient,
    db: Session,
    member_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    invalid_base_url: str,
) -> None:
    invalid_runtime = OllamaRuntimeConfig(
        enabled=True,
        base_url=invalid_base_url,
        trusted_base_url="https://openclaw.lsgood.cn",
        default_model="qwen3:8b",
        connect_timeout_seconds=20,
        read_timeout_seconds=180,
        verify_tls=True,
        access_client_id="",
        access_client_secret="",
    )
    monkeypatch.setattr(
        "app.api.routes.ai.get_ollama_runtime_config",
        lambda db, user: invalid_runtime,
    )

    response = client.get("/api/ai/models", headers=member_headers)

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "AI_MODEL_ERROR"
    assert "sensitive" not in response.text
    task = db.query(AITask).one()
    assert task.status == "failed"
    assert task.error_message == "model"
    assert json.loads(task.input_data) == {}


def test_ai_route_runs_sync_db_and_file_work_outside_event_loop(
    client: TestClient,
    member_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes import ai as ai_routes

    sync_threads: list[int] = []
    event_loop_threads: list[int] = []
    original_runtime = ai_routes.get_ollama_runtime_config
    original_categories = ai_routes._format_categories_for_prompt
    original_template = ai_routes.load_prompt_template
    original_create_task = ai_routes.create_ai_task

    def track_sync(callable_):
        def wrapper(*args, **kwargs):
            sync_threads.append(threading.get_ident())
            return callable_(*args, **kwargs)

        return wrapper

    class ThreadTrackingClient:
        def __init__(self, runtime: OllamaRuntimeConfig) -> None:
            self.runtime = runtime

        async def generate_json(self, **kwargs):
            event_loop_threads.append(threading.get_ident())
            return kwargs["response_model"].model_validate(
                {
                    "category_code": "C91",
                    "category_name": "社会学",
                    "confidence": 0.9,
                    "tags": ["社会学"],
                    "reason": "线程边界测试",
                    "model": kwargs["model"],
                }
            )

    monkeypatch.setattr(ai_routes, "get_ollama_runtime_config", track_sync(original_runtime))
    monkeypatch.setattr(ai_routes, "_format_categories_for_prompt", track_sync(original_categories))
    monkeypatch.setattr(ai_routes, "load_prompt_template", track_sync(original_template))
    monkeypatch.setattr(ai_routes, "create_ai_task", track_sync(original_create_task))
    monkeypatch.setattr(ai_routes, "OllamaClient", ThreadTrackingClient)

    response = client.post(
        "/api/ai/classify-book",
        headers=member_headers,
        json={"title": "乡土中国"},
    )

    assert response.status_code == 200
    assert event_loop_threads
    assert len(sync_threads) == 4
    assert all(thread_id != event_loop_threads[0] for thread_id in sync_threads)


def test_ai_failure_does_not_modify_book_or_block_non_ai_health(
    client: TestClient,
    db: Session,
    member_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    book = Book(title="资本论", author="马克思", summary="原始简介")
    db.add(book)
    db.commit()
    db.refresh(book)
    original = (book.title, book.author, book.summary, book.category_id)

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": "不是 JSON"})

    _mock_ollama(monkeypatch, handler)
    response = client.post(
        "/api/ai/classify-book",
        headers=member_headers,
        json={"title": book.title, "author": book.author, "summary": book.summary},
    )

    db.refresh(book)
    task = db.query(AITask).one()
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "AI_RESPONSE_INVALID"
    assert (book.title, book.author, book.summary, book.category_id) == original
    assert task.status == "failed"
    assert task.error_message == "response_invalid"
    assert client.get("/api/health").json() == {"status": "ok"}


def test_classify_book_accepts_valid_model_json(
    client: TestClient,
    db: Session,
    member_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/generate"
        return httpx.Response(
            200,
            json=_generate_response(
                {
                    "category_code": "C91",
                    "category_name": "社会学",
                    "confidence": 0.86,
                    "tags": ["社会学", "中国乡村"],
                    "reason": "该书讨论乡村社会结构。",
                }
            ),
        )

    _mock_ollama(monkeypatch, handler)

    response = client.post(
        "/api/ai/classify-book",
        headers=member_headers,
        json=_classify_payload(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["category_code"] == "C91"
    assert data["model"] == "qwen2.5"

    task = db.query(AITask).one()
    assert task.task_type == "classify_book"
    assert task.status == "success"
    assert json.loads(task.output_data or "{}")["category_code"] == "C91"


def test_classify_book_rejects_invalid_model_json(
    client: TestClient,
    db: Session,
    member_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": "不是 JSON"})

    _mock_ollama(monkeypatch, handler)

    response = client.post(
        "/api/ai/classify-book",
        headers=member_headers,
        json=_classify_payload(),
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "AI_RESPONSE_INVALID"

    task = db.query(AITask).one()
    assert task.status == "failed"
    assert task.error_message == "response_invalid"


def test_ollama_unavailable_returns_clear_error(
    client: TestClient,
    db: Session,
    member_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    _mock_ollama(monkeypatch, handler)

    response = client.get("/api/ai/models", headers=member_headers)

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "AI_UPSTREAM_ERROR"

    task = db.query(AITask).one()
    assert task.task_type == "models"
    assert task.status == "failed"


def test_generate_tags_records_success(
    client: TestClient,
    db: Session,
    member_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_generate_response({"tags": ["社会学", "经典", "乡村"], "reason": "主题明确"}),
        )

    _mock_ollama(monkeypatch, handler)

    response = client.post(
        "/api/ai/generate-tags",
        headers=member_headers,
        json={"title": "乡土中国", "summary": "社会学经典", "model": "qwen2.5"},
    )

    assert response.status_code == 200
    assert response.json()["tags"] == ["社会学", "经典", "乡村"]
    assert db.query(AITask).one().status == "success"


def test_recommend_book_content_records_success(
    client: TestClient,
    db: Session,
    member_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_generate_response(
                {
                    "recommended": {
                        "publisher": "人民出版社",
                        "publish_year": 2004,
                        "summary": "马克思主义政治经济学经典著作。",
                    },
                    "source_summary": "根据外部候选整理。",
                    "confidence": 0.82,
                    "reason": "出版社与年份来自候选数据。",
                }
            ),
        )

    _mock_ollama(monkeypatch, handler)

    response = client.post(
        "/api/ai/recommend-book-content",
        headers=member_headers,
        json={
            "current": {"title": "资本论", "author": "马克思"},
            "candidates": [
                {
                    "source": "openlibrary",
                    "title": "资本论",
                    "author": "马克思",
                    "publisher": "人民出版社",
                    "publish_year": 2004,
                }
            ],
            "missing_fields": ["publisher", "publish_year", "summary"],
            "model": "qwen2.5",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["recommended"]["publisher"] == "人民出版社"
    assert data["model"] == "qwen2.5"
    task = db.query(AITask).one()
    assert task.task_type == "recommend_book_content"
    assert task.status == "success"


def test_natural_search_records_failure_on_schema_error(
    client: TestClient,
    db: Session,
    member_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_generate_response({"publish_year_from": 2020, "publish_year_to": 2010}))

    _mock_ollama(monkeypatch, handler)

    response = client.post(
        "/api/ai/natural-search",
        headers=member_headers,
        json={"query": "找 2010 年前后的书"},
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "AI_RESPONSE_INVALID"
    assert db.query(AITask).one().status == "failed"
