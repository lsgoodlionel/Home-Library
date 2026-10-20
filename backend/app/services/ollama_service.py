from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"


def load_prompt_template(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


def parse_model_json(content: str) -> dict[str, Any]:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError("模型输出不是合法 JSON") from exc

    if not isinstance(data, dict):
        raise ValueError("模型输出 JSON 必须是对象")
    return data
