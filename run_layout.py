# -*- coding: utf-8 -*-
"""
CLI otomasi layout peta foto udara per estate (ArcMap 10.x).

Contoh:
    python run_layout.py --dry-run
    python run_layout.py --config D:\\config.xlsx
    python run_layout.py --estate SMSE --jpg
    python run_layout.py --estate SMSE,ABCE --output D:\\Hasil

Kode keluar (exit code):
    0 = semua estate berhasil / valid
    1 = ada estate yang gagal / tidak valid
    2 = kesalahan config (file tidak ada, kolom wajib hilang, kode estate salah)
    3 = arcpy tidak tersedia atau template bermasalah
"""
from __future__ import print_function, unicode_literals

import argparse
import datetime
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config as cfg  # noqa: E402
import layout_core as core  # noqa: E402


# ===========================================================================
# Util
# ===========================================================================
def _arg_teks(nilai):
    """Argumen CLI di Python 2 berupa bytes; ubah ke unicode."""
    if nilai is None or not isinstance(nilai, bytes):
        return nilai
    enc = sys.getfilesystemencoding() or "utf-8"
    return nilai.decode(enc, "replace")


def buat_folder(path):
    if not os.path.isdir(path):
        os.makedirs(path)
    return path


def siapkan_log(folder_log, verbose=False):
    """Log ke file (DEBUG, UTF-8) dan ke konsol (INFO / DEBUG bila verbose)."""
    buat_folder(folder_log)
    waktu = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path_log = os.path.join(folder_log, "layout_%s.log" % waktu)

    log = logging.getLogger("layout_peta")
    log.setLevel(logging.DEBUG)
    for h in list(log.handlers):
        log.removeHandler(h)

    fh = logging.FileHandler(path_log, mode="w", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] "
                                      "%(message)s", "%Y-%m-%d %H:%M:%S"))
    log.addHandler(fh)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG if verbose else logging.INFO)
    ch.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(ch)
    return log, path_log


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Otomasi layout peta foto udara per estate (ArcMap 10.x)")
    p.add_argument("--config",
                   help="file config .xlsx/.csv (default: config.xlsx atau "
                        "config.csv di folder tool)")
    p.add_argument("--estate",
                   help="proses estate tertentu saja, mis. SMSE atau "
                        "SMSE,ABCE")
    p.add_argument("--dry-run", action="store_true",
                   help="hanya validasi config, path, feature class, dan "
                        "template; tidak export apa pun")
    p.add_argument("--jpg", action="store_true",
                   help="export JPG juga selain PDF")
    p.add_argument("--output",
                   help="folder output (default: FOLDER_OUTPUT di config.py)")
    p.add_argument("--timpa", action="store_true",
                   help="timpa file output yang sudah ada (default: beri "
                        "akhiran _v2, _v3, ...)")
    p.add_argument("--verbose", "-v", action="store_true",
                   help="tampilkan detail (DEBUG) di konsol")
    args = p.parse_args(argv)
    for nama in ("config", "estate", "output"):
        setattr(args, nama, _arg_teks(getattr(args, nama)))
    return args


def cari_config(path_arg):
    if path_arg:
        return path_arg
    for p in cfg.CONFIG_DEFAULT:
        if os.path.isfile(p):
            return p
    raise core.ConfigError("file config tidak ditemukan. Buat salah satu: %s "
                           "atau gunakan --config" %
                           ", ".join(cfg.CONFIG_DEFAULT))


def muat_arcmap(log):
    """Import layout_arcmap (butuh arcpy). Mengembalikan modul atau None."""
    try:
        import layout_arcmap
        return layout_arcmap
    except ImportError as e:
        log.debug("import arcpy gagal: %s" % core.pesan_error(e))
        return None


