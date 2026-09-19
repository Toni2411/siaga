# Copyright (c) 2026, SIAGA and contributors
# For license information, please see license.txt

"""Agen tanya-jawab baca-saja di atas data maintenance.

Batasnya struktural, bukan janji di prompt: modul ini tidak punya jalur
tulis. Ia menyusun ringkasan keadaan (unit, work order, stok, forecast,
riwayat kerusakan) lewat frappe.get_list sebagai user yang bertanya —
jadi izin baca user itulah yang berlaku — lalu meminta LLM menjawab
*hanya dari ringkasan itu*. LLM tidak diberi alat, tidak menulis SQL, dan
jawabannya tidak pernah dieksekusi. Kalau jawabannya salah, yang salah
kalimatnya, bukan datanya.

LLM-nya Ollama lokal (OLLAMA_URL, OLLAMA_MODEL). Kosong berarti nonaktif.
Tiap tanya-jawab dicatat di Agent Query: pertanyaan, jawaban, model, waktu,
supaya kualitasnya bisa dinilai belakangan dari catatan, bukan dari kesan.
"""

import json
import os
import re
import time

import frappe
import requests
from frappe import _
from frappe.utils import flt, get_datetime, pretty_date

MAX_QUESTION = 500
MAX_ROWS = 30

SYSTEM = """Kamu asisten baca-saja untuk SIAGA, sistem maintenance berbasis kondisi di ERPNext.
Jawab pertanyaan planner atau mekanik HANYA dari data di bawah. Aturan:
- Kalau jawabannya tidak ada di data, katakan "tidak ada di data yang saya punya"; jangan menebak.
- Kamu tidak bisa mengubah apa pun. Kalau diminta membuat, menutup, memesan, atau mengubah sesuatu,
  katakan bahwa itu dilakukan lewat tombol /wo atau form ERPNext, bukan lewat kamu.
- Skor kesehatan 0-100; di bawah ambang pemicu (biasanya 40) tiga siklus berturut-turut memicu work order.
  "Proyeksi ke ambang" adalah ekstrapolasi tren linear, bukan prediksi sisa umur; sebut apa adanya.
- Jawab dalam bahasa Indonesia, ringkas, angka apa adanya, sebutkan nama dokumen (WO-..., MAT-MR-...) bila relevan.
- Jangan pakai tabel markdown; pakai kalimat atau daftar pendek."""


# ---- konfigurasi ----

def config():
	url = os.environ.get("OLLAMA_URL") or frappe.conf.get("siaga_ollama_url")
	model = os.environ.get("OLLAMA_MODEL") or frappe.conf.get("siaga_ollama_model") or "qwen2.5:7b"
	return (url.rstrip("/") if url else None), model


def enabled():
	return bool(config()[0])


# ---- ringkasan keadaan, sebagai user yang bertanya ----

def _fmt_when(value):
	return pretty_date(get_datetime(value)) if value else "-"


