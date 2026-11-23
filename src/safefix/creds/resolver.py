"""Pure credential resolution — port of legacy ``credResolver.ts``.

Priority: encrypted file (master password) > .env file > process environment.
``base_url`` / ``model`` priority: config > .env > process env.

Returns ``None`` when nothing usable exists. The CALLER decides what that means:
in ``real`` mode it must raise an explicit error — never silently fall back to a
scripted demo (legacy risk R3).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel

from safefix.creds.store import CredentialError, EncryptedFileStore

CredSource = Literal["encrypted-file", "env-file", "env"]


class ResolvedCreds(BaseModel):
    base_url: str
    key: str
    model: str | None = None
    source: CredSource


async def resolve_credentials(
    *,
    creds: EncryptedFileStore,
    config: Mapping[str, str],
    env_file: Mapping[str, str] | None = None,
    master_password: str | None = None,
    env: Mapping[str, str] | None = None,
) -> ResolvedCreds | None:
    env_file = env_file or {}
    env = env or {}

    base_url = config.get("base_url") or env_file.get("API_BASE_URL") or env.get("API_BASE_URL")
    model = config.get("model") or env_file.get("MODEL") or env.get("MODEL")

    if master_password:
        try:
            resolved = await creds.resolve(master_password)
            if resolved.key and base_url:
                return ResolvedCreds(base_url=base_url, key=resolved.key, model=model, source="encrypted-file")
        except CredentialError:
            pass  # wrong password / no file -> fall through to env fallback

    env_key = env_file.get("API_KEY") or env.get("API_KEY")
    if env_key and base_url:
        return ResolvedCreds(
            base_url=base_url,
            key=env_key,
            model=model,
            source="env-file" if env_file.get("API_KEY") else "env",
        )
    return None