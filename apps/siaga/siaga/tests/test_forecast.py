# Copyright (c) 2026, SIAGA and contributors
# For license information, please see license.txt

"""Forecast part: proyeksi mantap, kebutuhan terproyeksi, draft MR sebelum alarm."""

import frappe

from siaga import forecast, stock
from siaga.tests.fixtures import SiagaTestCase, auto_material_requests, make_env, open_auto_work_orders, score


class TestForecast(SiagaTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.env = make_env("UJI-F")

	def test_projection_needs_three_cycles_entirely_within_horizon(self):
		e = self.env
		# Dua siklus rapat, satu longgar: batas atas 31 hari di luar horizon 14.
		score(e.asset, 78, minutes_ago=30, projection=(13, 8, 31))
		score(e.asset, 76, minutes_ago=20, projection=(12, 7, 13))
		score(e.asset, 74, minutes_ago=10, projection=(11, 7, 13))
		self.assertIsNone(forecast.steady_projection(e.asset, 14))
		self.assertEqual(auto_material_requests(e.item, e.warehouse), [], "belum boleh memesan")

		score(e.asset, 72, minutes_ago=5, projection=(10, 6, 12))
		hs = forecast.steady_projection(e.asset, 14)
		self.assertIsNotNone(hs)
		self.assertEqual(hs.score, 72)

	def test_steady_projection_orders_before_alarm_with_reason(self):
		e = self.env
		for m, d in ((30, (6, 4, 9)), (20, (5.5, 4, 9)), (10, (5, 3.8, 9))):
			score(e.asset, 70, minutes_ago=m, projection=d)

		needs = forecast.projected_needs()
		mine = [n for n in needs if n.asset == e.asset]
		self.assertEqual(len(mine), 1)
		self.assertEqual((mine[0].item, mine[0].qty, mine[0].warehouse), (e.item, 1, e.warehouse))

		# Stok 2, kebutuhan terproyeksi 1 → sisa 1 < titik pesan 2 → draft MR, tanpa work order.
		self.assertEqual(open_auto_work_orders(e.asset), [])
		mrs = auto_material_requests(e.item, e.warehouse)
		self.assertEqual(len(mrs), 1)
		reason = frappe.db.get_value("Material Request", mrs[0], "siaga_reason")
		self.assertIn(e.asset_name, reason)
		self.assertIn("sebelum alarm", reason)
		self.assertIsNone(frappe.db.get_value("Material Request", mrs[0], "siaga_work_order"))

		# Siklus berikutnya tidak melahirkan draft kedua.
		score(e.asset, 68, minutes_ago=5, projection=(4.5, 3.5, 8))
		self.assertEqual(len(auto_material_requests(e.item, e.warehouse)), 1)

		# Alarm datang: reservasi menemukan draft yang sudah ada, work order menautkannya.
		for m in (4, 3, 2):
			score(e.asset, 30, minutes_ago=m)
		wos = open_auto_work_orders(e.asset)
		self.assertEqual(len(wos), 1)
		self.assertEqual(frappe.db.get_value("SIAGA Work Order", wos[0], "material_request"), mrs[0])
		self.assertEqual(len(auto_material_requests(e.item, e.warehouse)), 1)

	def test_no_order_when_stock_covers_projected_need(self):
		e = self.env
		from siaga.tests.fixtures import receipt
		receipt(e.item, e.warehouse, 3, e.company)  # tersedia 5, kebutuhan 1, sisa 4 ≥ titik pesan 2
		for m in (30, 20, 10):
			score(e.asset, 70, minutes_ago=m, projection=(5, 4, 9))
		self.assertEqual(auto_material_requests(e.item, e.warehouse), [])

	def test_units_in_alarm_are_committed_not_projected(self):
		e = self.env
		for m in (30, 20, 10):
			score(e.asset, 30, minutes_ago=m, projection=(0, 0, 0.5))
		self.assertEqual(len(open_auto_work_orders(e.asset)), 1)
		self.assertEqual([n for n in forecast.projected_needs() if n.asset == e.asset], [])

		row = next(r for r in forecast.table(warehouse=e.warehouse) if r.item == e.item)
		self.assertEqual(row.locked_qty, 1)
		self.assertEqual(row.projected_qty, 0)
		self.assertEqual(row.available_qty, stock.available_qty(e.item, e.warehouse))

	def test_table_advice(self):
		e = self.env
		row = next(r for r in forecast.table(warehouse=e.warehouse) if r.item == e.item)
		self.assertEqual((row.actual_qty, row.locked_qty, row.projected_qty), (2, 0, 0))
		self.assertEqual(row.advice, "Cukup")

		for m in (30, 20, 10):
			score(e.asset, 70, minutes_ago=m, projection=(5, 4, 9))
		row = next(r for r in forecast.table(warehouse=e.warehouse) if r.item == e.item)
		self.assertEqual(row.projected_qty, 1)
		self.assertEqual(row.projected_after, 1)
		self.assertIn(e.asset_name, row.projected_units)
		self.assertEqual(row.pending_mr_qty, 4)
		self.assertEqual(row.advice, "Draft MR menunggu")
