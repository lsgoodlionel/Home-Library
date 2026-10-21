from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import SplitResult, urljoin, urlsplit, urlunsplit

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
class ProviderRedirectPolicy:
    target_url: str
    forward_authorization: bool


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


def _resolved_addresses(hostname: str, port: int) -> tuple[set[ipaddress.IPv4Address | ipaddress.IPv6Address] | None, bool]:
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    if literal is not None:
        return {literal}, False

    try:
        answers = socket.getaddrinfo(
            hostname,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
        addresses = {ipaddress.ip_address(answer[4][0]) for answer in answers}
    except (OSError, UnicodeError, ValueError):
        return None, True
    if not addresses:
        return None, True
    return addresses, False


def _validate_cloud_provider_url(
    url: str,
    allowed_private_origins: set[str],
) -> str | AIProviderInvalidConfigurationError:
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
    return urlunsplit(parts)


def validate_cloud_provider_url(url: str, *, allowed_private_origins: set[str]) -> str:
    result = _validate_cloud_provider_url(url, allowed_private_origins)
    if isinstance(result, AIProviderInvalidConfigurationError):
        del url, allowed_private_origins
        raise result from None
    return result


def _validate_cloud_provider_redirect(
    current_url: str,
    redirect_url: str,
    allowed_private_origins: set[str],
) -> ProviderRedirectPolicy | AIProviderInvalidConfigurationError:
    target = urljoin(current_url, redirect_url)
    validated = _validate_cloud_provider_url(target, allowed_private_origins)
    if isinstance(validated, AIProviderInvalidConfigurationError):
        return _safe_error("redirect_not_allowed")
    current_parts = _normalized_parts(current_url, origin_only=False)
    if isinstance(current_parts, AIProviderInvalidConfigurationError):
        return _safe_error("redirect_not_allowed")
    target_parts = urlsplit(validated)
    return ProviderRedirectPolicy(
        target_url=validated,
        forward_authorization=_origin_from_parts(current_parts) == _origin_from_parts(target_parts),
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
    "ProviderRedirectPolicy",
    "normalize_cloud_provider_origin",
    "validate_cloud_provider_redirect",
    "validate_cloud_provider_url",
]
