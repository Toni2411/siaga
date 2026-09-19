"""Relay tanpa logika: tiap update Telegram diteruskan ke ERPNext.

Bot API tidak bisa memanggil ERPNext yang ada di jaringan lokal (tidak ada
alamat publik untuk webhook), jadi relay ini yang menarik update lewat
getUpdates lalu memanggil siaga.telegram_bot.handle_update sebagai user
siaga-bot. Semua keputusan, izin, dan balasan ada di ERPNext; relay hanya
menjaga offset supaya tiap update diproses sekali.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field

import requests

log = logging.getLogger("siaga.telegram")


@dataclass
class Settings:
    token: str = field(default_factory=lambda: os.environ.get("SIAGA_TELEGRAM_TOKEN", ""))
    erpnext_url: str = field(default_factory=lambda: os.environ.get("SIAGA_ERPNEXT_URL", "http://localhost:8080"))
    api_key: str = field(default_factory=lambda: os.environ.get("ERPNEXT_API_KEY", ""))
    api_secret: str = field(default_factory=lambda: os.environ.get("ERPNEXT_API_SECRET", ""))
    # Detik long polling di sisi Telegram; koneksi menggantung selama itu kalau sepi.
    poll_timeout_s: int = 30
    # Jeda sebelum mencoba lagi setelah jaringan gagal.
    backoff_s: float = 5.0


def next_offset(updates, current):
    """Offset getUpdates berikutnya: satu lebih dari update_id terbesar yang sudah dilihat."""
    if not updates:
        return current
    return max(u["update_id"] for u in updates) + 1


class Relay:
    def __init__(self, settings: Settings, session=None):
        self.s = settings
        self.http = session or requests.Session()
        self.offset = None

    # ---- Telegram ----

    def fetch(self):
        payload = {"timeout": self.s.poll_timeout_s, "allowed_updates": ["message", "callback_query"]}
        if self.offset is not None:
            payload["offset"] = self.offset
        r = self.http.post(
            "https://api.telegram.org/bot%s/getUpdates" % self.s.token,
            json=payload, timeout=self.s.poll_timeout_s + 10,
        )
        r.raise_for_status()
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError("getUpdates: %s" % data.get("description"))
        return data.get("result") or []

    # ---- ERPNext ----

    def forward(self, update) -> bool:
        r = self.http.post(
            self.s.erpnext_url.rstrip("/") + "/api/method/siaga.telegram_bot.handle_update",
            json={"update": update},
            headers={"Authorization": "token %s:%s" % (self.s.api_key, self.s.api_secret)},
            timeout=60,
        )
        if r.status_code >= 400:
            log.error("ERPNext %s untuk update %s: %s", r.status_code, update.get("update_id"), r.text[:300])
            return False
        return True

    # ---- loop ----

    def step(self) -> int:
        """Satu putaran: tarik, teruskan, majukan offset. Mengembalikan jumlah update."""
        updates = self.fetch()
        for u in updates:
            try:
                self.forward(u)
            except requests.RequestException as e:
                # ERPNext tidak bisa dihubungi: offset berhenti di update ini
                # supaya diproses lagi nanti, bukan hilang.
                log.error("ERPNext tidak terjangkau: %s", e)
                self.offset = u["update_id"]
                raise
        self.offset = next_offset(updates, self.offset)
        return len(updates)

    def run(self):
        log.info("relay aktif, meneruskan ke %s", self.s.erpnext_url)
        while True:
            try:
                n = self.step()
                if n:
                    log.info("%d update diteruskan", n)
            except (requests.RequestException, RuntimeError) as e:
                log.warning("%s; coba lagi %.0f s", e, self.s.backoff_s)
                time.sleep(self.s.backoff_s)
