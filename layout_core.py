# -*- coding: utf-8 -*-
"""
Logika murni (TANPA arcpy) untuk otomasi layout peta foto udara.

Isi modul:
- baca config estate (xlsx via xlrd, fallback CSV)
- validasi baris config, path, dan feature class (pengecekan FC lewat fungsi
  yang disuntikkan, sehingga bisa dites tanpa arcpy)
- perhitungan extent + buffer, pemilihan orientasi, pembulatan skala
- penyusunan teks elemen layout, nama file output, dan ringkasan hasil

Kompatibel Python 2.7 (ArcMap) dan Python 3 (untuk menjalankan tes).
"""
from __future__ import print_function, unicode_literals, division

import csv
import datetime
import io
import math
import os
import re
import sys

PY2 = sys.version_info[0] == 2

if PY2:  # pragma: no cover - hanya di Python 2
    teks_type = unicode  # noqa: F821
else:
    teks_type = str


# ===========================================================================
# Exception
# ===========================================================================
class ConfigError(Exception):
    """Kesalahan pada file config (tidak bisa dibaca / kolom wajib hilang)."""
    pass


# ===========================================================================
# Konstanta
# ===========================================================================
KOLOM_WAJIB = ["kode_estate", "nama_estate", "path_ortho", "path_gdb",
               "tanggal_akuisisi"]
KOLOM_OPSIONAL = ["catatan", "fc_estate", "fc_divisi", "fc_blok"]

EKSTENSI_ORTHO = (".tif", ".tiff", ".ecw", ".img", ".jp2", ".sid")

NAMA_BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
              "Agustus", "September", "Oktober", "November", "Desember"]

# Format tanggal teks yang diterima (urutan dicoba satu per satu).
# Format Indonesia: hari dulu baru bulan (dd/mm/yyyy).
FORMAT_TANGGAL = ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y%m%d",
                  "%Y/%m/%d", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S"]


# ===========================================================================
# Util teks
# ===========================================================================
def ke_teks(nilai):
    """Ubah nilai apa pun menjadi teks unicode yang sudah di-strip."""
    if nilai is None:
        return ""
    if isinstance(nilai, bytes):
        try:
            nilai = nilai.decode("utf-8")
        except UnicodeDecodeError:
            nilai = nilai.decode("cp1252")
    if isinstance(nilai, float) and nilai.is_integer():
        # Angka dari Excel (mis. 123.0) -> "123"
        nilai = int(nilai)
    return teks_type(nilai).strip()


def normalisasi_header(nama):
    """'Kode Estate ' -> 'kode_estate' (huruf kecil, spasi jadi underscore)."""
    nama = ke_teks(nama).lstrip("\ufeff").lower()
    nama = re.sub(r"[\s\-]+", "_", nama)
    return nama


def bersihkan_path(path):
    """Buang tanda kutip & spasi di ujung path, lalu normalkan separator."""
    path = ke_teks(path).strip().strip('"').strip("'").strip()
    if not path:
        return ""
    return os.path.normpath(path)


def sanitasi_kode(kode):
    """Kode estate untuk nama file: huruf besar, hanya A-Z 0-9 _ -."""
    kode = ke_teks(kode).upper()
    return re.sub(r"[^A-Z0-9_\-]", "_", kode)


# ===========================================================================
# Tanggal
# ===========================================================================
def parse_tanggal(nilai):
    """
    Ubah nilai tanggal (date/datetime/teks) menjadi datetime.date.
    Melempar ValueError bila format tidak dikenali.
    """
    if isinstance(nilai, datetime.datetime):
        return nilai.date()
    if isinstance(nilai, datetime.date):
        return nilai
    teks = ke_teks(nilai)
    if not teks:
        raise ValueError("tanggal kosong")
    for fmt in FORMAT_TANGGAL:
        try:
            return datetime.datetime.strptime(teks, fmt).date()
        except ValueError:
            continue
    raise ValueError("format tanggal tidak dikenali: '%s' (gunakan "
                     "YYYY-MM-DD atau DD/MM/YYYY)" % teks)


