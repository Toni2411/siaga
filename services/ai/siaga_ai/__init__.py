"""AI service SIAGA.

Membaca vektor ciri dari TimescaleDB, menilai kesehatan tiap unit dengan model
anomali yang dilatih pada baseline unit itu sendiri, lalu menulis Health Score
ke ERPNext. Arah panggilannya satu: service ini yang memanggil ERPNext, bukan
sebaliknya, supaya ERP tidak pernah menunggu inferensi.
"""

__version__ = "0.1.0"
