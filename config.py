# -*- coding: utf-8 -*-
"""
Pengaturan tool otomasi layout peta foto udara (ArcMap 10.x).

Ubah nilai-nilai di file ini sesuai lingkungan kerja Anda.
Semua path Windows ditulis sebagai raw string (r"...") agar backslash aman.
"""
from __future__ import print_function, unicode_literals

import os

# Folder tempat file-file tool ini berada
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Template MXD (A3). Template TIDAK pernah ditimpa; hasil disimpan via saveACopy.
# ---------------------------------------------------------------------------
TEMPLATE_LANDSCAPE = os.path.join(BASE_DIR, "template", "Template_A3_Landscape.mxd")
TEMPLATE_PORTRAIT = os.path.join(BASE_DIR, "template", "Template_A3_Portrait.mxd")

# ---------------------------------------------------------------------------
# Config estate & folder output
# ---------------------------------------------------------------------------
# File config default bila --config tidak diberikan (dicoba berurutan)
CONFIG_DEFAULT = [
    os.path.join(BASE_DIR, "config.xlsx"),
    os.path.join(BASE_DIR, "config.csv"),
]

# Folder output utama; subfolder pdf/, jpg/, mxd/, log/ dibuat otomatis
FOLDER_OUTPUT = os.path.join(BASE_DIR, "output")

# True  = file output dengan nama sama ditimpa
# False = diberi akhiran _v2, _v3, ... agar file lama tidak hilang
TIMPA_OUTPUT = False

# Simpan salinan MXD per estate (saveACopy)
SIMPAN_MXD = True

# ---------------------------------------------------------------------------
# Skala & extent
# ---------------------------------------------------------------------------
# Daftar skala standar (penyebut). Skala hasil dibulatkan KE ATAS ke daftar ini.
DAFTAR_SKALA = [5000, 7500, 10000, 15000, 20000, 25000, 50000]

# Bila skala melebihi skala terbesar di daftar, dibulatkan ke atas
# ke kelipatan nilai ini (dan dicatat sebagai peringatan di log).
KELIPATAN_SKALA_LEBIH = 10000

# Buffer di sekeliling batas estate, dalam persen dari sisi terpanjang extent.
BUFFER_PERSEN = 5.0

# Buffer untuk data frame "Inset" (persen dari sisi terpanjang extent estate).
BUFFER_INSET_PERSEN = 300.0

# Cara memilih orientasi:
#   "sederhana" -> landscape bila lebar >= tinggi, selain itu portrait
#   "presisi"   -> pilih template yang menghasilkan skala paling detail
#                  berdasarkan rasio data frame "Peta Utama" di tiap template
MODE_ORIENTASI = "sederhana"

# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
DPI_PDF = 300
DPI_JPG = 300
KUALITAS_JPG = 90          # 0-100
PDF_KUALITAS_GAMBAR = "BEST"   # BEST | BETTER | NORMAL | FASTER | FASTEST
PDF_GEOREF = True          # sertakan informasi georeferensi di PDF
EXPORT_JPG_DEFAULT = False # bisa diaktifkan juga dengan argumen --jpg

# Pola nama file output (tanpa ekstensi). Placeholder: {kode}, {tanggal}
POLA_NAMA_FILE = "{kode}_Peta_Foto_Udara_{tanggal}"

# ---------------------------------------------------------------------------
# Nama data frame & layer placeholder di template
# ---------------------------------------------------------------------------
NAMA_DF_UTAMA = "Peta Utama"
NAMA_DF_INSET = "Inset"      # opsional; bila tidak ada di template, dilewati

LAYER_ORTHO = "Orthophoto"
LAYER_ESTATE = "Batas Estate"
LAYER_DIVISI = "Batas Divisi"
LAYER_BLOK = "Batas Blok"

# ---------------------------------------------------------------------------
# Nama feature class di File Geodatabase Aresta (default untuk semua estate).
# Bisa di-override per estate lewat kolom opsional fc_estate, fc_divisi,
# fc_blok di config.xlsx/config.csv.
# Feature class boleh berada di dalam feature dataset.
# ---------------------------------------------------------------------------
FC_ESTATE = "Batas_Estate"
FC_DIVISI = "Batas_Divisi"
FC_BLOK = "Batas_Blok"

# Bila satu feature class berisi beberapa estate, isi dengan nama field kode
# estate (mis. "KODE_EST"); definition query  KODE_EST = 'SMSE'  dipasang
# otomatis pada ketiga layer Aresta. None = tanpa filter.
FIELD_FILTER_ESTATE = None

# ---------------------------------------------------------------------------
# Elemen teks (Element Name di template) & isinya
# Placeholder yang tersedia: {kode}, {nama}, {tanggal}, {skala}, {catatan}
# ---------------------------------------------------------------------------
ELEMEN_JUDUL = "TXT_JUDUL"
ELEMEN_ESTATE = "TXT_ESTATE"
ELEMEN_SKALA = "TXT_SKALA"
ELEMEN_TANGGAL = "TXT_TANGGAL"
ELEMEN_SUMBER = "TXT_SUMBER"
ELEMEN_PEMBUAT = "TXT_PEMBUAT"
ELEMEN_CATATAN = "TXT_CATATAN"   # opsional; diisi bila ada di template

TEKS_JUDUL = "PETA FOTO UDARA"
TEKS_ESTATE = "{nama} ({kode})"
TEKS_SKALA = "{skala}"            # hasil: "1 : 10.000"
TEKS_TANGGAL = "Tanggal Akuisisi: {tanggal}"
TEKS_SUMBER = "Sumber: Foto Udara UAV ({tanggal}); Batas Kebun: Aresta"
TEKS_PEMBUAT = "Dibuat oleh: Tim GIS"
TEKS_CATATAN = "{catatan}"
