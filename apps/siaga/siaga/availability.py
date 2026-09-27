# Copyright (c) 2026, SIAGA and contributors
# For license information, please see license.txt

"""Ketersediaan alat dalam bahasa yang dipakai operasi tambang.

PA, UA, MTBF, dan MTTR adalah angka yang muncul di rapat pagi site dan di
laporan ke pemilik tambang. Di lapangan angka itu biasanya dicatat tangan di
lembar shift, jadi sering jadi bahan perdebatan antara kontraktor dan owner.
Di sini ketiga bahannya datang dari catatan sistem sendiri:

- Jam operasi dari status operasi yang dikirim edge tiap cuplikan
  (operating_state di TimescaleDB), bukan dari entri manual.
- Jam perbaikan dari SIAGA Work Order: dari mekanik menekan "Mulai kerja"
  sampai menutup pekerjaan.
- Jumlah kerusakan dari Failure Log, yaitu apa yang benar benar rusak menurut
  mekanik, bukan jumlah alarm.

Rumus yang dipakai, versi kontraktor tambang yang paling umum:

    PA   = jam tersedia / jam kalender          (jam tersedia = kalender - perbaikan)
    UA   = jam operasi  / jam tersedia
    MA   = jam operasi  / (jam operasi + jam perbaikan)
    MTBF = jam operasi  / jumlah kerusakan
    MTTR = jam perbaikan / jumlah perbaikan

Yang tidak dihitung di sini, dan disebut terang terangan di laporan: downtime
terencana (servis berkala) tidak ada di data demo, jadi seluruh downtime di
sini bersifat korektif. Pada armada sungguhan keduanya dipisah, dan PA
biasanya hanya memperhitungkan downtime maintenance, bukan standby.
"""

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime

# Jeda antar cuplikan yang masih dianggap "alat menyala terus". Lebih dari ini
# berarti data hilang, dan waktunya tidak boleh dihitung sebagai jam operasi.
MAX_SAMPLE_GAP_S = 3600

RUNNING_STATES = ("stabil", "berbeban")
OPEN_STATUSES = ("Terbuka", "Dikerjakan")


def operating_hours(source_id, start, end):
	"""Jam alat berjalan menurut status operasi dari edge.

	None kalau TimescaleDB tidak bisa dihubungi, supaya laporan tetap bisa
	menampilkan kolom lain dan bukan gagal seluruhnya.
	"""
	from siaga.api.timeseries import timescale, to_utc

	sql = """
		with s as (
			select ts, state, lead(ts) over (order by ts) as next_ts
			from operating_state
			where source_id = %s and ts >= %s and ts < %s
		)
		select coalesce(sum(least(extract(epoch from (next_ts - ts)), %s)), 0) / 3600.0
		from s
		where state = any(%s) and next_ts is not null
	"""
	try:
		with timescale() as conn, conn.cursor() as cur:
			cur.execute(sql, (source_id, to_utc(start), to_utc(end), MAX_SAMPLE_GAP_S, list(RUNNING_STATES)))
			row = cur.fetchone()
			return flt(row[0]) if row else 0.0
	except Exception:
		frappe.log_error(title="SIAGA ketersediaan: Timescale", message=frappe.get_traceback())
		return None


def repair_hours(asset, start, end):
	"""Jam perbaikan dan jumlah perbaikan yang beririsan dengan jendela waktu.

	Work order yang masih dikerjakan dihitung sampai sekarang; yang mulai
	sebelum jendela atau selesai sesudahnya dipotong di batas jendela, supaya
	laporan bulanan tidak mewarisi downtime bulan sebelumnya.
	"""
	rows = frappe.get_all(
		"SIAGA Work Order",
		filters={"asset": asset, "docstatus": 1, "started_on": ["is", "set"]},
		fields=["name", "started_on", "completed_on", "status"],
	)
	now = now_datetime()
	total, count = 0.0, 0
	for r in rows:
		begin = get_datetime(r.started_on)
		finish = get_datetime(r.completed_on) if r.completed_on else (now if r.status in OPEN_STATUSES else begin)
		lo, hi = max(begin, start), min(finish, end)
		if hi <= lo:
			continue
		total += (hi - lo).total_seconds() / 3600.0
		count += 1
	return total, count


def failure_count(asset, start, end):
	"""Kerusakan yang dikonfirmasi mekanik dalam jendela waktu."""
	return frappe.db.count("Failure Log", {"asset": asset, "failed_on": ["between", [start, end]]})


def ratio(numerator, denominator):
	"""Persentase, atau None kalau penyebutnya nol atau bahannya tidak ada."""
	if numerator is None or denominator is None or denominator <= 0:
		return None
	return 100.0 * numerator / denominator


def for_asset(asset, start, end, source_id=None, asset_name=None):
	"""Satu baris ketersediaan untuk satu aset di satu jendela waktu."""
	start, end = get_datetime(start), get_datetime(end)
	calendar = (end - start).total_seconds() / 3600.0
	source_id = source_id or frappe.db.get_value("Asset Monitoring Profile", {"asset": asset}, "data_source_id")
	running = operating_hours(source_id, start, end) if source_id else None
	repair, repairs = repair_hours(asset, start, end)
	available = max(calendar - repair, 0.0)
	failures = failure_count(asset, start, end)

	# Alat yang sedang diperbaiki tidak dihitung beroperasi, meskipun cuplikan
	# sensor terakhir masih menyatakan berjalan. Tanpa batas ini UA bisa
	# melebihi 100%, yang tidak punya arti. Kalau batas ini sampai menggigit,
	# artinya jam sensor dan jam work order tidak konsisten, dan laporan
	# menyebutkannya alih alih menyembunyikannya.
	operating = running if running is None else min(running, available)
	capped = running is not None and running > available + 1e-9

	return frappe._dict(
		asset=asset,
		asset_name=asset_name or frappe.db.get_value("Asset", asset, "asset_name") or asset,
		source_id=source_id,
		calendar_hours=calendar,
		operating_hours=operating,
		running_hours=running,
		operating_capped=capped,
		repair_hours=repair,
		available_hours=available,
		pa=ratio(available, calendar),
		ua=ratio(operating, available),
		ma=ratio(operating, operating + repair) if operating is not None else None,
		failures=failures,
		repairs=repairs,
		# MTBF dari satu atau dua kerusakan bukan angka statistik; kolom jumlah
		# kerusakan sengaja ikut ditampilkan supaya pembaca tahu dasarnya.
		mtbf=(operating / failures) if operating is not None and failures else None,
		mttr=(repair / repairs) if repairs else None,
	)


def table(start, end, asset=None):
	"""Satu baris per aset yang dipantau, diurutkan dari ketersediaan terendah."""
	filters = {"monitoring_status": ["!=", "Nonaktif"]}
	if asset:
		filters["asset"] = asset
	profiles = frappe.get_list(
		"Asset Monitoring Profile", filters=filters,
		fields=["asset", "data_source_id"], limit_page_length=0,
	)
	rows = [for_asset(p.asset, start, end, source_id=p.data_source_id) for p in profiles]
	rows.sort(key=lambda r: (r.pa if r.pa is not None else 999, r.asset_name))
	return rows
