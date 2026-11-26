"""Explicit mode separation: real / mock / demo — never silent mock fallback."""

import pytest

from safefix.config import ConfigError, Mode, build_provider, load_env_file
from safefix.creds.store import EncryptedFileStore
from safefix.llm.mock import ScriptedMock
from safefix.llm.openai_compatible import OpenAICompatProvider


def test_load_env_file(tmp_path):
    f = tmp_path / ".env"
    f.write_text(
        '# comment\nAPI_KEY=sk-abc\nAPI_BASE_URL="https://x"\nexport MODEL=m1\n\nBAD LINE\n', encoding="utf-8"
    )
    env = load_env_file(f)
    assert env == {"API_KEY": "sk-abc", "API_BASE_URL": "https://x", "MODEL": "m1"}


def test_load_env_file_missing_is_empty(tmp_path):
    assert load_env_file(tmp_path / "absent") == {}


async def test_real_mode_without_credentials_raises_explicit_error(tmp_path):
    with pytest.raises(ConfigError, match="real mode"):
        await build_provider(
            mode=Mode.REAL,
            creds=EncryptedFileStore(tmp_path / "none.enc"),
            config={},
            env_file={},
            env={},
            master_password=None,
        )


async def test_real_mode_with_env_credentials_builds_real_provider(tmp_path):
    provider = await build_provider(
        mode=Mode.REAL,
        creds=EncryptedFileStore(tmp_path / "none.enc"),
        config={},
        env_file={"API_KEY": "sk-test", "API_BASE_URL": "https://api.test"},
        env={},
        master_password=None,
    )
    assert isinstance(provider, OpenAICompatProvider)


async def test_demo_mode_is_explicit_scripted_mock(tmp_path):
    provider = await build_provider(
        mode=Mode.DEMO,
        creds=EncryptedFileStore(tmp_path / "none.enc"),
        config={},
        env_file={},
        env={},
        master_password=None,
        demo_responses=['```action\n{"tool": "finish", "args": {}}\n```'],
    )
    assert isinstance(provider, ScriptedMock)


async def test_mock_mode_requires_injection(tmp_path):
    with pytest.raises(ConfigError, match="inject"):
        await build_provider(
            mode=Mode.MOCK,
            creds=EncryptedFileStore(tmp_path / "none.enc"),
            config={},
            env_file={},
            env={},
            master_password=None,
        )
