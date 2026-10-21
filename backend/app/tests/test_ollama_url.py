from __future__ import annotations

import pytest

from app.core.ollama_url import InvalidOllamaBaseURL, normalize_ollama_base_url


@pytest.mark.parametrize(
    "value",
    [
        "https://openclaw.lsgood.cn/api/version",
        "https://openclaw.lsgood.cn/api/tags/",
        "https://openclaw.lsgood.cn/api/ps",
        "https://openclaw.lsgood.cn/api/generate",
        "https://openclaw.lsgood.cn/api/chat",
    ],
)
def test_ollama_base_url_rejects_api_endpoint_paths(value: str) -> None:
    with pytest.raises(InvalidOllamaBaseURL, match="service root"):
        normalize_ollama_base_url(value)


def test_ollama_base_url_keeps_reverse_proxy_prefixes() -> None:
    assert (
        normalize_ollama_base_url("https://example.test/team-a/ollama")
        == "https://example.test/team-a/ollama"
    )
