# Copyright (c) 2026, SIAGA and contributors
# For license information, please see license.txt

"""Perintah masuk dari Telegram: work order dari HP, tanpa membuka ERP.

Relay service (services/telegram) meneruskan tiap update Telegram ke
`handle_update` sebagai user siaga-bot. Di sini chat dipetakan ke user
ERPNext lewat Telegram Chat, lalu tiap aksi dijalankan sebagai user itu
dengan pemeriksaan izin biasa: yang bisa dilakukan dari chat persis sama
dengan yang bisa dilakukan user itu di form.

Tidak ada LLM. Perintahnya terstruktur dan aksinya lewat tombol inline,
supaya tidak ada tafsir bebas antara jempol mekanik dan dokumen ERP.

Perintah:
    /mulai KODE   tautkan chat ini ke user ERPNext (kode dari Telegram Chat)
    /wo           work order terbuka, dengan tombol Mulai / Selesai
    /unit         kondisi unit yang dipantau
    /stok         stok part kritis di gudang
    /batal        batalkan langkah yang sedang menunggu jawaban
    /bantuan      daftar ini

Menutup work order lewat tombol berjalan tiga langkah: mode kerusakan
(tombol), komponen diganti atau tidak (tombol), catatan singkat (ketik,
atau /lewati). Langkah yang menunggu disimpan di Telegram Chat.pending,
jadi tidak hilang kalau worker berganti.
"""

import html
import json
import re

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, pretty_date

from siaga import telegram
from siaga.setup import BOT_EMAIL
from siaga.siaga.doctype.siaga_work_order.siaga_work_order import OPEN_STATUSES, TRAINING_LABEL

FAILURE_MODES = list(TRAINING_LABEL)
NO_FAILURE = "-"
PRIORITY_ICON = {"Kritis": "🔴", "Tinggi": "🟠", "Sedang": "🟡", "Rendah": "⚪"}
PRIORITY_RANK = {"Kritis": 0, "Tinggi": 1, "Sedang": 2, "Rendah": 3}

HELP = (
	"<b>Perintah SIAGA</b>\n"
	"/wo — work order terbuka, tombol Mulai / Selesai\n"
	"/unit — kondisi unit yang dipantau\n"
	"/stok — stok part kritis\n"
	"/batal — batalkan langkah yang menunggu jawaban\n"
	"/bantuan — daftar ini"
)

NOT_LINKED = (
	"Chat ini belum ditautkan ke user ERPNext.\n"
	"Minta planner membuat <b>Telegram Chat</b> untuk Anda di ERPNext, lalu kirim "
	"<code>/mulai KODE</code> ke sini.\n"
	"Chat ID Anda: <code>{chat_id}</code>"
)


# ---- pintu masuk ----

@frappe.whitelist()
def handle_update(update):
	"""Satu update Telegram (message atau callback_query), dipanggil relay."""
	require_relay()
	if isinstance(update, str):
		update = json.loads(update)
	session = Session.from_update(update)
	if session is None:
		return {"ignored": True}

	caller = frappe.session.user
	try:
		session.dispatch()
	except (frappe.ValidationError, frappe.PermissionError, frappe.DoesNotExistError) as e:
		# Ditolak aturan bisnis atau izin: balas alasannya ke chat, catat ringkas.
		frappe.db.rollback()
		frappe.clear_messages()
		frappe.log_error(title="SIAGA Telegram bot ditolak", message="%s | %s | %s" % (session.chat_id, session.text, e))
		session.reply("⚠️ " + html.escape(strip_html(str(e))))
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title="SIAGA Telegram bot", message=frappe.get_traceback())
		session.reply("⚠️ Terjadi galat di sisi server. Sudah dicatat.")
	finally:
		frappe.set_user(caller)
	return {"ok": True}


def require_relay():
	if frappe.session.user == BOT_EMAIL or "System Manager" in frappe.get_roles():
		return
	frappe.throw(_("Hanya relay Telegram yang boleh memanggil ini"), frappe.PermissionError)


def strip_html(text):
	return re.sub(r"<[^>]+>", "", text or "").strip()


