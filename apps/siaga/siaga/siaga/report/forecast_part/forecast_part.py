# Copyright (c) 2026, SIAGA and contributors
# For license information, please see license.txt

"""Kebutuhan part beberapa hari ke depan, dari kondisi alat.

Tiap baris satu item di satu gudang: stok fisik, yang terkunci untuk work
order terbuka, yang diproyeksikan dari unit yang sedang menurun, dan sebagai
pembanding rata-rata pemakaian historis yang dipakai cara lama. Kolom saran
memberi tahu berapa yang perlu dipesan supaya stok setelah semua kebutuhan
tidak jatuh di bawah titik pesan ulang.
"""

import frappe
from frappe import _

from siaga import forecast


def execute(filters=None):
	filters = filters or {}
	columns = [
		{"label": _("Item"), "fieldname": "item", "fieldtype": "Link", "options": "Item", "width": 130},
		{"label": _("Nama"), "fieldname": "item_name", "fieldtype": "Data", "width": 190},
		{"label": _("Gudang"), "fieldname": "warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 150},
		{"label": _("Fisik"), "fieldname": "actual_qty", "fieldtype": "Float", "precision": 0, "width": 70},
		{"label": _("Terkunci WO"), "fieldname": "locked_qty", "fieldtype": "Float", "precision": 0, "width": 100},
		{"label": _("Tersedia"), "fieldname": "available_qty", "fieldtype": "Float", "precision": 0, "width": 85},
		{"label": _("Proyeksi Kondisi"), "fieldname": "projected_qty", "fieldtype": "Float", "precision": 0, "width": 120},
		{"label": _("Paling Cepat (hari)"), "fieldname": "earliest_days", "fieldtype": "Float", "precision": 1, "width": 130},
		{"label": _("Unit Menurun"), "fieldname": "projected_units", "fieldtype": "Data", "width": 260},
		{"label": _("Sisa Setelah Proyeksi"), "fieldname": "projected_after", "fieldtype": "Float", "precision": 0, "width": 150},
		{"label": _("Titik Pesan"), "fieldname": "reorder_level", "fieldtype": "Float", "precision": 0, "width": 95},
		{"label": _("Draft MR Menunggu"), "fieldname": "pending_mr_qty", "fieldtype": "Float", "precision": 0, "width": 130},
		{"label": _("Saran"), "fieldname": "advice", "fieldtype": "Data", "width": 130},
		{"label": _("Historis / bulan"), "fieldname": "historical_monthly", "fieldtype": "Float", "precision": 2, "width": 120},
		{"label": _("Work Order Terbuka"), "fieldname": "committed_wos", "fieldtype": "Data", "width": 220},
	]
	rows = forecast.table(filters.get("horizon_days") or None, filters.get("warehouse") or None)
	return columns, rows
