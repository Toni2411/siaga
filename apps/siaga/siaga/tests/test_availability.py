# Copyright (c) 2026, SIAGA and contributors
# For license information, please see license.txt

"""Ketersediaan alat: jam perbaikan dipotong di batas jendela, PA/UA/MTBF/MTTR."""

import frappe
from frappe.utils import add_to_date, get_datetime

from siaga import availability
from siaga.tests.fixtures import SiagaTestCase, make_env, make_work_order


class TestAvailability(SiagaTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.env = make_env("UJI-V", stock_qty=5)

	def setUp(self):
		super().setUp()
		# Jam operasi datang dari Timescale yang tidak ada di lingkungan tes;
		# diganti nilai tetap supaya aritmetikanya yang diuji, bukan basis datanya.
		self._operating = availability.operating_hours
		availability.operating_hours = lambda source_id, start, end: 100.0

	def tearDown(self):
		availability.operating_hours = self._operating
		super().tearDown()

	def window(self, hours=168):
		end = get_datetime(frappe.utils.now_datetime())
		return add_to_date(end, hours=-hours), end

	def repaired(self, start_offset_h, end_offset_h):
		"""Work order yang dikerjakan dari sekian jam lalu sampai sekian jam lalu."""
		wo = make_work_order(self.env)
		now = get_datetime(frappe.utils.now_datetime())
		wo.db_set({
			"status": "Selesai",
			"started_on": add_to_date(now, hours=-start_offset_h),
			"completed_on": add_to_date(now, hours=-end_offset_h),
		})
		return wo

	def test_repair_hours_sums_completed_work(self):
		self.repaired(30, 26)  # 4 jam
		self.repaired(10, 8)   # 2 jam
		start, end = self.window()
		hours, count = availability.repair_hours(self.env.asset, start, end)
		self.assertAlmostEqual(hours, 6.0, places=2)
		self.assertEqual(count, 2)

	def test_repair_before_window_is_clipped_at_the_edge(self):
		"""Perbaikan yang mulai sebelum jendela hanya dihitung bagian di dalamnya,
		supaya laporan bulan ini tidak mewarisi downtime bulan lalu."""
		self.repaired(200, 164)  # mulai 200 jam lalu, selesai 164 jam lalu
		start, end = self.window(168)
		hours, count = availability.repair_hours(self.env.asset, start, end)
		self.assertAlmostEqual(hours, 4.0, places=2)  # hanya 168..164
		self.assertEqual(count, 1)

	def test_repair_entirely_outside_window_is_ignored(self):
		self.repaired(400, 390)
		start, end = self.window(168)
		hours, count = availability.repair_hours(self.env.asset, start, end)
		self.assertEqual((hours, count), (0.0, 0))

	def test_open_work_order_counts_until_now(self):
		wo = make_work_order(self.env)
		wo.db_set({"status": "Dikerjakan", "started_on": add_to_date(get_datetime(frappe.utils.now_datetime()), hours=-3)})
		start, end = self.window()
		hours, count = availability.repair_hours(self.env.asset, start, end)
		self.assertAlmostEqual(hours, 3.0, places=1)
		self.assertEqual(count, 1)

	def test_metrics_are_computed_from_hours_and_failures(self):
		e = self.env
		wo = self.repaired(10, 6)  # 4 jam perbaikan
		frappe.get_doc({
			"doctype": "Failure Log", "asset": e.asset, "component": e.component, "work_order": wo.name,
			"failed_on": add_to_date(get_datetime(frappe.utils.now_datetime()), hours=-10),
			"failure_mode": "Bearing outer race", "training_label": "bpfo", "confirmed_by_mechanic": 1,
		}).insert(ignore_permissions=True)

		availability.operating_hours = lambda source_id, start, end: 80.0
		start, end = self.window(100)
		row = availability.for_asset(e.asset, start, end)
		self.assertAlmostEqual(row.calendar_hours, 100.0, places=1)
		self.assertAlmostEqual(row.repair_hours, 4.0, places=2)
		self.assertAlmostEqual(row.available_hours, 96.0, places=2)
		self.assertAlmostEqual(row.pa, 96.0, places=1)              # 96 tersedia / 100 kalender
		self.assertAlmostEqual(row.ua, 80.0 / 96.0 * 100, places=1)  # 80 operasi / 96 tersedia
		self.assertAlmostEqual(row.ma, 80.0 / 84.0 * 100, places=1)  # 80 / (80 + 4 perbaikan)
		self.assertEqual((row.failures, row.repairs), (1, 1))
		self.assertAlmostEqual(row.mtbf, 80.0, places=1)            # 80 jam operasi / 1 kerusakan
		self.assertAlmostEqual(row.mttr, 4.0, places=2)
		self.assertFalse(row.operating_capped)

	def test_operating_hours_never_exceed_available_hours(self):
		"""Sensor bisa menyatakan alat berjalan selama jam perbaikan — di dataset
		demo rig memang tidak pernah berhenti. UA di atas 100% tidak punya arti,
		jadi jam operasi dibatasi pada jam tersedia dan ditandai."""
		self.repaired(10, 6)  # 4 jam perbaikan di dalam jendela
		availability.operating_hours = lambda source_id, start, end: 100.0
		start, end = self.window(100)
		row = availability.for_asset(self.env.asset, start, end)
		self.assertAlmostEqual(row.running_hours, 100.0, places=1)
		self.assertAlmostEqual(row.operating_hours, 96.0, places=1)
		self.assertAlmostEqual(row.ua, 100.0, places=1)
		self.assertTrue(row.operating_capped)

	def test_metrics_are_none_when_there_is_nothing_to_divide_by(self):
		start, end = self.window()
		row = availability.for_asset(self.env.asset, start, end)
		self.assertEqual(row.failures, 0)
		self.assertIsNone(row.mtbf, "tanpa kerusakan, MTBF tidak punya arti")
		self.assertIsNone(row.mttr)
		self.assertAlmostEqual(row.pa, 100.0, places=1)

	def test_missing_timescale_leaves_operating_columns_empty_not_broken(self):
		availability.operating_hours = lambda source_id, start, end: None
		start, end = self.window()
		row = availability.for_asset(self.env.asset, start, end)
		self.assertIsNone(row.operating_hours)
		self.assertIsNone(row.ua)
		self.assertIsNone(row.ma)
		self.assertIsNone(row.mtbf)
		self.assertIsNotNone(row.pa, "PA tetap bisa dihitung dari work order saja")

	def test_window_without_sensor_samples_reports_unknown_not_zero(self):
		"""Rentang di luar jangkauan data: UA 0% menyesatkan, harus kosong dan ditandai."""
		availability.operating_hours = lambda source_id, start, end: None
		start, end = self.window()
		row = availability.for_asset(self.env.asset, start, end)
		self.assertTrue(row.no_sensor_data)
		self.assertIsNone(row.operating_hours)
		self.assertIsNone(row.ua)
		self.assertIsNone(row.mtbf)
		self.assertAlmostEqual(row.pa, 100.0, places=1, msg="PA tetap terhitung dari work order")

	def test_table_lists_monitored_units_worst_first(self):
		self.repaired(20, 10)  # 10 jam downtime di unit uji
		start, end = self.window()
		rows = availability.table(start, end)
		self.assertTrue(rows)
		mine = next(r for r in rows if r.asset == self.env.asset)
		self.assertAlmostEqual(mine.repair_hours, 10.0, places=1)
		pas = [r.pa for r in rows if r.pa is not None]
		self.assertEqual(pas, sorted(pas), "urut dari ketersediaan terendah")