def format_tanggal_id(tanggal):
    """datetime.date(2026, 8, 15) -> '15 Agustus 2026'."""
    return "%d %s %d" % (tanggal.day, NAMA_BULAN[tanggal.month - 1],
                         tanggal.year)


# ===========================================================================
# Membaca config
# ===========================================================================
def xlrd_bisa_baca(ext):
    """
    True bila xlrd terpasang dan mendukung ekstensi tsb. xlrd >= 2.0 hanya
    bisa membaca .xls (ArcMap 10.x membawa xlrd 0.9/1.x yang masih bisa .xlsx).
    """
    try:
        import xlrd
    except ImportError:
        return False
    versi = getattr(xlrd, "__VERSION__", None) or \
        getattr(xlrd, "__version__", "0")
    try:
        mayor = int(ke_teks(versi).split(".")[0])
    except ValueError:
        mayor = 0
    return ext == ".xls" or mayor < 2


def baca_config(path):
    """
    Baca file config estate (.xlsx/.xls atau .csv).

    Bila file Excel diberikan tetapi modul xlrd tidak tersedia, dicoba file
    .csv dengan nama yang sama sebagai fallback.

    Mengembalikan list dict; setiap dict berisi kolom yang sudah dinormalisasi
    ditambah kunci '_baris' (nomor baris di file, untuk pesan error).
    """
    if not os.path.isfile(path):
        raise ConfigError("file config tidak ditemukan: %s" % path)

    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xls", ".xlsm"):
        if not xlrd_bisa_baca(ext):
            csv_path = os.path.splitext(path)[0] + ".csv"
            if os.path.isfile(csv_path):
                return _baca_csv(csv_path)
            raise ConfigError(
                "modul xlrd tidak tersedia / tidak mendukung %s untuk membaca "
                "%s. Simpan config sebagai CSV (%s) lalu jalankan ulang."
                % (ext, path, csv_path))
        return _baca_excel(path)
    elif ext in (".csv", ".txt"):
        return _baca_csv(path)
    raise ConfigError("format config tidak didukung: %s (pakai .xlsx atau "
                      ".csv)" % ext)


def _sel_kosong(v):
    if isinstance(v, (datetime.date, datetime.datetime)):
        return False
    return ke_teks(v) == ""


def _baris_ke_dict(header, baris_list, nomor_awal):
    """Gabungkan header + baris data menjadi list dict, lewati baris kosong."""
    header_norm = [normalisasi_header(h) for h in header]
    hilang = [k for k in KOLOM_WAJIB if k not in header_norm]
    if hilang:
        raise ConfigError("kolom wajib tidak ada di config: %s (kolom yang "
                          "ditemukan: %s)" % (", ".join(hilang),
                                               ", ".join(header_norm)))
    hasil = []
    for i, baris in enumerate(baris_list):
        nilai = list(baris) + [""] * (len(header_norm) - len(baris))
        if all(_sel_kosong(v) for v in nilai):
            continue  # baris kosong dilewati
        data = {}
        for kunci, v in zip(header_norm, nilai):
            if not kunci:
                continue
            if isinstance(v, (datetime.date, datetime.datetime)):
                data[kunci] = v
            else:
                data[kunci] = ke_teks(v)
        data["_baris"] = nomor_awal + i
        hasil.append(data)
    return hasil


def _deteksi_delimiter(baris_header):
    """Excel versi Indonesia sering menyimpan CSV dengan ';'."""
    kandidat = [";", ",", "\t"]
    jumlah = [(baris_header.count(d), d) for d in kandidat]
    jumlah.sort(reverse=True)
    return jumlah[0][1] if jumlah[0][0] > 0 else ","