def periksa_template(lam, log):
    """
    Validasi kedua template. Mengembalikan (ok, ukuran_df) dengan
    ukuran_df = {'landscape': (w, h), 'portrait': (w, h)}.
    """
    ok = True
    ukuran_df = {}
    for orientasi, path in (("landscape", cfg.TEMPLATE_LANDSCAPE),
                            ("portrait", cfg.TEMPLATE_PORTRAIT)):
        if lam is None:
            if not os.path.isfile(path):
                log.error("Template %s tidak ditemukan: %s" % (orientasi,
                                                               path))
                ok = False
            continue
        info = lam.info_template(path, cfg)
        for k in info["kesalahan"]:
            log.error("Template %s: %s" % (orientasi, k))
        for w in info["peringatan"]:
            log.warning("Template %s: %s" % (orientasi, w))
        if info["kesalahan"]:
            ok = False
        else:
            log.info("Template %s OK: %s" % (orientasi, path))
        ukuran_df[orientasi] = info["ukuran_df"]
    return ok, ukuran_df


# ===========================================================================
# Dry-run
# ===========================================================================
def jalankan_dry_run(estates, lam, log, ukuran_df=None):
    hasil = []
    for e in estates:
        mulai = time.time()
        keterangan = "siap diproses"
        if e.valid and lam is not None:
            # Pratinjau orientasi dari extent batas estate
            try:
                path_fc = lam.cari_fc(e.path_gdb, e.fc_estate)
                where = core.buat_where_filter(cfg.FIELD_FILTER_ESTATE,
                                               e.kode)
                ext, sr = lam.baca_extent(path_fc, where)
                if cfg.MODE_ORIENTASI == "presisi" and ukuran_df and \
                        all(ukuran_df.get(k) for k in ("landscape",
                                                       "portrait")):
                    orientasi = core.pilih_orientasi_presisi(
                        ext.lebar, ext.tinggi, ukuran_df["landscape"],
                        ukuran_df["portrait"])
                else:
                    orientasi = core.pilih_orientasi(ext.lebar, ext.tinggi)
                keterangan = "siap diproses (extent %.0f x %.0f, %s, %s)" % (
                    ext.lebar, ext.tinggi, orientasi, sr.name)
            except Exception as err:
                e.kesalahan.append("gagal membaca extent: %s"
                                   % core.pesan_error(err))
        status = core.VALID if e.valid else core.TIDAK_VALID
        if not e.valid:
            keterangan = "; ".join(e.kesalahan)
        hasil.append(core.HasilEstate(e.kode, status, keterangan,
                                      time.time() - mulai,
                                      peringatan=e.peringatan))
    return hasil


# ===========================================================================
# Main
# ===========================================================================
def tutup_log(log):
    """Tutup handler log agar file log tidak terkunci (penting di Windows)."""
    for h in list(log.handlers):
        h.close()
        log.removeHandler(h)


def main(argv=None):
    args = parse_args(argv)
    folder_output = args.output or cfg.FOLDER_OUTPUT
    log, path_log = siapkan_log(os.path.join(folder_output, "log"),
                                args.verbose)
    try:
        return jalankan(args, log, path_log, folder_output)
    finally:
        tutup_log(log)


