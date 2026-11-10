# -*- coding: utf-8 -*-
"""
Semua pemanggilan arcpy / arcpy.mapping (ArcMap 10.x, Python 2.7).

Logika murni (perhitungan skala, orientasi, teks, nama file) ada di
layout_core.py; modul ini hanya "menempelkan" hasilnya ke MXD.
"""
from __future__ import print_function, unicode_literals

import os
import time
import traceback

import arcpy

import layout_core as core


class LayoutError(Exception):
    """Kesalahan saat memproses layout satu estate."""
    pass


# ===========================================================================
# Feature class & extent
# ===========================================================================
def cari_fc(path_gdb, nama_fc):
    """
    Cari feature class di File Geodatabase, termasuk yang berada di dalam
    feature dataset. Mengembalikan path lengkap, atau None bila tidak ada.
    """
    if not nama_fc:
        return None
    langsung = os.path.join(path_gdb, nama_fc)
    if arcpy.Exists(langsung):
        return langsung

    ws_lama = arcpy.env.workspace
    try:
        arcpy.env.workspace = path_gdb
        for ds in arcpy.ListDatasets("", "Feature") or []:
            kandidat = os.path.join(path_gdb, ds, nama_fc)
            if arcpy.Exists(kandidat):
                return kandidat
    finally:
        arcpy.env.workspace = ws_lama
    return None


def fc_ada(path_gdb, nama_fc):
    """Dipakai layout_core.validasi_estate sebagai fungsi pengecek FC."""
    return cari_fc(path_gdb, nama_fc) is not None


def baca_extent(path_fc, where=""):
    """
    Hitung extent gabungan semua fitur (opsional difilter `where`) dalam
    sistem koordinat feature class itu sendiri.
    Mengembalikan (core.Extent, arcpy.SpatialReference).
    """
    sr = arcpy.Describe(path_fc).spatialReference
    xmin = ymin = float("inf")
    xmax = ymax = float("-inf")
    jumlah = 0
    with arcpy.da.SearchCursor(path_fc, ["SHAPE@"], where or None) as cur:
        for (geom,) in cur:
            if geom is None:
                continue  # geometri kosong dilewati
            e = geom.extent
            xmin = min(xmin, e.XMin)
            ymin = min(ymin, e.YMin)
            xmax = max(xmax, e.XMax)
            ymax = max(ymax, e.YMax)
            jumlah += 1
    if jumlah == 0:
        raise LayoutError("tidak ada fitur dengan geometri di %s%s"
                          % (path_fc, (" (filter: %s)" % where) if where
                             else ""))
    return core.Extent(xmin, ymin, xmax, ymax), sr


def _ke_arcpy_extent(ext):
    return arcpy.Extent(ext.xmin, ext.ymin, ext.xmax, ext.ymax)


# ===========================================================================
# Template
# ===========================================================================
def _sama(a, b):
    return core.ke_teks(a).strip().lower() == core.ke_teks(b).strip().lower()


def cari_df(mxd, nama):
    """Data frame dengan nama persis (tidak peka huruf besar/kecil)."""
    for df in arcpy.mapping.ListDataFrames(mxd):
        if _sama(df.name, nama):
            return df
    return None


def cari_layer(mxd, nama):
    """
    Semua layer (bukan group layer) bernama `nama` di SEMUA data frame,
    sehingga layer yang sama di data frame Inset ikut diganti sumbernya.
    """
    hasil = []
    for lyr in arcpy.mapping.ListLayers(mxd):
        if lyr.isGroupLayer:
            continue
        if _sama(lyr.name, nama):
            hasil.append(lyr)
    return hasil


def daftar_layer_wajib(cfg):
    return [cfg.LAYER_ORTHO, cfg.LAYER_ESTATE, cfg.LAYER_DIVISI,
            cfg.LAYER_BLOK]


def daftar_elemen_wajib(cfg):
    """Elemen teks utama (TXT_CATATAN opsional, tidak termasuk)."""
    return [nama for nama, _ in core.peta_elemen_dari_config(cfg)
            if nama != getattr(cfg, "ELEMEN_CATATAN", None)]


