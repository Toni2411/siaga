# -*- coding: utf-8 -*-
"""Cari chat id Telegram untuk .env.

1. Buat bot lewat @BotFather, salin tokennya.
2. Kirim satu pesan apa saja ke bot itu dari akun Anda (atau tambahkan bot ke
   grup lalu kirim pesan di grup).
3. Jalankan: python scripts/telegram_chat_id.py <token>
"""
import json
import sys
import urllib.request

if len(sys.argv) < 2:
    sys.exit(__doc__)
token = sys.argv[1]
with urllib.request.urlopen("https://api.telegram.org/bot%s/getUpdates" % token, timeout=15) as r:
    data = json.load(r)
seen = {}
for u in data.get("result", []):
    m = u.get("message") or u.get("channel_post") or {}
    chat = m.get("chat")
    if chat:
        seen[chat["id"]] = "%s (%s)" % (chat.get("title") or chat.get("first_name") or "", chat.get("type"))
if not seen:
    sys.exit("belum ada pesan masuk ke bot. Kirim pesan ke bot dulu, lalu jalankan lagi.")
for cid, label in seen.items():
    print("TELEGRAM_CHAT_ID=%s   # %s" % (cid, label))
