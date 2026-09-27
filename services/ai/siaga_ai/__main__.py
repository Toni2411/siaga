"""CLI AI service.

    python -m siaga_ai --once
    python -m siaga_ai --interval 30
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time

from .config import Settings
from .erpnext import ERPNextClient
from .pipeline import Pipeline
from .timescale import connect

log = logging.getLogger("siaga.ai")


def main(argv=None) -> int:
    settings = Settings()
    p = argparse.ArgumentParser(prog="siaga_ai", description="AI service SIAGA")
    p.add_argument("--once", action="store_true", help="satu siklus lalu keluar")
    p.add_argument("--interval", type=float, default=settings.interval_s, help="detik antar siklus")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args(argv)
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    erp = ERPNextClient(settings.erpnext_url, settings.erpnext_api_key, settings.erpnext_api_secret)

    # Di compose, ERPNext bisa siap beberapa menit setelah container ini.
    # Tunggu dengan sabar alih alih mati dan mengandalkan restart.
    for attempt in range(120):
        try:
            log.info("ERPNext %s sebagai %s, zona waktu %s", settings.erpnext_url, erp.whoami(), erp.tz)
            break
        except Exception as e:  # koneksi, 502 dari nginx, auth belum siap
            if attempt % 6 == 0:
                log.warning("ERPNext belum siap (%s), menunggu", str(e).splitlines()[0][:120])
            time.sleep(5)
    else:
        log.error("ERPNext tidak pernah siap di %s", settings.erpnext_url)
        return 1

    def open_timescale(attempts=60, quiet=False):
        for attempt in range(attempts):
            try:
                return connect(settings.timescale_dsn)
            except Exception as e:
                if not quiet and attempt % 6 == 0:
                    log.warning("TimescaleDB belum siap (%s), menunggu", str(e).splitlines()[0][:120])
                time.sleep(5)
        return None

    conn = open_timescale()
    if conn is None:
        log.error("TimescaleDB tidak pernah siap")
        return 1
    pipeline = Pipeline(settings, erp, conn)

    stop = {"flag": False}

    def handle(signum, frame):
        stop["flag"] = True

    signal.signal(signal.SIGINT, handle)
    signal.signal(signal.SIGTERM, handle)

    while True:
        started = time.monotonic()
        try:
            results = pipeline.run_once()
        except Exception as e:  # ERPNext atau database sedang tidak bisa dihubungi
            log.warning("siklus dilewati: %s", str(e).splitlines()[0][:160])
            results = []
            # Koneksi bisa diputus dari luar: reset demo memutus semua sesi ke
            # database supaya TRUNCATE bisa mengambil kuncinya. Tanpa menyambung
            # ulang, service ini diam selamanya sampai container direstart.
            if getattr(conn, "closed", 0):
                log.warning("koneksi TimescaleDB tertutup, menyambung ulang")
                new_conn = open_timescale(attempts=12, quiet=True)
                if new_conn is not None:
                    conn = new_conn
                    pipeline.conn = conn
                    log.info("koneksi TimescaleDB pulih")
        for r in results:
            log.info("%s: %s -> %s | %s%s", r.asset, r.status_before, r.status_after, r.note,
                     " | model baru" if r.trained else "")
        if args.once or stop["flag"]:
            break
        elapsed = time.monotonic() - started
        time.sleep(max(0.0, args.interval - elapsed))
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
