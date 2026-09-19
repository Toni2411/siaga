"""Model anomali per unit dan pemetaannya ke skor kesehatan.

Satu model per unit, bukan per kelas: dua pompa bertipe sama punya baseline
getaran berbeda karena dudukan dan bebannya berbeda. Model dilatih hanya pada
data baseline unit itu sendiri saat sehat, lalu menilai seberapa jauh kondisi
sekarang menyimpang dari "seperti apa rasanya saat saya sehat".

Dua pengukur jarak digabung, diambil yang terbesar:

- Isolation Forest untuk penyimpangan multivariat, ketika banyak ciri bergeser
  bersama seperti pada kerusakan yang sudah berkembang.
- Jarak z robust per ciri untuk penyimpangan univariat. Ini perlu karena
  Isolation Forest hampir buta terhadap satu ciri yang melonjak sendirian di
  tengah dua puluh ciri normal, padahal cacat bearing dini persis seperti itu:
  hanya energi BPFO yang naik, sisanya tenang.

Keduanya dikalibrasi ke tepi baseline yang sama, sehingga jarak 1 berarti
"sejauh 5% titik baseline terjauh" untuk kedua ukuran.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import RobustScaler

# Ciri mana yang menunjuk ke gejala fisik apa. Dipakai untuk memilih part
# kandidat dari Asset Class dan untuk menulis alasan pemicu yang bisa dibaca.
SYMPTOM_OF = {
    "bpfo_energy": "bpfo",
    "bpfi_energy": "bpfi",
    "bsf_energy": "bsf",
    "ftf_energy": "ftf",
    "ord_1x": "unbalance",
    "ord_2x": "misalignment",
    "ord_3x": "kelonggaran",
}
SYMPTOM_LABEL = {
    "bpfo": "cacat outer race bearing",
    "bpfi": "cacat inner race bearing",
    "bsf": "cacat elemen gelinding bearing",
    "ftf": "cacat sangkar bearing",
    "unbalance": "ketidakseimbangan rotor",
    "misalignment": "misalignment poros",
    "kelonggaran": "kelonggaran dudukan",
    "broadband": "kenaikan getaran lebar",
}


@dataclass
class Deviation:
    feature: str
    value: float
    baseline: float
    ratio: float
    z: float

    def as_dict(self) -> dict:
        # NaN bukan JSON yang sah; MariaDB menolaknya di kolom JSON.
        ratio = round(self.ratio, 3) if np.isfinite(self.ratio) else None
        return {"feature": self.feature, "value": round(self.value, 6), "baseline": round(self.baseline, 6),
                "ratio": ratio, "z": round(self.z, 2)}


@dataclass
class UnitModel:
    features: tuple[str, ...]
    scaler: RobustScaler
    forest: IsolationForest
    base_median: np.ndarray
    base_mad: np.ndarray
    score_median: float
    score_p05: float
    z_ref: float
    n_baseline: int
    trained_at: datetime
    version: str
    # Laju peluruhan skor terhadap jarak anomali: d=1 (tepi 5% baseline)
    # memberi skor 78, d=3 memberi 47, d=4 memberi 37, di bawah ambang 40.
    # Dipilih dari data IMS: nol alarm palsu di zona sehat keempat bearing,
    # skor sehat bermedian ~85, dan pemicu sekitar satu hari sebelum akhir.
    decay: float = 0.25
    meta: dict = field(default_factory=dict)

    # ---- pelatihan ----

    @classmethod
    def fit(cls, X: np.ndarray, features: tuple[str, ...], random_state: int = 0, **meta) -> "UnitModel":
        if X.ndim != 2 or X.shape[0] < 10:
            raise ValueError("baseline terlalu sedikit: %d baris" % X.shape[0])
        scaler = RobustScaler().fit(X)
        forest = IsolationForest(n_estimators=200, random_state=random_state).fit(scaler.transform(X))
        base_scores = forest.decision_function(scaler.transform(X))
        median = np.median(X, axis=0)
        mad = np.median(np.abs(X - median), axis=0) * 1.4826
        # Lantai 1% dari median: ciri yang nyaris konstan di baseline tidak
        # boleh meledakkan z hanya karena penyebutnya mendekati nol.
        mad = np.maximum(mad, 0.01 * np.abs(median))
        # tepi 95% dari |z| maksimum tiap baris baseline
        zmax = np.max(np.abs((X - median) / (mad + 1e-9)), axis=1)
        z_ref = float(max(np.percentile(zmax, 95), 1e-9))
        trained_at = datetime.now(timezone.utc)
        return cls(
            features=tuple(features),
            scaler=scaler,
            forest=forest,
            base_median=median,
            base_mad=mad,
            score_median=float(np.median(base_scores)),
            score_p05=float(np.percentile(base_scores, 5)),
            z_ref=z_ref,
            n_baseline=int(X.shape[0]),
            trained_at=trained_at,
            version="if1-%s-n%d" % (trained_at.strftime("%Y%m%d%H%M%S"), X.shape[0]),
            meta=meta,
        )

    # ---- penilaian ----

    def raw_scores(self, X: np.ndarray) -> np.ndarray:
        return self.forest.decision_function(self.scaler.transform(np.atleast_2d(X)))

    def forest_distance(self, X: np.ndarray) -> np.ndarray:
        """Jarak multivariat: 0 di median baseline, 1 di tepi 5% baseline."""
        s = self.raw_scores(X)
        spread = max(self.score_median - self.score_p05, 1e-9)
        return np.maximum(0.0, (self.score_median - s) / spread)

    def z_distance(self, X: np.ndarray) -> np.ndarray:
        """Jarak univariat: |z| maksimum antar ciri, 1 di tepi 95% baseline."""
        X = np.atleast_2d(X)
        z = np.abs((X - self.base_median) / (self.base_mad + 1e-9))
        return z.max(axis=1) / self.z_ref

    def distance(self, X: np.ndarray) -> np.ndarray:
        """Jarak anomali gabungan, yang terbesar dari keduanya."""
        return np.maximum(self.forest_distance(X), self.z_distance(X))

    def health(self, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Skor kesehatan 0..100 dan skor anomali mentah (jarak gabungan)."""
        d = self.distance(X)
        return 100.0 * np.exp(-self.decay * d), d

    def confidence(self, target_rows: int = 144) -> float:
        """Keyakinan kasar dari besarnya baseline: 144 cuplikan (satu hari) = 100%."""
        return float(min(100.0, 100.0 * self.n_baseline / target_rows))

    # ---- penjelasan ----

    def explain(self, x: np.ndarray, top: int = 3) -> list[Deviation]:
        """Ciri yang paling menyimpang dari baseline, diurutkan dari yang terjauh."""
        x = np.asarray(x, dtype=float).ravel()
        z = (x - self.base_median) / (self.base_mad + 1e-9)
        order = np.argsort(-np.abs(z))[:top]
        out = []
        for i in order:
            base = float(self.base_median[i])
            ratio = float(x[i] / base) if base > 0 else float("nan")
            out.append(Deviation(self.features[i], float(x[i]), base, ratio, float(z[i])))
        return out

    # Gejala spesifik (bearing, orde poros) hanya disebut kalau z-nya jelas
    # melampaui tepi baseline. Pada laju cuplik 3.2 kHz energi pita tinggi
    # hampir selalu mendominasi, jadi tanpa syarat ini semua kerusakan akan
    # terbaca "cacat bearing" hanya karena BPFO ikut naik sedikit.
    SYMPTOM_MIN_Z_FACTOR = 1.5

    def zscores(self, x: np.ndarray) -> np.ndarray:
        x = np.asarray(x, dtype=float).ravel()
        return (x - self.base_median) / (self.base_mad + 1e-9)

    def symptom(self, x: np.ndarray) -> tuple[str, Deviation | None]:
        """Gejala fisik dari ciri spesifik yang paling menyimpang ke atas."""
        z = self.zscores(x)
        best = None
        for i, f in enumerate(self.features):
            if f in SYMPTOM_OF and z[i] > self.SYMPTOM_MIN_Z_FACTOR * self.z_ref:
                if best is None or z[i] > z[best]:
                    best = i
        if best is None:
            return "broadband", None
        base = float(self.base_median[best])
        ratio = float(x[best] / base) if base > 0 else float("nan")
        return SYMPTOM_OF[self.features[best]], Deviation(self.features[best], float(x[best]), base, ratio, float(z[best]))

    def summary(self, x: np.ndarray, devs: list[Deviation] | None = None) -> str:
        symptom, key = self.symptom(x)
        devs = devs if devs is not None else self.explain(x)

        def fmt(d: Deviation) -> str:
            ratio = "%.1fx" % d.ratio if np.isfinite(d.ratio) else "-"
            return "%s %s baseline (z %+.1f)" % (d.feature, ratio, d.z)

        head = SYMPTOM_LABEL.get(symptom, symptom)
        if key is not None:
            head += " [%s]" % fmt(key)
        return "%s: %s" % (head, "; ".join(fmt(d) for d in devs))

    # ---- simpan / muat ----

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)
        return path

    @staticmethod
    def load(path: str | Path) -> "UnitModel":
        return joblib.load(path)
