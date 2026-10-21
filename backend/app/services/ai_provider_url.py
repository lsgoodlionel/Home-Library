from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import SplitResult, urljoin, urlsplit, urlunsplit

import httpcore
import httpx

from app.services.ai_providers.base import AIProviderInvalidConfigurationError

CLOUD_PROVIDER_FOLLOW_REDIRECTS = False

_METADATA_HOSTNAMES = {
    "instance-data",
    "metadata",
    "metadata.azure.internal",
    "metadata.google.internal",
}
_METADATA_ADDRESSES = {
    ipaddress.ip_address("100.100.100.200"),
    ipaddress.ip_address("168.63.129.16"),
    ipaddress.ip_address("169.254.169.254"),
    ipaddress.ip_address("169.254.170.2"),
    ipaddress.ip_address("fd00:ec2::254"),
}


@dataclass(frozen=True, slots=True)
class ValidatedCloudProviderTarget:
    url: str
    origin: str
    hostname: str
    port: int
    resolved_addresses: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProviderRedirectPolicy:
    target_url: str
    forward_authorization: bool
    validated_target: ValidatedCloudProviderTarget


def _canonical_address(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


def _safe_error(reason: str) -> AIProviderInvalidConfigurationError:
    return AIProviderInvalidConfigurationError(reason=reason)


def _normalized_parts(url: str, *, origin_only: bool) -> SplitResult | AIProviderInvalidConfigurationError:
    if not isinstance(url, str) or not url or url != url.strip():
        return _safe_error("target_not_allowed")
    if any(ord(character) < 33 for character in url) or "\\" in url:
        return _safe_error("target_not_allowed")

    candidate = url if "://" in url else f"https://{url}"
    try:
        parts = urlsplit(candidate)
        port = parts.port
        hostname = parts.hostname
    except (UnicodeError, ValueError):
        return _safe_error("target_not_allowed")

    if parts.scheme.lower() != "https" or not hostname:
        return _safe_error("target_not_allowed")
    if parts.username is not None or parts.password is not None:
        return _safe_error("target_not_allowed")
    if parts.query or parts.fragment:
        return _safe_error("target_not_allowed")
    if origin_only and parts.path not in {"", "/"}:
        return _safe_error("target_not_allowed")

    try:
        normalized_host = hostname.encode("idna").decode("ascii").lower()
    except UnicodeError:
        return _safe_error("target_not_allowed")
    if not normalized_host or normalized_host.endswith("."):
        normalized_host = normalized_host.rstrip(".")
    if not normalized_host:
        return _safe_error("target_not_allowed")

    display_host = f"[{normalized_host}]" if ":" in normalized_host else normalized_host
    netloc = display_host if port in {None, 443} else f"{display_host}:{port}"
    path = "" if origin_only else (parts.path.rstrip("/") or "")
    return SplitResult("https", netloc, path, "", "")


def normalize_cloud_provider_origin(url: str) -> str:
    result = _normalized_parts(url, origin_only=True)
    if isinstance(result, AIProviderInvalidConfigurationError):
        del url
        raise result from None
    return urlunsplit(result)


def _origin_from_parts(parts: SplitResult) -> str:
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


def _is_protected(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    address = _canonical_address(address)
    return (
        address in _METADATA_ADDRESSES
        or address.is_loopback
        or address.is_link_local
        or address.is_private
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
        or not address.is_global
    )


def _resolved_addresses(
    hostname: str,
    port: int,
) -> tuple[tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...] | None, bool]:
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    if literal is not None:
        return (_canonical_address(literal),), False

    try:
        answers = socket.getaddrinfo(
            hostname,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
        addresses = tuple(
            dict.fromkeys(
                _canonical_address(ipaddress.ip_address(answer[4][0]))
                for answer in answers
            )
        )
    except (OSError, UnicodeError, ValueError):
        return None, True
    if not addresses:
        return None, True
    return addresses, False


def _validate_cloud_provider_target(
    url: str,
    allowed_private_origins: set[str],
) -> ValidatedCloudProviderTarget | AIProviderInvalidConfigurationError:
    parts = _normalized_parts(url, origin_only=False)
    if isinstance(parts, AIProviderInvalidConfigurationError):
        return parts

    hostname = parts.hostname
    if hostname is None or hostname in _METADATA_HOSTNAMES:
        return _safe_error("target_not_allowed")
    origin = _origin_from_parts(parts)
    addresses, dns_failed = _resolved_addresses(hostname, parts.port or 443)
    if dns_failed or addresses is None:
        return _safe_error("dns_failure")
    if any(address in _METADATA_ADDRESSES for address in addresses):
        return _safe_error("target_not_allowed")
    if origin not in allowed_private_origins and any(_is_protected(address) for address in addresses):
        return _safe_error("target_not_allowed")
    return ValidatedCloudProviderTarget(
        url=urlunsplit(parts),
        origin=origin,
        hostname=hostname,
        port=parts.port or 443,
        resolved_addresses=tuple(str(address) for address in addresses),
    )


def validate_cloud_provider_target(
    url: str,
    *,
    allowed_private_origins: set[str],
) -> ValidatedCloudProviderTarget:
    result = _validate_cloud_provider_target(url, allowed_private_origins)
    if isinstance(result, AIProviderInvalidConfigurationError):
        del url, allowed_private_origins
        raise result from None
    return result


def validate_cloud_provider_url(url: str, *, allowed_private_origins: set[str]) -> str:
    result = _validate_cloud_provider_target(url, allowed_private_origins)
    if isinstance(result, AIProviderInvalidConfigurationError):
        del url, allowed_private_origins
        raise result from None
    return result.url


def _validate_cloud_provider_redirect(
    current_url: str,
    redirect_url: str,
    allowed_private_origins: set[str],
) -> ProviderRedirectPolicy | AIProviderInvalidConfigurationError:
    target = urljoin(current_url, redirect_url)
    validated = _validate_cloud_provider_target(target, allowed_private_origins)
    if isinstance(validated, AIProviderInvalidConfigurationError):
        return _safe_error("redirect_not_allowed")
    current_parts = _normalized_parts(current_url, origin_only=False)
    if isinstance(current_parts, AIProviderInvalidConfigurationError):
        return _safe_error("redirect_not_allowed")
    target_parts = urlsplit(validated.url)
    return ProviderRedirectPolicy(
        target_url=validated.url,
        forward_authorization=_origin_from_parts(current_parts) == _origin_from_parts(target_parts),
        validated_target=validated,
    )


class PinnedAsyncNetworkBackend(httpcore.AsyncNetworkBackend):
    def __init__(
        self,
        target: ValidatedCloudProviderTarget,
        delegate: httpcore.AsyncNetworkBackend,
    ) -> None:
        self._target = target
        self._delegate = delegate

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[tuple[object, ...]] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        if host.lower() != self._target.hostname or port != self._target.port:
            raise httpcore.ConnectError("Pinned provider target does not match request origin")

        last_error: httpcore.ConnectError | httpcore.ConnectTimeout | None = None
        for address in self._target.resolved_addresses:
            try:
                return await self._delegate.connect_tcp(
                    address,
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        raise httpcore.ConnectError("Pinned provider target has no validated address")

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[tuple[object, ...]] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        del path, timeout, socket_options
        raise httpcore.ConnectError("Unix sockets are not allowed for cloud providers")

    async def sleep(self, seconds: float) -> None:
        await self._delegate.sleep(seconds)


class PinnedAsyncHTTPTransport(httpx.AsyncHTTPTransport):
    def __init__(
        self,
        target: ValidatedCloudProviderTarget,
        *,
        verify: bool = True,
        limits: httpx.Limits | None = None,
        retries: int = 0,
        network_backend: httpcore.AsyncNetworkBackend | None = None,
    ) -> None:
        from httpcore._backends.auto import AutoBackend

        resolved_limits = limits or httpx.Limits(
            max_connections=100,
            max_keepalive_connections=20,
            keepalive_expiry=5.0,
        )
        self.network_backend = PinnedAsyncNetworkBackend(
            target,
            network_backend or AutoBackend(),
        )
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=httpx.create_ssl_context(verify=verify, trust_env=False),
            max_connections=resolved_limits.max_connections,
            max_keepalive_connections=resolved_limits.max_keepalive_connections,
            keepalive_expiry=resolved_limits.keepalive_expiry,
            http1=True,
            http2=False,
            retries=retries,
            network_backend=self.network_backend,
        )


def create_pinned_async_transport(
    target: ValidatedCloudProviderTarget,
    *,
    verify: bool = True,
    limits: httpx.Limits | None = None,
    retries: int = 0,
    network_backend: httpcore.AsyncNetworkBackend | None = None,
) -> PinnedAsyncHTTPTransport:
    return PinnedAsyncHTTPTransport(
        target,
        verify=verify,
        limits=limits,
        retries=retries,
        network_backend=network_backend,
    )


def validate_cloud_provider_redirect(
    current_url: str,
    redirect_url: str,
    *,
    allowed_private_origins: set[str],
) -> ProviderRedirectPolicy:
    result = _validate_cloud_provider_redirect(current_url, redirect_url, allowed_private_origins)
    if isinstance(result, AIProviderInvalidConfigurationError):
        del current_url, redirect_url, allowed_private_origins
        raise result from None
    return result


__all__ = [
    "CLOUD_PROVIDER_FOLLOW_REDIRECTS",
    "PinnedAsyncHTTPTransport",
    "PinnedAsyncNetworkBackend",
    "ProviderRedirectPolicy",
    "ValidatedCloudProviderTarget",
    "create_pinned_async_transport",
    "normalize_cloud_provider_origin",
    "validate_cloud_provider_redirect",
    "validate_cloud_provider_target",
    "validate_cloud_provider_url",
]