def split_command(text):
	"""'/mulai ABC' -> ('mulai', 'ABC'); '/wo@siaga_bot' -> ('wo', ''); 'halo' -> (None, 'halo')."""
	text = (text or "").strip()
	if not text.startswith("/"):
		return None, text
	head, _, rest = text[1:].partition(" ")
	return head.split("@", 1)[0].lower(), rest.strip()


# ---- sesi satu update ----

class Session:
	def __init__(self, chat_id, sender, text, callback_id=None):
		self.chat_id = str(chat_id)
		self.sender = sender or {}
		self.text = text or ""
		self.callback_id = callback_id
		self.chat = frappe.db.get_value(
			"Telegram Chat", {"chat_id": self.chat_id},
			["name", "user", "status", "pending"], as_dict=True,
		)

	@classmethod
	def from_update(cls, update):
		cb = update.get("callback_query")
		if cb:
			return cls(cb["message"]["chat"]["id"], cb.get("from"), cb.get("data"), cb.get("id"))
		msg = update.get("message") or update.get("edited_message")
		if msg and msg.get("chat"):
			return cls(msg["chat"]["id"], msg.get("from"), msg.get("text"))
		return None

	@property
	def sender_name(self):
		parts = [self.sender.get("first_name"), self.sender.get("last_name")]
		name = " ".join(p for p in parts if p)
		return name or self.sender.get("username") or self.chat_id

	def reply(self, text, buttons=None, silent=False):
		telegram.send(text, silent=silent, chat_id=self.chat_id, buttons=buttons)

	def ack(self, text=None):
		"""Hilangkan indikator memuat di tombol yang ditekan."""
		if self.callback_id:
			telegram.call("answerCallbackQuery", {"callback_query_id": self.callback_id, "text": text or ""})
			self.callback_id = None

	# ---- alur ----

	def dispatch(self):
		cmd, arg = split_command(self.text)
		if cmd in ("start", "mulai"):
			return self.link(arg)

		if not self.chat or self.chat.status != "Tertaut":
			self.ack()
			return self.reply(NOT_LINKED.format(chat_id=self.chat_id))
		if not frappe.db.get_value("User", self.chat.user, "enabled"):
			self.ack()
			return self.reply("User %s dinonaktifkan di ERPNext." % html.escape(self.chat.user))

		frappe.db.set_value("Telegram Chat", self.chat.name, "last_seen", now_datetime(), update_modified=False)
		frappe.set_user(self.chat.user)

		if self.callback_id:
			return self.callback(self.text)
		if cmd == "wo":
			return self.list_work_orders()
		if cmd == "unit":
			return self.list_units()
		if cmd == "stok":
			return self.list_stock()
		if cmd == "batal":
			self.set_pending(None)
			return self.reply("Dibatalkan.")
		if cmd == "lewati":
			return self.continue_pending("")
		if cmd in ("bantuan", "help"):
			return self.reply(HELP)
		if cmd is None and self.pending():
			return self.continue_pending(self.text)
		return self.reply("Perintah tidak dikenal.\n\n" + HELP)

	# ---- tautan chat ----

	def link(self, code):
		self.ack()
		if self.chat and self.chat.status == "Tertaut":
			return self.reply("Chat ini sudah tertaut ke <b>%s</b>.\n\n%s" % (html.escape(self.chat.user), HELP))
		if not code:
			return self.reply(NOT_LINKED.format(chat_id=self.chat_id))
		name = frappe.db.get_value("Telegram Chat", {"link_code": code.upper(), "status": "Menunggu tautan"}, "name")
		if not name:
			return self.reply("Kode <code>%s</code> tidak dikenal atau sudah dipakai." % html.escape(code))
		doc = frappe.get_doc("Telegram Chat", name)
		doc.chat_id = self.chat_id
		doc.telegram_name = self.sender_name
		doc.linked_on = now_datetime()
		doc.status = "Tertaut"
		doc.pending = None
		doc.flags.ignore_permissions = True
		doc.save()
		self.chat = frappe._dict(name=doc.name, user=doc.user, status=doc.status, pending=None)
		return self.reply("Tertaut sebagai <b>%s</b> (%s).\n\n%s" % (
			html.escape(doc.full_name or doc.user), html.escape(doc.user), HELP))

	# ---- daftar ----

	def list_work_orders(self):
		rows = frappe.get_list(
			"SIAGA Work Order",
			filters={"docstatus": 1, "status": ["in", OPEN_STATUSES]},
			fields=["name", "title", "asset_name", "status", "priority", "assigned_to", "due_date"],
			order_by="creation asc",
			limit_page_length=50,
		)
		if not rows:
			return self.reply("Tidak ada work order terbuka. 👍")
		# Yang ditugaskan ke saya dulu, lalu yang sedang dikerjakan, lalu prioritas.
		me = frappe.session.user
		rows.sort(key=lambda r: (r.assigned_to != me, r.status != "Dikerjakan", PRIORITY_RANK.get(r.priority, 9)))
		lines = ["<b>Work order terbuka</b> (%d)" % len(rows)]
		buttons = []
		for r in rows[:8]:
			tag = " · <i>saya</i>" if r.assigned_to == me else ""
			lines.append("%s %s — %s\n   %s · %s%s" % (
				PRIORITY_ICON.get(r.priority, "•"), telegram.link("SIAGA Work Order", r.name),
				html.escape(r.asset_name or ""), r.status, r.priority, tag))
			short = r.name.replace("WO-", "")
			if r.status == "Terbuka":
				buttons.append([("▶️ Mulai %s" % short, "wo:mulai:%s" % r.name),
				                ("✅ Selesai %s" % short, "wo:selesai:%s" % r.name)])
			else:
				buttons.append([("✅ Selesai %s" % short, "wo:selesai:%s" % r.name)])
		if len(rows) > 8:
			lines.append("… dan %d lagi di ERPNext." % (len(rows) - 8))
		return self.reply("\n".join(lines), buttons=buttons)

	def list_units(self):
		rows = frappe.get_list(
			"Asset Monitoring Profile",
			filters={"monitoring_status": ["!=", "Nonaktif"]},
			fields=["asset", "monitoring_status", "alarm_state", "last_score", "last_score_at", "last_auto_work_order"],
			order_by="last_score asc",
			limit_page_length=30,
		)
		if not rows:
			return self.reply("Belum ada unit yang dipantau.")
		lines = ["<b>Kondisi unit</b>"]
		for r in rows:
			name = frappe.db.get_value("Asset", r.asset, "asset_name") or r.asset
			if r.monitoring_status != "Dipantau":
				lines.append("⚪ %s — %s" % (html.escape(name), r.monitoring_status))
				continue
			icon = "🔴" if r.alarm_state == "Alarm" else ("🟢" if flt(r.last_score) >= 55 else "🟡")
			when = pretty_date(get_datetime(r.last_score_at)) if r.last_score_at else "-"
			line = "%s %s — skor <b>%.0f</b> (%s)" % (icon, html.escape(name), flt(r.last_score), when)
			if r.alarm_state == "Alarm" and r.last_auto_work_order:
				line += "\n   alarm → " + telegram.link("SIAGA Work Order", r.last_auto_work_order)
			lines.append(line)
		return self.reply("\n".join(lines))

	def list_stock(self):
		from siaga import stock

		levels = frappe.get_all(
			"Item Reorder", fields=["parent", "warehouse", "warehouse_reorder_level"],
			order_by="parent asc",
		)
		if not levels:
			return self.reply("Belum ada part dengan titik pesan ulang.")
		if not frappe.has_permission("Stock Ledger Entry", "read"):
			frappe.throw(_("Tidak punya izin melihat stok"), frappe.PermissionError)
		lines = ["<b>Stok part kritis</b> (tersedia setelah reservasi)"]
		for lv in levels:
			avail = stock.available_qty(lv.parent, lv.warehouse)
			icon = "🔴" if avail < flt(lv.warehouse_reorder_level) else "🟢"
			lines.append("%s %s — <b>%g</b> di %s (titik pesan %g)" % (
				icon, html.escape(lv.parent), avail, html.escape(lv.warehouse), flt(lv.warehouse_reorder_level)))
		pending = frappe.db.count("Material Request", {"siaga_auto": 1, "docstatus": 0})
		if pending:
			lines.append("🛒 %d draft permintaan pembelian menunggu approval." % pending)
		return self.reply("\n".join(lines))

	# ---- aksi tombol ----

	def callback(self, data):
		parts = (data or "").split(":")
		if len(parts) < 3 or parts[0] != "wo":
			self.ack()
			return self.reply("Tombol ini tidak dikenal lagi.")
		action, name = parts[1], parts[2]
		wo = frappe.get_doc("SIAGA Work Order", name)
		wo.check_permission("write")

		if action == "mulai":
			wo.start_work()
			self.ack("Dikerjakan")
			return self.reply("▶️ %s <b>Dikerjakan</b> oleh %s.\n%s" % (
				telegram.link("SIAGA Work Order", wo.name), html.escape(frappe.session.user), html.escape(wo.asset_name or "")),
				buttons=telegram.work_order_buttons(wo))

		if action == "selesai":
			wo._require_status("Terbuka", "Dikerjakan")
			self.ack()
			buttons = [[(mode, "wo:fm:%s:%d" % (name, i))] for i, mode in enumerate(FAILURE_MODES)]
			buttons.append([("Tanpa catatan kerusakan", "wo:fm:%s:%s" % (name, NO_FAILURE))])
			buttons.append([("✖ Batal", "wo:batal:%s" % name)])
			return self.reply("Menutup %s — %s.\n<b>Apa yang rusak?</b>" % (
				telegram.link("SIAGA Work Order", wo.name), html.escape(wo.asset_name or "")), buttons=buttons)

		if action == "fm":
			fm = parts[3] if len(parts) > 3 else NO_FAILURE
			failure_mode = None if fm == NO_FAILURE else FAILURE_MODES[int(fm)]
			self.ack(failure_mode or "Tanpa catatan")
			state = {"action": "selesai", "wo": name, "failure_mode": failure_mode, "component_replaced": 0}
			if wo.component:
				self.set_pending(state)
				return self.reply("Komponen <b>%s</b> diganti?" % html.escape(wo.component), buttons=[[
					("Ya, diganti", "wo:cr:%s:1" % name), ("Tidak", "wo:cr:%s:0" % name)]])
			return self.ask_notes(state)

		if action == "cr":
			state = self.pending()
			if not state or state.get("wo") != name:
				return self.reply("Langkah ini sudah kedaluwarsa. Tekan Selesai lagi dari /wo.")
			state["component_replaced"] = int(parts[3]) if len(parts) > 3 else 0
			self.ack("Diganti" if state["component_replaced"] else "Tidak diganti")
			return self.ask_notes(state)

		if action == "batal":
			self.set_pending(None)
			self.ack("Dibatalkan")
			return self.reply("Dibatalkan. %s tetap %s." % (wo.name, wo.status))

		self.ack()
		return self.reply("Tombol ini tidak dikenal lagi.")

	def ask_notes(self, state):
		self.set_pending(state)
		return self.reply("Ketik catatan singkat untuk %s, atau kirim /lewati." % state["wo"])

	def continue_pending(self, text):
		state = self.pending()
		if not state:
			return self.reply("Tidak ada langkah yang menunggu.\n\n" + HELP)
		if state.get("action") != "selesai":
			self.set_pending(None)
			return self.reply("Langkah tidak dikenal, dibatalkan.")
		wo = frappe.get_doc("SIAGA Work Order", state["wo"])
		wo.check_permission("write")
		wo.complete_work(
			notes=text.strip() or None,
			failure_mode=state.get("failure_mode"),
			component_replaced=state.get("component_replaced") or 0,
		)
		self.set_pending(None)
		frappe.clear_messages()
		lines = ["✅ %s <b>Selesai</b>." % telegram.link("SIAGA Work Order", wo.name)]
		if state.get("failure_mode"):
			lines.append("Kerusakan tercatat: <b>%s</b>" % html.escape(state["failure_mode"]))
		if state.get("component_replaced") and wo.component:
			lines.append("Komponen %s ditandai Diganti." % html.escape(wo.component))
		if wo.parts:
			lines.append("Part dikeluarkan dari gudang: " + ", ".join(
				"%s ×%g" % (html.escape(p.item), flt(p.qty)) for p in wo.parts))
		return self.reply("\n".join(lines))

	# ---- state percakapan ----

	def pending(self):
		raw = self.chat.pending if self.chat else None
		if not raw:
			return None
		try:
			return json.loads(raw)
		except ValueError:
			return None

	def set_pending(self, state):
		value = json.dumps(state) if state else None
		frappe.db.set_value("Telegram Chat", self.chat.name, "pending", value, update_modified=False)
		self.chat.pending = value
