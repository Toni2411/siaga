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

# Aset statis app (public/) harus tertaut di folder assets image, karena
# sites/assets di volume hanya symlink ke folder lokal tiap container.
# Tanpa ini nginx di container frontend tidak pernah melihat JS app.
RUN ln -s /home/frappe/frappe-bench/apps/siaga/siaga/public /home/frappe/frappe-bench/assets/siaga
