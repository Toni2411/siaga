# Copyright (c) 2026, SIAGA and contributors
# For license information, please see license.txt

"""Forecast part dari kondisi alat, bukan dari konsumsi historis.

Tiga sumber kebutuhan per item per gudang, dalam horizon beberapa hari:

1. Terkunci: reservasi aktif work order yang sudah terbuka. Sudah pasti.
2. Proyeksi kondisi: unit yang dipantau, belum alarm, tapi tren skornya
   diproyeksikan menyentuh ambang dalam horizon. Part-nya diambil dari tabel
   part kandidat kelas alat untuk gejala yang sedang terlihat.
3. Pembanding: konsumsi historis (Material Issue 90 hari terakhir) — cara
   lama meramal, ditampilkan berdampingan supaya bedanya terlihat.

Proyeksi dipakai hanya kalau *mantap*: beberapa siklus terakhir berturut turut
semuanya memproyeksikan ambang dalam horizon, dan batas atas intervalnya pun
di dalam horizon. Satu proyeksi dari jendela pendek yang kebetulan miring
tidak boleh memesan bearing.

Kalau stok tersedia dikurangi kebutuhan terproyeksi jatuh di bawah titik
pesan ulang, draft Material Request terbit lewat jalur yang sama dengan
reservasi (satu draft per item per gudang), dengan alasan tertulis. Ini
yang membuat procurement melihat permintaan *sebelum* alarm, bukan pada
saat alarm.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, flt, get_datetime, nowdate

from siaga import stock, telegram

DEFAULT_HORIZON_DAYS = 14
STEADY_CYCLES = 3
HISTORY_DAYS = 90


# ---- sumber kebutuhan ----

def steady_projection(asset, horizon_days, cycles=STEADY_CYCLES):
	"""Skor terakhir unit kalau `cycles` skor stabil terakhir semuanya memproyeksikan
	ambang dalam horizon, termasuk batas atas intervalnya; selain itu None.

	Batas atas ikut diuji karena proyeksi dini sering punya titik tengah 13 hari
	dengan interval 8 sampai 31: tren memang turun, tapi kemiringannya belum
	pasti. Memesan bearing dari itu berarti memesan dari derau."""
	recent = frappe.get_all(
		"Health Score",
		filters={"asset": asset, "operating_state": "stabil"},
		fields=["name", "score", "scored_at", "has_projection", "days_to_threshold",
		        "projection_low", "projection_high", "top_features", "trigger_summary"],
		order_by="scored_at desc",
		limit=cycles,
	)
	if len(recent) < cycles:
		return None
	for r in recent:
		high = flt(r.projection_high)
		if not r.has_projection or high <= 0 or high > horizon_days:
			return None
	return recent[0]


def projected_needs(horizon_days=None, warehouse=None):
	"""Kebutuhan part dari unit yang menurun tapi belum alarm. Satu baris per unit per part."""
	from siaga.automation import candidate_parts, symptom_of

	profiles = frappe.get_all(
		"Asset Monitoring Profile",
		filters={"monitoring_status": "Dipantau", "alarm_state": ["!=", "Alarm"], "asset_class": ["!=", ""]},
		fields=["asset", "asset_class"],
	)
	rows = []
	for p in profiles:
		cls = frappe.get_cached_doc("Asset Class", p.asset_class)
		if not cls.monitoring_enabled or not cls.default_warehouse:
			continue
		if warehouse and cls.default_warehouse != warehouse:
			continue
		horizon = horizon_days or cls.forecast_horizon_days or DEFAULT_HORIZON_DAYS
		hs = steady_projection(p.asset, horizon)
		if not hs:
			continue
		symptom = symptom_of(hs)
		for part in candidate_parts(cls, symptom):
			rows.append(frappe._dict(
				asset=p.asset,
				asset_name=frappe.db.get_value("Asset", p.asset, "asset_name") or p.asset,
				item=part.item, qty=flt(part.qty) or 1, warehouse=cls.default_warehouse,
				component_type=part.component_type, symptom=symptom,
				score=flt(hs.score), scored_at=hs.scored_at, health_score=hs.name,
				days=flt(hs.days_to_threshold), low=flt(hs.projection_low), high=flt(hs.projection_high),
				horizon=horizon,
			))
	return rows


def committed_needs(warehouse=None):
	"""Reservasi aktif per item per gudang, dengan work order penyumbangnya."""
	filters = {"status": "Aktif"}
	if warehouse:
		filters["warehouse"] = warehouse
	return frappe.get_all("Part Reservation", filters=filters,
	                      fields=["item", "warehouse", "qty", "work_order", "asset"])


def historical_monthly(item, warehouse, days=HISTORY_DAYS):
	"""Rata-rata pemakaian per bulan dari Material Issue, cara lama meramal."""
	rows = frappe.db.sql(
		"""
		select coalesce(sum(-sle.actual_qty), 0)
		from `tabStock Ledger Entry` sle
		join `tabStock Entry` se on se.name = sle.voucher_no
		where sle.voucher_type = 'Stock Entry' and se.purpose = 'Material Issue'
		  and sle.item_code = %s and sle.warehouse = %s and sle.is_cancelled = 0
		  and sle.posting_date >= %s
		""",
		(item, warehouse, add_days(nowdate(), -days)),
	)
	return flt(rows[0][0]) / (days / 30.0) if rows else 0.0


def pending_auto_qty(item, warehouse):
	rows = frappe.db.sql(
		"""
		select coalesce(sum(mri.qty), 0) from `tabMaterial Request` mr
		join `tabMaterial Request Item` mri on mri.parent = mr.name
		where mr.docstatus = 0 and mr.siaga_auto = 1 and mri.item_code = %s and mri.warehouse = %s
		""",
		(item, warehouse),
	)
	return flt(rows[0][0]) if rows else 0.0


# ---- tabel gabungan ----

def table(horizon_days=None, warehouse=None):
	"""Satu baris per item per gudang: stok, terkunci, proyeksi, historis, saran."""
	keys = set()
	levels = {}
	for lv in frappe.get_all("Item Reorder", fields=["parent", "warehouse", "warehouse_reorder_level", "warehouse_reorder_qty"]):
		if warehouse and lv.warehouse != warehouse:
			continue
		keys.add((lv.parent, lv.warehouse))
		levels[(lv.parent, lv.warehouse)] = lv

	committed = defaultdict(list)
	for r in committed_needs(warehouse):
		committed[(r.item, r.warehouse)].append(r)
		keys.add((r.item, r.warehouse))

	projected = defaultdict(list)
	for r in projected_needs(horizon_days, warehouse):
		projected[(r.item, r.warehouse)].append(r)
		keys.add((r.item, r.warehouse))

	rows = []
	for item, wh in sorted(keys):
		lv = levels.get((item, wh))
		actual = stock.actual_qty(item, wh)
		locked = sum(flt(r.qty) for r in committed[(item, wh)])
		available = actual - locked
		proj_rows = sorted(projected[(item, wh)], key=lambda r: r.days)
		proj_qty = sum(r.qty for r in proj_rows)
		after = available - proj_qty
		level = flt(lv.warehouse_reorder_level) if lv else 0.0
		pending = pending_auto_qty(item, wh)
		need = level - after
		if need <= 0:
			advice = _("Cukup")
		elif pending >= need:
			advice = _("Draft MR menunggu")
		else:
			advice = _("Pesan {0}").format(int(round(need - pending)))
		rows.append(frappe._dict(
			item=item, item_name=frappe.db.get_value("Item", item, "item_name"), warehouse=wh,
			actual_qty=actual, locked_qty=locked, available_qty=available,
			projected_qty=proj_qty, projected_after=after,
			earliest_days=proj_rows[0].days if proj_rows else None,
			projected_units=", ".join("%s (~%s hari)" % (r.asset_name, fmt_days(r.days)) for r in proj_rows),
			committed_wos=", ".join(sorted({r.work_order for r in committed[(item, wh)]})),
			historical_monthly=historical_monthly(item, wh),
			reorder_level=level, reorder_qty=flt(lv.warehouse_reorder_qty) if lv else 0.0,
			pending_mr_qty=pending, advice=advice,
		))
	return rows


def fmt_days(d):
	d = flt(d)
	return "%.1f" % d if d < 10 else "%.0f" % d


# ---- tindakan: draft MR sebelum alarm ----

def reason_text(needs):
	parts = []
	for r in needs:
		rng = " (%s–%s)" % (fmt_days(r.low), fmt_days(r.high)) if r.high else ""
		parts.append("%s skor %.0f, proyeksi ke ambang ~%s hari%s" % (r.asset_name, r.score, fmt_days(r.days), rng))
	return _("Proyeksi kondisi SIAGA, sebelum alarm: ") + "; ".join(parts)


def check_projection(asset, cls):
	"""Dipanggil dari hook Health Score untuk unit yang belum alarm.

	Kalau proyeksi unit ini mantap dan stok tersedia dikurangi seluruh
	kebutuhan terproyeksi jatuh di bawah titik pesan ulang, terbitkan draft
	Material Request. Mengembalikan daftar (item, nama MR) yang baru dibuat.
	"""
	horizon = cls.forecast_horizon_days or DEFAULT_HORIZON_DAYS
	if not steady_projection(asset, horizon):
		return []
	all_needs = projected_needs()
	mine = [r for r in all_needs if r.asset == asset]
	created = []
	for r in mine:
		level = stock.reorder_level(r.item, r.warehouse)
		if not level:
			continue
		total = sum(x.qty for x in all_needs if x.item == r.item and x.warehouse == r.warehouse)
		after = stock.available_qty(r.item, r.warehouse) - total
		if after >= flt(level.warehouse_reorder_level):
			continue
		qty = max(flt(level.warehouse_reorder_qty), flt(level.warehouse_reorder_level) - after)
		company = frappe.db.get_value("Warehouse", r.warehouse, "company")
		mr, is_new = stock.ensure_material_request(r.item, r.warehouse, qty, company)
		if is_new:
			needs = [x for x in all_needs if x.item == r.item and x.warehouse == r.warehouse]
			frappe.db.set_value("Material Request", mr, "siaga_reason", reason_text(needs))
			telegram.notify_forecast_material_request(mr, r.item, qty, r.warehouse, needs)
			created.append((r.item, mr))
	return created
