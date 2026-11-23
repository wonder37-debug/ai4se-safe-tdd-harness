"""MemoryStore parity (legacy memoryStore.ts): file-backed notes, prompt injection."""

from safefix.memory.store import MemoryStore


async def test_read_missing_dir_is_empty(tmp_path):
    store = MemoryStore(tmp_path / "nope")
    assert await store.read() == []


async def test_write_read_roundtrip(tmp_path):
    store = MemoryStore(tmp_path / "mem")
    await store.write("findings", "bug is in parser.py")
    notes = await store.read()
    assert len(notes) == 1
    assert notes[0].key == "findings" and notes[0].note == "bug is in parser.py"


async def test_write_overwrites_same_key(tmp_path):
    store = MemoryStore(tmp_path / "mem")
    await store.write("k", "v1")
    await store.write("k", "v2")
    notes = await store.read()
    assert len(notes) == 1 and notes[0].note == "v2"


async def test_clear_removes_note(tmp_path):
    store = MemoryStore(tmp_path / "mem")
    await store.write("k", "v")
    await store.clear("k")
    assert await store.read() == []
    await store.clear("k")  # idempotent, no error


async def test_system_prompt_formats_notes(tmp_path):
    store = MemoryStore(tmp_path / "mem")
    assert await store.system_prompt() == ""
    await store.write("a", "note-a")
    prompt = await store.system_prompt()
    assert prompt.startswith("Project notes:")
    assert "- [a] note-a" in prompt


async def test_read_sorted_by_key_for_determinism(tmp_path):
    store = MemoryStore(tmp_path / "mem")
    await store.write("z", "1")
    await store.write("a", "2")
    assert [n.key for n in await store.read()] == ["a", "z"]


async def test_key_path_traversal_rejected(tmp_path):
    import pytest

    store = MemoryStore(tmp_path / "mem")
    with pytest.raises(ValueError):
        await store.write("../evil", "x")