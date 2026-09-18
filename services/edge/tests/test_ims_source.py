"""Uji pemutar ulang IMS dengan cache kecil buatan, tanpa dataset asli."""

import io
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from siaga_edge.config import IMS_PUMP_CLASS
from siaga_edge.publisher import StdoutPublisher
from siaga_edge.runner import NominalScalars, operating_state, run
from siaga_edge.sources.ims import IMSReplay, describe


@pytest.fixture
def cache(tmp_path):
    """Lima cuplikan, dua kanal, sepuluh menit terpisah. Kanal 1 mati di akhir."""
    n, ch, samples = 5, 2, 3200
    rng = np.random.default_rng(0)
    waves = rng.normal(0, 0.05, (n, ch, samples)).astype(np.float32)
    waves[-1, 1] = 0.0001 * rng.normal(0, 1, samples)  # alat mati
    t0 = datetime(2004, 2, 12, 10, 32, 39)
    ts = [(t0 + timedelta(minutes=10 * i)).isoformat() for i in range(n)]
    files = [(t0 + timedelta(minutes=10 * i)).strftime("%Y.%m.%d.%H.%M.%S") for i in range(n)]
    path = tmp_path / "mini.npz"
    np.savez(path, waves=waves, ts=np.array(ts), files=np.array(files),
             sample_rate_hz=np.int32(3200), dataset=np.str_("uji"))
    return path


def test_describe(cache):
    d = describe(cache)
    assert d["snapshots"] == 5 and d["channels"] == 2 and d["samples"] == 3200
    assert d["span"] == "0:40:00"


def test_blocks_come_in_time_order_per_channel(cache):
    src = IMSReplay(cache, source_ids=("A", "B"), speed=0)
    blocks = list(src)
    assert len(blocks) == 10
    assert [b.source_id for b in blocks[:4]] == ["A", "B", "A", "B"]
    ts = [b.ts for b in blocks if b.source_id == "A"]
    assert ts == sorted(ts)
    assert ts[1] - ts[0] == timedelta(minutes=10)


def test_virtual_clock_shifts_dataset_time(cache):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    src = IMSReplay(cache, source_ids=("A", "B"), speed=0, start=start)
    blocks = list(src)
    assert blocks[0].ts == start
    assert blocks[-1].ts == start + timedelta(minutes=40)


def test_default_window_ends_now(cache):
    before = datetime.now(timezone.utc)
    src = IMSReplay(cache, source_ids=("A", "B"), speed=0)
    last = list(src)[-1].ts
    assert before - timedelta(seconds=5) <= last <= datetime.now(timezone.utc) + timedelta(seconds=5)


def test_first_and_limit(cache):
    src = IMSReplay(cache, source_ids=("A", "B"), speed=0, first=1, limit=2)
    blocks = list(src)
    assert src.snapshots == 2
    assert [b.origin["index"] for b in blocks] == [1, 1, 2, 2]


def test_origin_carries_dataset_provenance(cache):
    b = next(iter(IMSReplay(cache, source_ids=("A", "B"), speed=0)))
    assert b.origin["dataset"] == "uji"
    assert b.origin["file"] == "2004.02.12.10.32.39"
    assert b.origin["channel"] == 0


def test_too_few_source_ids_rejected(cache):
    with pytest.raises(ValueError):
        IMSReplay(cache, source_ids=("A",), speed=0)


def test_missing_cache_has_helpful_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="prepare_dataset"):
        IMSReplay(tmp_path / "tidak-ada.npz")


class TestOperatingState:
    def test_off_below_threshold(self):
        assert operating_state(0.001, IMS_PUMP_CLASS) == "mati"

    def test_running_above_threshold(self):
        assert operating_state(0.05, IMS_PUMP_CLASS) == "stabil"


class TestRun:
    def test_end_to_end_to_stdout(self, cache, capsys):
        src = IMSReplay(cache, source_ids=("A", "B"), speed=0)
        sent = run(src, StdoutPublisher(), IMS_PUMP_CLASS, NominalScalars(seed=1))
        assert sent == 10
        lines = capsys.readouterr().out.strip().splitlines()
        assert len(lines) == 10
        assert lines[0].startswith("siaga/edge/A/features ")
        # kanal B di cuplikan terakhir mati, arusnya harus nol
        import json
        last_b = json.loads(lines[-1].split(" ", 1)[1])
        assert last_b["source_id"] == "B"
        assert last_b["operating_state"] == "mati"
        assert last_b["features"]["current_rms"] == 0.0
        assert last_b["synthetic"] == ["current_rms", "temperature_c"]

    def test_max_messages_stops_early(self, cache):
        src = IMSReplay(cache, source_ids=("A", "B"), speed=0)
        sink = StdoutPublisher(io.StringIO())
        assert run(src, sink, IMS_PUMP_CLASS, max_messages=3) == 3
        assert sink.published == 3
