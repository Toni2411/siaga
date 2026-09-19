# Copyright (c) 2026, SIAGA and contributors
# For license information, please see license.txt

"""Dari skor ke work order: aturan pemicu, histeresis, peredam duplikasi, stok."""

import frappe

from siaga import stock
from siaga.tests.fixtures import SiagaTestCase, auto_material_requests, make_env, open_auto_work_orders, score


class TestAutomation(SiagaTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.env = make_env("UJI-A")

	def profile(self, *fields):
		return frappe.db.get_value("Asset Monitoring Profile", self.env.profile, list(fields), as_dict=True)

	def test_three_low_scores_open_one_work_order_with_reservation(self):
		e = self.env
		score(e.asset, 35, minutes_ago=30)
		score(e.asset, 33, minutes_ago=20)
		self.assertEqual(open_auto_work_orders(e.asset), [], "dua siklus belum boleh memicu")

		score(e.asset, 30, minutes_ago=10)
		wos = open_auto_work_orders(e.asset)
		self.assertEqual(len(wos), 1)
		wo = frappe.get_doc("SIAGA Work Order", wos[0])
		self.assertEqual(wo.status, "Terbuka")
		self.assertEqual(wo.priority, "Tinggi")
		self.assertEqual(wo.component, e.component, "komponen diambil dari part kandidat gejala")
		self.assertEqual([(p.item, p.qty) for p in wo.parts], [(e.item, 1)])

		p = self.profile("alarm_state", "last_auto_work_order")
		self.assertEqual(p.alarm_state, "Alarm")
		self.assertEqual(p.last_auto_work_order, wo.name)

		# Part dikunci: stok tersedia turun dari 2 ke 1, di bawah titik pesan ulang → satu draft MR.
		self.assertEqual(stock.available_qty(e.item, e.warehouse), 1)
		mrs = auto_material_requests(e.item, e.warehouse)
		self.assertEqual(len(mrs), 1)
		self.assertEqual(wo.material_request, mrs[0])
		self.assertIn(wo.name, frappe.db.get_value("Material Request", mrs[0], "siaga_reason"))

		# Skor rendah berikutnya selama Alarm tidak melahirkan work order kedua.
		score(e.asset, 20, minutes_ago=5)
		score(e.asset, 10, minutes_ago=4)
		score(e.asset, 5, minutes_ago=3)
		self.assertEqual(open_auto_work_orders(e.asset), [wo.name])
		self.assertEqual(len(auto_material_requests(e.item, e.warehouse)), 1)

	def test_hysteresis_recovers_only_above_recover_threshold(self):
		e = self.env
		for m, v in ((30, 30), (20, 30), (10, 30)):
			score(e.asset, v, minutes_ago=m)
		self.assertEqual(self.profile("alarm_state").alarm_state, "Alarm")

		score(e.asset, 48, minutes_ago=5)  # di atas pemicu, di bawah pulih
		self.assertEqual(self.profile("alarm_state").alarm_state, "Alarm", "48 belum melewati ambang pulih 55")

		score(e.asset, 60, minutes_ago=4)
		self.assertEqual(self.profile("alarm_state").alarm_state, "Normal")

	def test_unstable_operating_state_is_ignored(self):
		e = self.env
		for m in (30, 20, 10):
			score(e.asset, 5, minutes_ago=m, operating_state="mati")
		self.assertEqual(open_auto_work_orders(e.asset), [])
		self.assertEqual(self.profile("alarm_state").alarm_state, "Normal")

	def test_critical_priority_below_twenty(self):
		e = self.env
		for m in (30, 20, 10):
			score(e.asset, 15, minutes_ago=m)
		wo = frappe.get_doc("SIAGA Work Order", open_auto_work_orders(e.asset)[0])
		self.assertEqual(wo.priority, "Kritis")
		self.assertEqual(wo.health_score and frappe.db.get_value("Health Score", wo.health_score, "work_order"), wo.name)

	def test_notification_reaches_maintenance_managers(self):
		e = self.env
		for m in (30, 20, 10):
			score(e.asset, 30, minutes_ago=m)
		wo = open_auto_work_orders(e.asset)[0]
		managers = [u for u in frappe.get_all("Has Role", filters={"role": "Maintenance Manager", "parenttype": "User"}, pluck="parent")
		            if u not in ("Administrator", "Guest") and not u.startswith("siaga-bot") and frappe.db.get_value("User", u, "enabled")]
		logs = frappe.get_all("Notification Log", filters={"document_type": "SIAGA Work Order", "document_name": wo}, pluck="for_user")
		self.assertEqual(sorted(set(logs)), sorted(set(managers)))