def build_context(max_rows=MAX_ROWS):
	"""Teks ringkas keadaan sistem. Semua lewat get_list, jadi izin baca user berlaku."""
	from siaga import forecast

	parts = []

	units = frappe.get_list(
		"Asset Monitoring Profile",
		fields=["asset", "monitoring_status", "alarm_state", "last_score", "last_score_at", "last_auto_work_order", "asset_class"],
		order_by="last_score asc", limit_page_length=max_rows,
	)
	lines = []
	for u in units:
		name = frappe.db.get_value("Asset", u.asset, "asset_name") or u.asset
		line = "- %s (%s): status %s" % (name, u.asset, u.monitoring_status)
		if u.monitoring_status == "Dipantau":
			line += ", skor %.0f (%s), alarm %s" % (flt(u.last_score), _fmt_when(u.last_score_at), u.alarm_state or "Normal")
			latest = frappe.get_list("Health Score", filters={"asset": u.asset, "operating_state": "stabil"},
			                         fields=["has_projection", "days_to_threshold", "projection_low", "projection_high", "trigger_summary"],
			                         order_by="scored_at desc", limit_page_length=1)
			if latest and latest[0].has_projection:
				h = latest[0]
				line += ", proyeksi ke ambang ~%.1f hari (%.1f-%.1f)" % (flt(h.days_to_threshold), flt(h.projection_low), flt(h.projection_high))
			if latest and latest[0].trigger_summary:
				line += ", gejala: %s" % latest[0].trigger_summary.split(":", 1)[0].strip()
		if u.last_auto_work_order:
			line += ", work order alarm terakhir %s" % u.last_auto_work_order
		lines.append(line)
	parts.append("## Unit yang dipantau (%d)\n%s" % (len(units), "\n".join(lines) or "- tidak ada"))

	wos = frappe.get_list(
		"SIAGA Work Order", filters={"docstatus": 1, "status": ["in", ("Terbuka", "Dikerjakan")]},
		fields=["name", "title", "asset_name", "status", "priority", "trigger_source", "assigned_to", "creation", "component", "material_request"],
		order_by="creation desc", limit_page_length=max_rows,
	)
	lines = ["- %s: %s | %s | %s | prioritas %s | %s | dibuat %s%s%s" % (
		w.name, w.asset_name, w.title, w.status, w.priority, w.trigger_source, _fmt_when(w.creation),
		" | ditugaskan ke %s" % w.assigned_to if w.assigned_to else "",
		" | permintaan pembelian %s" % w.material_request if w.material_request else "") for w in wos]
	parts.append("## Work order terbuka (%d)\n%s" % (len(wos), "\n".join(lines) or "- tidak ada"))

	done = frappe.get_list(
		"SIAGA Work Order", filters={"docstatus": 1, "status": "Selesai"},
		fields=["name", "asset_name", "completed_on", "failure_log", "completion_notes", "trigger_source"],
		order_by="completed_on desc", limit_page_length=10,
	)
	lines = []
	for w in done:
		mode = frappe.db.get_value("Failure Log", w.failure_log, "failure_mode") if w.failure_log else None
		lines.append("- %s: %s | selesai %s | kerusakan: %s | %s | catatan: %s" % (
			w.name, w.asset_name, _fmt_when(w.completed_on), mode or "tidak dicatat", w.trigger_source, (w.completion_notes or "-")[:120]))
	parts.append("## Work order selesai terakhir (%d)\n%s" % (len(done), "\n".join(lines) or "- tidak ada"))

	try:
		rows = forecast.table()
		lines = ["- %s (%s) di %s: fisik %g, terkunci WO %g, tersedia %g, proyeksi kondisi %g%s, titik pesan %g, draft MR menunggu %g, saran: %s, rata-rata pemakaian historis %.1f/bulan" % (
			r.item, r.item_name, r.warehouse, r.actual_qty, r.locked_qty, r.available_qty, r.projected_qty,
			" (%s)" % r.projected_units if r.projected_units else "", r.reorder_level, r.pending_mr_qty, r.advice, r.historical_monthly)
			for r in rows]
		parts.append("## Stok dan forecast part\n%s" % ("\n".join(lines) or "- tidak ada"))
	except frappe.PermissionError:
		parts.append("## Stok dan forecast part\n- tidak boleh dilihat user ini")

	mrs = frappe.get_list(
		"Material Request", filters={"siaga_auto": 1, "docstatus": 0},
		fields=["name", "transaction_date", "siaga_reason", "siaga_work_order"], limit_page_length=max_rows,
	)
	lines = []
	for m in mrs:
		items = frappe.get_all("Material Request Item", filters={"parent": m.name}, fields=["item_code", "qty", "warehouse"])
		lines.append("- %s (%s): %s | alasan: %s" % (
			m.name, m.transaction_date, ", ".join("%s x%g ke %s" % (i.item_code, flt(i.qty), i.warehouse) for i in items),
			m.siaga_reason or ("dari work order %s" % m.siaga_work_order)))
	parts.append("## Draft permintaan pembelian otomatis menunggu approval (%d)\n%s" % (len(mrs), "\n".join(lines) or "- tidak ada"))

	logs = frappe.get_list(
		"Failure Log", fields=["name", "asset", "failed_on", "failure_mode", "training_label", "work_order", "root_cause"],
		order_by="failed_on desc", limit_page_length=10,
	)
	lines = []
	for lg in logs:
		name = frappe.db.get_value("Asset", lg.asset, "asset_name") or lg.asset
		lines.append("- %s: %s | %s | %s (label %s) | work order %s%s" % (
			lg.name, name, _fmt_when(lg.failed_on), lg.failure_mode, lg.training_label, lg.work_order or "-",
			" | akar masalah: %s" % lg.root_cause if lg.root_cause else ""))
	parts.append("## Riwayat kerusakan terakhir (%d)\n%s" % (len(logs), "\n".join(lines) or "- tidak ada"))

	return "\n\n".join(parts)