def _baca_csv(path):
    with io.open(path, "rb") as f:
        data = f.read()
    try:
        teks = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        teks = data.decode("cp1252")

    baris_pertama = teks.splitlines()[0] if teks.strip() else ""
    if not baris_pertama:
        raise ConfigError("file config kosong: %s" % path)
    delim = _deteksi_delimiter(baris_pertama)

    if PY2:  # pragma: no cover - modul csv Python 2 hanya menerima bytes
        reader = csv.reader(io.BytesIO(teks.encode("utf-8")),
                            delimiter=str(delim))
        semua = [[c.decode("utf-8") for c in r] for r in reader]
    else:
        reader = csv.reader(io.StringIO(teks), delimiter=delim)
        semua = [r for r in reader]

    if not semua:
        raise ConfigError("file config kosong: %s" % path)
    # Baris data pertama = baris ke-2 di file
    return _baris_ke_dict(semua[0], semua[1:], 2)


def _baca_excel(path):
    import xlrd
    try:
        buku = xlrd.open_workbook(path)
    except Exception as e:
        raise ConfigError("gagal membuka Excel %s: %s" % (path, e))

    # Pakai sheet bernama "config" bila ada, selain itu sheet pertama
    nama_sheet = [s.lower() for s in buku.sheet_names()]
    if "config" in nama_sheet:
        sheet = buku.sheet_by_index(nama_sheet.index("config"))
    else:
        sheet = buku.sheet_by_index(0)
    if sheet.nrows == 0:
        raise ConfigError("sheet '%s' kosong" % sheet.name)

    def nilai_sel(sel):
        if sel.ctype == xlrd.XL_CELL_DATE:
            tup = xlrd.xldate_as_tuple(sel.value, buku.datemode)
            return datetime.datetime(*tup)
        if sel.ctype == xlrd.XL_CELL_NUMBER:
            return sel.value  # float; ke_teks() mengubah 123.0 -> "123"
        if sel.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
            return ""
        return sel.value

    header = [nilai_sel(s) for s in sheet.row(0)]
    data = [[nilai_sel(s) for s in sheet.row(r)] for r in range(1, sheet.nrows)]
    return _baris_ke_dict(header, data, 2)


# ===========================================================================
# Model estate & validasi
# ===========================================================================
class Estate(object):
    """Satu baris config yang sudah dinormalisasi."""

    def __init__(self, kode, nama, path_ortho, path_gdb, tanggal, catatan="",
                 fc_estate="", fc_divisi="", fc_blok="", baris=None):
        self.kode = kode
        self.nama = nama
        self.path_ortho = path_ortho
        self.path_gdb = path_gdb
        self.tanggal = tanggal          # datetime.date atau None
        self.catatan = catatan
        self.fc_estate = fc_estate
        self.fc_divisi = fc_divisi
        self.fc_blok = fc_blok
        self.baris = baris
        self.kesalahan = []
        self.peringatan = []

    @property
    def valid(self):
        return not self.kesalahan

    def daftar_fc(self):
        """[(jenis, nama_fc), ...] untuk estate, divisi, blok."""
        return [("estate", self.fc_estate), ("divisi", self.fc_divisi),
                ("blok", self.fc_blok)]

    def __repr__(self):
        return "Estate(%s)" % self.kode


def buat_estate(baris, fc_default):
    """
    Buat objek Estate dari dict baris config.

    fc_default: dict {'estate': ..., 'divisi': ..., 'blok': ...} dari config.py,
    dipakai bila kolom fc_* di config kosong/tidak ada.
    Kesalahan parsing dicatat di estate.kesalahan (tidak melempar exception).
    """
    e = Estate(
        kode=ke_teks(baris.get("kode_estate")).upper(),
        nama=ke_teks(baris.get("nama_estate")),
        path_ortho=bersihkan_path(baris.get("path_ortho")),
        path_gdb=bersihkan_path(baris.get("path_gdb")),
        tanggal=None,
        catatan=ke_teks(baris.get("catatan")),
        fc_estate=ke_teks(baris.get("fc_estate")) or fc_default["estate"],
        fc_divisi=ke_teks(baris.get("fc_divisi")) or fc_default["divisi"],
        fc_blok=ke_teks(baris.get("fc_blok")) or fc_default["blok"],
        baris=baris.get("_baris"),
    )
    if not e.kode:
        e.kesalahan.append("kode_estate kosong")
    elif sanitasi_kode(e.kode) != e.kode:
        e.kesalahan.append("kode_estate '%s' mengandung karakter tidak valid "
                           "(gunakan huruf/angka/_/-)" % e.kode)
    if not e.nama:
        e.kesalahan.append("nama_estate kosong")
    try:
        e.tanggal = parse_tanggal(baris.get("tanggal_akuisisi"))
    except ValueError as err:
        e.kesalahan.append("tanggal_akuisisi: %s" % err)
    return e


