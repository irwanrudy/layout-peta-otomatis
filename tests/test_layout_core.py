# -*- coding: utf-8 -*-
"""
Tes unit untuk layout_core (tanpa arcpy).

Jalankan dari folder proyek:
    C:\\Python27\\ArcGIS10.8\\python.exe -m unittest discover -s tests -v
atau (Python 3):
    python -m unittest discover -s tests -v
"""
from __future__ import print_function, unicode_literals

import datetime
import io
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import layout_core as core  # noqa: E402

FC_DEFAULT = {"estate": "Batas_Estate", "divisi": "Batas_Divisi",
              "blok": "Batas_Blok"}


def tulis_file(path, teks, encoding="utf-8"):
    with io.open(path, "w", encoding=encoding, newline="") as f:
        f.write(teks)


class TesTanggal(unittest.TestCase):

    def test_berbagai_format(self):
        harap = datetime.date(2026, 8, 15)
        for teks in ["2026-08-15", "15/08/2026", "15-08-2026", "15.08.2026",
                     "20260815", "2026/08/15", " 2026-08-15 ",
                     "2026-08-15 00:00:00"]:
            self.assertEqual(core.parse_tanggal(teks), harap, teks)

    def test_objek_date_dan_datetime(self):
        self.assertEqual(core.parse_tanggal(datetime.datetime(2026, 1, 2, 3, 4)),
                         datetime.date(2026, 1, 2))
        self.assertEqual(core.parse_tanggal(datetime.date(2026, 1, 2)),
                         datetime.date(2026, 1, 2))

    def test_angka_dari_excel(self):
        # Sel Excel berisi angka 20260815 (bukan format tanggal)
        self.assertEqual(core.parse_tanggal(20260815.0),
                         datetime.date(2026, 8, 15))

    def test_tidak_valid(self):
        for teks in ["", None, "besok", "31/02/2026", "08/15/2026"]:
            self.assertRaises(ValueError, core.parse_tanggal, teks)

    def test_format_indonesia(self):
        self.assertEqual(core.format_tanggal_id(datetime.date(2026, 8, 5)),
                         "5 Agustus 2026")
        self.assertEqual(core.format_tanggal_id(datetime.date(2026, 12, 31)),
                         "31 Desember 2026")


class TesSkala(unittest.TestCase):
    DAFTAR = [5000, 7500, 10000, 15000, 20000, 25000, 50000]

    def test_bulat_ke_atas(self):
        kasus = [(1, 5000), (4999.9, 5000), (5000, 5000), (5001, 7500),
                 (7500, 7500), (9000, 10000), (10001, 15000),
                 (24000, 25000), (25001, 50000), (50000, 50000)]
        for skala, harap in kasus:
            hasil, pesan = core.bulatkan_skala(skala, self.DAFTAR)
            self.assertEqual(hasil, harap, skala)
            self.assertIsNone(pesan)

    def test_toleransi_floating_point(self):
        self.assertEqual(core.bulatkan_skala(10000.0004, self.DAFTAR)[0], 10000)

    def test_daftar_tidak_urut(self):
        self.assertEqual(core.bulatkan_skala(8000, [50000, 5000, 10000])[0],
                         10000)

    def test_melebihi_daftar(self):
        hasil, pesan = core.bulatkan_skala(50001, self.DAFTAR, 10000)
        self.assertEqual(hasil, 60000)
        self.assertIn("melebihi", pesan)
        self.assertEqual(core.bulatkan_skala(70000, self.DAFTAR, 10000)[0],
                         70000)
        self.assertEqual(core.bulatkan_skala(123456, self.DAFTAR, 25000)[0],
                         125000)

    def test_skala_tidak_valid(self):
        self.assertRaises(ValueError, core.bulatkan_skala, 0, self.DAFTAR)
        self.assertRaises(ValueError, core.bulatkan_skala, -5, self.DAFTAR)
        self.assertRaises(ValueError, core.bulatkan_skala, 100, [])

    def test_format(self):
        self.assertEqual(core.format_skala(10000), "1 : 10.000")
        self.assertEqual(core.format_skala(7500), "1 : 7.500")
        self.assertEqual(core.format_skala(1250000), "1 : 1.250.000")
        self.assertEqual(core.format_ribuan(500), "500")


