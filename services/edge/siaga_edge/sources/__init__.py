"""Sumber gelombang mentah untuk virtual edge.

Setiap sumber menghasilkan Block: satu potongan gelombang dari satu alat pada
satu waktu virtual. Edge tidak peduli dari mana gelombang itu datang, dan itu
yang membuat ESP32 nanti bisa menggantikan proses ini tanpa perubahan di hulu.
"""

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np


@dataclass
class Block:
    source_id: str
    ts: datetime
    wave: np.ndarray
    sample_rate_hz: int
    origin: dict = field(default_factory=dict)
