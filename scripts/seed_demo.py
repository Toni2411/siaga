# -*- coding: utf-8 -*-
"""Isi data demo SIAGA ke site yang sudah hidup.

Membuat kelas alat pertama (pompa dewatering dengan bearing rig IMS), item
spare part, lalu menautkan aset yang ada ke kelasnya beserta profil
pemantauan dan komponennya. Aman dijalankan ulang.

Pakai:
    python scripts/seed_demo.py                      # localhost:8080, Administrator/admin
    SIAGA_URL=... SIAGA_PASSWORD=... python scripts/seed_demo.py
"""
import http.cookiejar
import json
import os
import sys
import urllib.error
import urllib.request
from urllib.parse import quote

BASE = os.environ.get("SIAGA_URL", "http://localhost:8080")
USER = os.environ.get("SIAGA_USER", "Administrator")
PASSWORD = os.environ.get("SIAGA_PASSWORD", "admin")
COMPANY = os.environ.get("SIAGA_COMPANY", "PT Tambang Demo")

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    try:
        with opener.open(req) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        if e.code == 404:
            raise LookupError(path)
        try:
            j = json.loads(raw)
            msg = j.get("exception") or j.get("_server_messages") or raw
        except Exception:
            msg = raw
        raise RuntimeError("%s %s -> %s\n%s" % (method, path, e.code, msg[:1200]))


def resource(doctype, name=None):
    p = "/api/resource/" + quote(doctype)
    return p + "/" + quote(name) if name else p


def get(doctype, name):
    try:
        return call("GET", resource(doctype, name))["data"]
    except LookupError:
        return None


def ensure(doctype, name, doc):
    """Buat kalau belum ada, kembalikan dokumennya."""
    existing = get(doctype, name)
    if existing:
        print("   ada  %-26s %s" % (doctype, name))
        return existing
    created = call("POST", resource(doctype), doc)["data"]
    print("   buat %-26s %s" % (doctype, created["name"]))
    return created


def update(doctype, name, patch):
    return call("PUT", resource(doctype, name), patch)["data"]


def find(doctype, filters, fields=("name",)):
    q = "?filters=%s&fields=%s&limit_page_length=100" % (
        quote(json.dumps(filters)), quote(json.dumps(list(fields))))
    return call("GET", resource(doctype) + q)["data"]


