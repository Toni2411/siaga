"""Loop utama virtual edge: ambil blok, ekstrak ciri, terbitkan."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable

import numpy as np

from . import message
from .config import AssetClassConfig
from .features import extract_features
from .sources import Block

log = logging.getLogger("siaga.edge")

SYNTHETIC_SCALARS = ("current_rms", "temperature_c")


@dataclass
class NominalScalars:
    """Arus dan suhu nominal berderau.

    Dataset IMS hanya memuat getaran. Supaya skema ciri tetap utuh, dua kanal
    skalar diisi nilai nominal dengan derau kecil. Nilainya sengaja tidak
    dikaitkan dengan degradasi, sehingga model tidak bisa "belajar" dari
    sesuatu yang tidak pernah diukur. Pesan menandai keduanya sebagai
    synthetic.
    """

    current_a: float = 12.0
    temperature_c: float = 55.0
    noise: float = 0.02
    seed: int = 0

    def __post_init__(self):
        self._rng = np.random.default_rng(self.seed)

    def sample(self, running: bool) -> tuple[float, float]:
        if not running:
            return 0.0, float(self.temperature_c * 0.5)
        cur = self.current_a * (1.0 + self._rng.normal(0.0, self.noise))
        tmp = self.temperature_c + self._rng.normal(0.0, self.noise * 20)
        return float(cur), float(tmp)


def operating_state(vib_rms: float, cfg: AssetClassConfig) -> str:
    """Klasifikasi state sederhana dari RMS getaran.

    V1 hanya membedakan mati dan stabil. Membedakan start dan berbeban butuh
    kanal arus yang sungguhan, dan itu baru ada saat hardware masuk.
    """
    return "mati" if vib_rms < cfg.off_rms_threshold_g else "stabil"


def run(
    blocks: Iterable[Block],
    publisher,
    cfg: AssetClassConfig,
    scalars: NominalScalars | None = None,
    max_messages: int | None = None,
) -> int:
    """Jalankan loop sampai sumber habis. Mengembalikan jumlah pesan terbit."""
    scalars = scalars or NominalScalars()
    publisher.connect()
    sent = 0
    try:
        for block in blocks:
            vib_rms = float(np.sqrt(np.mean((block.wave - block.wave.mean()) ** 2)))
            state = operating_state(vib_rms, cfg)
            current, temperature = scalars.sample(running=state != "mati")

            features = extract_features(block.wave, current, temperature, cfg)
            msg = message.build(
                source_id=block.source_id,
                ts=block.ts,
                features=features,
                operating_state=state,
                sample_rate_hz=block.sample_rate_hz,
                samples=int(block.wave.size),
                origin=block.origin,
                synthetic=SYNTHETIC_SCALARS,
            )
            publisher.publish(message.topic_for(block.source_id), message.dumps(msg))
            sent += 1
            if sent % 100 == 0:
                log.info("%d pesan terbit, terakhir %s @ %s", sent, block.source_id, msg["ts"])
            if max_messages and sent >= max_messages:
                break
    finally:
        publisher.close()
    return sent
