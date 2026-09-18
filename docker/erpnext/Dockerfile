# Image ERPNext dengan app siaga sudah terpasang di dalamnya.
#
# Dibangun dari akar repo supaya apps/siaga ikut masuk konteks build. Semua
# container ERPNext, termasuk worker dan scheduler, memakai image ini, sehingga
# tidak ada container yang kehilangan modul siaga.
#
# pip install -e hanya mencatat path app di venv. Saat pengembangan, compose
# menimpa path itu dengan bind mount ke ./apps/siaga, sehingga perubahan kode
# langsung terbaca tanpa membangun ulang image.

ARG ERPNEXT_VERSION=v15
FROM frappe/erpnext:${ERPNEXT_VERSION}

USER frappe
WORKDIR /home/frappe/frappe-bench

COPY --chown=frappe:frappe apps/siaga apps/siaga
RUN env/bin/pip install --no-cache-dir -e apps/siaga
