-- Skema time series SIAGA.
-- Dijalankan sekali saat volume TimescaleDB pertama kali dibuat.
--
-- Kunci baris adalah source_id, yaitu id yang dipakai edge di topik MQTT
-- (misal PUMP-01), bukan nama aset ERPNext. Pemetaan source_id ke aset ada di
-- DocType Asset Monitoring Profile dan dilakukan oleh AI service. Gateway
-- sengaja tidak tahu apa apa tentang ERPNext.

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Vektor ciri disimpan dalam bentuk panjang, satu baris per ciri per waktu.
-- Bentuk ini dipilih supaya menambah ciri baru tidak menuntut perubahan
-- struktur tabel, dan versi skema ikut tercatat di tiap baris.
CREATE TABLE IF NOT EXISTS sensor_reading (
    ts             timestamptz      NOT NULL,
    source_id      text             NOT NULL,
    feature        text             NOT NULL,
    value          double precision NOT NULL,
    schema_version smallint         NOT NULL DEFAULT 1
);

SELECT create_hypertable('sensor_reading', 'ts', if_not_exists => TRUE);

-- Unik per (sumber, ciri, waktu) supaya replay yang diulang tidak
-- menggandakan data. Gateway memakai ON CONFLICT DO NOTHING.
CREATE UNIQUE INDEX IF NOT EXISTS sensor_reading_unique
    ON sensor_reading (source_id, feature, ts);

-- Burst gelombang mentah, satu rekaman dua detik tiap jam, sebagai bukti dan
-- bahan analisis ulang kalau definisi ciri berubah.
CREATE TABLE IF NOT EXISTS raw_burst (
    ts             timestamptz NOT NULL,
    source_id      text        NOT NULL,
    sample_rate_hz integer     NOT NULL,
    samples        bytea       NOT NULL,
    PRIMARY KEY (source_id, ts)
);

-- Status operasi alat per pesan, dipakai AI service untuk gating: skor
-- anomali hanya dihitung saat alat berjalan stabil.
CREATE TABLE IF NOT EXISTS operating_state (
    ts        timestamptz NOT NULL,
    source_id text        NOT NULL,
    state     text        NOT NULL CHECK (state IN ('mati', 'start', 'stabil', 'berbeban')),
    PRIMARY KEY (source_id, ts)
);
