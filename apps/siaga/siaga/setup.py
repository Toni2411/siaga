# Copyright (c) 2026, SIAGA and contributors
# For license information, please see license.txt

"""Bootstrap satu perintah untuk site baru.

Dipanggil container `bootstrap` di docker compose setelah site dibuat:

    bench --site <site> execute siaga.setup.bootstrap

Semua langkah idempoten, jadi aman diulang pada site yang sudah hidup.
Konfigurasi dibaca dari environment container (lihat .env.example).
"""

import os

import frappe
from frappe.utils import add_days, nowdate
from frappe.utils.password import update_password


def env(key, default=None):
	return os.environ.get(key) or default


def step(msg):
	print("==> " + msg, flush=True)


def bootstrap():
	ensure_setup_wizard()
	ensure_scheduler()
	ensure_bot_user()
	seed_demo()
	frappe.db.commit()
	step("bootstrap selesai")


# ---- 1. setup wizard ----

def ensure_setup_wizard():
	if frappe.db.count("Company"):
		step("setup wizard sudah selesai, lewati")
		return
	from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

	year = nowdate()[:4]
	args = {
		"language": "English",
		"country": env("SIAGA_COUNTRY", "Indonesia"),
		"timezone": env("SIAGA_TIMEZONE", "Asia/Jakarta"),
		"currency": env("SIAGA_CURRENCY", "IDR"),
		"full_name": env("SIAGA_ADMIN_NAME", "Maintenance Planner"),
		"email": env("SIAGA_ADMIN_EMAIL", "planner@siaga.local"),
		"password": env("ADMIN_PASSWORD", "admin"),
		"company_name": env("SIAGA_COMPANY", "PT Tambang Demo"),
		"company_abbr": env("SIAGA_COMPANY_ABBR", "PTD"),
		"chart_of_accounts": env("SIAGA_CHART_OF_ACCOUNTS", "Standard"),
		"fy_start_date": "%s-01-01" % year,
		"fy_end_date": "%s-12-31" % year,
		"setup_demo": 0,
	}
	step("menjalankan setup wizard untuk %s" % args["company_name"])
	setup_complete(args)
	frappe.db.commit()
	# Default perusahaan untuk semua user, supaya form tidak memilih yang lain.
	frappe.db.set_single_value("Global Defaults", "default_company", args["company_name"])


def company():
	return env("SIAGA_COMPANY", "PT Tambang Demo")


def abbr():
	return frappe.db.get_value("Company", company(), "abbr")


# ---- 2. scheduler ----

def ensure_scheduler():
	frappe.db.set_single_value("System Settings", "enable_scheduler", 1)
	step("scheduler aktif")


# ---- 3. user bot untuk AI service ----

BOT_EMAIL = "siaga-bot@siaga.local"
BOT_ROLES = ["Maintenance Manager", "Maintenance User", "Accounts User", "Stock User", "Purchase User"]


def ensure_bot_user():
	key = env("ERPNEXT_API_KEY")
	secret = env("ERPNEXT_API_SECRET")
	if not key or not secret:
		step("ERPNEXT_API_KEY/SECRET kosong, user bot dilewati")
		return
	if frappe.db.exists("User", BOT_EMAIL):
		user = frappe.get_doc("User", BOT_EMAIL)
	else:
		user = frappe.get_doc({
			"doctype": "User",
			"email": BOT_EMAIL,
			"first_name": "SIAGA Bot",
			"user_type": "System User",
			"send_welcome_email": 0,
		})
	have = {r.role for r in user.roles}
	for role in BOT_ROLES:
		if role not in have:
			user.append("roles", {"role": role})
	user.api_key = key
	user.api_secret = secret  # field Password, disimpan terenkripsi
	user.flags.ignore_permissions = True
	user.save()
	step("user bot %s siap dengan API key dari .env" % BOT_EMAIL)


# ---- 4. data demo ----

def ensure(doctype, name, doc):
	if frappe.db.exists(doctype, name):
		return frappe.get_doc(doctype, name)
	d = frappe.get_doc(dict(doctype=doctype, **doc))
	d.insert(ignore_permissions=True)
	step("buat %s %s" % (doctype, d.name))
	return d


def account_by_type(account_type):
	return frappe.db.get_value(
		"Account", {"company": company(), "account_type": account_type, "is_group": 0}, "name",
	)


