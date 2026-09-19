# Copyright (c) 2026, SIAGA and contributors
# For license information, please see license.txt

"""Seberapa dini sistem menandai kerusakan yang kemudian benar terjadi.

Untuk tiap Failure Log yang terhubung ke work order otomatis, bandingkan cap
waktu skor pemicu dengan tanggal kerusakan yang dicatat mekanik, dan gejala
tebakan sistem dengan label sebenarnya. Ini cara sistem mengukur dirinya:
angka lead time dan ketepatan gejala datang dari catatan lapangan, bukan
dari klaim.
"""

import json

import frappe
from frappe import _
from frappe.utils import get_datetime


def execute(filters=None):
	filters = filters or {}
	columns = [
		{"label": _("Catatan Kerusakan"), "fieldname": "failure_log", "fieldtype": "Link", "options": "Failure Log", "width": 110},
		{"label": _("Aset"), "fieldname": "asset_name", "fieldtype": "Data", "width": 190},
		{"label": _("Waktu Rusak"), "fieldname": "failed_on", "fieldtype": "Datetime", "width": 150},
		{"label": _("Kerusakan Sebenarnya"), "fieldname": "failure_mode", "fieldtype": "Data", "width": 160},
		{"label": _("Work Order"), "fieldname": "work_order", "fieldtype": "Link", "options": "SIAGA Work Order", "width": 130},
		{"label": _("Sumber"), "fieldname": "trigger_source", "fieldtype": "Data", "width": 80},
		{"label": _("Skor Pemicu"), "fieldname": "score", "fieldtype": "Float", "precision": 1, "width": 95},
		{"label": _("Waktu Pemicu"), "fieldname": "scored_at", "fieldtype": "Datetime", "width": 150},
		{"label": _("Lead Time (jam)"), "fieldname": "lead_hours", "fieldtype": "Float", "precision": 1, "width": 115},
		{"label": _("Gejala Tebakan"), "fieldname": "predicted", "fieldtype": "Data", "width": 110},
		{"label": _("Label Sebenarnya"), "fieldname": "training_label", "fieldtype": "Data", "width": 110},
		{"label": _("Cocok"), "fieldname": "match", "fieldtype": "Data", "width": 70},
	]

	conditions = {"work_order": ["!=", ""]}
	if filters.get("asset"):
		conditions["asset"] = filters["asset"]
	if filters.get("from_date"):
		conditions["failed_on"] = [">=", filters["from_date"]]

	logs = frappe.get_all(
		"Failure Log", filters=conditions,
		fields=["name", "asset", "failed_on", "failure_mode", "training_label", "work_order"],
		order_by="failed_on desc",
	)

	rows = []
	for log in logs:
		wo = frappe.db.get_value(
			"SIAGA Work Order", log.work_order,
			["trigger_source", "health_score", "asset_name"], as_dict=True,
		) or {}
		hs = None
		if wo.get("health_score"):
			hs = frappe.db.get_value(
				"Health Score", wo["health_score"], ["score", "scored_at", "top_features"], as_dict=True,
			)
		predicted = None
		lead = None
		if hs:
			try:
				predicted = (json.loads(hs.top_features or "{}") or {}).get("symptom")
			except ValueError:
				predicted = None
			if hs.scored_at and log.failed_on:
				lead = (get_datetime(log.failed_on) - get_datetime(hs.scored_at)).total_seconds() / 3600.0

		match = None
		if predicted and log.training_label:
			if predicted == log.training_label:
				match = _("Ya")
			elif predicted == "broadband":
				match = _("Umum")  # sistem tidak menebak spesifik, jadi tidak salah tapi tidak menunjuk
			else:
				match = _("Tidak")

		rows.append({
			"failure_log": log.name,
			"asset_name": wo.get("asset_name") or log.asset,
			"failed_on": log.failed_on,
			"failure_mode": log.failure_mode,
			"work_order": log.work_order,
			"trigger_source": wo.get("trigger_source"),
			"score": hs.score if hs else None,
			"scored_at": hs.scored_at if hs else None,
			"lead_hours": round(lead, 1) if lead is not None else None,
			"predicted": predicted,
			"training_label": log.training_label,
			"match": match,
		})

	summary = []
	leads = [r["lead_hours"] for r in rows if r["lead_hours"] is not None]
	if leads:
		summary.append({"label": _("Kejadian dengan pemicu otomatis"), "value": len(leads), "indicator": "blue"})
		summary.append({"label": _("Lead time median (jam)"), "value": round(sorted(leads)[len(leads) // 2], 1), "indicator": "green"})
		exact = sum(1 for r in rows if r["match"] == _("Ya"))
		summary.append({"label": _("Gejala tepat"), "value": "%d / %d" % (exact, len(rows)), "indicator": "orange"})

	return columns, rows, None, None, summary
