"""Gateway SIAGA: dari MQTT ke TimescaleDB.

Menerima vektor ciri dari edge, memvalidasi terhadap kontrak pesan, dan
menyimpannya sebagai time series. Tidak tahu apa apa tentang ERPNext, dan tidak
tahu siapa penerbitnya, sehingga ESP32 nanti bisa menggantikan virtual edge
tanpa ada yang berubah di sini.
"""

__version__ = "0.1.0"