class TesExtentOrientasi(unittest.TestCase):

    def test_buffer_pakai_sisi_terpanjang(self):
        ext = core.Extent(0, 0, 1000, 200)
        b = core.tambah_buffer(ext, 5)
        self.assertEqual(b.sebagai_tuple(), (-50, -50, 1050, 250))
        self.assertEqual(b.tengah, ext.tengah)

    def test_buffer_nol(self):
        ext = core.Extent(10, 20, 30, 40)
        self.assertEqual(core.tambah_buffer(ext, 0), ext)

    def test_buffer_extent_nol(self):
        self.assertRaises(ValueError, core.tambah_buffer,
                          core.Extent(5, 5, 5, 5), 5)
        self.assertRaises(ValueError, core.tambah_buffer,
                          core.Extent(0, 0, 1, 1), -1)

    def test_extent_terbalik(self):
        self.assertRaises(ValueError, core.Extent, 10, 0, 0, 10)

    def test_orientasi_sederhana(self):
        self.assertEqual(core.pilih_orientasi(100, 50), "landscape")
        self.assertEqual(core.pilih_orientasi(100, 100), "landscape")
        self.assertEqual(core.pilih_orientasi(50, 100), "portrait")
        self.assertRaises(ValueError, core.pilih_orientasi, 0, 10)

    def test_orientasi_presisi(self):
        # Data frame A3 (cm): landscape 38x25, portrait 26x36
        L, P = (38.0, 25.0), (26.0, 36.0)
        self.assertEqual(core.pilih_orientasi_presisi(2000, 1000, L, P),
                         "landscape")
        self.assertEqual(core.pilih_orientasi_presisi(1000, 2000, L, P),
                         "portrait")
        # Sedikit lebih lebar dari tinggi: faktor L = max(1100/38, 1050/25)
        # = 42, faktor P = max(1100/26, 1050/36) = 42.3 -> landscape
        self.assertEqual(core.pilih_orientasi_presisi(1100, 1050, L, P),
                         "landscape")
        # Hampir persegi: L = max(1000/38, 1050/25)=42, P = max(1000/26,
        # 1050/36)=38.5 -> portrait walau lebar ~ tinggi
        self.assertEqual(core.pilih_orientasi_presisi(1000, 1050, L, P),
                         "portrait")

    def test_faktor_muat(self):
        self.assertAlmostEqual(core.faktor_muat(1000, 500, (10, 10)), 100.0)
        self.assertRaises(ValueError, core.faktor_muat, 1, 1, (0, 10))


class TesTeksDanNamaFile(unittest.TestCase):

    def setUp(self):
        self.estate = core.Estate("SMSE", "Sawit Mas Estate", "x.tif",
                                  "x.gdb", datetime.date(2026, 8, 15),
                                  catatan="Revisi 1")

    def test_susun_teks(self):
        peta = [("TXT_JUDUL", "PETA FOTO UDARA"),
                ("TXT_ESTATE", "{nama} ({kode})"),
                ("TXT_SKALA", "{skala}"),
                ("TXT_TANGGAL", "Tanggal Akuisisi: {tanggal}"),
                ("TXT_CATATAN", "{catatan}"),
                ("", "diabaikan")]
        teks = core.susun_teks(self.estate, 10000, peta)
        self.assertEqual(teks["TXT_ESTATE"], "Sawit Mas Estate (SMSE)")
        self.assertEqual(teks["TXT_SKALA"], "1 : 10.000")
        self.assertEqual(teks["TXT_TANGGAL"], "Tanggal Akuisisi: 15 Agustus 2026")
        self.assertEqual(teks["TXT_CATATAN"], "Revisi 1")
        self.assertEqual(len(teks), 5)

    def test_pola_salah(self):
        self.assertRaises(core.ConfigError, core.susun_teks, self.estate,
                          10000, [("TXT_X", "{tidak_ada}")])

    def test_nama_dasar(self):
        self.assertEqual(core.nama_dasar_output("smse",
                                                datetime.date(2026, 8, 15)),
                         "SMSE_Peta_Foto_Udara_20260815")

    def test_path_unik(self):
        sudah_ada = set([os.path.join("out", "A.pdf"),
                         os.path.join("out", "A_v2.pdf")])
        ada = lambda p: p in sudah_ada  # noqa: E731
        self.assertEqual(core.path_output_unik("out", "A", "pdf", ada=ada),
                         os.path.join("out", "A_v3.pdf"))
        self.assertEqual(core.path_output_unik("out", "A", ".pdf", timpa=True,
                                               ada=ada),
                         os.path.join("out", "A.pdf"))
        self.assertEqual(core.path_output_unik("out", "B", ".pdf", ada=ada),
                         os.path.join("out", "B.pdf"))

    def test_pisah_raster(self):
        folder, nama = core.pisah_path_raster(os.path.join("data", "SMSE.ecw"))
        self.assertEqual((folder, nama), ("data", "SMSE.ecw"))
        self.assertRaises(ValueError, core.pisah_path_raster, "SMSE.ecw")

    def test_where_filter(self):
        self.assertEqual(core.buat_where_filter("KODE_EST", "SMSE"),
                         "KODE_EST = 'SMSE'")
        self.assertEqual(core.buat_where_filter("K", "O'X"), "K = 'O''X'")
        self.assertEqual(core.buat_where_filter(None, "SMSE"), "")