def info_template(path_template, cfg):
    """
    Periksa template tanpa mengubahnya.
    Mengembalikan dict: kesalahan (list), peringatan (list),
    ukuran_df ((lebar, tinggi) data frame utama dalam satuan halaman / None).
    """
    info = {"kesalahan": [], "peringatan": [], "ukuran_df": None}
    if not os.path.isfile(path_template):
        info["kesalahan"].append("template tidak ditemukan: %s"
                                 % path_template)
        return info
    mxd = None
    try:
        mxd = arcpy.mapping.MapDocument(path_template)
        df = cari_df(mxd, cfg.NAMA_DF_UTAMA)
        if df is None:
            info["kesalahan"].append("data frame '%s' tidak ada"
                                     % cfg.NAMA_DF_UTAMA)
        else:
            info["ukuran_df"] = (df.elementWidth, df.elementHeight)
        if cfg.NAMA_DF_INSET and cari_df(mxd, cfg.NAMA_DF_INSET) is None:
            info["peringatan"].append("data frame Inset '%s' tidak ada "
                                      "(dilewati)" % cfg.NAMA_DF_INSET)
        for nama in daftar_layer_wajib(cfg):
            if not cari_layer(mxd, nama):
                info["kesalahan"].append("layer '%s' tidak ada" % nama)
        nama_elemen = set(e.name for e in
                          arcpy.mapping.ListLayoutElements(mxd,
                                                           "TEXT_ELEMENT"))
        for nama in daftar_elemen_wajib(cfg):
            if nama not in nama_elemen:
                info["peringatan"].append("elemen teks '%s' tidak ada"
                                          % nama)
    except Exception as e:
        info["kesalahan"].append("gagal membuka template: %s"
                                 % core.pesan_error(e))
    finally:
        del mxd
    return info


# ===========================================================================
# Langkah-langkah layout
# ===========================================================================
def ganti_sumber_layer(mxd, estate, path_fc, cfg, where, log):
    """
    Ganti sumber data layer placeholder:
      Orthophoto   -> RASTER_WORKSPACE  (folder, nama file raster + ekstensi)
      Batas *      -> FILEGDB_WORKSPACE (path .gdb, nama feature class)
    path_fc: dict {'estate': path_lengkap, 'divisi': ..., 'blok': ...}
    """
    folder_ortho, nama_ortho = core.pisah_path_raster(estate.path_ortho)
    rencana = [
        (cfg.LAYER_ORTHO, folder_ortho, "RASTER_WORKSPACE", nama_ortho, False),
        (cfg.LAYER_ESTATE, estate.path_gdb, "FILEGDB_WORKSPACE",
         os.path.basename(path_fc["estate"]), True),
        (cfg.LAYER_DIVISI, estate.path_gdb, "FILEGDB_WORKSPACE",
         os.path.basename(path_fc["divisi"]), True),
        (cfg.LAYER_BLOK, estate.path_gdb, "FILEGDB_WORKSPACE",
         os.path.basename(path_fc["blok"]), True),
    ]
    for nama_layer, ws, jenis_ws, dataset, pakai_filter in rencana:
        layers = cari_layer(mxd, nama_layer)
        if not layers:
            raise LayoutError("layer '%s' tidak ada di template" % nama_layer)
        for lyr in layers:
            if not lyr.supports("DATASOURCE"):
                raise LayoutError("layer '%s' tidak mendukung penggantian "
                                  "sumber data" % nama_layer)
            try:
                lyr.replaceDataSource(ws, jenis_ws, dataset, True)
            except ValueError as e:
                raise LayoutError("replaceDataSource gagal untuk layer '%s' "
                                  "-> %s\\%s (%s): %s"
                                  % (nama_layer, ws, dataset, jenis_ws,
                                     core.pesan_error(e)))
            if lyr.isBroken:
                raise LayoutError("layer '%s' masih broken setelah "
                                  "replaceDataSource ke %s\\%s"
                                  % (nama_layer, ws, dataset))
            if pakai_filter and where and lyr.supports("DEFINITIONQUERY"):
                lyr.definitionQuery = where
            log.debug("  layer '%s' -> %s" % (nama_layer, lyr.dataSource))