def main():
    call("POST", "/api/method/login", {"usr": USER, "pwd": PASSWORD})

    print("== Item spare part")
    ensure("Item", "BRG-ZA-2115", {
        "item_code": "BRG-ZA-2115",
        "item_name": "Bearing Rexnord ZA-2115",
        "item_group": "Consumable",
        "stock_uom": "Nos",
        "is_stock_item": 1,
        "description": "Bearing double row, dipakai pada rig IMS. Komponen kritis pompa dewatering.",
    })
    ensure("Item", "SEAL-MEK-100", {
        "item_code": "SEAL-MEK-100",
        "item_name": "Seal Mekanik Pompa 100 HP",
        "item_group": "Consumable",
        "stock_uom": "Nos",
        "is_stock_item": 1,
    })

    print("== Gudang site dan stok awal")
    abbr = get("Company", COMPANY)["abbr"]
    warehouse = ensure("Warehouse", "Gudang Site A - %s" % abbr, {
        "warehouse_name": "Gudang Site A",
        "company": COMPANY,
        "parent_warehouse": "All Warehouses - %s" % abbr,
    })["name"]
    # Titik pesan ulang: kalau stok setelah reservasi < 2, pesan 4.
    item = get("Item", "BRG-ZA-2115")
    if not any(r.get("warehouse") == warehouse for r in item.get("reorder_levels", [])):
        update("Item", "BRG-ZA-2115", {"reorder_levels": [{
            "warehouse_group": "All Warehouses - %s" % abbr,
            "warehouse": warehouse,
            "warehouse_reorder_level": 2,
            "warehouse_reorder_qty": 4,
            "material_request_type": "Purchase",
        }], "valuation_rate": 3500000})
        print("   set  %-26s titik pesan ulang BRG-ZA-2115 @ %s" % ("Item Reorder", warehouse))
    else:
        print("   ada  %-26s titik pesan ulang BRG-ZA-2115" % "Item Reorder")
    if not find("Stock Ledger Entry", [["warehouse", "=", warehouse], ["item_code", "=", "BRG-ZA-2115"], ["is_cancelled", "=", 0]]):
        se = call("POST", resource("Stock Entry"), {
            "stock_entry_type": "Material Receipt",
            "company": COMPANY,
            "to_warehouse": warehouse,
            "items": [
                {"item_code": "BRG-ZA-2115", "qty": 2, "basic_rate": 3500000, "t_warehouse": warehouse},
                {"item_code": "SEAL-MEK-100", "qty": 3, "basic_rate": 850000, "t_warehouse": warehouse},
            ],
            "docstatus": 1,
        })["data"]
        print("   buat %-26s %s (2 bearing, 3 seal)" % ("Stock Entry", se["name"]))
    else:
        print("   ada  %-26s stok awal sudah masuk" % "Stock Entry")

    print("== Asset Class")
    # Geometri bearing Rexnord ZA-2115 pada rig IMS, poros 2000 RPM.
    # Menghasilkan BPFO 236.4 Hz dan BPFI 296.9 Hz, sama dengan yang diuji di
    # services/edge/tests/test_features.py.
    asset_class = ensure("Asset Class", "Pompa dewatering listrik", {
        "class_name": "Pompa dewatering listrik",
        "default_warehouse": warehouse,
        "description": "Pompa sentrifugal bermotor listrik. Kelas alat pertama SIAGA, "
                       "sumber data v1 dari dataset run to failure IMS.",
        "monitoring_enabled": 1,
        "sample_rate_hz": 3200,
        "feature_schema_version": 1,
        "rpm_nominal": 2000,
        "rolling_elements": 16,
        "ball_diameter_mm": 8.4074,
        "pitch_diameter_mm": 71.501,
        "contact_angle_deg": 15.17,
        "threshold_trigger": 40,
        "threshold_recover": 55,
        "consecutive_cycles": 3,
        "baseline_days": 1,
        "candidate_parts": [
            {"component_type": "Bearing DE", "symptom": "bpfo", "item": "BRG-ZA-2115", "qty": 1},
            {"component_type": "Bearing DE", "symptom": "bpfi", "item": "BRG-ZA-2115", "qty": 1},
            {"component_type": "Bearing NDE", "symptom": "bpfo", "item": "BRG-ZA-2115", "qty": 1},
            {"component_type": "Bearing NDE", "symptom": "bpfi", "item": "BRG-ZA-2115", "qty": 1},
            {"component_type": "Seal mekanik", "symptom": "seal", "item": "SEAL-MEK-100", "qty": 1},
            # Kalau gejala tidak spesifik, dugaan terbesar pada pompa adalah
            # bearing sisi kopling. Ini konfigurasi kelas, bukan tebakan kode.
            {"component_type": "Bearing DE", "symptom": "broadband", "item": "BRG-ZA-2115", "qty": 1},
        ],
    })
    if not asset_class.get("default_warehouse"):
        update("Asset Class", asset_class["name"], {"default_warehouse": warehouse})
        print("   set  %-26s gudang spare part -> %s" % ("Asset Class", warehouse))
    if not any(r.get("symptom") == "broadband" for r in asset_class.get("candidate_parts", [])):
        rows = [{k: r[k] for k in ("component_type", "symptom", "item", "qty")} for r in asset_class["candidate_parts"]]
        rows.append({"component_type": "Bearing DE", "symptom": "broadband", "item": "BRG-ZA-2115", "qty": 1})
        update("Asset Class", asset_class["name"], {"candidate_parts": rows})
        print("   set  %-26s part kandidat broadband" % "Asset Class")
    print("      BPFO %.1f Hz | BPFI %.1f Hz | BSF %.1f Hz | FTF %.1f Hz" % (
        asset_class["bpfo_hz"], asset_class["bpfi_hz"], asset_class["bsf_hz"], asset_class["ftf_hz"]))

    print("== Aset: empat unit, satu per kanal dataset IMS")
    # Kanal 0..3 dataset = PUMP-01..04. Bearing 1 (PUMP-01) yang gagal.
    location = ensure("Location", "Site Tambang A", {"location_name": "Site Tambang A"})["name"]
    assets = []
    for unit in range(1, 5):
        asset_name = "Pompa Dewatering Unit %02d" % unit
        found = find("Asset", [["asset_name", "=", asset_name], ["docstatus", "=", 1]],
                     fields=("name", "asset_name", "asset_class"))
        if found:
            a = found[0]
            print("   ada  %-26s %s (%s)" % ("Asset", a["name"], asset_name))
        else:
            a = call("POST", resource("Asset"), {
                "asset_name": asset_name,
                "item_code": "PUMP-DW-100",
                "company": COMPANY,
                "location": location,
                "is_existing_asset": 1,
                "gross_purchase_amount": 450000000,
                "purchase_date": "2026-01-15",
                "available_for_use_date": "2026-01-15",
                "calculate_depreciation": 0,
                "asset_class": asset_class["name"],
                "docstatus": 1,
            })["data"]
            print("   buat %-26s %s (%s)" % ("Asset", a["name"], asset_name))
        if a.get("asset_class") != asset_class["name"]:
            update("Asset", a["name"], {"asset_class": asset_class["name"]})
            print("   taut %-26s %s -> %s" % ("Asset", a["name"], asset_class["name"]))
        assets.append((unit, a))

    for unit, a in assets:
        source_id = "PUMP-%02d" % unit
        profile = get("Asset Monitoring Profile", a["name"])
        if profile and profile.get("data_source_id") != source_id:
            update("Asset Monitoring Profile", a["name"], {"data_source_id": source_id})
            print("   set  %-26s %s -> %s" % ("Asset Monitoring Profile", a["name"], source_id))
        else:
            ensure("Asset Monitoring Profile", a["name"], {
                "asset": a["name"],
                "data_source_id": source_id,
                "monitoring_status": "Belum terdaftar",
            })

        for ctype, cname in (("Bearing DE", "Bearing sisi kopling"),
                             ("Bearing NDE", "Bearing sisi bebas"),
                             ("Seal mekanik", "Seal poros")):
            if find("Asset Component", [["asset", "=", a["name"]], ["component_type", "=", ctype]]):
                continue
            item = "SEAL-MEK-100" if ctype == "Seal mekanik" else "BRG-ZA-2115"
            c = call("POST", resource("Asset Component"), {
                "asset": a["name"],
                "component_type": ctype,
                "component_name": cname,
                "item": item,
                "status": "Terpasang",
                "design_life_hours": 20000 if ctype != "Seal mekanik" else 8000,
            })["data"]
            print("   buat %-26s %s (%s / %s)" % ("Asset Component", c["name"], a["asset_name"], ctype))

    print("selesai")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        print("GAGAL:", e)
        sys.exit(1)
