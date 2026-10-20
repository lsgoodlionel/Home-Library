from __future__ import annotations

from urllib.parse import urlsplit

import httpx


class InvalidOllamaBaseURL(ValueError):
    pass


def normalize_ollama_base_url(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise InvalidOllamaBaseURL("Ollama base URL is invalid")
    if any(_is_forbidden_url_character(character) for character in value):
        raise InvalidOllamaBaseURL("Ollama base URL is invalid")

    parsed: httpx.URL | None = None
    try:
        structural = urlsplit(value)
        structural.port
        parsed = httpx.URL(value)
        valid = (
            structural.scheme.lower() in {"http", "https"}
            and structural.hostname is not None
            and structural.username is None
            and structural.password is None
            and parsed.scheme in {"http", "https"}
            and bool(parsed.host)
            and not parsed.username
            and not parsed.password
        )
        normalized = str(parsed)
        httpx.URL(normalized)
    except (httpx.InvalidURL, UnicodeError, ValueError):
        valid = False
        normalized = ""

    if not valid or parsed is None:
        raise InvalidOllamaBaseURL("Ollama base URL is invalid")
    return normalized


def _is_forbidden_url_character(character: str) -> bool:
    codepoint = ord(character)
    return character.isspace() or codepoint <= 0x1F or 0x7F <= codepoint <= 0x9F
