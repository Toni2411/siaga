# Copyright (c) 2026, SIAGA and contributors
# For license information, please see license.txt

"""Siklus hidup work order: reservasi, penutupan, label pelatihan, pembatalan."""

import frappe

from siaga import stock
from siaga.tests.fixtures import SiagaTestCase, make_env, make_work_order


class TestWorkOrder(SiagaTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.env = make_env("UJI-W", stock_qty=3)

	def test_submit_reserves_and_complete_issues_stock_with_failure_label(self):
		e = self.env
		before = stock.actual_qty(e.item, e.warehouse)
		wo = make_work_order(e, component=e.component)
		self.assertEqual(wo.status, "Terbuka")
		self.assertEqual(stock.active_reserved_qty(e.item, e.warehouse), 1)
		self.assertEqual(stock.available_qty(e.item, e.warehouse), before - 1)

		wo.start_work()
		self.assertEqual(wo.status, "Dikerjakan")
		self.assertIsNotNone(wo.started_on)

		wo.complete_work(notes="bearing diganti", failure_mode="Bearing outer race", component_replaced=1)
		wo.reload()
		self.assertEqual(wo.status, "Selesai")
		self.assertEqual(wo.completion_notes, "bearing diganti")
		self.assertEqual(stock.active_reserved_qty(e.item, e.warehouse), 0, "reservasi berubah jadi Dipakai")
		self.assertEqual(stock.actual_qty(e.item, e.warehouse), before - 1, "part dikeluarkan dari gudang")

		log = frappe.get_doc("Failure Log", wo.failure_log)
		self.assertEqual(log.failure_mode, "Bearing outer race")
		self.assertEqual(log.training_label, "bpfo")
		self.assertEqual(log.work_order, wo.name)
		self.assertTrue(log.confirmed_by_mechanic)
		self.assertEqual(frappe.db.get_value("Asset Component", e.component, "status"), "Diganti")

	def test_complete_without_failure_mode_writes_no_log(self):
		wo = make_work_order(self.env)
		wo.complete_work()
		wo.reload()
		self.assertEqual(wo.status, "Selesai")
		self.assertFalse(wo.failure_log)

	def test_cancel_releases_reservation(self):
		e = self.env
		wo = make_work_order(e)
		self.assertEqual(stock.active_reserved_qty(e.item, e.warehouse), 1)
		wo.cancel()
		self.assertEqual(stock.active_reserved_qty(e.item, e.warehouse), 0)
		self.assertEqual(frappe.db.get_value("SIAGA Work Order", wo.name, "status"), "Dibatalkan")

	def test_duplicate_open_auto_work_order_is_rejected(self):
		e = self.env
		first = make_work_order(e, trigger_source="Otomatis", component=e.component)
		with self.assertRaises(frappe.ValidationError):
			make_work_order(e, trigger_source="Otomatis", component=e.component)
		first.cancel()
		# Manual hanya diperingatkan, tidak ditolak.
		a = make_work_order(e, trigger_source="Manual", component=e.component)
		b = make_work_order(e, trigger_source="Manual", component=e.component)
		self.assertTrue(a.name and b.name)

	def test_cannot_complete_twice(self):
		wo = make_work_order(self.env)
		wo.complete_work()
		with self.assertRaises(frappe.ValidationError):
			wo.complete_work()
