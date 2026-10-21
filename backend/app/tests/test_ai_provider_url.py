from __future__ import annotations

import asyncio
import socket
import ssl
from typing import Any

import httpcore
import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.services.ai_provider_url import (
    CLOUD_PROVIDER_FOLLOW_REDIRECTS,
    PinnedAsyncNetworkBackend,
    ProviderRedirectPolicy,
    create_pinned_async_transport,
    normalize_cloud_provider_origin,
    validate_cloud_provider_redirect,
    validate_cloud_provider_target,
    validate_cloud_provider_url,
)
from app.services.ai_providers.base import AIProviderInvalidConfigurationError


def _install_dns(monkeypatch: pytest.MonkeyPatch, addresses: list[str]) -> None:
    def fake_getaddrinfo(
        host: str,
        port: int,
        family: int = 0,
        type: int = 0,
        proto: int = 0,
        flags: int = 0,
    ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        del host, family, type, proto, flags
        return [
            (
                socket.AF_INET6 if ":" in address else socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                (address, port),
            )
            for address in addresses
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)


def test_cloud_url_defaults_to_https_and_preserves_safe_base_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_dns(monkeypatch, ["93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946"])

    assert validate_cloud_provider_url(
        "API.Example.test/v1/",
        allowed_private_origins=set(),
    ) == "https://api.example.test/v1"


@pytest.mark.parametrize(
    "url",
    [
        "http://api.example.test",
        "https://user:pass@api.example.test",
        "https://api.example.test:bad",
        "https://api.example.test:70000",
        "https://api.example.test/v1?api_key=secret",
        "https://api.example.test/v1#fragment",
    ],
)
def test_cloud_url_rejects_unsafe_syntax(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_dns(monkeypatch, ["93.184.216.34"])

    with pytest.raises(AIProviderInvalidConfigurationError):
        validate_cloud_provider_url(url, allowed_private_origins=set())


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "::1",
        "10.0.0.1",
        "169.254.10.20",
        "224.0.0.1",
        "0.0.0.0",
        "192.0.2.1",
        "169.254.169.254",
        "168.63.129.16",
        "100.100.100.200",
        "fd00:ec2::254",
    ],
)
def test_cloud_url_rejects_protected_and_metadata_literal_addresses(address: str) -> None:
    host = f"[{address}]" if ":" in address else address

    with pytest.raises(AIProviderInvalidConfigurationError) as captured:
        validate_cloud_provider_url(f"https://{host}", allowed_private_origins=set())

    assert captured.value.reason == "target_not_allowed"


def test_cloud_url_checks_every_dns_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_dns(monkeypatch, ["93.184.216.34", "10.0.0.8"])

    with pytest.raises(AIProviderInvalidConfigurationError) as captured:
        validate_cloud_provider_url("https://api.example.test", allowed_private_origins=set())

    assert captured.value.reason == "target_not_allowed"