def seed_demo():
	comp = company()
	ab = abbr()
	if not ab:
		step("perusahaan %s tidak ada, seed dilewati" % comp)
		return

	# Item spare part dan aset
	ensure("Item", "BRG-ZA-2115", {
		"item_code": "BRG-ZA-2115", "item_name": "Bearing Rexnord ZA-2115",
		"item_group": "Consumable", "stock_uom": "Nos", "is_stock_item": 1, "valuation_rate": 3500000,
		"description": "Bearing double row pada rig IMS. Komponen kritis pompa dewatering.",
	})
	ensure("Item", "SEAL-MEK-100", {
		"item_code": "SEAL-MEK-100", "item_name": "Seal Mekanik Pompa 100 HP",
		"item_group": "Consumable", "stock_uom": "Nos", "is_stock_item": 1, "valuation_rate": 850000,
	})
	category = ensure("Asset Category", "Pompa Dewatering", {
		"asset_category_name": "Pompa Dewatering",
		"enable_cwip_accounting": 0,
		"accounts": [{
			"company_name": comp,
			"fixed_asset_account": account_by_type("Fixed Asset"),
			"accumulated_depreciation_account": account_by_type("Accumulated Depreciation"),
			"depreciation_expense_account": account_by_type("Depreciation"),
		}],
	})
	ensure("Item", "PUMP-DW-100", {
		"item_code": "PUMP-DW-100", "item_name": "Pompa Dewatering 100 HP",
		"item_group": "Products", "stock_uom": "Nos", "is_stock_item": 0, "is_fixed_asset": 1,
		"asset_category": category.name,
	})
	location = ensure("Location", "Site Tambang A", {"location_name": "Site Tambang A"})

	# Gudang site, titik pesan ulang, stok awal
	warehouse = ensure("Warehouse", "Gudang Site A - %s" % ab, {
		"warehouse_name": "Gudang Site A", "company": comp, "parent_warehouse": "All Warehouses - %s" % ab,
	}).name
	item = frappe.get_doc("Item", "BRG-ZA-2115")
	if not any(r.warehouse == warehouse for r in item.reorder_levels):
		item.append("reorder_levels", {
			"warehouse_group": "All Warehouses - %s" % ab, "warehouse": warehouse,
			"warehouse_reorder_level": 2, "warehouse_reorder_qty": 4, "material_request_type": "Purchase",
		})
		item.save(ignore_permissions=True)
		step("titik pesan ulang BRG-ZA-2115 @ %s" % warehouse)
	if not frappe.db.exists("Stock Ledger Entry", {"warehouse": warehouse, "item_code": "BRG-ZA-2115", "is_cancelled": 0}):
		se = frappe.get_doc({
			"doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "company": comp,
			"to_warehouse": warehouse,
			"items": [
				{"item_code": "BRG-ZA-2115", "qty": 2, "basic_rate": 3500000, "t_warehouse": warehouse},
				{"item_code": "SEAL-MEK-100", "qty": 3, "basic_rate": 850000, "t_warehouse": warehouse},
			],
		})
		se.insert(ignore_permissions=True)
		se.submit()
		step("stok awal %s (2 bearing, 3 seal)" % se.name)

	# Kelas alat pertama: geometri bearing rig IMS
	asset_class = ensure("Asset Class", "Pompa dewatering listrik", {
		"class_name": "Pompa dewatering listrik",
		"description": "Pompa sentrifugal bermotor listrik. Kelas alat pertama SIAGA, sumber data v1 dari dataset run to failure IMS.",
		"monitoring_enabled": 1, "sample_rate_hz": 3200, "feature_schema_version": 1,
		"default_warehouse": warehouse,
		"rpm_nominal": 2000, "rolling_elements": 16, "ball_diameter_mm": 8.4074,
		"pitch_diameter_mm": 71.501, "contact_angle_deg": 15.17,
		"threshold_trigger": 40, "threshold_recover": 55, "consecutive_cycles": 3, "baseline_days": 1,
		"candidate_parts": [
			{"component_type": "Bearing DE", "symptom": "bpfo", "item": "BRG-ZA-2115", "qty": 1},
			{"component_type": "Bearing DE", "symptom": "bpfi", "item": "BRG-ZA-2115", "qty": 1},
			{"component_type": "Bearing NDE", "symptom": "bpfo", "item": "BRG-ZA-2115", "qty": 1},
			{"component_type": "Bearing NDE", "symptom": "bpfi", "item": "BRG-ZA-2115", "qty": 1},
			{"component_type": "Seal mekanik", "symptom": "seal", "item": "SEAL-MEK-100", "qty": 1},
			{"component_type": "Bearing DE", "symptom": "broadband", "item": "BRG-ZA-2115", "qty": 1},
		],
	})

	# Empat unit, satu per kanal dataset
	for unit in range(1, 5):
		asset_name = "Pompa Dewatering Unit %02d" % unit
		name = frappe.db.get_value("Asset", {"asset_name": asset_name, "docstatus": 1}, "name")
		if not name:
			asset = frappe.get_doc({
				"doctype": "Asset", "asset_name": asset_name, "item_code": "PUMP-DW-100",
				"company": comp, "location": location.name, "is_existing_asset": 1,
				"gross_purchase_amount": 450000000, "purchase_date": add_days(nowdate(), -240),
				"available_for_use_date": add_days(nowdate(), -240), "calculate_depreciation": 0,
				"asset_class": asset_class.name,
			})
			asset.insert(ignore_permissions=True)
			asset.submit()
			name = asset.name
			step("buat Asset %s (%s)" % (name, asset_name))
		elif frappe.db.get_value("Asset", name, "asset_class") != asset_class.name:
			frappe.db.set_value("Asset", name, "asset_class", asset_class.name)

		source_id = "PUMP-%02d" % unit
		profile = frappe.db.get_value("Asset Monitoring Profile", {"asset": name}, ["name", "data_source_id"], as_dict=True)
		if not profile:
			ensure("Asset Monitoring Profile", name, {"asset": name, "data_source_id": source_id, "monitoring_status": "Belum terdaftar"})
		elif profile.data_source_id != source_id:
			frappe.db.set_value("Asset Monitoring Profile", profile.name, "data_source_id", source_id)

		for ctype, cname in (("Bearing DE", "Bearing sisi kopling"), ("Bearing NDE", "Bearing sisi bebas"), ("Seal mekanik", "Seal poros")):
			if frappe.db.exists("Asset Component", {"asset": name, "component_type": ctype}):
				continue
			frappe.get_doc({
				"doctype": "Asset Component", "asset": name, "component_type": ctype, "component_name": cname,
				"item": "SEAL-MEK-100" if ctype == "Seal mekanik" else "BRG-ZA-2115",
				"status": "Terpasang", "design_life_hours": 8000 if ctype == "Seal mekanik" else 20000,
			}).insert(ignore_permissions=True)
	step("data demo siap: kelas alat, 4 unit, profil, komponen, stok")
