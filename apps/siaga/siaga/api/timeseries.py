# Copyright (c) 2026, SIAGA and contributors
# For license information, please see license.txt

"""Baca time series dari TimescaleDB untuk ditampilkan di ERPNext.

Sensor Reading sengaja tidak disimpan di MariaDB milik ERPNext. Endpoint ini
adalah satu satunya jalan ERPNext menyentuh Timescale, dan hanya untuk baca.
DSN diambil dari site config: siaga_timescale_dsn.
"""

from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils import add_to_date, now_datetime

DEFAULT_FEATURES = ["vib_rms", "bpfo_energy", "bpfi_energy", "vib_kurtosis"]

# Lebar bucket dipilih dari panjang jendela supaya grafik selalu sekitar
# seratus sampai dua ratus titik, apa pun rentangnya.
BUCKET_FOR_HOURS = ((24, "10 minutes"), (24 * 7, "1 hour"), (24 * 30, "6 hours"))


@contextmanager
def timescale():
	import psycopg

	dsn = frappe.conf.get("siaga_timescale_dsn")
	if not dsn:
		frappe.throw(_("siaga_timescale_dsn belum diatur di site config"))
	conn = psycopg.connect(dsn)
	try:
		yield conn
	finally:
		conn.close()


def source_for(asset):
	source = frappe.db.get_value("Asset Monitoring Profile", {"asset": asset}, "data_source_id")
	if not source:
		frappe.throw(_("Aset {0} belum punya profil pemantauan dengan id sumber data").format(asset))
	return source


def bucket_for(hours):
	for limit, bucket in BUCKET_FOR_HOURS:
		if hours <= limit:
			return bucket
	return "1 day"


@frappe.whitelist()
def get_trend(asset, features=None, hours=168, normalize=1):
	"""Tren ciri per bucket waktu untuk satu aset.

	normalize=1 membagi tiap ciri dengan rata ratanya di 10% jendela pertama,
	sehingga semua ciri bisa digambar di satu sumbu sebagai kelipatan
	baseline. Itu yang paling mudah dibaca planner: "BPFO sudah 3x normal".
	"""
	frappe.has_permission("Asset", "read", asset, throw=True)
	hours = int(hours)
	if isinstance(features, str):
		features = frappe.parse_json(features)
	features = list(features or DEFAULT_FEATURES)
	source = source_for(asset)
	bucket = bucket_for(hours)
	since = add_to_date(now_datetime(), hours=-hours)

	with timescale() as conn, conn.cursor() as cur:
		cur.execute(
			"""
			select time_bucket(%s::interval, ts) as bucket, feature, avg(value)
			from sensor_reading
			where source_id = %s and feature = any(%s) and ts >= %s
			group by 1, 2
			order by 1
			""",
			(bucket, source, features, since),
		)
		rows = cur.fetchall()

	buckets = sorted({r[0] for r in rows})
	index = {b: i for i, b in enumerate(buckets)}
	series = {f: [None] * len(buckets) for f in features}
	for b, f, v in rows:
		series[f][index[b]] = float(v)

	if int(normalize) and buckets:
		head = max(1, len(buckets) // 10)
		for f, values in series.items():
			base = [v for v in values[:head] if v is not None]
			mean = sum(base) / len(base) if base else 0.0
			if mean > 0:
				series[f] = [None if v is None else round(v / mean, 3) for v in values]

	return {
		"source_id": source,
		"bucket": bucket,
		"normalized": bool(int(normalize)),
		"labels": [b.strftime("%d/%m %H:%M") for b in buckets],
		"datasets": [{"name": f, "values": series[f]} for f in features],
	}


@frappe.whitelist()
def latest(asset):
	"""Kondisi terkini: state operasi dan beberapa ciri kunci pada cap waktu terakhir."""
	frappe.has_permission("Asset", "read", asset, throw=True)
	source = source_for(asset)
	with timescale() as conn, conn.cursor() as cur:
		cur.execute(
			"select ts, state from operating_state where source_id = %s order by ts desc limit 1",
			(source,),
		)
		state = cur.fetchone()
		if not state:
			return {"source_id": source, "ts": None, "state": None, "features": {}}
		cur.execute(
			"select feature, value from sensor_reading where source_id = %s and ts = %s",
			(source, state[0]),
		)
		feats = {f: float(v) for f, v in cur.fetchall()}
	return {"source_id": source, "ts": state[0].isoformat(), "state": state[1], "features": feats}


@frappe.whitelist()
def get_health(asset, hours=168):
	"""Riwayat skor kesehatan dari Health Score, plus ambang kelasnya."""
	frappe.has_permission("Asset", "read", asset, throw=True)
	hours = int(hours)
	since = add_to_date(now_datetime(), hours=-hours)
	rows = frappe.get_all(
		"Health Score",
		filters={"asset": asset, "scored_at": [">=", since]},
		fields=["scored_at", "score", "work_order"],
		order_by="scored_at asc",
		limit=5000,
	)
	profile = frappe.db.get_value(
		"Asset Monitoring Profile", {"asset": asset},
		["monitoring_status", "alarm_state", "asset_class", "last_auto_work_order"], as_dict=True,
	) or {}
	thresholds = {}
	if profile.get("asset_class"):
		thresholds = frappe.db.get_value(
			"Asset Class", profile["asset_class"], ["threshold_trigger", "threshold_recover"], as_dict=True,
		) or {}
	# Jarangkan supaya grafik tetap ringan: maksimal sekitar 300 titik.
	step = max(1, len(rows) // 300)
	rows = rows[::step]
	return {
		"labels": [r.scored_at.strftime("%d/%m %H:%M") for r in rows],
		"scores": [r.score for r in rows],
		"work_orders": [r.work_order for r in rows],
		"thresholds": thresholds,
		"profile": profile,
	}
