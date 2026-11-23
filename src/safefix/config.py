"""Explicit configuration and provider construction.

Mode separation is a hard safety property (legacy risk R3):
- ``real``  -> real OpenAI-compatible provider; missing credentials raise an
  explicit ``ConfigError``. NEVER a silent scripted-demo fallback.
- ``mock``  -> caller must inject a deterministic provider (tests).
- ``demo``  -> explicit scripted demonstration, clearly labelled as such.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path

from safefix.creds.resolver import resolve_credentials
from safefix.creds.store import EncryptedFileStore
from safefix.llm.base import LLMProvider
from safefix.llm.mock import ScriptedMock
from safefix.llm.openai_compatible import OpenAICompatProvider

log = logging.getLogger("safefix")


class ConfigError(Exception):
    """Actionable configuration failure (missing credentials, wrong mode, ...)."""


class Mode(StrEnum):
    REAL = "real"
    MOCK = "mock"
    DEMO = "demo"


def load_env_file(path: str | Path) -> dict[str, str]:
    """Parse a .env file (KEY=VALUE, optional export prefix / quotes, # comments).

    The file is plaintext and process-env-visible by nature; prefer the encrypted
    store for long-lived keys. Missing file -> empty dict (not an error).
    """
    p = Path(path)
    if not p.exists():
        return {}
    out: dict[str, str] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", line)
        if not m:
            continue
        value = m.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[m.group(1)] = value
    return out


async def build_provider(
    *,
    mode: Mode,
    creds: EncryptedFileStore,
    config: Mapping[str, str],
    env_file: Mapping[str, str] | None = None,
    env: Mapping[str, str] | None = None,
    master_password: str | None = None,
    model: str | None = None,
    demo_responses: list[str] | None = None,
) -> LLMProvider:
    if mode == Mode.MOCK:
        raise ConfigError("mock mode requires an injected scripted provider (use ScriptedMock in tests)")
    if mode == Mode.DEMO:
        return ScriptedMock(demo_responses or ['```action\n{"tool": "finish", "args": {}}\n```'])

    resolved = await resolve_credentials(
        creds=creds, config=config, env_file=env_file, master_password=master_password, env=env
    )
    if resolved is None:
        raise ConfigError(
            "real mode requires API credentials: set API_KEY + API_BASE_URL in .env or the environment, "
            "or configure the encrypted store. Refusing to fall back to a scripted demo."
        )
    if resolved.source != "encrypted-file":
        log.warning(
            "[security] plaintext API key in use (source=%s); prefer the encrypted store", resolved.source
        )
    return OpenAICompatProvider(
        base_url=resolved.base_url,
        api_key=resolved.key,
        model=model or resolved.model or "gpt-4o-mini",
    )