class TesHelperLain(unittest.TestCase):

    def test_peta_elemen_dari_config(self):
        class Cfg(object):
            ELEMEN_JUDUL = "TXT_JUDUL"
            TEKS_JUDUL = "PETA"
            ELEMEN_SKALA = "TXT_SKALA"
            TEKS_SKALA = "{skala}"
            ELEMEN_CATATAN = None
            TEKS_CATATAN = "{catatan}"
        self.assertEqual(core.peta_elemen_dari_config(Cfg),
                         [("TXT_JUDUL", "PETA"), ("TXT_SKALA", "{skala}")])

    def test_peta_elemen_config_asli(self):
        import config
        peta = dict(core.peta_elemen_dari_config(config))
        self.assertEqual(len(peta), 7)
        e = core.Estate("SMSE", "Sawit Mas Estate", "", "",
                        datetime.date(2026, 8, 15))
        teks = core.susun_teks(e, 7500, core.peta_elemen_dari_config(config))
        self.assertEqual(teks[config.ELEMEN_SKALA], "1 : 7.500")

    def test_cek_pyramid(self):
        tif = os.path.join("d", "ortho.tif")
        self.assertIsNotNone(core.cek_pyramid(tif, path_ada=lambda p: False))
        self.assertIsNone(core.cek_pyramid(
            tif, path_ada=lambda p: p == tif + ".ovr"))
        self.assertIsNone(core.cek_pyramid(os.path.join("d", "o.ecw"),
                                           path_ada=lambda p: False))

    def test_pesan_error(self):
        self.assertEqual(core.pesan_error(ValueError("rusak ")), "rusak")
        self.assertEqual(core.pesan_error(RuntimeError()), "RuntimeError")


