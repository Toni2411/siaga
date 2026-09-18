# Copyright (c) 2026, SIAGA and contributors
# For license information, please see license.txt

"""Reservasi spare part dan titik pesan ulang.

Stock Reservation Entry bawaan v15 terikat ke Sales Order, jadi SIAGA memakai
DocType Part Reservation sendiri. Stok yang "tersedia" bagi work order baru
adalah stok aktual di Bin dikurangi reservasi aktif work order lain.

Material Request dibuat langsung di sini, bukan menunggu scheduler reorder
bawaan, karena scheduler itu membaca projected_qty di Bin yang tidak tahu apa
apa soal reservasi SIAGA, dan karena rantai tujuh langkah harus selesai dalam
hitungan detik, bukan menunggu jadwal harian.
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, now_datetime, nowdate


def actual_qty(item, warehouse):
	return flt(frappe.db.get_value("Bin", {"item_code": item, "warehouse": warehouse}, "actual_qty"))


def active_reserved_qty(item, warehouse, exclude_work_order=None):
	filters = {"item": item, "warehouse": warehouse, "status": "Aktif"}
	if exclude_work_order:
		filters["work_order"] = ["!=", exclude_work_order]
	rows = frappe.get_all("Part Reservation", filters=filters, fields=["sum(qty) as qty"])
	return flt(rows[0].qty) if rows else 0.0


def available_qty(item, warehouse, exclude_work_order=None):
	return actual_qty(item, warehouse) - active_reserved_qty(item, warehouse, exclude_work_order)


def reorder_level(item, warehouse):
	"""Ambil (level, qty pesan) dari child table Item Reorder untuk gudang ini."""
	row = frappe.db.get_value(
		"Item Reorder",
		{"parent": item, "warehouse": warehouse},
		["warehouse_reorder_level", "warehouse_reorder_qty", "material_request_type"],
		as_dict=True,
	)
	return row


def reserve(work_order, item, warehouse, qty):
	doc = frappe.get_doc({
		"doctype": "Part Reservation",
		"work_order": work_order,
		"item": item,
		"warehouse": warehouse,
		"qty": qty,
		"status": "Aktif",
		"reserved_on": now_datetime(),
	})
	doc.insert(ignore_permissions=True)
	return doc


def release(work_order, new_status="Dilepas"):
	"""Ubah semua reservasi aktif satu work order jadi Dilepas atau Dipakai."""
	names = frappe.get_all("Part Reservation", filters={"work_order": work_order, "status": "Aktif"}, pluck="name")
	for name in names:
		frappe.db.set_value("Part Reservation", name, {"status": new_status, "released_on": now_datetime()})
	return names


def open_auto_material_request(item, warehouse):
	"""Draft Material Request buatan SIAGA yang masih terbuka untuk item dan gudang ini."""
	return frappe.db.sql(
		"""
		select mr.name from `tabMaterial Request` mr
		join `tabMaterial Request Item` mri on mri.parent = mr.name
		where mr.docstatus = 0 and mr.siaga_auto = 1
		  and mri.item_code = %s and mri.warehouse = %s
		limit 1
		""",
		(item, warehouse),
	)


def ensure_material_request(item, warehouse, qty, company, work_order=None):
	"""Terbitkan draft Material Request kalau belum ada yang terbuka.

	Satu draft per item per gudang. Kalau sudah ada, kembalikan yang ada,
	supaya sepuluh work order untuk part yang sama tidak melahirkan sepuluh
	permintaan pembelian.
	"""
	existing = open_auto_material_request(item, warehouse)
	if existing:
		return existing[0][0], False

	mr = frappe.get_doc({
		"doctype": "Material Request",
		"material_request_type": "Purchase",
		"company": company,
		"transaction_date": nowdate(),
		"schedule_date": add_days(nowdate(), 7),
		"set_warehouse": warehouse,
		"siaga_auto": 1,
		"siaga_work_order": work_order,
		"items": [{
			"item_code": item,
			"qty": qty,
			"warehouse": warehouse,
			"schedule_date": add_days(nowdate(), 7),
		}],
	})
	mr.insert(ignore_permissions=True)
	return mr.name, True


def check_reorder(item, warehouse, company, work_order=None):
	"""Kalau stok setelah reservasi jatuh di bawah titik pesan ulang, buat MR.

	Mengembalikan (nama MR atau None, baru dibuat atau tidak).
	"""
	level = reorder_level(item, warehouse)
	if not level:
		return None, False
	remaining = available_qty(item, warehouse)
	if remaining >= flt(level.warehouse_reorder_level):
		return None, False
	qty = max(flt(level.warehouse_reorder_qty), flt(level.warehouse_reorder_level) - remaining)
	return ensure_material_request(item, warehouse, qty, company, work_order)


def issue_stock(work_order_doc, remarks=None):
	"""Keluarkan part yang direservasi dari gudang lewat Stock Entry Material Issue.

	Dipanggil saat work order selesai. Ini yang benar benar mengurangi stok;
	reservasi hanya menjanjikan.
	"""
	reservations = frappe.get_all(
		"Part Reservation",
		filters={"work_order": work_order_doc.name, "status": "Aktif"},
		fields=["item", "warehouse", "qty"],
	)
	if not reservations:
		return None
	company = frappe.db.get_value("Asset", work_order_doc.asset, "company")
	se = frappe.get_doc({
		"doctype": "Stock Entry",
		"stock_entry_type": "Material Issue",
		"company": company,
		"remarks": remarks or _("Pemakaian part untuk {0}").format(work_order_doc.name),
		"items": [{
			"item_code": r.item,
			"qty": r.qty,
			"s_warehouse": r.warehouse,
		} for r in reservations],
	})
	se.insert(ignore_permissions=True)
	se.submit()
	return se.name