def jalankan(args, log, path_log, folder_output):
    mulai_total = time.time()
    log.info("=" * 78)
    log.info("Layout Peta Foto Udara - %s"
             % datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S"))
    log.info("Mode: %s" % ("DRY-RUN (validasi saja)" if args.dry_run
                           else "PROSES"))
    log.info("Log : %s" % path_log)

    # --- 1. Baca config ---
    try:
        path_config = cari_config(args.config)
        log.info("Config: %s" % path_config)
        baris = core.baca_config(path_config)
    except core.ConfigError as e:
        log.error("Config error: %s" % core.pesan_error(e))
        return 2

    fc_default = {"estate": cfg.FC_ESTATE, "divisi": cfg.FC_DIVISI,
                  "blok": cfg.FC_BLOK}
    estates = [core.buat_estate(b, fc_default) for b in baris]
    try:
        estates = core.filter_estate(estates, args.estate)
    except core.ConfigError as e:
        log.error("Config error: %s" % core.pesan_error(e))
        return 2
    if not estates:
        log.error("Tidak ada estate di config.")
        return 2
    log.info("Jumlah estate: %d" % len(estates))

    # --- 2. Validasi ---
    lam = muat_arcmap(log)
    if lam is None:
        if not args.dry_run:
            log.error("arcpy tidak tersedia. Jalankan dengan Python bawaan "
                      "ArcMap (lihat run_layout.bat).")
            return 3
        log.warning("arcpy tidak tersedia: feature class & template tidak "
                    "dicek secara mendalam.")

    core.validasi_daftar(estates, fc_ada=lam.fc_ada if lam else None)
    for e in estates:
        if e.path_ortho and os.path.isfile(e.path_ortho):
            pesan = core.cek_pyramid(e.path_ortho)
            if pesan:
                e.peringatan.append(pesan)
        for k in e.kesalahan:
            log.warning("[%s] baris %s: %s" % (e.kode or "-", e.baris, k))
        for w in e.peringatan:
            log.warning("[%s] peringatan: %s" % (e.kode or "-", w))

    template_ok, ukuran_df = periksa_template(lam, log)

    if args.dry_run:
        hasil = jalankan_dry_run(estates, lam, log, ukuran_df)
        if not template_ok:
            log.error("Template bermasalah; perbaiki sebelum proses.")
        log.info("\n" + core.buat_ringkasan(hasil, time.time() - mulai_total,
                                            "RINGKASAN DRY-RUN"))
        if not template_ok:
            return 3
        return 0 if all(h.berhasil for h in hasil) else 1

    if not template_ok:
        log.error("Template bermasalah; proses dibatalkan.")
        return 3

    # --- 3. Proses per estate ---
    opsi = {
        "folder_pdf": buat_folder(os.path.join(folder_output, "pdf")),
        "folder_jpg": os.path.join(folder_output, "jpg"),
        "folder_mxd": buat_folder(os.path.join(folder_output, "mxd")),
        "export_jpg": args.jpg or cfg.EXPORT_JPG_DEFAULT,
        "timpa": args.timpa or cfg.TIMPA_OUTPUT,
        "ukuran_df": ukuran_df if (len(ukuran_df) == 2 and
                                   all(ukuran_df.values())) else None,
    }
    if opsi["export_jpg"]:
        buat_folder(opsi["folder_jpg"])

    hasil = []
    for i, e in enumerate(estates):
        log.info("-" * 78)
        log.info("[%d/%d] %s - %s" % (i + 1, len(estates), e.kode, e.nama))
        if not e.valid:
            log.error("  dilewati, validasi gagal: %s" % "; ".join(e.kesalahan))
            hasil.append(core.HasilEstate(e.kode, core.GAGAL,
                                          "validasi: " + "; ".join(e.kesalahan),
                                          0, peringatan=e.peringatan))
            continue
        try:
            h = lam.proses_estate(e, cfg, opsi, log)
        except KeyboardInterrupt:
            log.warning("Dihentikan pengguna (Ctrl+C).")
            hasil.append(core.HasilEstate(e.kode, core.GAGAL,
                                          "dihentikan pengguna"))
            break
        except Exception as err:  # pengaman tambahan
            log.exception("  error tak terduga")
            h = core.HasilEstate(e.kode, core.GAGAL, core.pesan_error(err))
        hasil.append(h)
        if h.berhasil:
            log.info("  SUKSES (%s)" % core.format_durasi(h.durasi))

    log.info("\n" + core.buat_ringkasan(hasil, time.time() - mulai_total))
    log.info("Log lengkap: %s" % path_log)
    return 0 if all(h.berhasil for h in hasil) else 1


if __name__ == "__main__":
    sys.exit(main())
