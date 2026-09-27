# Copyright (c) 2026, SIAGA and contributors
# For license information, please see license.txt

"""Utilitas demo: mengembalikan rantai otomasi ke titik awal.

Dipanggil lewat bench execute siaga.demo.reset_automation. Hanya menyentuh
dokumen yang dibuat otomatis oleh SIAGA; work order manual, stok, dan master
data dibiarkan.
"""

import frappe

# Stok awal data demo, sama dengan yang dibuat bootstrap. Tiap putaran demo
# mengeluarkan part dari gudang saat work order ditutup, jadi tanpa pengisian
# ulang putaran berikutnya gagal di tengah jalan dengan stok kosong.
DEMO_STOCK = {"BRG-ZA-2115": 2, "SEAL-MEK-100": 3}


def restock(targets=None):
	"""Kembalikan stok part demo ke jumlah awal lewat Material Receipt."""
	targets = targets or DEMO_STOCK
	warehouse = frappe.db.get_value("Warehouse", {"warehouse_name": "Gudang Site A"}, "name")
	if not warehouse:
		print("gudang demo tidak ada, pengisian stok dilewati")
		return None
	company = frappe.db.get_value("Warehouse", warehouse, "company")
	items = []
	for item, target in targets.items():
		if not frappe.db.exists("Item", item):
			continue
		actual = frappe.db.get_value("Bin", {"item_code": item, "warehouse": warehouse}, "actual_qty") or 0
		missing = target - actual
		if missing > 0:
			rate = frappe.db.get_value("Item", item, "valuation_rate") or 1
			items.append({"item_code": item, "qty": missing, "basic_rate": rate, "t_warehouse": warehouse})
	if not items:
		print("stok demo sudah sesuai, tidak perlu diisi")
		return None
	se = frappe.get_doc({
		"doctype": "Stock Entry", "stock_entry_type": "Material Receipt",
		"company": company, "to_warehouse": warehouse, "items": items,
	})
	se.insert(ignore_permissions=True)
	se.submit()
	frappe.db.commit()
	print("stok demo diisi ulang lewat %s: %s" % (se.name, ", ".join("%s +%g" % (i["item_code"], i["qty"]) for i in items)))
	return se.name


def reset_automation():
	# Termasuk yang sudah Selesai: laporan ketersediaan dan lead time membaca
	# work order yang masih tersubmit, jadi putaran demo sebelumnya harus
	# ikut dibatalkan supaya jam perbaikannya tidak menumpuk.
	cancelled = 0
	for name in frappe.get_all(
		"SIAGA Work Order", filters={"trigger_source": "Otomatis", "docstatus": 1}, pluck="name",
	):
		frappe.get_doc("SIAGA Work Order", name).cancel()
		cancelled += 1

	deleted = 0
	for name in frappe.get_all("Material Request", filters={"siaga_auto": 1, "docstatus": 0}, pluck="name"):
		# Work order yang merujuk MR ini (termasuk yang sudah dibatalkan) harus
		# dilepas dulu; Frappe menolak menghapus dokumen yang masih ditautkan.
		for wo in frappe.get_all("SIAGA Work Order", filters={"material_request": name}, pluck="name"):
			frappe.db.set_value("SIAGA Work Order", wo, "material_request", None, update_modified=False)
		frappe.delete_doc("Material Request", name, ignore_permissions=True)
		deleted += 1

	# Catatan kerusakan dari work order otomatis putaran lama ikut dibuang:
	# skor pemicunya sudah tidak ada setelah reset pemantauan.
	auto_wos = frappe.get_all("SIAGA Work Order", filters={"trigger_source": "Otomatis"}, pluck="name")
	logs = frappe.get_all("Failure Log", filters={"work_order": ["in", auto_wos]}, pluck="name") if auto_wos else []
	for name in logs:
		for wo in frappe.get_all("SIAGA Work Order", filters={"failure_log": name}, pluck="name"):
			frappe.db.set_value("SIAGA Work Order", wo, "failure_log", None, update_modified=False)
		frappe.delete_doc("Failure Log", name, ignore_permissions=True, force=True)

	notifications = frappe.db.count("Notification Log", {"document_type": "SIAGA Work Order"})
	frappe.db.delete("Notification Log", {"document_type": "SIAGA Work Order"})

	frappe.db.sql("update `tabAsset Monitoring Profile` set alarm_state='Normal', alarm_since=NULL, last_auto_work_order=NULL")
	frappe.db.sql("update `tabTelegram Chat` set pending=NULL")

	# Komponen yang ditandai Diganti saat work order ditutup dikembalikan ke
	# Terpasang. Tanpa ini, putaran demo berikutnya tidak menemukan komponen
	# terpasang untuk dicantumkan di work order, dan kolom komponen jadi kosong.
	restored = frappe.db.count("Asset Component", {"status": "Diganti"})
	frappe.db.sql("update `tabAsset Component` set status = 'Terpasang', replaced_on = NULL where status = 'Diganti'")
	frappe.db.commit()
	restock()
	print("komponen dikembalikan ke Terpasang: %d" % restored)
	print("work order otomatis dibatalkan: %d | draft MR dihapus: %d | catatan kerusakan dihapus: %d | notifikasi dihapus: %d" % (cancelled, deleted, len(logs), notifications))


