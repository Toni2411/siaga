# Copyright (c) 2026, SIAGA and contributors
# For license information, please see license.txt

from math import cos, radians

import frappe
from frappe import _
from frappe.model.document import Document


class AssetClass(Document):
	def validate(self):
		self.validate_thresholds()
		self.compute_defect_frequencies()

	def validate_thresholds(self):
		if self.threshold_recover <= self.threshold_trigger:
			frappe.throw(
				_("Ambang Pulih ({0}) harus lebih tinggi dari Ambang Pemicu ({1}), supaya histeresis bekerja").format(
					self.threshold_recover, self.threshold_trigger
				)
			)
		if self.consecutive_cycles < 1:
			frappe.throw(_("Siklus Berturut-turut minimal 1"))

	def compute_defect_frequencies(self):
		"""Turunkan frekuensi cacat bearing dari geometri.

		Rumusnya sama persis dengan services/edge/siaga_edge/config.py. Kalau
		salah satu diubah, yang lain harus ikut, karena edge memakai angka ini
		untuk memilih pita frekuensi yang diukur.
		"""
		if not (self.rolling_elements and self.ball_diameter_mm and self.pitch_diameter_mm):
			self.bpfo_hz = self.bpfi_hz = self.bsf_hz = self.ftf_hz = 0
			return

		shaft_hz = (self.rpm_nominal or 0) / 60.0
		ratio = (self.ball_diameter_mm / self.pitch_diameter_mm) * cos(radians(self.contact_angle_deg or 0))
		n = self.rolling_elements

		self.ftf_hz = 0.5 * shaft_hz * (1.0 - ratio)
		self.bpfo_hz = 0.5 * n * shaft_hz * (1.0 - ratio)
		self.bpfi_hz = 0.5 * n * shaft_hz * (1.0 + ratio)
		self.bsf_hz = 0.5 * (self.pitch_diameter_mm / self.ball_diameter_mm) * shaft_hz * (1.0 - ratio * ratio)

		nyquist = (self.sample_rate_hz or 0) / 2.0
		if nyquist and max(self.bpfo_hz, self.bpfi_hz) * 2 >= nyquist:
			frappe.msgprint(
				_("Harmonisa kedua frekuensi cacat ({0} Hz) melewati Nyquist ({1} Hz). Naikkan laju cuplik atau terima bahwa harmonisa tidak terbaca.").format(
					round(max(self.bpfo_hz, self.bpfi_hz) * 2, 1), round(nyquist, 1)
				),
				indicator="orange",
			)
