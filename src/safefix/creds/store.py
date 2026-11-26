"""Encrypted credential store — upgraded port of legacy ``credentialStore.ts``.

Format: ``SFX1`` magic || 16-byte random salt || 12-byte nonce || AES-256-GCM
ciphertext (tag appended by AESGCM). Key derivation: PBKDF2-HMAC-SHA256,
100_000 iterations. Upgrades over the original: per-write random salt (the legacy
store used a fixed salt) and a versioned blob header.

Threat model: protects the API key at rest against casual disk reads / accidental
commits. The master password lives in process memory while unlocked; a compromised
host or a logged process environment is out of scope (documented in security-model).
"""

from __future__ import annotations

import os
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from pydantic import BaseModel

_MAGIC = b"SFX1"
_SALT_LEN = 16
_NONCE_LEN = 12
_ITERATIONS = 100_000


class CredentialError(Exception):
    """Missing store, wrong master password, or corrupted blob."""


class StoreStatus(BaseModel):
    present: bool
    source: str = "encrypted-file"


class ResolvedKey(BaseModel):
    key: str
    source: str = "encrypted-file"


def _derive_key(master: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=_ITERATIONS)
    return kdf.derive(master.encode("utf-8"))


class EncryptedFileStore:
    def __init__(self, file: str | Path):
        self._file = Path(file)

    def status(self) -> StoreStatus:
        return StoreStatus(present=self._file.exists())

    async def set(self, key: str, master_password: str) -> None:
        salt = os.urandom(_SALT_LEN)
        nonce = os.urandom(_NONCE_LEN)
        ct = AESGCM(_derive_key(master_password, salt)).encrypt(nonce, key.encode("utf-8"), None)
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._file.write_bytes(_MAGIC + salt + nonce + ct)

    async def resolve(self, master_password: str) -> ResolvedKey:
        if not self._file.exists():
            raise CredentialError("no encrypted credentials")
        buf = self._file.read_bytes()
        header = len(_MAGIC) + _SALT_LEN + _NONCE_LEN
        if not buf.startswith(_MAGIC) or len(buf) <= header:
            raise CredentialError("corrupted credential store (bad header)")
        salt = buf[len(_MAGIC) : len(_MAGIC) + _SALT_LEN]
        nonce = buf[len(_MAGIC) + _SALT_LEN : header]
        ct = buf[header:]
        try:
            plain = AESGCM(_derive_key(master_password, salt)).decrypt(nonce, ct, None)
        except InvalidTag as e:
            raise CredentialError("invalid master password or corrupted credential store") from e
        return ResolvedKey(key=plain.decode("utf-8"))

    async def clear(self) -> None:
        self._file.unlink(missing_ok=True)
