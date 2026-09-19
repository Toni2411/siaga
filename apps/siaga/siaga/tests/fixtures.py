# Copyright (c) 2026, SIAGA and contributors
# For license information, please see license.txt

"""Data uji untuk tes app: satu kelas alat, satu unit, satu gudang, satu part.

Dibuat di dalam transaksi tes (FrappeTestCase menggulung balik semuanya
setelah kelas tes selesai), memakai perusahaan default site. Namanya diberi
awalan supaya tidak bertabrakan dengan data demo.

Jalankan:
    bench --site siaga.localhost run-tests --app siaga --skip-test-records
"""

import json
import os

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_to_date, now_datetime, nowdate


class SiagaTestCase(FrappeTestCase):
	"""Tiap metode tes berjalan di savepoint sendiri, jadi skor, work order,
	dan reservasi dari satu tes tidak bocor ke tes berikutnya. Data dari
	setUpClass (make_env) tetap ada sampai kelas selesai."""

	def setUp(self):
		super().setUp()
		frappe.db.savepoint("siaga_test")

	def tearDown(self):
		frappe.db.rollback(save_point="siaga_test")
		super().tearDown()


def company():
	"""Perusahaan yang dibuat bootstrap; jatuh ke default global kalau tidak ada."""
	name = os.environ.get("SIAGA_COMPANY") or "PT Tambang Demo"
	if frappe.db.exists("Company", name):
		return name
	return frappe.defaults.get_global_default("company") or frappe.db.get_value("Company", {}, "name")


def account_by_type(comp, account_type):
	return frappe.db.get_value("Account", {"company": comp, "account_type": account_type, "is_group": 0}, "name")


def ensure(doctype, name, doc):
	if frappe.db.exists(doctype, name):
		return frappe.get_doc(doctype, name)
	d = frappe.get_doc(dict(doctype=doctype, **doc))
	d.insert(ignore_permissions=True)
	return d


def receipt(item, warehouse, qty, comp, rate=100.0):
	se = frappe.get_doc({
		"doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "company": comp,
		"to_warehouse": warehouse,
		"items": [{"item_code": item, "qty": qty, "basic_rate": rate, "t_warehouse": warehouse}],
	})
	se.insert(ignore_permissions=True)
	se.submit()
	return se


