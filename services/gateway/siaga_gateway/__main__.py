"""CLI gateway.

    python -m siaga_gateway
    SIAGA_MQTT_URL=mqtt://mosquitto:1883 SIAGA_TIMESCALE_DSN=postgresql://... python -m siaga_gateway
"""

from __future__ import annotations

import argparse
import logging
import os
import queue
import signal
import sys
import time
from urllib.parse import urlparse

import paho.mqtt.client as mqtt

from siaga_edge.message import TOPIC_PREFIX, loads

from .store import TimescaleStore

log = logging.getLogger("siaga.gateway")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="siaga_gateway", description="Gateway SIAGA: MQTT ke TimescaleDB")
    p.add_argument("--broker", default=os.environ.get("SIAGA_MQTT_URL", "mqtt://localhost:1883"))
    p.add_argument("--dsn", default=os.environ.get(
        "SIAGA_TIMESCALE_DSN", "postgresql://siaga:siaga@localhost:5432/siaga_ts"))
    p.add_argument("--topic", default=TOPIC_PREFIX + "/+/features")
    p.add_argument("--batch-size", type=int, default=int(os.environ.get("SIAGA_BATCH_SIZE", "200")))
    p.add_argument("--flush-interval", type=float, default=0.25, help="detik menunggu saat antrean kosong")
    p.add_argument("--log-level", default=os.environ.get("SIAGA_LOG_LEVEL", "INFO"))
    args = p.parse_args(argv)

    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    store = TimescaleStore(args.dsn)
    store.connect()

    rejected = {"count": 0}
    inbox: queue.Queue = queue.Queue()

    def on_connect(client, userdata, flags, reason_code, properties):
        log.info("terhubung ke broker, berlangganan %s", args.topic)
        client.subscribe(args.topic, qos=1)

    def on_message(client, userdata, m):
        # Jalan di thread jaringan paho. Hanya validasi lalu antrekan;
        # penulisan ke database dilakukan thread utama dalam batch.
        try:
            inbox.put(loads(m.payload))
        except ValueError as e:
            rejected["count"] += 1
            log.warning("pesan ditolak di %s: %s", m.topic, e)

    def flush() -> int:
        batch = []
        try:
            while len(batch) < args.batch_size:
                batch.append(inbox.get_nowait())
        except queue.Empty:
            pass
        if not batch:
            return 0
        try:
            store.write_many(batch)
        except Exception:
            log.exception("gagal menulis batch %d pesan", len(batch))
            return 0
        last = batch[-1]
        if store.messages // args.batch_size != (store.messages - len(batch)) // args.batch_size:
            log.info("%d pesan, %d baris, %d ditolak; terakhir %s @ %s",
                     store.messages, store.rows, rejected["count"], last["source_id"], last["ts"])
        return len(batch)

    parsed = urlparse(args.broker)
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="siaga-gateway")
    if parsed.username:
        client.username_pw_set(parsed.username, parsed.password)
    client.on_connect = on_connect
    client.on_message = on_message

    stop = {"flag": False}

    def handle_signal(signum, frame):
        stop["flag"] = True

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # Sambung dengan percobaan ulang, karena di compose broker bisa hidup
    # beberapa detik setelah gateway.
    for attempt in range(30):
        try:
            client.connect(parsed.hostname or "localhost", parsed.port or 1883, keepalive=30)
            break
        except OSError as e:
            log.warning("broker belum siap (%s), coba lagi", e)
            time.sleep(2)
    else:
        log.error("tidak bisa terhubung ke broker %s", args.broker)
        return 1

    client.loop_start()
    try:
        while not stop["flag"]:
            if flush() == 0:
                time.sleep(args.flush_interval)
        while flush():
            pass  # kosongkan antrean sebelum berhenti
    finally:
        client.loop_stop()
        client.disconnect()
        store.close()
        log.info("berhenti: %d pesan, %d baris, %d ditolak", store.messages, store.rows, rejected["count"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
