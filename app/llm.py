from __future__ import annotations

import json
from typing import Any

import httpx

from .config import settings


SYSTEM_PROMPT = """你是服装门店内部导购知识助手。你只能根据给定资料回答。
输出必须是JSON，字段为 conclusion、suggested_script、conditions、warning。
涉及退款、赔偿、活动叠加、会员权益、投诉及特殊退换货时，warning必须明确写“需店长确认”。
资料不足、过期、冲突或没有可靠来源时，不得猜测，应拒绝回答。
推荐话术应自然、礼貌，不得承诺资料中没有的折扣、赔偿、功效或特殊处理。"""


def llm_available() -> bool:
    return bool(settings.llm_api_key.strip())


def generate_with_llm(question: str, context: str, risk_level: str) -> dict[str, Any] | None:
    if not llm_available():
        return None
    payload = {
        "model": settings.llm_model,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"用户问题：{question}\n风险等级：{risk_level}\n可用资料：\n{context}",
            },
        ],
    }
    headers = {"Authorization": f"Bearer {settings.llm_api_key}", "Content-Type": "application/json"}
    try:
        with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
            response = client.post(
                f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            return parsed if isinstance(parsed, dict) else None
    except (httpx.HTTPError, KeyError, ValueError, json.JSONDecodeError):
        return None