def validasi_estate(estate, fc_ada=None, path_ada=os.path.isfile,
                    folder_ada=os.path.isdir):
    """
    Validasi path dan feature class satu estate. Hasil ditambahkan ke
    estate.kesalahan / estate.peringatan.

    fc_ada(path_gdb, nama_fc) -> bool. Bila None, pengecekan FC dilewati
    (dicatat sebagai peringatan).
    """
    # --- Orthomosaic ---
    if not estate.path_ortho:
        estate.kesalahan.append("path_ortho kosong")
    else:
        if not path_ada(estate.path_ortho):
            estate.kesalahan.append("file ortho tidak ditemukan: %s"
                                    % estate.path_ortho)
        ext = os.path.splitext(estate.path_ortho)[1].lower()
        if ext not in EKSTENSI_ORTHO:
            estate.peringatan.append("ekstensi ortho '%s' tidak umum "
                                     "(diharapkan %s)"
                                     % (ext, ", ".join(EKSTENSI_ORTHO)))

    # --- File Geodatabase ---
    gdb_ok = False
    if not estate.path_gdb:
        estate.kesalahan.append("path_gdb kosong")
    elif not estate.path_gdb.lower().endswith(".gdb"):
        estate.kesalahan.append("path_gdb bukan File Geodatabase (.gdb): %s"
                                % estate.path_gdb)
    elif not folder_ada(estate.path_gdb):
        estate.kesalahan.append("folder GDB tidak ditemukan: %s"
                                % estate.path_gdb)
    else:
        gdb_ok = True

    # --- Feature class ---
    if gdb_ok:
        if fc_ada is None:
            estate.peringatan.append("feature class tidak dicek (arcpy "
                                     "tidak tersedia)")
        else:
            for jenis, nama_fc in estate.daftar_fc():
                if not fc_ada(estate.path_gdb, nama_fc):
                    estate.kesalahan.append(
                        "feature class batas %s '%s' tidak ditemukan di %s"
                        % (jenis, nama_fc, estate.path_gdb))
    return estate


def validasi_daftar(daftar_estate, fc_ada=None, path_ada=os.path.isfile,
                    folder_ada=os.path.isdir):
    """Validasi semua estate + cek kode duplikat. Mengembalikan daftar yg sama."""
    hitung = {}
    for e in daftar_estate:
        if e.kode:
            hitung[e.kode] = hitung.get(e.kode, 0) + 1
    for e in daftar_estate:
        if e.kode and hitung[e.kode] > 1:
            e.kesalahan.append("kode_estate '%s' muncul %d kali di config"
                               % (e.kode, hitung[e.kode]))
        validasi_estate(e, fc_ada=fc_ada, path_ada=path_ada,
                        folder_ada=folder_ada)
    return daftar_estate


def filter_estate(daftar_estate, kode_list):
    """
    Ambil estate sesuai kode (tidak peka huruf besar/kecil).
    kode_list: list kode atau string 'SMSE,ABCE'. None/kosong = semua.
    Melempar ConfigError bila ada kode yang tidak ada di config.
    """
    if not kode_list:
        return list(daftar_estate)
    if not isinstance(kode_list, (list, tuple)):
        kode_list = ke_teks(kode_list).split(",")
    diminta = [k.strip().upper() for k in kode_list if k.strip()]
    ada = set(e.kode for e in daftar_estate)
    hilang = [k for k in diminta if k not in ada]
    if hilang:
        raise ConfigError("kode estate tidak ada di config: %s"
                          % ", ".join(hilang))
    return [e for e in daftar_estate if e.kode in diminta]


