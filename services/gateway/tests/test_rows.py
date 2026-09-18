from datetime import datetime, timezone

import pytest

from siaga_edge import FEATURE_COUNT, FEATURE_NAMES, message
from siaga_gateway.rows import reading_rows, state_row

TS = datetime(2026, 9, 18, 10, 0, 0, tzinfo=timezone.utc)


def msg():
    feats = {name: float(i) for i, name in enumerate(FEATURE_NAMES)}
    return message.build("PUMP-01", TS, feats, "stabil", 3200, 3200)


def test_one_row_per_feature():
    rows = reading_rows(msg())
    assert len(rows) == FEATURE_COUNT
    ts, source, feature, value, version = rows[0]
    assert ts == TS and source == "PUMP-01" and feature == FEATURE_NAMES[0]
    assert value == 0.0 and version == 1


def test_values_preserved():
    rows = {r[2]: r[3] for r in reading_rows(msg())}
    assert rows["bpfo_energy"] == float(FEATURE_NAMES.index("bpfo_energy"))


def test_state_row():
    assert state_row(msg()) == (TS, "PUMP-01", "stabil")


def test_invalid_message_rejected_before_any_row():
    bad = msg()
    del bad["features"]["vib_rms"]
    with pytest.raises(ValueError):
        reading_rows(bad)
