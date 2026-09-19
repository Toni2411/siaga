"""Siklus penilaian per aset.

Mesin status profil pemantauan:

    Belum terdaftar -> Mengumpulkan baseline -> Dipantau
                                             -> Ditangguhkan (manual)

Baseline adalah data sehat unit itu sendiri selama baseline_days pertama.
Setelah cukup, model per unit dilatih dan setiap cuplikan berikutnya dinilai.
Cuplikan dengan kondisi selain stabil tidak dinilai sama sekali: skor anomali
pada alat mati atau sedang start hanya derau.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from .config import MODEL_FEATURES, Settings
from .erpnext import ERPNextClient
from .model import UnitModel
from .projection import project
from .timescale import FeatureFrame, load_features

log = logging.getLogger("siaga.ai.pipeline")

PROFILE_FIELDS = ["name", "asset", "asset_class", "data_source_id", "monitoring_status",
                  "baseline_started_on", "baseline_completed_on", "model_version", "last_score_at"]
CLASS_FIELDS = ["name", "monitoring_enabled", "baseline_days", "threshold_trigger",
                "threshold_recover", "consecutive_cycles"]


@dataclass
class CycleResult:
    asset: str
    status_before: str
    status_after: str
    scored: int = 0
    trained: bool = False
    last_score: float | None = None
    note: str = ""


class Pipeline:
    def __init__(self, settings: Settings, erp: ERPNextClient, conn):
        self.settings = settings
        self.erp = erp
        self.conn = conn
        self.models: dict[str, UnitModel] = {}
        self._classes: dict[str, dict] = {}

    # ---- pembantu ----

    def asset_class(self, name: str) -> dict:
        if name not in self._classes:
            self._classes[name] = self.erp.get("Asset Class", name)
        return self._classes[name]

    def model_path(self, asset: str) -> Path:
        safe = asset.replace("/", "_").replace(" ", "_")
        return Path(self.settings.model_dir) / ("%s.joblib" % safe)

    def load_model(self, asset: str) -> UnitModel | None:
        if asset in self.models:
            return self.models[asset]
        path = self.model_path(asset)
        if path.exists():
            self.models[asset] = UnitModel.load(path)
            return self.models[asset]
        return None

    # ---- satu siklus untuk semua aset ----

    def run_once(self) -> list[CycleResult]:
        profiles = self.erp.get_list("Asset Monitoring Profile", PROFILE_FIELDS)
        results = []
        for p in profiles:
            try:
                results.append(self.process(p))
            except Exception:
                log.exception("gagal memproses %s", p.get("asset"))
        return results

    # ---- satu aset ----

    def process(self, profile: dict) -> CycleResult:
        asset = profile["asset"]
        status = profile["monitoring_status"]
        res = CycleResult(asset=asset, status_before=status, status_after=status)

        if status == "Ditangguhkan":
            res.note = "ditangguhkan"
            return res
        source = profile.get("data_source_id")
        if not source or not profile.get("asset_class"):
            res.note = "tanpa sumber data atau kelas"
            return res
        cls = self.asset_class(profile["asset_class"])
        if not cls.get("monitoring_enabled"):
            res.note = "pemantauan kelas nonaktif"
            return res

        if status == "Belum terdaftar":
            frame = load_features(self.conn, source)
            if not len(frame):
                res.note = "belum ada data"
                return res
            started = frame.ts[0]
            self.erp.set_value("Asset Monitoring Profile", profile["name"], {
                "monitoring_status": "Mengumpulkan baseline",
                "baseline_started_on": self.erp.to_site(started),
            })
            profile["monitoring_status"] = "Mengumpulkan baseline"
            profile["baseline_started_on"] = self.erp.to_site(started)
            status = res.status_after = "Mengumpulkan baseline"
            log.info("%s: mulai mengumpulkan baseline sejak %s", asset, started.isoformat())

        if status == "Mengumpulkan baseline":
            return self._collect_baseline(profile, cls, source, res)

        if status == "Dipantau":
            return self._score_new(profile, cls, source, res)

        res.note = "status tidak dikenal: %s" % status
        return res

    def _collect_baseline(self, profile, cls, source, res: CycleResult) -> CycleResult:
        started = self.erp.from_site(profile["baseline_started_on"])
        window_end = started + timedelta(days=float(cls.get("baseline_days") or 1))
        frame = load_features(self.conn, source)
        if not len(frame) or frame.ts[-1] < window_end:
            res.note = "baseline belum lengkap sampai %s" % window_end.isoformat()
            return res

        ts = np.array(frame.ts)
        in_window = np.array([(started <= t <= window_end) for t in frame.ts]) & frame.running
        n = int(in_window.sum())
        if n < self.settings.min_baseline_rows:
            res.note = "hanya %d cuplikan sehat di baseline, minimal %d" % (n, self.settings.min_baseline_rows)
            return res

        model = UnitModel.fit(frame.X[in_window], frame.features,
                              asset=profile["asset"], source_id=source, baseline_end=window_end.isoformat())
        model.save(self.model_path(profile["asset"]))
        self.models[profile["asset"]] = model
        res.trained = True
        log.info("%s: model %s dilatih dari %d cuplikan baseline", profile["asset"], model.version, n)

        # Penanda skor terakhir tidak boleh mundur: kalau model dilatih ulang
        # (misal volume model hilang), riwayat yang sudah dinilai jangan
        # dinilai dua kali.
        previous = self.erp.from_site(profile.get("last_score_at"))
        resume_from = max(window_end, previous) if previous else window_end
        self.erp.set_value("Asset Monitoring Profile", profile["name"], {
            "monitoring_status": "Dipantau",
            "baseline_completed_on": self.erp.to_site(window_end),
            "model_version": model.version,
            "model_trained_on": self.erp.to_site(model.trained_at),
            "last_score_at": self.erp.to_site(resume_from),
        })
        profile["monitoring_status"] = "Dipantau"
        profile["last_score_at"] = self.erp.to_site(resume_from)
        res.status_after = "Dipantau"

        # nilai sisa data setelah baseline pada siklus yang sama
        return self._score_new(profile, cls, source, res)

    def _score_new(self, profile, cls, source, res: CycleResult) -> CycleResult:
        model = self.load_model(profile["asset"])
        if model is None:
            res.note = "model hilang, kembali mengumpulkan baseline"
            self.erp.set_value("Asset Monitoring Profile", profile["name"], {"monitoring_status": "Mengumpulkan baseline"})
            res.status_after = "Mengumpulkan baseline"
            return res

        last = self.erp.from_site(profile.get("last_score_at"))
        window = timedelta(hours=self.settings.projection_window_h)
        # muat sedikit riwayat sebelum `last` supaya proyeksi punya konteks
        frame = load_features(self.conn, source, since=(last - window) if last else None)
        if not len(frame):
            res.note = "tidak ada data baru"
            return res

        health, raw = model.health(frame.X)
        running = frame.running
        health_run = np.where(running, health, np.nan)
        is_new = np.array([(last is None) or (t > last) for t in frame.ts])

        docs = []
        threshold = float(cls.get("threshold_trigger") or 40)
        conf = model.confidence()
        for i in np.where(is_new & running)[0]:
            t = frame.ts[i]
            devs = model.explain(frame.X[i])
            symptom, _ = model.symptom(frame.X[i])
            lo = t - window
            hist = [(frame.ts[j], health_run[j]) for j in range(0, i + 1) if frame.ts[j] >= lo]
            proj = project([h[0] for h in hist], np.array([h[1] for h in hist]), threshold)
            docs.append({
                "doctype": "Health Score",
                "asset": profile["asset"],
                "scored_at": self.erp.to_site(t),
                "score": round(float(health[i]), 2),
                "anomaly_score": round(float(raw[i]), 5),
                "operating_state": frame.state[i],
                "confidence": round(conf, 1),
                "model_version": model.version,
                "has_projection": 0 if proj is None else 1,
                "days_to_threshold": 0 if proj is None else round(proj.days, 2),
                "projection_low": 0 if proj is None else round(proj.low, 2),
                "projection_high": 0 if proj is None or proj.high is None else round(proj.high, 2),
                "trigger_summary": model.summary(frame.X[i], devs),
                "top_features": json.dumps({"symptom": symptom, "deviations": [d.as_dict() for d in devs]}),
            })

        for k in range(0, len(docs), self.settings.insert_batch):
            self.erp.insert_many(docs[k:k + self.settings.insert_batch])
        res.scored = len(docs)

        # cuplikan baru yang tidak dinilai (mati dsb) tetap memajukan penanda
        newest = max((frame.ts[i] for i in np.where(is_new)[0]), default=None)
        values = {}
        if newest is not None:
            values["last_score_at"] = self.erp.to_site(newest)
        if docs:
            values["last_score"] = docs[-1]["score"]
            res.last_score = docs[-1]["score"]
        if values:
            self.erp.set_value("Asset Monitoring Profile", profile["name"], values)
        skipped = int((is_new & ~running).sum())
        res.note = "%d dinilai, %d dilewati (tidak stabil)" % (len(docs), skipped)
        return res
