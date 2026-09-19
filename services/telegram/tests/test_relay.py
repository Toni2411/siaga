"""Relay harus memproses tiap update sekali dan tidak kehilangan update saat ERPNext mati."""

import pytest
import requests

from siaga_telegram.relay import Relay, Settings, next_offset


class FakeResponse:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload or {}
        self.text = str(payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


class FakeHttp:
    """Sesi HTTP palsu: getUpdates mengembalikan antrean yang disiapkan, ERPNext dicatat."""

    def __init__(self, batches, erpnext_ok=True, erpnext_down=False):
        self.batches = list(batches)
        self.erpnext_ok = erpnext_ok
        self.erpnext_down = erpnext_down
        self.forwarded = []
        self.offsets = []

    def post(self, url, json=None, headers=None, timeout=None):
        if "getUpdates" in url:
            self.offsets.append(json.get("offset"))
            batch = self.batches.pop(0) if self.batches else []
            return FakeResponse(200, {"ok": True, "result": batch})
        if self.erpnext_down:
            raise requests.ConnectionError("refused")
        self.forwarded.append(json["update"]["update_id"])
        return FakeResponse(200 if self.erpnext_ok else 500, {"message": {"ok": True}})


def settings():
    return Settings(token="t", erpnext_url="http://erp", api_key="k", api_secret="s", backoff_s=0)


def upd(i):
    return {"update_id": i, "message": {"chat": {"id": 1}, "text": "/wo"}}


def test_next_offset_is_one_past_largest_seen():
    assert next_offset([], 7) == 7
    assert next_offset([upd(3), upd(5), upd(4)], None) == 6


def test_step_forwards_each_update_once_and_advances_offset():
    http = FakeHttp([[upd(10), upd(11)], [upd(12)], []])
    relay = Relay(settings(), session=http)
    assert relay.step() == 2
    assert relay.step() == 1
    assert relay.step() == 0
    assert http.forwarded == [10, 11, 12]
    assert http.offsets == [None, 12, 13]


def test_erpnext_error_response_does_not_block_the_queue():
    """Update yang ditolak ERPNext (4xx/5xx) dicatat lalu dilewati, bukan diulang selamanya."""
    http = FakeHttp([[upd(1)], [upd(2)]], erpnext_ok=False)
    relay = Relay(settings(), session=http)
    relay.step()
    relay.step()
    assert http.forwarded == [1, 2]
    assert relay.offset == 3


def test_erpnext_unreachable_keeps_offset_at_failed_update():
    """Kalau ERPNext mati, offset berhenti di update yang gagal supaya diproses lagi nanti."""
    http = FakeHttp([[upd(20), upd(21)]], erpnext_down=True)
    relay = Relay(settings(), session=http)
    with pytest.raises(requests.RequestException):
        relay.step()
    assert relay.offset == 20
    assert http.forwarded == []