# ===========================================================================
# Extent, orientasi, skala
# ===========================================================================
class Extent(object):
    """Extent sederhana (xmin, ymin, xmax, ymax) dalam satuan peta."""

    def __init__(self, xmin, ymin, xmax, ymax):
        if xmax < xmin or ymax < ymin:
            raise ValueError("extent tidak valid: max lebih kecil dari min")
        self.xmin = float(xmin)
        self.ymin = float(ymin)
        self.xmax = float(xmax)
        self.ymax = float(ymax)

    @property
    def lebar(self):
        return self.xmax - self.xmin

    @property
    def tinggi(self):
        return self.ymax - self.ymin

    @property
    def tengah(self):
        return ((self.xmin + self.xmax) / 2.0, (self.ymin + self.ymax) / 2.0)

    def sebagai_tuple(self):
        return (self.xmin, self.ymin, self.xmax, self.ymax)

    def __eq__(self, lain):
        return isinstance(lain, Extent) and \
            self.sebagai_tuple() == lain.sebagai_tuple()

    def __ne__(self, lain):
        return not self.__eq__(lain)

    def __repr__(self):
        return "Extent(%.3f, %.3f, %.3f, %.3f)" % self.sebagai_tuple()


def tambah_buffer(extent, persen):
    """
    Perbesar extent di keempat sisi sebesar `persen` % dari sisi TERPANJANG,
    sehingga margin di semua sisi sama (estate memanjang tetap punya margin
    yang layak di sisi pendeknya).
    """
    if persen < 0:
        raise ValueError("buffer tidak boleh negatif")
    sisi = max(extent.lebar, extent.tinggi)
    if sisi <= 0:
        raise ValueError("extent estate berukuran nol (geometri kosong?)")
    d = sisi * persen / 100.0
    return Extent(extent.xmin - d, extent.ymin - d,
                  extent.xmax + d, extent.ymax + d)


def pilih_orientasi(lebar, tinggi):
    """Aturan sederhana: landscape bila lebar >= tinggi, selain itu portrait."""
    if lebar <= 0 or tinggi <= 0:
        raise ValueError("lebar/tinggi extent harus > 0")
    return "landscape" if lebar >= tinggi else "portrait"


def faktor_muat(lebar, tinggi, ukuran_df):
    """
    Satuan peta per satuan kertas yang dibutuhkan agar extent muat penuh di
    data frame berukuran ukuran_df = (lebar_df, tinggi_df). Semakin kecil,
    semakin detail (skala semakin besar).
    """
    lebar_df, tinggi_df = ukuran_df
    if lebar_df <= 0 or tinggi_df <= 0:
        raise ValueError("ukuran data frame harus > 0")
    return max(lebar / float(lebar_df), tinggi / float(tinggi_df))


def pilih_orientasi_presisi(lebar, tinggi, ukuran_df_landscape,
                            ukuran_df_portrait):
    """
    Pilih orientasi yang menghasilkan skala paling detail. Ukuran data frame
    kedua template harus dalam satuan halaman yang sama. Seri -> landscape.
    """
    if lebar <= 0 or tinggi <= 0:
        raise ValueError("lebar/tinggi extent harus > 0")
    f_l = faktor_muat(lebar, tinggi, ukuran_df_landscape)
    f_p = faktor_muat(lebar, tinggi, ukuran_df_portrait)
    return "landscape" if f_l <= f_p * (1 + 1e-9) else "portrait"


TOLERANSI_SKALA = 0.01


def bulatkan_skala(skala, daftar_skala, kelipatan_lebih=10000):
    """
    Bulatkan skala (penyebut) KE ATAS ke skala standar terdekat.

    Mengembalikan (skala_bulat, peringatan). peringatan = None bila skala
    masih dalam daftar; bila melebihi skala terbesar, dibulatkan ke atas ke
    kelipatan `kelipatan_lebih` dan peringatan berisi penjelasan.

    Toleransi absolut 0,01 dipakai agar 10000.0001 (galat floating point)
    tetap menjadi 10000, bukan 15000.
    """
    if skala is None or skala <= 0:
        raise ValueError("skala harus > 0")
    if not daftar_skala:
        raise ValueError("daftar skala kosong")
    for s in sorted(daftar_skala):
        if skala <= s + TOLERANSI_SKALA:
            return int(s), None
    if kelipatan_lebih and kelipatan_lebih > 0:
        bulat = int(math.ceil(skala / float(kelipatan_lebih) - 1e-9)
                    * kelipatan_lebih)
    else:
        bulat = int(math.ceil(skala))
    pesan = ("skala hasil 1:%s melebihi skala standar terbesar 1:%s; "
             "dibulatkan ke 1:%s" % (format_ribuan(int(round(skala))),
                                      format_ribuan(max(daftar_skala)),
                                      format_ribuan(bulat)))
    return bulat, pesan


