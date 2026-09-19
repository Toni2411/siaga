"""Klien REST ERPNext untuk AI service.

Memakai user khusus siaga-bot dengan API key, bukan Administrator. Semua cap
waktu ke dan dari ERPNext diubah ke zona waktu site, karena Frappe menyimpan
Datetime sebagai naive di zona itu.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests


class ERPNextError(RuntimeError):
    pass


class ERPNextClient:
    def __init__(self, url: str, api_key: str, api_secret: str, timeout: float = 30.0):
        if not api_key or not api_secret:
            raise ValueError("ERPNEXT_API_KEY dan ERPNEXT_API_SECRET harus diisi")
        self.url = url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": "token %s:%s" % (api_key, api_secret),
            "Accept": "application/json",
            "Content-Type": "application/json",
        })
        self.timeout = timeout
        self._tz: ZoneInfo | None = None

    # ---- dasar ----

    def _request(self, method: str, path: str, **kw):
        r = self.session.request(method, self.url + path, timeout=self.timeout, **kw)
        if r.status_code >= 400:
            try:
                body = r.json()
                msg = body.get("exception") or body.get("_server_messages") or r.text
            except ValueError:
                msg = r.text
            raise ERPNextError("%s %s -> %d: %s" % (method, path, r.status_code, str(msg)[:800]))
        return r.json()

    def get_list(self, doctype: str, fields: list[str], filters: list | None = None, limit: int = 500) -> list[dict]:
        params = {"fields": json.dumps(fields), "limit_page_length": limit}
        if filters:
            params["filters"] = json.dumps(filters)
        return self._request("GET", "/api/resource/" + quote(doctype), params=params)["data"]

    def get(self, doctype: str, name: str) -> dict:
        return self._request("GET", "/api/resource/%s/%s" % (quote(doctype), quote(name)))["data"]

    def set_value(self, doctype: str, name: str, values: dict) -> dict:
        return self._request("PUT", "/api/resource/%s/%s" % (quote(doctype), quote(name)), data=json.dumps(values))["data"]

    def insert(self, doc: dict) -> dict:
        return self._request("POST", "/api/resource/" + quote(doc["doctype"]), data=json.dumps(doc))["data"]

    def insert_many(self, docs: list[dict]) -> list[str]:
        if not docs:
            return []
        return self._request("POST", "/api/method/frappe.client.insert_many", data=json.dumps({"docs": docs}))["message"]

    def call(self, method: str, **args):
        return self._request("POST", "/api/method/" + method, data=json.dumps(args)).get("message")

    def whoami(self) -> str:
        return self._request("GET", "/api/method/frappe.auth.get_logged_user")["message"]

    # ---- zona waktu ----

    @property
    def tz(self) -> ZoneInfo:
        if self._tz is None:
            # System Settings butuh System Manager; endpoint ini terbuka untuk semua user.
            msg = self._request("GET", "/api/method/frappe.client.get_time_zone").get("message")
            name = msg.get("time_zone") if isinstance(msg, dict) else msg
            self._tz = ZoneInfo(name or "UTC")
        return self._tz

    def to_site(self, dt: datetime) -> str:
        """UTC aware -> string naive zona site, format yang diterima Frappe."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(self.tz).strftime("%Y-%m-%d %H:%M:%S.%f")

    def from_site(self, value: str | None) -> datetime | None:
        """String naive zona site -> UTC aware."""
        if not value:
            return None
        fmt = "%Y-%m-%d %H:%M:%S.%f" if "." in value else "%Y-%m-%d %H:%M:%S"
        return datetime.strptime(value, fmt).replace(tzinfo=self.tz).astimezone(timezone.utc)
