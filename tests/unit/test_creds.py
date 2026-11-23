"""Encrypted credential store + resolver parity (upgraded: random salt, versioned blob)."""

import pytest

from safefix.creds.resolver import resolve_credentials
from safefix.creds.store import CredentialError, EncryptedFileStore


async def test_set_resolve_roundtrip(tmp_path):
    store = EncryptedFileStore(tmp_path / "creds.enc")
    await store.set("sk-secret-123", "master-pw")
    got = await store.resolve("master-pw")
    assert got.key == "sk-secret-123" and got.source == "encrypted-file"


async def test_wrong_master_password_rejected(tmp_path):
    store = EncryptedFileStore(tmp_path / "creds.enc")
    await store.set("sk-secret", "right")
    with pytest.raises(CredentialError):
        await store.resolve("wrong")


async def test_resolve_missing_file_raises(tmp_path):
    store = EncryptedFileStore(tmp_path / "absent.enc")
    with pytest.raises(CredentialError):
        await store.resolve("pw")


async def test_status_and_clear(tmp_path):
    store = EncryptedFileStore(tmp_path / "creds.enc")
    assert store.status().present is False
    await store.set("k", "pw")
    assert store.status().present is True
    await store.clear()
    assert store.status().present is False
    await store.clear()  # idempotent


async def test_plaintext_never_written_to_disk(tmp_path):
    f = tmp_path / "creds.enc"
    await EncryptedFileStore(f).set("sk-plaintext-canary", "pw")
    assert b"sk-plaintext-canary" not in f.read_bytes()


async def test_random_salt_per_write(tmp_path):
    f = tmp_path / "creds.enc"
    store = EncryptedFileStore(f)
    await store.set("same-key", "same-pw")
    blob1 = f.read_bytes()
    await store.set("same-key", "same-pw")
    assert f.read_bytes() != blob1  # random salt + nonce


async def test_resolver_prefers_encrypted_file(tmp_path):
    store = EncryptedFileStore(tmp_path / "creds.enc")
    await store.set("enc-key", "pw")
    got = await resolve_credentials(
        creds=store,
        config={"base_url": "https://api.example.com"},
        env_file={"API_KEY": "env-key"},
        master_password="pw",
        env={},
    )
    assert got.key == "enc-key" and got.source == "encrypted-file"


async def test_resolver_env_file_fallback(tmp_path):
    got = await resolve_credentials(
        creds=EncryptedFileStore(tmp_path / "none.enc"),
        config={},
        env_file={"API_KEY": "envfile-key", "API_BASE_URL": "https://x", "MODEL": "m1"},
        master_password=None,
        env={"API_KEY": "proc-key"},
    )
    assert got.key == "envfile-key" and got.source == "env-file"
    assert got.base_url == "https://x" and got.model == "m1"


async def test_resolver_process_env_fallback(tmp_path):
    got = await resolve_credentials(
        creds=EncryptedFileStore(tmp_path / "none.enc"),
        config={"base_url": "https://cfg"},
        env_file={},
        master_password=None,
        env={"API_KEY": "proc-key", "API_BASE_URL": "https://env"},
    )
    assert got.key == "proc-key" and got.source == "env"
    assert got.base_url == "https://cfg"  # config wins over env


async def test_resolver_no_credentials_returns_none(tmp_path):
    got = await resolve_credentials(
        creds=EncryptedFileStore(tmp_path / "none.enc"),
        config={},
        env_file={},
        master_password=None,
        env={},
    )
    assert got is None


async def test_resolver_wrong_password_falls_back_to_env(tmp_path):
    store = EncryptedFileStore(tmp_path / "creds.enc")
    await store.set("enc-key", "right")
    got = await resolve_credentials(
        creds=store,
        config={"base_url": "https://x"},
        env_file={"API_KEY": "env-key"},
        master_password="wrong",
        env={},
    )
    assert got.key == "env-key" and got.source == "env-file"