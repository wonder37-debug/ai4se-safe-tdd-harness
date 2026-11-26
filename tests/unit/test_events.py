"""Event log + JSONL sink + fan-out."""

import json

from safefix.agent.events import EventLog, FanOutSink, JsonlSink
from safefix.models import ExecutionEvent


def test_event_log_assigns_sequential_ids():
    log = EventLog()
    log.emit(ExecutionEvent(seq=0, type="thought", payload={"text": "hi"}))
    log.emit(ExecutionEvent(seq=0, type="halt", payload={"reason": "finish"}))
    assert [e.seq for e in log.events] == [1, 2]
    assert log.events[0].ts > 0


def test_jsonl_sink_writes_parseable_lines(tmp_path):
    f = tmp_path / "events.jsonl"
    sink = JsonlSink(f)
    sink.emit(ExecutionEvent(seq=1, type="action", payload={"tool": "finish"}, iter=1))
    lines = f.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert obj["type"] == "action" and obj["payload"]["tool"] == "finish"


def test_fan_out(tmp_path):
    log = EventLog()
    f = tmp_path / "e.jsonl"
    fan = FanOutSink([log, JsonlSink(f)])
    fan.emit(ExecutionEvent(seq=0, type="halt", payload={}))
    assert len(log.events) == 1 and f.exists()
