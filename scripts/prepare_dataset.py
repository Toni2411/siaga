# -*- coding: utf-8 -*-
"""Unduh dan siapkan dataset bearing IMS untuk replay.

Sumber: NASA Prognostics Center of Excellence, disediakan oleh Center for
Intelligent Maintenance Systems, University of Cincinnati, dengan dukungan
Rexnord. Rujukan: Qiu, Lee, Lin, "Wavelet Filter-based Weak Signature
Detection Method and its Application on Roller Bearing Prognostics",
Journal of Sound and Vibration 289 (2006).

Arsipnya tiga lapis: zip berisi IMS.7z berisi <set>.rar berisi berkas teks,
satu berkas per cuplikan satu detik pada 20 kHz. Skrip ini membongkar
semuanya, menurunkan laju cuplik ke 3.2 kHz (batas ESP32 dan ADXL345), dan
menyimpan hasilnya sebagai satu .npz kecil. Tiap langkah dilewati kalau
hasilnya sudah ada.

    python scripts/prepare_dataset.py            # set 2, default
    python scripts/prepare_dataset.py --set 1    # set 1, 35 hari, 8 kanal

Butuh: numpy, scipy, pandas, py7zr, dan alat pembuka rar (unrar, bsdtar, tar
bawaan Windows 11, atau 7z).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

URL = "https://phm-datasets.s3.amazonaws.com/NASA/4.+Bearings.zip"
EXPECTED_ZIP_BYTES = 1075597174

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
CACHE = ROOT / "data" / "cache"

SETS = {
    1: dict(rar="1st_test.rar", folder="1st_test", channels=8),
    2: dict(rar="2nd_test.rar", folder="2nd_test", channels=4),
    3: dict(rar="3rd_test.rar", folder="3rd_test", channels=4),
}

SOURCE_RATE = 20000     # Hz, dari readme dataset
TARGET_RATE = 3200      # Hz, laju cuplik edge
SECONDS_PER_FILE = 1    # tiap berkas satu detik; 20480 titik, dipakai 20000


def step(msg):
    print("==> " + msg, flush=True)


def download(zip_path: Path):
    if zip_path.exists() and zip_path.stat().st_size == EXPECTED_ZIP_BYTES:
        step("zip sudah ada, lewati unduhan")
        return
    step("mengunduh %s (1.0 GB)" % URL)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = zip_path.with_suffix(".part")
    t = time.time()

    def hook(blocks, block_size, total):
        done = blocks * block_size
        if blocks % 500 == 0:
            sys.stdout.write("\r    %.0f MB / %.0f MB" % (done / 1048576, total / 1048576))
            sys.stdout.flush()

    urllib.request.urlretrieve(URL, tmp, reporthook=hook)
    print()
    if tmp.stat().st_size != EXPECTED_ZIP_BYTES:
        raise SystemExit("ukuran unduhan %d tidak sesuai, harusnya %d" % (tmp.stat().st_size, EXPECTED_ZIP_BYTES))
    tmp.rename(zip_path)
    step("unduhan selesai dalam %.0f s" % (time.time() - t))


def extract_7z_from_zip(zip_path: Path) -> Path:
    seven = RAW / "4. Bearings" / "IMS.7z"
    if seven.exists():
        step("IMS.7z sudah ada, lewati")
        return seven
    step("mengeluarkan IMS.7z dari zip")
    with zipfile.ZipFile(zip_path) as z:
        z.extract("4. Bearings/IMS.7z", RAW)
    return seven


def extract_rar_from_7z(seven: Path, rar_name: str) -> Path:
    out_dir = RAW / "ims"
    rar = out_dir / rar_name
    if rar.exists():
        step("%s sudah ada, lewati" % rar_name)
        return rar
    import py7zr  # impor di sini supaya --help tetap jalan tanpa py7zr

    step("mengeluarkan %s dari IMS.7z (butuh sekitar satu menit)" % rar_name)
    with py7zr.SevenZipFile(seven, "r") as a:
        a.extract(path=out_dir, targets=[rar_name, "Readme Document for IMS Bearing Data.pdf"])
    return rar


def find_rar_tool() -> list[str]:
    candidates = [
        ["unrar", "x", "-o+"],
        ["bsdtar", "-xf"],
        [r"C:\Windows\System32\tar.exe", "-xf"],
        ["tar", "-xf"],
        ["7z", "x", "-y"],
    ]
    for cmd in candidates:
        if shutil.which(cmd[0]) or Path(cmd[0]).exists():
            return cmd
    raise SystemExit("tidak ada alat pembuka rar: pasang unrar, 7-Zip, atau pakai tar bawaan Windows 11")


def extract_txt_from_rar(rar: Path, folder: str) -> Path:
    out = RAW / "ims" / folder
    if out.exists() and any(out.iterdir()):
        step("%s sudah diekstrak, lewati" % folder)
        return out
    tool = find_rar_tool()
    step("membuka %s dengan %s" % (rar.name, tool[0]))
    subprocess.run(tool + [str(rar)], cwd=RAW / "ims", check=True)
    if not out.exists():
        raise SystemExit("folder %s tidak muncul setelah ekstraksi" % out)
    return out


def build_cache(txt_dir: Path, set_no: int, channels: int, cache_path: Path):
    if cache_path.exists():
        step("cache %s sudah ada, lewati" % cache_path.name)
        return
    import numpy as np
    import pandas as pd
    from scipy.signal import resample_poly

    files = sorted(f for f in os.listdir(txt_dir) if not f.startswith("."))
    step("parsing %d cuplikan, resample %d Hz -> %d Hz" % (len(files), SOURCE_RATE, TARGET_RATE))
    n_in = SOURCE_RATE * SECONDS_PER_FILE
    # 20000 * 4 / 25 = 3200 tepat. resample_poly memasang filter anti-alias
    # sendiri, jadi energi di atas 1.6 kHz tidak melipat ke pita cacat bearing.
    up, down = 4, 25
    n_out = n_in * up // down
    waves = np.empty((len(files), channels, n_out), dtype=np.float32)
    ts = []
    t = time.time()
    for i, fn in enumerate(files):
        raw = pd.read_csv(txt_dir / fn, sep="\t", header=None, dtype=np.float64).to_numpy()
        if raw.shape[1] != channels:
            raise SystemExit("%s punya %d kolom, harusnya %d" % (fn, raw.shape[1], channels))
        for ch in range(channels):
            waves[i, ch] = resample_poly(raw[:n_in, ch], up, down)
        ts.append(datetime.strptime(fn, "%Y.%m.%d.%H.%M.%S").isoformat())
        if (i + 1) % 200 == 0:
            print("    %d/%d" % (i + 1, len(files)), flush=True)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        cache_path,
        waves=waves,
        ts=np.array(ts),
        files=np.array(files),
        sample_rate_hz=np.int32(TARGET_RATE),
        dataset=np.str_("IMS set %d" % set_no),
    )
    step("cache ditulis: %s (%.1f MB, %.0f s)" % (cache_path, cache_path.stat().st_size / 1048576, time.time() - t))


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--set", type=int, default=2, choices=SETS, help="nomor test set IMS (default 2)")
    args = p.parse_args()
    spec = SETS[args.set]

    zip_path = RAW / "4_Bearings.zip"
    download(zip_path)
    seven = extract_7z_from_zip(zip_path)
    rar = extract_rar_from_7z(seven, spec["rar"])
    txt_dir = extract_txt_from_rar(rar, spec["folder"])
    cache = CACHE / ("ims_%s_%dhz.npz" % (spec["folder"], TARGET_RATE))
    build_cache(txt_dir, args.set, spec["channels"], cache)
    step("siap. Jalankan: python -m siaga_edge --cache %s --describe" % cache.relative_to(ROOT))


if __name__ == "__main__":
    main()