def format_ribuan(angka):
    """10000 -> '10.000' (pemisah ribuan titik, gaya Indonesia)."""
    return "{0:,}".format(int(angka)).replace(",", ".")


def format_skala(skala):
    """10000 -> '1 : 10.000'."""
    return "1 : %s" % format_ribuan(skala)


# ===========================================================================
# Teks layout & nama file
# ===========================================================================
def susun_teks(estate, skala, peta_elemen):
    """
    Susun isi elemen teks layout.

    peta_elemen: list (element_name, pola_teks). Placeholder yang tersedia:
    {kode}, {nama}, {tanggal}, {skala}, {catatan}.
    Mengembalikan dict {element_name: teks}.
    """
    nilai = {
        "kode": estate.kode,
        "nama": estate.nama,
        "tanggal": format_tanggal_id(estate.tanggal) if estate.tanggal else "",
        "skala": format_skala(skala) if skala else "",
        "catatan": estate.catatan,
    }
    hasil = {}
    for nama_elemen, pola in peta_elemen:
        if not nama_elemen:
            continue
        try:
            hasil[nama_elemen] = ke_teks(pola).format(**nilai)
        except (KeyError, IndexError, ValueError) as e:
            raise ConfigError("pola teks untuk %s tidak valid ('%s'): %s"
                              % (nama_elemen, pola, e))
    return hasil


def nama_dasar_output(kode, tanggal, pola="{kode}_Peta_Foto_Udara_{tanggal}"):
    """('SMSE', date(2026,8,15)) -> 'SMSE_Peta_Foto_Udara_20260815'."""
    return pola.format(kode=sanitasi_kode(kode),
                       tanggal=tanggal.strftime("%Y%m%d"))


def path_output_unik(folder, nama_dasar, ext, timpa=False,
                     ada=os.path.exists):
    """
    Path output lengkap. Bila timpa=False dan file sudah ada, tambahkan
    akhiran _v2, _v3, ... sampai ditemukan nama yang belum dipakai.
    """
    if not ext.startswith("."):
        ext = "." + ext
    path = os.path.join(folder, nama_dasar + ext)
    if timpa or not ada(path):
        return path
    n = 2
    while True:
        path = os.path.join(folder, "%s_v%d%s" % (nama_dasar, n, ext))
        if not ada(path):
            return path
        n += 1


def pisah_path_raster(path_ortho):
    """
    'D:\\ortho\\SMSE.tif' -> ('D:\\ortho', 'SMSE.tif') untuk replaceDataSource
    dengan RASTER_WORKSPACE (nama dataset raster file TERMASUK ekstensi).
    """
    folder, nama = os.path.split(path_ortho)
    if not folder or not nama:
        raise ValueError("path ortho tidak valid: %s" % path_ortho)
    return folder, nama


def buat_where_filter(field, kode):
    """Definition query filter estate:  KODE_EST = 'SMSE'  (kutip di-escape)."""
    if not field:
        return ""
    return "%s = '%s'" % (field, ke_teks(kode).replace("'", "''"))


PASANGAN_ELEMEN = [("ELEMEN_JUDUL", "TEKS_JUDUL"),
                   ("ELEMEN_ESTATE", "TEKS_ESTATE"),
                   ("ELEMEN_SKALA", "TEKS_SKALA"),
                   ("ELEMEN_TANGGAL", "TEKS_TANGGAL"),
                   ("ELEMEN_SUMBER", "TEKS_SUMBER"),
                   ("ELEMEN_PEMBUAT", "TEKS_PEMBUAT"),
                   ("ELEMEN_CATATAN", "TEKS_CATATAN")]


