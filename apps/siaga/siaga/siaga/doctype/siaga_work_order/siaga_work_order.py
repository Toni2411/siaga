# Copyright (c) 2026, SIAGA and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime

from siaga import stock

OPEN_STATUSES = ("Terbuka", "Dikerjakan")


class SIAGAWorkOrder(Document):
	def validate(self):
		self.fill_part_defaults()
		self.refresh_availability()
		self.check_duplicate_open_work_order()
		if self.docstatus == 0:
			self.status = "Draft"

	def fill_part_defaults(self):
		for row in self.parts:
			if not row.warehouse:
				row.warehouse = self.warehouse
			if not row.warehouse:
				frappe.throw(_("Baris part {0}: gudang belum diisi").format(row.idx))
			if flt(row.qty) <= 0:
				frappe.throw(_("Baris part {0}: jumlah harus lebih dari nol").format(row.idx))

	def refresh_availability(self):
		for row in self.parts:
			row.stock_available = stock.available_qty(row.item, row.warehouse, exclude_work_order=self.name)

	def check_duplicate_open_work_order(self):
		"""Satu work order terbuka per pasangan aset dan komponen.

		Untuk work order otomatis ini aturan keras, bagian dari peredam
		duplikasi. Untuk work order manual hanya peringatan, karena planner
		mungkin memang sengaja.
		"""
		if not self.component:
			return
		other = frappe.db.get_value(
			"SIAGA Work Order",
			{
				"asset": self.asset,
				"component": self.component,
				"status": ["in", OPEN_STATUSES],
				"name": ["!=", self.name],
			},
			"name",
		)
		if not other:
			return
		msg = _("Sudah ada work order terbuka {0} untuk komponen yang sama").format(other)
		if self.trigger_source == "Otomatis":
			frappe.throw(msg)
		frappe.msgprint(msg, indicator="orange", alert=True)

	def on_submit(self):
		company = frappe.db.get_value("Asset", self.asset, "company")
		self.db_set("status", "Terbuka")

		# Langkah 5: kunci part untuk work order ini.
		for row in self.parts:
			stock.reserve(self.name, row.item, row.warehouse, row.qty)

		# Langkah 6: kalau sisa stok jatuh di bawah titik pesan ulang, draft
		# Material Request terbit ke antrean procurement.
		created = []
		for row in self.parts:
			mr, is_new = stock.check_reorder(row.item, row.warehouse, company, work_order=self.name)
			if mr:
				created.append((row.item, mr, is_new))

		if created:
			self.db_set("material_request", created[0][1])
			for item, mr, is_new in created:
				if is_new:
					frappe.msgprint(
						_("Stok {0} jatuh di bawah titik pesan ulang. Draft Material Request {1} diterbitkan.").format(item, mr),
						indicator="orange", alert=True,
					)

	def on_cancel(self):
		stock.release(self.name, "Dilepas")
		self.db_set("status", "Dibatalkan")

	@frappe.whitelist()
	def start_work(self):
		self._require_status("Terbuka")
		self.db_set({"status": "Dikerjakan", "started_on": now_datetime()})
		return self.status

	@frappe.whitelist()
	def complete_work(self, notes=None):
		self._require_status("Terbuka", "Dikerjakan")
		stock_entry = stock.issue_stock(self, remarks=notes)
		stock.release(self.name, "Dipakai")
		values = {"status": "Selesai", "completed_on": now_datetime()}
		if notes:
			values["completion_notes"] = notes
		self.db_set(values)
		if stock_entry:
			frappe.msgprint(_("Part dikeluarkan dari gudang lewat {0}").format(stock_entry), alert=True)
		return self.status

	def _require_status(self, *allowed):
		if self.docstatus != 1:
			frappe.throw(_("Work order harus sudah submit"))
		if self.status not in allowed:
			frappe.throw(_("Tidak bisa dari status {0}").format(self.status))
