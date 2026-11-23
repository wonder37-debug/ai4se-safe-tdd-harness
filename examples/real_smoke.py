"""Minimal REAL-provider smoke test (no mock substitution).

Verifies: request reaches provider; requested model responds; fenced-action
fallback parses & validates; native tool calling when supported; usage recorded;
provider errors are explicit. Evidence JSON contains NO credentials.

Run: uv run python examples/real_smoke.py
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from urllib.parse import urlparse

from safefix.agent.protocol import parse_actions
from safefix.config import Mode, build_provider, load_env_file
from safefix.creds.store import EncryptedFileStore
from safefix.llm.openai_compatible import AuthError, OpenAICompatProvider, ProviderError
from safefix.models import Message
from safefix.tools.files import ReadFileTool
from safefix.tools.registry import ToolRegistry


async def main() -> None:
    env = load_env_file(".env")
    provider = await build_provider(
        mode=Mode.REAL,
        creds=EncryptedFileStore(".safefix-runs/absent.enc"),
        config={},
        env_file=env,
        env=dict(os.environ),
        master_password=None,
    )
    assert isinstance(provider, OpenAICompatProvider), "real mode must not use a mock"
    evidence: dict = {
        "mode": "real",
        "model": env.get("MODEL"),
        "endpoint_host": urlparse(env.get("API_BASE_URL", "")).hostname,
        "checks": {},
    }

    # 1) fenced-action fallback + validation + usage
    resp = await provider.complete(
        [
            Message(
                role="system",
                content='Reply with exactly one fenced block and nothing else:\n```action\n{"tool": "finish", "args": {}}\n```',
            ),
            Message(role="user", content="Emit the finish action now."),
        ]
    )
    acts = parse_actions(resp.text)
    evidence["checks"]["request_reached_provider"] = True
    evidence["checks"]["fenced_action_parsed"] = len(acts) == 1 and acts[0].tool == "finish"
    evidence["checks"]["action_validated"] = bool(acts) and isinstance(acts[0].args, dict)
    evidence["checks"]["usage_recorded"] = resp.usage.total_tokens > 0
    evidence["usage_sample"] = resp.usage.model_dump()
    evidence["stop_reason"] = resp.stop_reason

    # 2) native tool calling (when the endpoint supports it)
    reg = ToolRegistry([ReadFileTool()])
    try:
        resp2 = await provider.complete(
            [Message(role="user", content="Use the read_file tool to read the file a.py.")],
            tools=reg.schemas(),
        )
        evidence["checks"]["native_tool_calling"] = len(resp2.tool_calls) > 0
        if resp2.tool_calls:
            evidence["native_tool_call"] = {
                "name": resp2.tool_calls[0].name,
                "arguments": resp2.tool_calls[0].arguments,
            }
    except (ProviderError, AuthError) as e:
        evidence["checks"]["native_tool_calling"] = False
        evidence["native_tool_error"] = f"{type(e).__name__}: {str(e)[:200]}"

    # 3) explicit provider error on invalid model (no silent success)
    bad = OpenAICompatProvider(
        base_url=env["API_BASE_URL"],
        api_key=env["API_KEY"],
        model="nonexistent-model-xyz",
        max_retries=0,
    )
    try:
        await bad.complete([Message(role="user", content="hi")])
        evidence["checks"]["explicit_provider_error"] = False
    except (ProviderError, AuthError) as e:
        evidence["checks"]["explicit_provider_error"] = True
        evidence["error_type"] = type(e).__name__

    out = Path("docs/verification/evidence/real-smoke.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(evidence["checks"], indent=2))
    print(f"evidence -> {out}")


if __name__ == "__main__":
    asyncio.run(main())