class TesBacaConfig(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_csv_koma_dengan_bom(self):
        p = os.path.join(self.tmp, "config.csv")
        tulis_file(p, "\ufeffKode Estate,Nama_Estate,path_ortho,path_gdb,"
                      "tanggal_akuisisi,catatan\r\n"
                      "smse,Sawit Mas Estate,\"D:\\Ortho\\SMSE.tif\","
                      "D:\\GDB\\SMSE.gdb,15/08/2026,\"catatan, dengan koma\"\r\n"
                      ",,,,,\r\n"
                      "ABCE,Âlpha Estate,D:\\o.ecw,D:\\a.gdb,2026-09-01,\r\n")
        rows = core.baca_config(p)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["kode_estate"], "smse")
        self.assertEqual(rows[0]["catatan"], "catatan, dengan koma")
        self.assertEqual(rows[0]["_baris"], 2)
        self.assertEqual(rows[1]["nama_estate"], "Âlpha Estate")
        self.assertEqual(rows[1]["_baris"], 4)

    def test_csv_titik_koma_cp1252(self):
        p = os.path.join(self.tmp, "config.csv")
        tulis_file(p, "kode_estate;nama_estate;path_ortho;path_gdb;"
                      "tanggal_akuisisi\nSMSE;Sawit Mas Ésta;a.tif;b.gdb;"
                      "2026-08-15\n", encoding="cp1252")
        rows = core.baca_config(p)
        self.assertEqual(rows[0]["nama_estate"], "Sawit Mas Ésta")
        self.assertNotIn("catatan", rows[0])

    def test_kolom_wajib_hilang(self):
        p = os.path.join(self.tmp, "config.csv")
        tulis_file(p, "kode_estate,nama_estate\nSMSE,Sawit\n")
        self.assertRaises(core.ConfigError, core.baca_config, p)

    def test_file_tidak_ada_dan_format_salah(self):
        self.assertRaises(core.ConfigError, core.baca_config,
                          os.path.join(self.tmp, "tidak_ada.csv"))
        p = os.path.join(self.tmp, "config.json")
        tulis_file(p, "{}")
        self.assertRaises(core.ConfigError, core.baca_config, p)

    def test_file_kosong(self):
        p = os.path.join(self.tmp, "config.csv")
        tulis_file(p, "")
        self.assertRaises(core.ConfigError, core.baca_config, p)

    def test_xlsx_fallback_ke_csv_bila_tanpa_xlrd(self):
        if core.xlrd_bisa_baca(".xlsx"):
            self.skipTest("xlrd tersedia; fallback tidak relevan")
        tulis_file(os.path.join(self.tmp, "config.xlsx"), "bukan excel")
        tulis_file(os.path.join(self.tmp, "config.csv"),
                   "kode_estate,nama_estate,path_ortho,path_gdb,"
                   "tanggal_akuisisi\nSMSE,S,a.tif,b.gdb,2026-08-15\n")
        rows = core.baca_config(os.path.join(self.tmp, "config.xlsx"))
        self.assertEqual(rows[0]["kode_estate"], "SMSE")

    def test_xlsx_dengan_xlrd(self):
        try:
            import openpyxl
        except ImportError:
            self.skipTest("openpyxl (pembuat file uji) tidak tersedia")
        if not core.xlrd_bisa_baca(".xlsx"):
            self.skipTest("xlrd tidak tersedia / versi >= 2.0")
        if sys.version_info >= (3, 9):
            # xlrd 1.x memakai API ElementTree yang dihapus di Python 3.9
            self.skipTest("xlrd 1.x tidak kompatibel dengan Python 3.9+")
        p = os.path.join(self.tmp, "config.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Config"
        ws.append(["kode_estate", "nama_estate", "path_ortho", "path_gdb",
                   "tanggal_akuisisi", "catatan", "fc_blok"])
        ws.append(["SMSE", "Sawit Mas Estate", "D:\\SMSE.ecw",
                   "D:\\SMSE.gdb", datetime.datetime(2026, 8, 15), 123,
                   "Blok_2026"])
        ws.append([None] * 7)
        ws.append(["ABCE", "Alpha", "a.tif", "a.gdb", "01/09/2026", None,
                   None])
        wb.save(p)
        rows = core.baca_config(p)
        self.assertEqual(len(rows), 2)
        self.assertEqual(core.parse_tanggal(rows[0]["tanggal_akuisisi"]),
                         datetime.date(2026, 8, 15))
        self.assertEqual(rows[0]["catatan"], "123")
        self.assertEqual(rows[0]["fc_blok"], "Blok_2026")
        self.assertEqual(core.parse_tanggal(rows[1]["tanggal_akuisisi"]),
                         datetime.date(2026, 9, 1))


class TesValidasi(unittest.TestCase):

    def baris(self, **kw):
        b = {"kode_estate": "smse", "nama_estate": "Sawit Mas Estate",
             "path_ortho": "D:\\ortho\\SMSE.tif", "path_gdb": "D:\\SMSE.gdb",
             "tanggal_akuisisi": "2026-08-15", "catatan": "", "_baris": 2}
        b.update(kw)
        return b

    def test_buat_estate_normalisasi(self):
        e = core.buat_estate(self.baris(fc_blok="Blok_Baru"), FC_DEFAULT)
        self.assertEqual(e.kode, "SMSE")
        self.assertEqual(e.tanggal, datetime.date(2026, 8, 15))
        self.assertEqual(e.fc_estate, "Batas_Estate")
        self.assertEqual(e.fc_blok, "Blok_Baru")
        self.assertTrue(e.valid)

    def test_buat_estate_salah(self):
        e = core.buat_estate(self.baris(kode_estate="", nama_estate="",
                                        tanggal_akuisisi="xx"), FC_DEFAULT)
        self.assertEqual(len(e.kesalahan), 3)
        e = core.buat_estate(self.baris(kode_estate="SM SE"), FC_DEFAULT)
        self.assertFalse(e.valid)

    def test_validasi_semua_ok(self):
        e = core.buat_estate(self.baris(), FC_DEFAULT)
        core.validasi_estate(e, fc_ada=lambda g, f: True,
                             path_ada=lambda p: True,
                             folder_ada=lambda p: True)
        self.assertTrue(e.valid, e.kesalahan)
        self.assertEqual(e.peringatan, [])

    def test_validasi_path_dan_fc(self):
        e = core.buat_estate(self.baris(path_ortho="D:\\ortho\\SMSE.png"),
                             FC_DEFAULT)
        dicek = []

        def fc_ada(gdb, fc):
            dicek.append(fc)
            return fc != "Batas_Blok"

        core.validasi_estate(e, fc_ada=fc_ada, path_ada=lambda p: False,
                             folder_ada=lambda p: True)
        self.assertEqual(dicek, ["Batas_Estate", "Batas_Divisi", "Batas_Blok"])
        teks = " | ".join(e.kesalahan)
        self.assertIn("file ortho tidak ditemukan", teks)
        self.assertIn("Batas_Blok", teks)
        self.assertEqual(len(e.kesalahan), 2)
        self.assertEqual(len(e.peringatan), 1)  # ekstensi .png

    def test_gdb_bukan_gdb_atau_tidak_ada(self):
        e = core.buat_estate(self.baris(path_gdb="D:\\data"), FC_DEFAULT)
        core.validasi_estate(e, fc_ada=lambda g, f: True,
                             path_ada=lambda p: True,
                             folder_ada=lambda p: True)
        self.assertIn("bukan File Geodatabase", e.kesalahan[0])

        e = core.buat_estate(self.baris(), FC_DEFAULT)
        dipanggil = []
        core.validasi_estate(e, fc_ada=lambda g, f: dipanggil.append(f),
                             path_ada=lambda p: True,
                             folder_ada=lambda p: False)
        self.assertIn("folder GDB tidak ditemukan", e.kesalahan[0])
        self.assertEqual(dipanggil, [])  # FC tidak dicek bila GDB tidak ada

    def test_tanpa_arcpy(self):
        e = core.buat_estate(self.baris(), FC_DEFAULT)
        core.validasi_estate(e, fc_ada=None, path_ada=lambda p: True,
                             folder_ada=lambda p: True)
        self.assertTrue(e.valid)
        self.assertIn("arcpy", e.peringatan[0])

    def test_duplikat_dan_filter(self):
        daftar = [core.buat_estate(self.baris(), FC_DEFAULT),
                  core.buat_estate(self.baris(kode_estate="SMSE"), FC_DEFAULT),
                  core.buat_estate(self.baris(kode_estate="ABCE"), FC_DEFAULT)]
        core.validasi_daftar(daftar, fc_ada=lambda g, f: True,
                             path_ada=lambda p: True,
                             folder_ada=lambda p: True)
        self.assertFalse(daftar[0].valid)
        self.assertFalse(daftar[1].valid)
        self.assertTrue(daftar[2].valid)

        self.assertEqual([e.kode for e in core.filter_estate(daftar, "abce")],
                         ["ABCE"])
        self.assertEqual(len(core.filter_estate(daftar, None)), 3)
        self.assertEqual(len(core.filter_estate(daftar, "SMSE, ABCE")), 3)
        self.assertRaises(core.ConfigError, core.filter_estate, daftar, "XXXX")


class TesRingkasan(unittest.TestCase):

    def test_durasi(self):
        self.assertEqual(core.format_durasi(0), "00:00:00")
        self.assertEqual(core.format_durasi(83.4), "00:01:23")
        self.assertEqual(core.format_durasi(3725), "01:02:05")

    def test_ringkasan(self):
        hasil = [core.HasilEstate("SMSE", core.SUKSES, "1 : 10.000 landscape",
                                  65, peringatan=["skala dibulatkan"]),
                 core.HasilEstate("ABCE", core.GAGAL, "layer tidak ada", 5)]
        teks = core.buat_ringkasan(hasil)
        self.assertIn("Total: 2 | Berhasil: 1 | Gagal: 1", teks)
        self.assertIn("00:01:10", teks)
        self.assertIn("layer tidak ada", teks)
        self.assertIn("! skala dibulatkan", teks)


if __name__ == "__main__":
    unittest.main()
