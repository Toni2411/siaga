# -*- coding: utf-8 -*-
"""Buat .env dari .env.example dengan rahasia acak.

    python scripts/init_env.py            # tidak menimpa .env yang sudah ada
    python scripts/init_env.py --force    # timpa
"""
import re
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
example = ROOT / ".env.example"
target = ROOT / ".env"

if target.exists() and "--force" not in sys.argv:
    sys.exit(".env sudah ada. Pakai --force untuk menimpa.")

text = example.read_text(encoding="utf-8")
fills = {
    "DB_ROOT_PASSWORD": secrets.token_urlsafe(18),
    "TIMESCALE_PASSWORD": secrets.token_urlsafe(18),
    "ERPNEXT_API_KEY": secrets.token_hex(8)[:15],
    "ERPNEXT_API_SECRET": secrets.token_urlsafe(15),
}
for key, value in fills.items():
    text = re.sub(r"^%s=.*$" % key, "%s=%s" % (key, value), text, flags=re.M)
target.write_text(text, encoding="utf-8")
print("==> .env dibuat. Password Administrator: admin (ubah ADMIN_PASSWORD kalau perlu).")
