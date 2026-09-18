"""CLI virtual edge.

    python -m siaga_edge --cache data/cache/ims_2nd_test_3200hz.npz --speed 600
    python -m siaga_edge --cache ... --dry-run --limit 3
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime

from .config import IMS_PUMP_CLASS
from .publisher import MqttPublisher, StdoutPublisher
from .runner import run
from .sources.ims import IMSReplay, describe


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="siaga_edge", description="Virtual edge SIAGA")
    p.add_argument("--cache", default=os.environ.get("SIAGA_CACHE", "data/cache/ims_2nd_test_3200hz.npz"))
    p.add_argument("--broker", default=os.environ.get("SIAGA_MQTT_URL", "mqtt://localhost:1883"))
    p.add_argument("--speed", type=float, default=float(os.environ.get("SIAGA_REPLAY_SPEED", "600")),
                   help="faktor percepatan; 1 = waktu asli, 600 = satu cuplikan per detik, 0 = tanpa jeda")
    p.add_argument("--start", default=os.environ.get("SIAGA_REPLAY_START"),
                   help="cap waktu virtual untuk cuplikan pertama (ISO 8601, timezone-aware). Default: berakhir sekarang")
    p.add_argument("--first", type=int, default=int(os.environ.get("SIAGA_REPLAY_FIRST", "0")))
    p.add_argument("--limit", type=int, default=None, help="jumlah cuplikan yang diputar")
    p.add_argument("--sources", default=os.environ.get("SIAGA_SOURCE_IDS", "PUMP-01,PUMP-02,PUMP-03,PUMP-04"))
    p.add_argument("--dry-run", action="store_true", help="cetak ke stdout, jangan terbitkan ke broker")
    p.add_argument("--describe", action="store_true", help="tampilkan ringkasan cache lalu keluar")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args(argv)

    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log = logging.getLogger("siaga.edge")

    if args.describe:
        for k, v in describe(args.cache).items():
            print("%-10s %s" % (k, v))
        return 0

    start = datetime.fromisoformat(args.start) if args.start else None
    source = IMSReplay(
        args.cache,
        source_ids=tuple(s.strip() for s in args.sources.split(",")),
        speed=args.speed,
        start=start,
        first=args.first,
        limit=args.limit,
    )
    log.info("replay %d cuplikan x %d alat, speed %.0f, mulai %s",
             source.snapshots, len(source.source_ids), source.speed, source.start.isoformat())

    publisher = StdoutPublisher() if args.dry_run else MqttPublisher(args.broker)
    sent = run(source, publisher, IMS_PUMP_CLASS)
    log.info("selesai, %d pesan terbit", sent)
    return 0


if __name__ == "__main__":
    sys.exit(main())