def atur_extent_dan_skala(df, extent, sr, cfg):
    """
    Set sistem koordinat & extent data frame utama (batas estate + buffer),
    lalu bulatkan skala ke atas ke daftar skala standar.
    Mengembalikan (skala_asli, skala_bulat, pesan_peringatan_atau_None).
    """
    df.spatialReference = sr
    ext_buffer = core.tambah_buffer(extent, cfg.BUFFER_PERSEN)
    df.extent = _ke_arcpy_extent(ext_buffer)
    skala_asli = df.scale
    skala, pesan = core.bulatkan_skala(skala_asli, cfg.DAFTAR_SKALA,
                                       cfg.KELIPATAN_SKALA_LEBIH)
    df.scale = skala  # pusat peta tetap; hanya skala yang diubah
    return skala_asli, skala, pesan


def atur_inset(mxd, extent, sr, cfg, log):
    """Data frame Inset (opsional): tampilkan estate dengan buffer besar."""
    if not cfg.NAMA_DF_INSET:
        return
    df = cari_df(mxd, cfg.NAMA_DF_INSET)
    if df is None:
        log.debug("  data frame Inset tidak ada, dilewati")
        return
    df.spatialReference = sr
    df.extent = _ke_arcpy_extent(
        core.tambah_buffer(extent, cfg.BUFFER_INSET_PERSEN))


def isi_teks(mxd, teks):
    """
    Isi elemen teks berdasarkan Element Name.
    Mengembalikan list nama elemen yang tidak ditemukan di template.
    """
    sisa = dict(teks)
    for elm in arcpy.mapping.ListLayoutElements(mxd, "TEXT_ELEMENT"):
        if elm.name in sisa:
            # Teks kosong tidak diizinkan ArcMap -> pakai satu spasi
            elm.text = sisa.pop(elm.name) or " "
    return sorted(sisa.keys())


def export_pdf(mxd, path, cfg):
    arcpy.mapping.ExportToPDF(
        mxd, path, "PAGE_LAYOUT",
        resolution=cfg.DPI_PDF,
        image_quality=cfg.PDF_KUALITAS_GAMBAR,
        georef_info=cfg.PDF_GEOREF)


def export_jpg(mxd, path, cfg):
    arcpy.mapping.ExportToJPEG(
        mxd, path, "PAGE_LAYOUT",
        resolution=cfg.DPI_JPG,
        jpeg_quality=cfg.KUALITAS_JPG)


def _path_sama(a, b):
    return os.path.normcase(os.path.abspath(a)) == \
        os.path.normcase(os.path.abspath(b))


