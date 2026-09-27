# Copyright (c) 2026, SIAGA and contributors
# For license information, please see license.txt

"""PA, UA, MTBF, dan MTTR per unit — bahasa yang dipakai rapat pagi site.

Jam operasi datang dari status operasi yang dikirim edge tiap cuplikan, bukan
dari lembar shift yang diisi tangan. Jam perbaikan datang dari work order,
dan jumlah kerusakan dari catatan mekanik saat menutupnya.
"""

import frappe
from frappe import _

from siaga import availability


def execute(filters=None):
	filters = filters or {}
	if not filters.get("from_date") or not filters.get("to_date"):
		frappe.throw(_("Isi rentang waktunya dulu"))

	columns = [
		{"label": _("Aset"), "fieldname": "asset", "fieldtype": "Link", "options": "Asset", "width": 130},
		{"label": _("Nama"), "fieldname": "asset_name", "fieldtype": "Data", "width": 200},
		{"label": _("Jam Kalender"), "fieldname": "calendar_hours", "fieldtype": "Float", "precision": 1, "width": 110},
		{"label": _("Jam Operasi"), "fieldname": "operating_hours", "fieldtype": "Float", "precision": 1, "width": 105},
		{"label": _("Jam Perbaikan"), "fieldname": "repair_hours", "fieldtype": "Float", "precision": 1, "width": 115},
		{"label": _("Jam Tersedia"), "fieldname": "available_hours", "fieldtype": "Float", "precision": 1, "width": 110},
		{"label": _("PA %"), "fieldname": "pa", "fieldtype": "Float", "precision": 1, "width": 80},
		{"label": _("UA %"), "fieldname": "ua", "fieldtype": "Float", "precision": 1, "width": 80},
		{"label": _("MA %"), "fieldname": "ma", "fieldtype": "Float", "precision": 1, "width": 80},
		{"label": _("Kerusakan"), "fieldname": "failures", "fieldtype": "Int", "width": 90},
		{"label": _("MTBF (jam)"), "fieldname": "mtbf", "fieldtype": "Float", "precision": 1, "width": 100},
		{"label": _("Perbaikan"), "fieldname": "repairs", "fieldtype": "Int", "width": 90},
		{"label": _("MTTR (jam)"), "fieldname": "mttr", "fieldtype": "Float", "precision": 1, "width": 100},
	]

	rows = availability.table(filters["from_date"], filters["to_date"], filters.get("asset"))
	return columns, rows, message(rows)


def message(rows):
	"""Catatan di atas tabel: dari mana angkanya, dan apa yang belum dihitung."""
	sedikit = [r.asset_name for r in rows if r.failures and r.failures < 3]
	bentrok = [r.asset_name for r in rows if r.operating_capped]
	catatan = [
		_("Jam operasi dihitung dari status operasi yang dikirim edge tiap cuplikan, bukan dari entri manual."),
		_("Seluruh downtime di sini bersifat korektif; servis berkala belum ada di data demo, dan pada armada sungguhan keduanya dipisah."),
	]
	if sedikit:
		catatan.append(_("MTBF pada {0} dihitung dari kurang dari tiga kerusakan, jadi belum berarti secara statistik.").format(", ".join(sedikit)))
	if bentrok:
		catatan.append(_("Pada {0} sensor masih menyatakan alat berjalan selama jam perbaikan; jam operasi dibatasi pada jam tersedia.").format(", ".join(bentrok)))
	return "<br>".join("• " + c for c in catatan)
