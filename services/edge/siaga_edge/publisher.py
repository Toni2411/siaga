"""Penerbit pesan ke broker MQTT."""

from __future__ import annotations

import sys
from urllib.parse import urlparse

import paho.mqtt.client as mqtt


class MqttPublisher:
    def __init__(self, url: str = "mqtt://localhost:1883", client_id: str = "siaga-edge"):
        parsed = urlparse(url)
        if parsed.scheme not in ("mqtt", "tcp"):
            raise ValueError("url broker harus mqtt://host:port, dapat %r" % url)
        self.host = parsed.hostname or "localhost"
        self.port = parsed.port or 1883
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id, clean_session=True)
        if parsed.username:
            self.client.username_pw_set(parsed.username, parsed.password)
        self.published = 0

    def connect(self) -> None:
        self.client.connect(self.host, self.port, keepalive=30)
        self.client.loop_start()

    def publish(self, topic: str, payload: bytes) -> None:
        info = self.client.publish(topic, payload, qos=1)
        info.wait_for_publish(timeout=10)
        self.published += 1

    def close(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()


class StdoutPublisher:
    """Pengganti broker untuk uji coba: cetak topik dan payload ke stdout."""

    def __init__(self, stream=None):
        self.stream = stream or sys.stdout
        self.published = 0

    def connect(self) -> None:
        pass

    def publish(self, topic: str, payload: bytes) -> None:
        self.stream.write("%s %s\n" % (topic, payload.decode()))
        self.published += 1

    def close(self) -> None:
        self.stream.flush()
