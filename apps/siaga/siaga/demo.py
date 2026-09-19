# Copyright (c) 2026, SIAGA and contributors
# For license information, please see license.txt

"""Utilitas demo: mengembalikan rantai otomasi ke titik awal.

Dipanggil lewat bench execute siaga.demo.reset_automation. Hanya menyentuh
dokumen yang dibuat otomatis oleh SIAGA; work order manual, stok, dan master
data dibiarkan.
"""

import frappe


def reset_automation():
	cancelled = 0
	for name in frappe.get_all(
		"SIAGA Work Order",
		filters={"trigger_source": "Otomatis", "docstatus": 1, "status": ["in", ("Terbuka", "Dikerjakan")]},
		pluck="name",
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
	frappe.db.commit()
	print("work order otomatis dibatalkan: %d | draft MR dihapus: %d | catatan kerusakan dihapus: %d | notifikasi dihapus: %d" % (cancelled, deleted, len(logs), notifications))
