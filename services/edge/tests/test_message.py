"""Uji kontrak pesan. Gateway dan firmware v1.5 harus tunduk pada ini."""

from datetime import datetime, timezone

import pytest

from siaga_edge import FEATURE_NAMES, SCHEMA_VERSION
from siaga_edge import message

TS = datetime(2026, 9, 18, 10, 0, 0, tzinfo=timezone.utc)


def features(value=1.0):
    return {name: value for name in FEATURE_NAMES}


def good():
    return message.build("PUMP-01", TS, features(), "stabil", 3200, 3200,
                         origin={"dataset": "uji"}, synthetic=("current_rms",))


class TestBuild:
    def test_roundtrip_through_json(self):
        msg = good()
        again = message.loads(message.dumps(msg))
        assert again == msg

    def test_topic(self):
        assert message.topic_for("PUMP-01") == "siaga/edge/PUMP-01/features"

    def test_ts_is_utc_with_z(self):
        assert good()["ts"] == "2026-09-18T10:00:00Z"

    def test_naive_ts_rejected(self):
        with pytest.raises(ValueError):
            message.build("PUMP-01", datetime(2026, 9, 18), features(), "stabil", 3200, 3200)

    def test_features_follow_schema_order(self):
        assert list(good()["features"]) == list(FEATURE_NAMES)

    def test_synthetic_is_declared(self):
        assert good()["synthetic"] == ["current_rms"]


class TestValidate:
    def test_wrong_schema_version_rejected(self):
        msg = good()
        msg["schema_version"] = SCHEMA_VERSION + 1
        with pytest.raises(ValueError, match="schema_version"):
            message.validate(msg)

    def test_missing_feature_rejected(self):
        msg = good()
        del msg["features"]["bpfo_energy"]
        with pytest.raises(ValueError, match="bpfo_energy"):
            message.validate(msg)

    def test_unknown_feature_rejected(self):
        msg = good()
        msg["features"]["ciri_baru"] = 1.0
        with pytest.raises(ValueError, match="ciri_baru"):
            message.validate(msg)

    def test_nan_rejected(self):
        msg = good()
        msg["features"]["vib_rms"] = float("nan")
        with pytest.raises(ValueError, match="finite"):
            message.validate(msg)

    def test_unknown_state_rejected(self):
        msg = good()
        msg["operating_state"] = "meledak"
        with pytest.raises(ValueError, match="operating_state"):
            message.validate(msg)

    def test_offset_timestamp_accepted(self):
        msg = good()
        msg["ts"] = "2026-09-18T17:00:00+07:00"
        message.validate(msg)
        assert message.parse_ts(msg["ts"]) == TS
