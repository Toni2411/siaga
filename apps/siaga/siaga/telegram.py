# Copyright (c) 2026, SIAGA and contributors
# For license information, please see license.txt

"""Notifikasi keluar ke Telegram.

Telegram di sini hanya saluran; ERPNext tetap sumber kebenaran dan yang
dikirim adalah ringkasan dokumen yang sudah tercatat. Pengiriman dilakukan
lewat antrean setelah commit, jadi hook yang memanggilnya tidak pernah
menunggu jaringan dan gagalnya Telegram tidak menggagalkan dokumennya.

Konfigurasi dari environment container (SIAGA_TELEGRAM_TOKEN,
SIAGA_TELEGRAM_CHAT_ID) atau site config (siaga_telegram_token,
siaga_telegram_chat_id). Kosong berarti nonaktif, tanpa galat.
"""

import html
import os

import frappe
import requests
from frappe import _
from frappe.utils import flt, get_url_to_form, nowdate

API = "https://api.telegram.org/bot{token}/sendMessage"


def config():
	token = os.environ.get("SIAGA_TELEGRAM_TOKEN") or frappe.conf.get("siaga_telegram_token")
	chat_id = os.environ.get("SIAGA_TELEGRAM_CHAT_ID") or frappe.conf.get("siaga_telegram_chat_id")
	return token, chat_id


def enabled():
	token, chat_id = config()
	return bool(token and chat_id)


def link(doctype, name, label=None):
	base = os.environ.get("SIAGA_PUBLIC_URL") or frappe.conf.get("siaga_public_url")
	url = get_url_to_form(doctype, name)
	if base:
		# get_url_to_form memakai host site; ganti dengan alamat yang bisa dibuka dari HP
		url = base.rstrip("/") + url[url.index("/app/"):]
	return '<a href="%s">%s</a>' % (url, html.escape(label or name))


def send(text, silent=False):
	"""Kirim sekarang (dipanggil worker). Aman dipanggil kalau nonaktif."""
	token, chat_id = config()
	if not token or not chat_id:
		return False
	try:
		r = requests.post(
			API.format(token=token),
			json={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
			      "disable_web_page_preview": True, "disable_notification": bool(silent)},
			timeout=15,
		)
		if r.status_code >= 400:
			frappe.log_error("Telegram %s: %s" % (r.status_code, r.text[:300]), "SIAGA Telegram")
			return False
		return True
	except requests.RequestException as e:
		frappe.log_error(str(e), "SIAGA Telegram")
		return False


def queue(text, silent=False):
	"""Antrekan pengiriman setelah transaksi saat ini commit."""
	if not enabled():
		return
	frappe.enqueue("siaga.telegram.send", text=text, silent=silent,
	               queue="short", enqueue_after_commit=True)


# ---- pesan per kejadian ----

def notify_auto_work_order(wo, score):
	symptom = (score.trigger_summary or "").split(":", 1)[0].strip()
	lines = [
		"🚨 <b>Work order otomatis</b> %s" % link("SIAGA Work Order", wo.name),
		html.escape(wo.asset_name or wo.asset),
		"Skor kesehatan <b>%.0f</b> · prioritas <b>%s</b>" % (flt(score.score), wo.priority),
		"Gejala: %s" % html.escape(symptom or "-"),
	]
	if wo.component:
		lines.append("Komponen dugaan: %s" % html.escape(wo.component))
	if wo.parts:
		lines.append("Part dikunci: " + ", ".join("%s ×%g" % (html.escape(p.item), flt(p.qty)) for p in wo.parts))
	queue("\n".join(lines))


def notify_material_request(mr_name, item, qty, warehouse, wo_name=None):
	lines = [
		"🛒 <b>Draft permintaan pembelian</b> %s" % link("Material Request", mr_name),
		"%s ×%g ke %s" % (html.escape(item), flt(qty), html.escape(warehouse)),
		"Stok setelah reservasi di bawah titik pesan ulang. Menunggu approval procurement.",
	]
	if wo_name:
		lines.append("Dipicu " + link("SIAGA Work Order", wo_name))
	queue("\n".join(lines))


def notify_work_order_completed(wo, failure_log=None):
	lines = [
		"✅ <b>Work order selesai</b> %s" % link("SIAGA Work Order", wo.name),
		html.escape(wo.asset_name or wo.asset),
	]
	if failure_log:
		lines.append("Kerusakan tercatat: <b>%s</b> (%s)" % (
			html.escape(failure_log.failure_mode or "-"), link("Failure Log", failure_log.name)))
	if wo.completion_notes:
		lines.append(html.escape(wo.completion_notes))
	queue("\n".join(lines), silent=True)


def daily_summary(now=False):
	"""Ringkasan pagi: dijadwalkan lewat scheduler_events daily.

	now=True mengirim langsung tanpa antrean, untuk pemicu manual lewat
	bench execute yang prosesnya selesai sebelum sempat commit.
	"""
	if not enabled():
		return
	alarms = frappe.get_all("Asset Monitoring Profile", filters={"alarm_state": "Alarm"}, fields=["asset", "last_auto_work_order"])
	open_wo = frappe.db.count("SIAGA Work Order", {"status": ["in", ("Terbuka", "Dikerjakan")], "docstatus": 1})
	pending_mr = frappe.db.count("Material Request", {"siaga_auto": 1, "docstatus": 0})
	monitored = frappe.db.count("Asset Monitoring Profile", {"monitoring_status": "Dipantau"})
	lines = [
		"🌅 <b>Ringkasan SIAGA %s</b>" % nowdate(),
		"Unit dipantau: %d · dalam alarm: %d" % (monitored, len(alarms)),
		"Work order terbuka: %d · draft pembelian menunggu: %d" % (open_wo, pending_mr),
	]
	for a in alarms:
		name = frappe.db.get_value("Asset", a.asset, "asset_name") or a.asset
		lines.append("• %s → %s" % (html.escape(name), link("SIAGA Work Order", a.last_auto_work_order) if a.last_auto_work_order else "-"))
	text = "\n".join(lines)
	return send(text, silent=True) if now else queue(text, silent=True)
