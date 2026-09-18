-- Skema time series SIAGA.
-- Dijalankan sekali saat volume TimescaleDB pertama kali dibuat.

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Vektor ciri disimpan dalam bentuk panjang, satu baris per ciri per waktu.
-- Bentuk ini dipilih supaya menambah ciri baru tidak menuntut perubahan
-- struktur tabel, dan versi skema ikut tercatat di tiap baris.
CREATE TABLE IF NOT EXISTS sensor_reading (
    ts             timestamptz      NOT NULL,
    asset_id       text             NOT NULL,
    feature        text             NOT NULL,
    value          double precision NOT NULL,
    schema_version smallint         NOT NULL DEFAULT 1
);

SELECT create_hypertable('sensor_reading', 'ts', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS sensor_reading_asset_feature_ts
    ON sensor_reading (asset_id, feature, ts DESC);

-- Burst gelombang mentah, satu rekaman dua detik tiap jam, sebagai bukti dan
-- bahan analisis ulang kalau definisi ciri berubah.
CREATE TABLE IF NOT EXISTS raw_burst (
    ts             timestamptz NOT NULL,
    asset_id       text        NOT NULL,
    sample_rate_hz integer     NOT NULL,
    samples        bytea       NOT NULL,
    PRIMARY KEY (asset_id, ts)
);

-- Status operasi alat, dipakai AI service untuk gating: skor anomali hanya
-- dihitung saat alat berjalan stabil.
CREATE TABLE IF NOT EXISTS operating_state (
    ts       timestamptz NOT NULL,
    asset_id text        NOT NULL,
    state    text        NOT NULL CHECK (state IN ('mati', 'start', 'stabil', 'berbeban')),
    PRIMARY KEY (asset_id, ts)
);