# Jeda yang dipakai saat menutup work order demo. Dataset IMS merekam rig yang
# berjalan sampai bearing gagal; tidak ada peristiwa perbaikan di dalamnya, jadi
# lama respons dan lama perbaikan di bawah ini adalah angka ilustrasi yang
# masuk akal untuk site tambang, bukan hasil pengukuran. Disebut terang terangan
# di laporan Ketersediaan Alat dan di README.
RESPONSE_HOURS = 2.0
REPAIR_HOURS = 3.5


def last_reading(asset):
	"""Cap waktu cuplikan terakhir aset ini, yaitu saat rig berhenti di dataset."""
	from siaga.api.timeseries import timescale, to_site_tz

	source = frappe.db.get_value("Asset Monitoring Profile", {"asset": asset}, "data_source_id")
	if not source:
		return None
	try:
		with timescale() as conn, conn.cursor() as cur:
			cur.execute("select max(ts) from operating_state where source_id = %s", (source,))
			row = cur.fetchone()
			return to_site_tz(row[0]) if row and row[0] else None
	except Exception:
		return None


def close_alarm_work_order(asset_name=None, failure_mode="Bearing outer race", notes=None):
	"""Tutup satu work order alarm seperti mekanik menutupnya di lapangan.

	Dipakai untuk menyiapkan demo: tanpa satu pun pekerjaan yang selesai,
	laporan Lead Time Deteksi dan Ketersediaan Alat tidak punya apa apa untuk
	dihitung, karena keduanya bertumpu pada catatan mekanik.

	Mode kerusakan bawaan mengikuti readme dataset IMS set 2: bearing 1 gagal
	di outer race. Unit 01 di demo adalah kanal bearing itu.
	"""
	from frappe.utils import add_to_date, now_datetime

	filters = {"trigger_source": "Otomatis", "docstatus": 1, "status": ["in", ("Terbuka", "Dikerjakan")]}
	if asset_name:
		filters["asset_name"] = asset_name
	wo_name = frappe.db.get_value("SIAGA Work Order", filters, "name", order_by="creation asc")
	if not wo_name:
		print("tidak ada work order alarm yang terbuka, dilewati")
		return None

	wo = frappe.get_doc("SIAGA Work Order", wo_name)
	# Kerusakan terjadi saat rig berhenti, yaitu di ujung rekaman dataset —
	# bukan saat alarm berbunyi. Selisih keduanya itulah lead time yang
	# dilaporkan, jadi cap waktu ini tidak boleh diambil dari skor pemicu.
	failed_on = last_reading(wo.asset) or now_datetime()

	wo.start_work()
	wo.complete_work(
		notes=notes or "Bearing sisi kopling diganti, getaran kembali normal setelah uji jalan.",
		failure_mode=failure_mode,
		component_replaced=1,
		failed_on=failed_on,
	)
	# Cap waktu pekerjaan dirapikan ke jeda yang masuk akal: mekanik berangkat
	# dua jam setelah alarm, perbaikan tiga setengah jam.
	started = add_to_date(failed_on, hours=RESPONSE_HOURS)
	wo.db_set({"started_on": started, "completed_on": add_to_date(started, hours=REPAIR_HOURS)})
	frappe.db.commit()
	print("work order %s (%s) ditutup: %s, mulai %s, selesai %s" % (
		wo.name, wo.asset_name, failure_mode, started, add_to_date(started, hours=REPAIR_HOURS)))
	return wo.name
