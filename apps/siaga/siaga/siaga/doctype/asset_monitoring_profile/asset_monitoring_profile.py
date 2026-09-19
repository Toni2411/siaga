# Copyright (c) 2026, SIAGA and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class AssetMonitoringProfile(Document):
	@frappe.whitelist()
	def restart_baseline(self):
		"""Kumpulkan baseline baru, misalnya setelah komponen diganti.

		Model lama tidak berlaku lagi karena "seperti apa rasanya saat sehat"
		sudah berubah bersama komponennya. AI service akan melatih model baru
		setelah baseline_days data sehat terkumpul sejak sekarang, dan penanda
		skor terakhir tidak mundur sehingga riwayat lama tidak dinilai ulang.
		"""
		self.db_set({
			"monitoring_status": "Mengumpulkan baseline",
			"baseline_started_on": now_datetime(),
			"baseline_completed_on": None,
			"model_version": None,
			"model_trained_on": None,
			"alarm_state": "Normal",
			"alarm_since": None,
		})
		frappe.msgprint(_("Baseline dikumpulkan ulang sejak sekarang; model per unit akan dilatih ulang."), alert=True)
		return self.monitoring_status