def peta_elemen_dari_config(cfg):
    """
    Ambil pasangan (element_name, pola_teks) dari modul/objek config.
    Elemen yang namanya kosong/None dilewati.
    """
    hasil = []
    for attr_elemen, attr_teks in PASANGAN_ELEMEN:
        nama = getattr(cfg, attr_elemen, None)
        if nama:
            hasil.append((nama, getattr(cfg, attr_teks, "") or ""))
    return hasil


def cek_pyramid(path_ortho, path_ada=os.path.isfile):
    """
    Peringatan bila GeoTIFF/IMG tampaknya belum punya pyramids eksternal
    (.ovr / .rrd). ECW/JP2/MrSID sudah multi-resolusi sehingga tidak dicek.
    Catatan: pyramids internal di GeoTIFF tidak terdeteksi oleh cek ini.
    """
    ext = os.path.splitext(path_ortho)[1].lower()
    if ext not in (".tif", ".tiff", ".img"):
        return None
    dasar = os.path.splitext(path_ortho)[0]
    kandidat = [path_ortho + ".ovr", dasar + ".ovr", dasar + ".rrd"]
    if any(path_ada(k) for k in kandidat):
        return None
    return ("pyramids (.ovr/.rrd) tidak ditemukan untuk %s; export bisa "
            "sangat lambat -> jalankan Build Pyramids"
            % os.path.basename(path_ortho))


def pesan_error(err):
    """Teks exception yang aman untuk unicode di Python 2 maupun 3."""
    try:
        teks = teks_type(err)
    except UnicodeError:  # pragma: no cover - khusus Python 2
        teks = str(err).decode("utf-8", "replace")
    teks = teks.strip()
    return teks or err.__class__.__name__


# ===========================================================================
# Hasil & ringkasan
# ===========================================================================
SUKSES = "SUKSES"
GAGAL = "GAGAL"
VALID = "VALID"
TIDAK_VALID = "TIDAK VALID"


class HasilEstate(object):
    """Hasil pemrosesan (atau validasi) satu estate."""

    def __init__(self, kode, status, keterangan="", durasi=0.0,
                 file_output=None, peringatan=None):
        self.kode = kode
        self.status = status
        self.keterangan = keterangan
        self.durasi = durasi
        self.file_output = file_output or []
        self.peringatan = peringatan or []

    @property
    def berhasil(self):
        return self.status in (SUKSES, VALID)


def format_durasi(detik):
    """83.4 -> '00:01:23'."""
    detik = int(round(max(0, detik)))
    return "%02d:%02d:%02d" % (detik // 3600, (detik % 3600) // 60, detik % 60)


def buat_ringkasan(daftar_hasil, durasi_total=None, judul="RINGKASAN"):
    """Teks ringkasan multi-baris untuk log dan konsol."""
    jml_ok = sum(1 for h in daftar_hasil if h.berhasil)
    jml_gagal = len(daftar_hasil) - jml_ok
    if durasi_total is None:
        durasi_total = sum(h.durasi for h in daftar_hasil)

    lebar_kode = max([len("KODE")] + [len(h.kode or "-") for h in daftar_hasil])
    garis = "=" * 78
    baris = [garis, judul, garis,
             "Total: %d | Berhasil: %d | Gagal: %d | Durasi total: %s"
             % (len(daftar_hasil), jml_ok, jml_gagal,
                format_durasi(durasi_total)),
             "-" * 78,
             "%-*s  %-11s  %-8s  %s" % (lebar_kode, "KODE", "STATUS",
                                        "DURASI", "KETERANGAN")]
    for h in daftar_hasil:
        baris.append("%-*s  %-11s  %-8s  %s"
                     % (lebar_kode, h.kode or "-", h.status,
                        format_durasi(h.durasi), h.keterangan))
        for p in h.peringatan:
            baris.append("%-*s  %-11s  %-8s  ! %s" % (lebar_kode, "", "", "",
                                                       p))
    baris.append(garis)
    return "\n".join(baris)