def test_ipv4_mapped_ipv6_metadata_is_never_allowlisted(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_dns(monkeypatch, ["::ffff:169.254.169.254"])

    with pytest.raises(AIProviderInvalidConfigurationError) as captured:
        validate_cloud_provider_url(
            "https://allowed.example/v1",
            allowed_private_origins={"https://allowed.example"},
        )

    assert captured.value.reason == "target_not_allowed"


def test_exact_normalized_origin_allowlist_can_authorize_private_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_dns(monkeypatch, ["10.0.0.8"])
    allowed = {normalize_cloud_provider_origin("API.Example.test:443")}

    assert validate_cloud_provider_url(
        "https://api.example.test/v1",
        allowed_private_origins=allowed,
    ) == "https://api.example.test/v1"

    with pytest.raises(AIProviderInvalidConfigurationError):
        validate_cloud_provider_url(
            "https://api.example.test:8443/v1",
            allowed_private_origins=allowed,
        )


def test_dns_failures_are_stable_and_do_not_expose_resolver_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = "resolver-sensitive-marker"

    def fail_resolution(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise socket.gaierror(marker)

    monkeypatch.setattr(socket, "getaddrinfo", fail_resolution)

    with pytest.raises(AIProviderInvalidConfigurationError) as captured:
        validate_cloud_provider_url("https://api.example.test", allowed_private_origins=set())

    assert captured.value.reason == "dns_failure"
    assert marker not in str(captured.value)
    assert marker not in repr(captured.value)
    assert captured.value.__cause__ is None


def test_private_origin_setting_defaults_empty_and_normalizes_entries() -> None:
    assert Settings(_env_file=None).ai_provider_allowed_private_origins == set()

    settings = Settings(
        _env_file=None,
        AI_PROVIDER_ALLOWED_PRIVATE_ORIGINS="API.Example.test:443, https://[fd00::1]:8443",
    )

    assert settings.ai_provider_allowed_private_origins == {
        "https://api.example.test",
        "https://[fd00::1]:8443",
    }


@pytest.mark.parametrize(
    "entry",
    [
        "http://private.example.test",
        "https://user@private.example.test",
        "https://private.example.test/path",
        "https://private.example.test?query=value",
        "https://private.example.test#fragment",
        "https://private.example.test:bad",
    ],
)
def test_private_origin_setting_rejects_invalid_entries(entry: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, AI_PROVIDER_ALLOWED_PRIVATE_ORIGINS=entry)


def test_redirect_contract_revalidates_target_and_strips_cross_origin_authorization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_dns(monkeypatch, ["93.184.216.34"])

    same_origin = validate_cloud_provider_redirect(
        "https://api.example.test/v1/chat",
        "/v2/chat",
        allowed_private_origins=set(),
    )
    cross_origin = validate_cloud_provider_redirect(
        "https://api.example.test/v1/chat",
        "https://other.example.test/v2/chat",
        allowed_private_origins=set(),
    )

    assert CLOUD_PROVIDER_FOLLOW_REDIRECTS is False
    assert same_origin == ProviderRedirectPolicy(
        target_url="https://api.example.test/v2/chat",
        forward_authorization=True,
        validated_target=same_origin.validated_target,
    )
    assert cross_origin == ProviderRedirectPolicy(
        target_url="https://other.example.test/v2/chat",
        forward_authorization=False,
        validated_target=cross_origin.validated_target,
    )
    assert same_origin.validated_target.resolved_addresses == ("93.184.216.34",)
    assert cross_origin.validated_target.resolved_addresses == ("93.184.216.34",)


def test_redirect_to_private_target_is_rejected_before_authorization_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_dns(monkeypatch, ["10.0.0.8"])

    with pytest.raises(AIProviderInvalidConfigurationError) as captured:
        validate_cloud_provider_redirect(
            "https://api.example.test/v1/chat",
            "https://private.example.test/latest/meta-data",
            allowed_private_origins=set(),
        )

    assert captured.value.reason == "redirect_not_allowed"


class _RecordingStream(httpcore.AsyncNetworkStream):
    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.server_hostnames: list[str | None] = []
        self._response_sent = False

    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        del max_bytes, timeout
        if self._response_sent:
            return b""
        self._response_sent = True
        return b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok"

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:
        del timeout
        self.writes.append(buffer)

    async def aclose(self) -> None:
        return None

    async def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> httpcore.AsyncNetworkStream:
        del ssl_context, timeout
        self.server_hostnames.append(server_hostname)
        return self

    def get_extra_info(self, info: str) -> Any:
        del info
        return None


class _RecordingBackend(httpcore.AsyncNetworkBackend):
    def __init__(self, stream: _RecordingStream) -> None:
        self.stream = stream
        self.connect_hosts: list[tuple[str, int]] = []

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: object = None,
    ) -> httpcore.AsyncNetworkStream:
        del timeout, local_address, socket_options
        self.connect_hosts.append((host, port))
        return self.stream

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: object = None,
    ) -> httpcore.AsyncNetworkStream:
        del path, timeout, socket_options
        raise AssertionError("Unix sockets are not part of the pinned cloud transport")

    async def sleep(self, seconds: float) -> None:
        del seconds


def test_pinned_transport_uses_first_validated_dns_answers_and_preserves_host_and_sni(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dns_answers = [["93.184.216.34"], ["10.0.0.8"]]
    dns_calls = 0

    def changing_getaddrinfo(
        host: str,
        port: int,
        family: int = 0,
        type: int = 0,
        proto: int = 0,
        flags: int = 0,
    ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        nonlocal dns_calls
        del host, family, type, proto, flags
        answers = dns_answers[min(dns_calls, len(dns_answers) - 1)]
        dns_calls += 1
        return [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, port))
            for address in answers
        ]

    monkeypatch.setattr(socket, "getaddrinfo", changing_getaddrinfo)
    target = validate_cloud_provider_target(
        "https://api.example.test/v1",
        allowed_private_origins=set(),
    )
    stream = _RecordingStream()
    delegate = _RecordingBackend(stream)
    transport = create_pinned_async_transport(target, network_backend=delegate)

    async def request() -> httpx.Response:
        async with httpx.AsyncClient(transport=transport) as client:
            return await client.get("https://api.example.test/v1/models")

    response = asyncio.run(request())

    assert response.status_code == 200
    assert dns_calls == 1
    assert target.resolved_addresses == ("93.184.216.34",)
    assert delegate.connect_hosts == [("93.184.216.34", 443)]
    assert stream.server_hostnames == ["api.example.test"]
    assert b"Host: api.example.test" in b"".join(stream.writes)
    assert isinstance(transport.network_backend, PinnedAsyncNetworkBackend)
