# Copyright (c) 2026, SIAGA and contributors
# For license information, please see license.txt

"""Dari skor kesehatan ke work order, tanpa tangan manusia.

Dipanggil lewat hook after_insert Health Score. Aturannya ada di sini, bukan
di AI service, karena semua yang dibutuhkan untuk memutuskan (ambang kelas,
status alarm profil, work order yang masih terbuka, part kandidat) ada di
ERPNext dan keputusan itu harus terjadi dalam transaksi yang sama dengan
skornya.

Tiga aturan menjaga planner tidak kebanjiran dokumen:

1. Skor harus di bawah ambang pemicu selama N siklus berturut turut.
2. Histeresis: setelah alarm, status baru Normal lagi kalau skor naik
   melewati ambang pulih. Selama Alarm tidak ada work order baru.
3. Satu work order terbuka per pasangan aset dan komponen, dijaga controller
   work order untuk pemicu Otomatis.
"""

import json

import frappe
from frappe import _
from frappe.utils import flt, now_datetime

from siaga import telegram

OPEN_STATUSES = ("Terbuka", "Dikerjakan")


def on_health_score(doc, method=None):
	"""Hook after_insert Health Score."""
	if doc.operating_state and doc.operating_state != "stabil":
		return
	profile = frappe.db.get_value(
		"Asset Monitoring Profile", {"asset": doc.asset},
		["name", "asset_class", "monitoring_status", "alarm_state"], as_dict=True,
	)
	if not profile or profile.monitoring_status != "Dipantau" or not profile.asset_class:
		return
	cls = frappe.get_cached_doc("Asset Class", profile.asset_class)
	if not cls.monitoring_enabled:
		return

	trigger = flt(cls.threshold_trigger)
	recover = flt(cls.threshold_recover)

	# Pulih: alarm dicabut hanya setelah melewati ambang pulih, bukan ambang pemicu.
	if profile.alarm_state == "Alarm":
		if flt(doc.score) >= recover:
			frappe.db.set_value("Asset Monitoring Profile", profile.name,
				{"alarm_state": "Normal", "alarm_since": None})
		return

	if flt(doc.score) >= trigger:
		return
	if not consecutive_below(doc, trigger, int(cls.consecutive_cycles or 1)):
		return

	work_order = create_work_order(doc, cls)
	if not work_order:
		return
	frappe.db.set_value("Asset Monitoring Profile", profile.name, {
		"alarm_state": "Alarm",
		"alarm_since": now_datetime(),
		"last_auto_work_order": work_order.name,
	})
	frappe.db.set_value("Health Score", doc.name, "work_order", work_order.name)


def consecutive_below(doc, trigger, cycles):
	"""Benar kalau `cycles` skor terakhir aset ini (termasuk doc) semuanya di bawah ambang."""
	if cycles <= 1:
		return True
	recent = frappe.get_all(
		"Health Score",
		filters={"asset": doc.asset, "operating_state": "stabil", "scored_at": ["<=", doc.scored_at]},
		fields=["score"],
		order_by="scored_at desc",
		limit=cycles,
	)
	if len(recent) < cycles:
		return False
	return all(flt(r.score) < trigger for r in recent)


def symptom_of(doc):
	try:
		return (json.loads(doc.top_features or "{}") or {}).get("symptom") or "broadband"
	except ValueError:
		return "broadband"


def candidate_parts(cls, symptom):
	"""Part kandidat kelas untuk gejala ini; kalau tidak ada, pakai baris broadband."""
	rows = [r for r in cls.candidate_parts if r.symptom == symptom]
	if not rows and symptom != "broadband":
		rows = [r for r in cls.candidate_parts if r.symptom == "broadband"]
	return rows


def pick_component(asset, component_type):
	"""Komponen terpasang di aset dengan jenis yang cocok."""
	return frappe.db.get_value(
		"Asset Component",
		{"asset": asset, "component_type": component_type, "status": "Terpasang"},
		"name",
	)


def priority_for(doc):
	"""Work order otomatis terbit setelah pelanggaran ambang yang bertahan,
	jadi minimal Tinggi. Kritis kalau skornya sudah sangat rendah. Proyeksi
	tidak dipakai di sini: saat pemicu, proyeksi ke ambang selalu nol."""
	return "Kritis" if flt(doc.score) < 20 else "Tinggi"


def create_work_order(doc, cls):
	symptom = symptom_of(doc)
	parts = candidate_parts(cls, symptom)
	component = None
	if parts:
		component = pick_component(doc.asset, parts[0].component_type)

	# Peredam duplikasi: satu work order terbuka per aset dan komponen.
	dup_filters = {"asset": doc.asset, "status": ["in", OPEN_STATUSES], "trigger_source": "Otomatis"}
	if component:
		dup_filters["component"] = component
	if frappe.db.exists("SIAGA Work Order", dup_filters):
		return None

	asset_name = frappe.db.get_value("Asset", doc.asset, "asset_name") or doc.asset
	symptom_label = (doc.trigger_summary or "").split(":", 1)[0].strip() or symptom
	warehouse = cls.default_warehouse

	wo = frappe.get_doc({
		"doctype": "SIAGA Work Order",
		"title": _("Otomatis: {0} pada {1}").format(symptom_label, asset_name),
		"asset": doc.asset,
		"component": component,
		"priority": priority_for(doc),
		"trigger_source": "Otomatis",
		"health_score": doc.name,
		"confidence": doc.confidence,
		"days_to_threshold": doc.days_to_threshold if doc.has_projection else None,
		"trigger_summary": doc.trigger_summary,
		"description": _(
			"Diterbitkan otomatis oleh SIAGA. Skor kesehatan {0} pada {1}. "
			"Part di bawah adalah dugaan dari gejala '{2}'; pastikan saat inspeksi."
		).format(doc.score, doc.scored_at, symptom),
		"warehouse": warehouse,
		"parts": [{"item": r.item, "qty": r.qty or 1, "warehouse": warehouse} for r in parts],
	})
	wo.insert(ignore_permissions=True)
	wo.submit()
	notify_planners(wo, doc)
	telegram.notify_auto_work_order(wo, doc)
	return wo


def notify_planners(wo, doc):
	"""Notifikasi lonceng ke semua Maintenance Manager yang aktif."""
	users = frappe.get_all(
		"Has Role",
		filters={"role": "Maintenance Manager", "parenttype": "User"},
		pluck="parent",
	)
	users = [u for u in set(users) if u not in ("Administrator", "Guest")
	         and not u.startswith("siaga-bot")
	         and frappe.db.get_value("User", u, "enabled")]
	for user in users:
		frappe.get_doc({
			"doctype": "Notification Log",
			"for_user": user,
			"type": "Alert",
			"document_type": "SIAGA Work Order",
			"document_name": wo.name,
			"subject": _("Work order otomatis {0}: {1} (skor {2})").format(wo.name, wo.title, doc.score),
			"email_content": doc.trigger_summary,
		}).insert(ignore_permissions=True)