# ---- LLM ----

class Ollama:
	def __init__(self, url, model, timeout=180):
		self.url, self.model, self.timeout = url, model, timeout

	def chat(self, system, user):
		r = requests.post(self.url + "/api/chat", json={
			"model": self.model, "stream": False, "think": False,
			"messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
			"options": {"temperature": 0.2, "num_predict": 700},
		}, timeout=self.timeout)
		r.raise_for_status()
		data = r.json()
		return (data.get("message") or {}).get("content", "").strip()


def client():
	url, model = config()
	if not url:
		frappe.throw(_("Agen tanya-jawab tidak aktif: OLLAMA_URL kosong"))
	return Ollama(url, model)


# ---- tanya ----

@frappe.whitelist()
def ask(question, channel="API", chat_id=None):
	"""Jawab satu pertanyaan sebagai user sesi ini. Mengembalikan dict jawaban dan metadata."""
	question = (question or "").strip()
	if not question:
		frappe.throw(_("Pertanyaannya kosong"))
	if len(question) > MAX_QUESTION:
		frappe.throw(_("Pertanyaan terlalu panjang (maksimal {0} karakter)").format(MAX_QUESTION))

	llm = client()
	started = time.time()
	context = build_context()
	log = frappe.get_doc({
		"doctype": "Agent Query", "user": frappe.session.user, "channel": channel, "chat_id": chat_id,
		"question": question, "model": llm.model, "context_chars": len(context), "status": "Diproses",
	})
	try:
		answer = llm.chat(SYSTEM, "DATA SAAT INI:\n\n%s\n\nPERTANYAAN: %s" % (context, question))
		if not answer:
			answer = _("Model tidak memberi jawaban.")
		log.update({"answer": answer, "status": "Selesai", "latency_ms": int((time.time() - started) * 1000)})
	except requests.RequestException as e:
		log.update({"status": "Gagal", "error": str(e)[:500], "latency_ms": int((time.time() - started) * 1000)})
		log.insert(ignore_permissions=True)
		frappe.throw(_("Model tidak bisa dihubungi: {0}").format(str(e)[:200]))
	log.insert(ignore_permissions=True)
	return {"answer": answer, "model": llm.model, "latency_ms": log.latency_ms, "context_chars": len(context), "query": log.name}


def to_telegram_html(text):
	"""Markdown ringan dari model ke HTML Telegram: tebal, kode; judul dibuang; sisanya di-escape."""
	out = frappe.utils.escape_html(text)
	out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
	out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
	out = re.sub(r"(?m)^#{1,6}\s*", "", out)
	return out


def answer_to_chat(chat_id, user, question):
	"""Pekerjaan latar: jawab lalu kirim ke chat. Dijalankan sebagai user penanya."""
	from siaga import telegram

	frappe.set_user(user)
	try:
		result = ask(question, channel="Telegram", chat_id=chat_id)
		text = "💬 %s\n\n<i>%s · %.0f s · baca-saja, dari data saat ini</i>" % (
			to_telegram_html(result["answer"]), frappe.utils.escape_html(result["model"]), result["latency_ms"] / 1000.0)
	except Exception as e:
		text = "⚠️ %s" % frappe.utils.escape_html(frappe.utils.strip_html(str(e)) or _("Gagal menjawab"))
	telegram.send(text, chat_id=chat_id)
