"""Evaluasi offline yang bisa diulang: dari cache dataset ke angka di README.

Menjalankan jalur yang sama dengan sistem hidup (ekstraksi ciri edge, model per
unit, skor, aturan pemicu) langsung dari cache .npz, tanpa MQTT, database, atau
ERPNext. Hasilnya tabel per unit: alarm palsu di zona sehat, waktu pemicu, lead
time, dan gejala tebakan dibandingkan label.

    python -m siaga_ai.evaluate --cache data/cache/ims_2nd_test_3200hz.npz \\
        --channels 0,1,2,3 --failed 0:bpfo

    python -m siaga_ai.evaluate --cache data/cache/ims_1st_test_3200hz.npz \\
        --channels 0,2,4,6 --failed 2:bpfi,3:bsf

Label kegagalan dari readme dataset IMS: set 2 bearing 1 outer race; set 1
bearing 3 inner race dan bearing 4 elemen gelinding.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta

import numpy as np

from siaga_edge.config import IMS_PUMP_CLASS
from siaga_edge.features import extract_features
from siaga_edge.runner import operating_state

from .baseline import baseline_mask
from .config import MODEL_FEATURES
from .model import UnitModel

LABEL_NAME = {"bpfo": "outer race", "bpfi": "inner race", "bsf": "elemen gelinding", "ftf": "sangkar"}


def load_cache(path):
    z = np.load(path)
    ts = [datetime.fromisoformat(str(t)) for t in z["ts"]]
    return z["waves"], ts, str(z["dataset"]) if "dataset" in z else "IMS"


def features_for_channel(waves, ch, cfg):
    """Matriks ciri model dan kondisi operasi untuk satu kanal, lewat ekstraktor edge."""
    X = np.empty((waves.shape[0], len(MODEL_FEATURES)))
    running = np.empty(waves.shape[0], dtype=bool)
    for i in range(waves.shape[0]):
        wave = waves[i, ch].astype(np.float64)
        rms = float(np.sqrt(np.mean((wave - wave.mean()) ** 2)))
        running[i] = operating_state(rms, cfg) == "stabil"
        f = extract_features(wave, 0.0, 0.0, cfg)
        X[i] = [f[name] for name in MODEL_FEATURES]
    return X, running


def evaluate_channel(ts, X, running, baseline_days, trigger, recover, cycles, healthy_margin_h, label):
    ts = np.array(ts)
    base, base_start, _ = baseline_mask(list(ts), running, ts[0], baseline_days)
    model = UnitModel.fit(X[base], MODEL_FEATURES)
    health, _ = model.health(X)
    health = np.where(running, health, np.nan)

    end = ts[running][-1]
    after = ~base & running
    healthy = after & np.array([t < end - timedelta(hours=healthy_margin_h) for t in ts])

    trig = None
    for i in np.where(after & (health < trigger))[0]:
        if i + cycles - 1 < len(health) and np.all(health[i:i + cycles] < trigger):
            trig = i
            break

    row = {
        "baseline_n": int(base.sum()),
        "baseline_start": base_start,
        "healthy_median": float(np.nanmedian(health[healthy])) if healthy.any() else float("nan"),
        "healthy_p05": float(np.nanpercentile(health[healthy], 5)) if healthy.any() else float("nan"),
        "false_alarms": int(np.nansum(health[healthy] < trigger)),
        "healthy_days": float((ts[healthy][-1] - ts[healthy][0]).total_seconds() / 86400) if healthy.any() else 0.0,
        "trigger_at": ts[trig] if trig is not None else None,
        "lead_h": float((end - ts[trig]).total_seconds() / 3600) if trig is not None else None,
        "symptom": model.symptom(X[trig])[0] if trig is not None else None,
        "label": label,
        "end": end,
        "path": [(h, float(np.nanmin(health[np.searchsorted(ts, end - timedelta(hours=h)):][:1]) if np.searchsorted(ts, end - timedelta(hours=h)) < len(health) else float("nan")))
                 for h in (72, 48, 36, 24, 12, 6)],
    }
    return row


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="siaga_ai.evaluate", description="Evaluasi offline SIAGA dari cache dataset")
    p.add_argument("--cache", required=True)
    p.add_argument("--channels", default="0,1,2,3", help="indeks kanal cache yang dievaluasi, satu per unit")
    p.add_argument("--failed", default="", help="label kegagalan per posisi kanal, misal 0:bpfo atau 2:bpfi,3:bsf")
    p.add_argument("--baseline-days", type=float, default=1.0)
    p.add_argument("--trigger", type=float, default=40.0)
    p.add_argument("--recover", type=float, default=55.0)
    p.add_argument("--cycles", type=int, default=3)
    p.add_argument("--healthy-margin-h", type=float, default=36.0,
                   help="zona sehat berakhir sekian jam sebelum akhir rekaman")
    p.add_argument("--markdown", action="store_true", help="cetak tabel markdown untuk README")
    args = p.parse_args(argv)

    channels = [int(c) for c in args.channels.split(",")]
    labels = {}
    for item in filter(None, args.failed.split(",")):
        pos, lab = item.split(":")
        labels[int(pos)] = lab

    waves, ts, dataset = load_cache(args.cache)
    cfg = IMS_PUMP_CLASS
    print("%s: %d cuplikan, %s sampai %s, %d kanal dievaluasi" % (
        dataset, len(ts), ts[0].date(), ts[-1].date(), len(channels)), file=sys.stderr)

    rows = []
    for pos, ch in enumerate(channels):
        X, running = features_for_channel(waves, ch, cfg)
        row = evaluate_channel(ts, X, running, args.baseline_days, args.trigger, args.recover,
                               args.cycles, args.healthy_margin_h, labels.get(pos))
        row["unit"] = "Unit %02d (kanal %d)" % (pos + 1, ch)
        rows.append(row)
        print("  %s selesai" % row["unit"], file=sys.stderr)

    fmt_t = lambda t: t.strftime("%d/%m %H:%M") if t else "-"
    fmt_h = lambda h: "%.1f" % h if h is not None else "-"

    if args.markdown:
        print("| Unit | Label | Sehat med / p05 | Alarm palsu (hari sehat) | Pemicu | Lead (jam) | Gejala tebakan | Skor −48/−24/−12 jam |")
        print("| --- | --- | --- | --- | --- | --- | --- | --- |")
    else:
        print("%-18s %-16s %-14s %-22s %-13s %-10s %-12s %s" % (
            "unit", "label", "sehat med/p05", "alarm palsu (hari)", "pemicu", "lead jam", "gejala", "skor -48/-24/-12"))

    for r in rows:
        label = LABEL_NAME.get(r["label"], r["label"]) if r["label"] else "sehat"
        path = {h: v for h, v in r["path"]}
        traj = "%.0f / %.0f / %.0f" % (path[48], path[24], path[12])
        judged = ""
        if r["label"] and r["symptom"]:
            judged = " (tepat)" if r["symptom"] == r["label"] else (" (umum)" if r["symptom"] == "broadband" else " (salah)")
        if args.markdown:
            print("| %s | %s | %.0f / %.0f | %d (%.1f) | %s | %s | %s%s | %s |" % (
                r["unit"], label, r["healthy_median"], r["healthy_p05"], r["false_alarms"], r["healthy_days"],
                fmt_t(r["trigger_at"]), fmt_h(r["lead_h"]), r["symptom"] or "-", judged, traj))
        else:
            print("%-18s %-16s %5.0f / %-6.0f %3d (%5.1f)            %-13s %-10s %-12s %s" % (
                r["unit"], label, r["healthy_median"], r["healthy_p05"], r["false_alarms"], r["healthy_days"],
                fmt_t(r["trigger_at"]), fmt_h(r["lead_h"]), (r["symptom"] or "-") + judged, traj))
    return 0


if __name__ == "__main__":
    sys.exit(main())