# ===========================================================================
# Proses satu estate
# ===========================================================================
def proses_estate(estate, cfg, opsi, log):
    """
    Jalankan seluruh alur layout untuk satu estate. TIDAK melempar exception:
    semua kesalahan dikembalikan sebagai HasilEstate berstatus GAGAL agar
    estate lain tetap diproses.

    opsi (dict):
      folder_pdf, folder_jpg, folder_mxd : folder output
      export_jpg : bool
      timpa      : bool, timpa file output yang sudah ada
      ukuran_df  : {'landscape': (w, h), 'portrait': (w, h)} (mode presisi)
    """
    mulai = time.time()
    peringatan = list(estate.peringatan)
    file_output = []
    mxd = None
    try:
        where = core.buat_where_filter(cfg.FIELD_FILTER_ESTATE, estate.kode)

        # --- a. Extent batas estate & orientasi ---
        path_fc = {}
        for jenis, nama_fc in estate.daftar_fc():
            path = cari_fc(estate.path_gdb, nama_fc)
            if path is None:
                raise LayoutError("feature class batas %s '%s' tidak "
                                  "ditemukan di %s"
                                  % (jenis, nama_fc, estate.path_gdb))
            path_fc[jenis] = path

        extent, sr = baca_extent(path_fc["estate"], where)
        if sr.type == "Geographic":
            peringatan.append("batas estate dalam koordinat geografis (%s); "
                              "orientasi & skala kurang akurat, disarankan "
                              "proyeksi UTM" % sr.name)

        if cfg.MODE_ORIENTASI == "presisi" and opsi.get("ukuran_df"):
            orientasi = core.pilih_orientasi_presisi(
                extent.lebar, extent.tinggi,
                opsi["ukuran_df"]["landscape"], opsi["ukuran_df"]["portrait"])
        else:
            orientasi = core.pilih_orientasi(extent.lebar, extent.tinggi)
        template = cfg.TEMPLATE_LANDSCAPE if orientasi == "landscape" \
            else cfg.TEMPLATE_PORTRAIT
        log.info("  extent %.0f x %.0f (%s) -> %s"
                 % (extent.lebar, extent.tinggi, sr.name, orientasi))

        # --- b. Buka template & ganti sumber layer ---
        if not os.path.isfile(template):
            raise LayoutError("template tidak ditemukan: %s" % template)
        mxd = arcpy.mapping.MapDocument(template)
        df = cari_df(mxd, cfg.NAMA_DF_UTAMA)
        if df is None:
            raise LayoutError("data frame '%s' tidak ada di template %s"
                              % (cfg.NAMA_DF_UTAMA, template))
        ganti_sumber_layer(mxd, estate, path_fc, cfg, where, log)

        # --- c. Extent + buffer, pembulatan skala ---
        skala_asli, skala, pesan = atur_extent_dan_skala(df, extent, sr, cfg)
        if pesan:
            peringatan.append(pesan)
        log.info("  skala 1:%.0f -> %s" % (skala_asli,
                                            core.format_skala(skala)))
        atur_inset(mxd, extent, sr, cfg, log)

        # --- d. Elemen teks ---
        teks = core.susun_teks(estate, skala,
                               core.peta_elemen_dari_config(cfg))
        hilang = isi_teks(mxd, teks)
        for nama in hilang:
            if nama != getattr(cfg, "ELEMEN_CATATAN", None):
                peringatan.append("elemen teks '%s' tidak ada di template"
                                  % nama)

        # --- e. Export ---
        nama_dasar = core.nama_dasar_output(estate.kode, estate.tanggal,
                                            cfg.POLA_NAMA_FILE)
        timpa = opsi.get("timpa", False)
        path_pdf = core.path_output_unik(opsi["folder_pdf"], nama_dasar,
                                         ".pdf", timpa)
        log.info("  export PDF %d dpi: %s" % (cfg.DPI_PDF, path_pdf))
        t0 = time.time()
        export_pdf(mxd, path_pdf, cfg)
        log.info("  PDF selesai (%s)" % core.format_durasi(time.time() - t0))
        file_output.append(path_pdf)

        if opsi.get("export_jpg"):
            path_jpg = core.path_output_unik(opsi["folder_jpg"], nama_dasar,
                                             ".jpg", timpa)
            log.info("  export JPG %d dpi: %s" % (cfg.DPI_JPG, path_jpg))
            export_jpg(mxd, path_jpg, cfg)
            file_output.append(path_jpg)

        # --- f. Salinan MXD (template tidak pernah ditimpa) ---
        if cfg.SIMPAN_MXD:
            path_mxd = core.path_output_unik(opsi["folder_mxd"], nama_dasar,
                                             ".mxd", timpa)
            if _path_sama(path_mxd, template):
                raise LayoutError("path salinan MXD sama dengan template, "
                                  "dibatalkan: %s" % path_mxd)
            mxd.saveACopy(path_mxd)
            file_output.append(path_mxd)
            log.info("  MXD disimpan: %s" % path_mxd)

        keterangan = "%s, %s -> %s" % (
            core.format_skala(skala), orientasi,
            ", ".join(os.path.basename(p) for p in file_output))
        return core.HasilEstate(estate.kode, core.SUKSES, keterangan,
                                time.time() - mulai, file_output, peringatan)

    except Exception as e:
        log.error("  GAGAL: %s" % core.pesan_error(e))
        log.debug(traceback.format_exc())
        return core.HasilEstate(estate.kode, core.GAGAL, core.pesan_error(e),
                                time.time() - mulai, file_output, peringatan)
    finally:
        # Lepaskan referensi MXD agar file lock (.lock) dilepas
        del mxd