def make_env(tag="UJI", stock_qty=2, reorder_level=2, reorder_qty=4):
	"""Kelas alat + unit Dipantau + komponen + gudang berisi `stock_qty` part."""
	comp = company()
	ab = frappe.db.get_value("Company", comp, "abbr")

	item = ensure("Item", "%s-BRG" % tag, {
		"item_code": "%s-BRG" % tag, "item_name": "Bearing uji %s" % tag,
		"item_group": "Consumable", "stock_uom": "Nos", "is_stock_item": 1, "valuation_rate": 100,
	}).name
	warehouse = ensure("Warehouse", "Gudang %s - %s" % (tag, ab), {
		"warehouse_name": "Gudang %s" % tag, "company": comp, "parent_warehouse": "All Warehouses - %s" % ab,
	}).name

	# ERPNext menyimpan daftar anak gudang di request_cache, yang di test runner
	# hidup sepanjang seluruh run; gudang baru tidak akan terlihat tanpa ini.
	if hasattr(frappe.local, "request_cache"):
		frappe.local.request_cache.clear()

	it = frappe.get_doc("Item", item)
	it.set("reorder_levels", [r for r in it.reorder_levels if r.warehouse != warehouse])
	it.append("reorder_levels", {
		"warehouse_group": "All Warehouses - %s" % ab, "warehouse": warehouse,
		"warehouse_reorder_level": reorder_level, "warehouse_reorder_qty": reorder_qty,
		"material_request_type": "Purchase",
	})
	it.save(ignore_permissions=True)
	if stock_qty:
		receipt(item, warehouse, stock_qty, comp)

	category = ensure("Asset Category", "Kategori %s" % tag, {
		"asset_category_name": "Kategori %s" % tag, "enable_cwip_accounting": 0,
		"accounts": [{
			"company_name": comp,
			"fixed_asset_account": account_by_type(comp, "Fixed Asset"),
			"accumulated_depreciation_account": account_by_type(comp, "Accumulated Depreciation"),
			"depreciation_expense_account": account_by_type(comp, "Depreciation"),
		}],
	}).name
	pump_item = ensure("Item", "%s-PUMP" % tag, {
		"item_code": "%s-PUMP" % tag, "item_name": "Pompa uji %s" % tag, "item_group": "Products",
		"stock_uom": "Nos", "is_stock_item": 0, "is_fixed_asset": 1, "asset_category": category,
	}).name
	location = ensure("Location", "Site %s" % tag, {"location_name": "Site %s" % tag}).name

	cls = ensure("Asset Class", "Kelas %s" % tag, {
		"class_name": "Kelas %s" % tag, "monitoring_enabled": 1, "sample_rate_hz": 3200,
		"feature_schema_version": 1, "default_warehouse": warehouse,
		"rpm_nominal": 2000, "rolling_elements": 16, "ball_diameter_mm": 8.4074,
		"pitch_diameter_mm": 71.501, "contact_angle_deg": 15.17,
		"threshold_trigger": 40, "threshold_recover": 55, "consecutive_cycles": 3,
		"baseline_days": 3, "forecast_horizon_days": 14,
		"candidate_parts": [
			{"component_type": "Bearing DE", "symptom": "bpfo", "item": item, "qty": 1},
			{"component_type": "Bearing DE", "symptom": "broadband", "item": item, "qty": 1},
		],
	})

	asset_name = "Pompa %s 01" % tag
	name = frappe.db.get_value("Asset", {"asset_name": asset_name, "docstatus": 1}, "name")
	if not name:
		asset = frappe.get_doc({
			"doctype": "Asset", "asset_name": asset_name, "item_code": pump_item, "company": comp,
			"location": location, "is_existing_asset": 1, "gross_purchase_amount": 1000000,
			"purchase_date": add_days(nowdate(), -240), "available_for_use_date": add_days(nowdate(), -240),
			"calculate_depreciation": 0, "asset_class": cls.name,
		})
		asset.insert(ignore_permissions=True)
		asset.submit()
		name = asset.name

	profile = ensure("Asset Monitoring Profile", name, {
		"asset": name, "data_source_id": "%s-01" % tag, "monitoring_status": "Dipantau",
		"asset_class": cls.name, "alarm_state": "Normal",
	})
	if profile.monitoring_status != "Dipantau" or profile.alarm_state != "Normal":
		frappe.db.set_value("Asset Monitoring Profile", profile.name,
			{"monitoring_status": "Dipantau", "alarm_state": "Normal", "alarm_since": None, "last_auto_work_order": None})

	component = frappe.db.get_value("Asset Component", {"asset": name, "component_type": "Bearing DE", "status": "Terpasang"}, "name")
	if not component:
		component = frappe.get_doc({
			"doctype": "Asset Component", "asset": name, "component_type": "Bearing DE",
			"component_name": "Bearing sisi kopling", "item": item, "status": "Terpasang",
			"design_life_hours": 20000,
		}).insert(ignore_permissions=True).name

	return frappe._dict(
		company=comp, abbr=ab, item=item, warehouse=warehouse, asset_class=cls.name,
		asset=name, asset_name=asset_name, profile=profile.name, component=component,
	)


def score(asset, value, at=None, minutes_ago=0, projection=None, symptom="bpfo", operating_state="stabil"):
	"""Sisipkan satu Health Score; hook otomasi berjalan seperti di produksi.

	`projection` = (days, low, high) atau None.
	"""
	at = at or add_to_date(now_datetime(), minutes=-minutes_ago)
	doc = frappe.get_doc({
		"doctype": "Health Score", "asset": asset, "scored_at": at, "score": value,
		"operating_state": operating_state, "confidence": 0.9, "model_version": "uji",
		"anomaly_score": 1.0, "trigger_summary": "%s: uji" % symptom,
		"top_features": json.dumps({"symptom": symptom, "features": []}),
		"has_projection": 1 if projection else 0,
		"days_to_threshold": projection[0] if projection else 0,
		"projection_low": projection[1] if projection else 0,
		"projection_high": projection[2] if projection else 0,
	})
	doc.insert(ignore_permissions=True)
	return doc


def make_work_order(env, trigger_source="Manual", component=None, qty=1):
	wo = frappe.get_doc({
		"doctype": "SIAGA Work Order", "title": "Uji", "asset": env.asset,
		"component": component, "priority": "Sedang", "trigger_source": trigger_source,
		"warehouse": env.warehouse, "parts": [{"item": env.item, "qty": qty}],
	})
	wo.insert(ignore_permissions=True)
	wo.submit()
	return wo


def open_auto_work_orders(asset):
	return frappe.get_all("SIAGA Work Order", filters={
		"asset": asset, "trigger_source": "Otomatis", "docstatus": 1, "status": ["in", ("Terbuka", "Dikerjakan")],
	}, pluck="name")


def auto_material_requests(item, warehouse):
	return frappe.db.sql_list("""
		select mr.name from `tabMaterial Request` mr
		join `tabMaterial Request Item` mri on mri.parent = mr.name
		where mr.docstatus = 0 and mr.siaga_auto = 1 and mri.item_code = %s and mri.warehouse = %s
	""", (item, warehouse))
