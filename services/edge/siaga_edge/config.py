"""Konfigurasi kelas alat.

Isi kelas ini nanti tinggal di DocType Asset Class di ERPNext. Di sisi edge ia
dipakai untuk menurunkan frekuensi cacat bearing dari geometri, sehingga
menambah kelas alat baru berarti mengisi angka, bukan menulis kode.
"""

from dataclasses import dataclass
from math import cos, radians

SAMPLE_RATE_HZ = 3200
WINDOW_SIZE = 1024


@dataclass(frozen=True)
class AssetClassConfig:
    """Geometri dan parameter operasi satu kelas alat."""

    name: str
    rpm: float
    rolling_elements: int
    ball_diameter_mm: float
    pitch_diameter_mm: float
    contact_angle_deg: float = 0.0

    sample_rate_hz: int = SAMPLE_RATE_HZ
    window_size: int = WINDOW_SIZE

    # Lebar jendela integrasi di sekitar tiap frekuensi cacat. Perlu ada karena
    # slip bearing membuat frekuensi sebenarnya meleset beberapa persen dari
    # nilai teoretis.
    defect_tolerance_hz: float = 5.0
    defect_harmonics: int = 2
    order_tolerance_hz: float = 3.0

    @property
    def shaft_hz(self) -> float:
        return self.rpm / 60.0

    @property
    def _ratio(self) -> float:
        """(d/D) cos(phi), faktor yang muncul di semua rumus frekuensi cacat."""
        return (
            self.ball_diameter_mm / self.pitch_diameter_mm
        ) * cos(radians(self.contact_angle_deg))

    @property
    def ftf_hz(self) -> float:
        """Fundamental train frequency, laju putar sangkar bearing."""
        return 0.5 * self.shaft_hz * (1.0 - self._ratio)

    @property
    def bpfo_hz(self) -> float:
        """Ball pass frequency, outer race."""
        return 0.5 * self.rolling_elements * self.shaft_hz * (1.0 - self._ratio)

    @property
    def bpfi_hz(self) -> float:
        """Ball pass frequency, inner race."""
        return 0.5 * self.rolling_elements * self.shaft_hz * (1.0 + self._ratio)

    @property
    def bsf_hz(self) -> float:
        """Ball spin frequency."""
        ratio = self._ratio
        return (
            0.5
            * (self.pitch_diameter_mm / self.ball_diameter_mm)
            * self.shaft_hz
            * (1.0 - ratio * ratio)
        )

    @property
    def nyquist_hz(self) -> float:
        return self.sample_rate_hz / 2.0

    def defect_frequencies(self) -> dict:
        return {
            "bpfo": self.bpfo_hz,
            "bpfi": self.bpfi_hz,
            "bsf": self.bsf_hz,
            "ftf": self.ftf_hz,
        }


# Bearing Rexnord ZA-2115 pada rig IMS, empat unit di satu poros 2000 RPM.
# Dipakai sebagai kelas alat pertama karena dataset run to failure-nya publik.
IMS_PUMP_CLASS = AssetClassConfig(
    name="Pompa dewatering listrik",
    rpm=2000.0,
    rolling_elements=16,
    ball_diameter_mm=8.4074,   # 0.331 in
    pitch_diameter_mm=71.501,  # 2.815 in
    contact_angle_deg=15.17,
)
