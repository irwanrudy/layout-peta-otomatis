# -*- coding: utf-8 -*-
"""
Tes asap layout_arcmap memakai arcpy TIRUAN (mock).

Tes ini hanya memeriksa alur (urutan langkah, penanganan error, nama file),
BUKAN perilaku ArcMap sesungguhnya. Di komputer dengan ArcMap (arcpy asli
tersedia) tes ini dilewati.
"""
from __future__ import print_function, unicode_literals

import datetime
import logging
import os
import shutil
import sys
import tempfile
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import arcpy  # noqa: F401
    ARCPY_ASLI = True
except ImportError:
    ARCPY_ASLI = False


# ---------------------------------------------------------------------------
# arcpy tiruan
# ---------------------------------------------------------------------------
class Obj(object):
    """Pengganti types.SimpleNamespace (tidak ada di Python 2)."""
    def __init__(self, **kw):
        self.__dict__.update(kw)


class FakeExtent(object):
    def __init__(self, xmin, ymin, xmax, ymax):
        self.XMin, self.YMin, self.XMax, self.YMax = xmin, ymin, xmax, ymax


class FakeGeom(object):
    def __init__(self, ext):
        self.extent = ext


class FakeSR(object):
    def __init__(self, nama="WGS_1984_UTM_Zone_48S", jenis="Projected"):
        self.name = nama
        self.type = jenis


class FakeLayer(object):
    def __init__(self, nama, group=False):
        self.name = nama
        self.isGroupLayer = group
        self.isBroken = True
        self.dataSource = ""
        self.definitionQuery = ""

    def supports(self, _):
        return True

    def replaceDataSource(self, ws, jenis, dataset, validate=True):
        if dataset in FAKE.dataset_rusak:
            raise ValueError("Unable to replace data source")
        self.dataSource = os.path.join(ws, dataset)
        self.isBroken = False


class FakeDF(object):
    def __init__(self, nama, w, h):
        self.name = nama
        self.elementWidth, self.elementHeight = w, h
        self.spatialReference = None
        self._extent = None
        self.scale = None

    @property
    def extent(self):
        return self._extent

    @extent.setter
    def extent(self, ext):
        # Tiru ArcMap: skala = faktor muat extent ke data frame (cm -> m)
        self._extent = ext
        lebar, tinggi = ext.XMax - ext.XMin, ext.YMax - ext.YMin
        self.scale = max(lebar / (self.elementWidth / 100.0),
                         tinggi / (self.elementHeight / 100.0))


class FakeText(object):
    def __init__(self, nama):
        self.name = nama
        self.text = "placeholder"


class FakeMXD(object):
    def __init__(self, path):
        self.path = path
        portrait = "portrait" in os.path.basename(path).lower()
        w, h = (26.0, 36.0) if portrait else (38.0, 25.0)
        self.dfs = [FakeDF("Peta Utama", w, h), FakeDF("Inset", 6, 6)]
        self.layers = [FakeLayer("Orthophoto"), FakeLayer("Batas Estate"),
                       FakeLayer("Batas Divisi"), FakeLayer("Batas Blok"),
                       FakeLayer("Batas Estate"),  # di Inset
                       FakeLayer("Grup", group=True)]
        self.teks = [FakeText(n) for n in FAKE.elemen_template]
        FAKE.mxd_terakhir = self

    def saveACopy(self, path):
        FAKE.disimpan.append(path)


def _buat_arcpy_tiruan():
    m = types.ModuleType(str("arcpy"))
    m.env = Obj(workspace=None)
    m.Extent = FakeExtent
    m.Exists = lambda p: os.path.normpath(p) in FAKE.fc_ada
    m.ListDatasets = lambda *a: list(FAKE.datasets)
    m.Describe = lambda p: Obj(spatialReference=FAKE.sr)

    class Cursor(object):
        def __init__(self, fc, fields, where=None):
            FAKE.where_dipakai.append(where)
            self.rows = [(FakeGeom(e),) for e in FAKE.geom]

        def __enter__(self):
            return iter(self.rows)

        def __exit__(self, *a):
            return False

    m.da = types.ModuleType(str("arcpy.da"))
    m.da.SearchCursor = Cursor

    mp = types.ModuleType(str("arcpy.mapping"))
    mp.MapDocument = FakeMXD
    mp.ListDataFrames = lambda mxd, wc="": list(mxd.dfs)
    mp.ListLayers = lambda mxd, wc="", df=None: list(mxd.layers)
    mp.ListLayoutElements = lambda mxd, t="", wc="": list(mxd.teks)

    def export(mxd, path, *a, **kw):
        if FAKE.export_gagal:
            raise IOError("PageLayoutObject: Error in exporting")
        FAKE.diexport.append((path, kw))
    mp.ExportToPDF = export
    mp.ExportToJPEG = export
    m.mapping = mp
    return m


class _State(object):
    def reset(self):
        self.fc_ada = set()
        self.datasets = []
        self.geom = []
        self.sr = FakeSR()
        self.dataset_rusak = set()
        self.elemen_template = ["TXT_JUDUL", "TXT_ESTATE", "TXT_SKALA",
                                "TXT_TANGGAL", "TXT_SUMBER", "TXT_PEMBUAT"]
        self.export_gagal = False
        self.diexport = []
        self.disimpan = []
        self.where_dipakai = []
        self.mxd_terakhir = None


FAKE = _State()
FAKE.reset()


@unittest.skipIf(ARCPY_ASLI, "arcpy asli tersedia; tes mock dilewati")
class TesProsesEstateMock(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._arcpy_lama = sys.modules.get("arcpy")
        sys.modules["arcpy"] = _buat_arcpy_tiruan()
        sys.modules.pop("layout_arcmap", None)
        import layout_arcmap
        import layout_core
        import config
        cls.lam = layout_arcmap
        cls.core = layout_core
        cls.cfg = config

    @classmethod
    def tearDownClass(cls):
        sys.modules.pop("arcpy", None)
        sys.modules.pop("layout_arcmap", None)
        if cls._arcpy_lama is not None:
            sys.modules["arcpy"] = cls._arcpy_lama

    def setUp(self):
        FAKE.reset()
        self.tmp = tempfile.mkdtemp()
        self.gdb = os.path.join(self.tmp, "SMSE.gdb")
        for fc in ["Batas_Estate", "Batas_Divisi", "Batas_Blok"]:
            FAKE.fc_ada.add(os.path.normpath(os.path.join(self.gdb, fc)))
        # Estate 4 km x 2 km -> landscape
        FAKE.geom = [FakeExtent(500000, 9800000, 502000, 9801000),
                     FakeExtent(501000, 9800500, 504000, 9802000)]
        # Template harus ada sebagai file
        self.tpl_l = os.path.join(self.tmp, "tpl_landscape.mxd")
        self.tpl_p = os.path.join(self.tmp, "tpl_portrait.mxd")
        for p in (self.tpl_l, self.tpl_p):
            open(p, "w").close()

        cfg = types.ModuleType(str("cfg_uji"))
        for k in dir(self.cfg):
            if k.isupper():
                setattr(cfg, k, getattr(self.cfg, k))
        cfg.TEMPLATE_LANDSCAPE = self.tpl_l
        cfg.TEMPLATE_PORTRAIT = self.tpl_p
        self.cfg_uji = cfg

        self.opsi = {"folder_pdf": self.tmp, "folder_jpg": self.tmp,
                     "folder_mxd": self.tmp, "export_jpg": True,
                     "timpa": False}
        self.estate = self.core.Estate(
            "SMSE", "Sawit Mas Estate", os.path.join(self.tmp, "o.tif"),
            self.gdb, datetime.date(2026, 8, 15),
            fc_estate="Batas_Estate", fc_divisi="Batas_Divisi",
            fc_blok="Batas_Blok")
        self.log = logging.getLogger("uji")
        self.log.addHandler(logging.NullHandler())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_alur_sukses(self):
        h = self.lam.proses_estate(self.estate, self.cfg_uji, self.opsi,
                                   self.log)
        self.assertEqual(h.status, self.core.SUKSES, h.keterangan)
        mxd = FAKE.mxd_terakhir
        self.assertEqual(mxd.path, self.tpl_l)
        # Extent 4000 x 2000 + buffer 5% (200 m) -> 4400 x 2400;
        # skala = max(4400/0.38, 2400/0.25) = 11578.9 -> 15000
        self.assertEqual(mxd.dfs[0].scale, 15000)
        self.assertIn("1 : 15.000", h.keterangan)
        teks = dict((t.name, t.text) for t in mxd.teks)
        self.assertEqual(teks["TXT_SKALA"], "1 : 15.000")
        self.assertEqual(teks["TXT_ESTATE"], "Sawit Mas Estate (SMSE)")
        # Semua layer non-group terhubung
        for lyr in mxd.layers:
            if not lyr.isGroupLayer:
                self.assertFalse(lyr.isBroken, lyr.name)
        self.assertTrue(mxd.layers[0].dataSource.endswith("o.tif"))
        # Inset diatur
        self.assertIsNotNone(mxd.dfs[1].extent)
        # PDF + JPG + MXD
        nama = [os.path.basename(p) for p, _ in FAKE.diexport]
        self.assertEqual(nama, ["SMSE_Peta_Foto_Udara_20260815.pdf",
                                "SMSE_Peta_Foto_Udara_20260815.jpg"])
        self.assertEqual(FAKE.diexport[0][1]["resolution"], 300)
        self.assertEqual(os.path.basename(FAKE.disimpan[0]),
                         "SMSE_Peta_Foto_Udara_20260815.mxd")
        self.assertEqual(len(h.file_output), 3)

    def test_portrait(self):
        FAKE.geom = [FakeExtent(0, 0, 1000, 3000)]
        h = self.lam.proses_estate(self.estate, self.cfg_uji, self.opsi,
                                   self.log)
        self.assertEqual(h.status, self.core.SUKSES, h.keterangan)
        self.assertEqual(FAKE.mxd_terakhir.path, self.tpl_p)
        self.assertIn("portrait", h.keterangan)

    def test_fc_di_feature_dataset_dan_filter(self):
        FAKE.fc_ada = set(os.path.normpath(os.path.join(self.gdb, "Aresta", f))
                          for f in ["Batas_Estate", "Batas_Divisi",
                                    "Batas_Blok"])
        FAKE.datasets = ["Aresta"]
        self.cfg_uji.FIELD_FILTER_ESTATE = "KODE_EST"
        h = self.lam.proses_estate(self.estate, self.cfg_uji, self.opsi,
                                   self.log)
        self.assertEqual(h.status, self.core.SUKSES, h.keterangan)
        self.assertEqual(FAKE.where_dipakai, ["KODE_EST = 'SMSE'"])
        lyr_estate = FAKE.mxd_terakhir.layers[1]
        self.assertEqual(lyr_estate.definitionQuery, "KODE_EST = 'SMSE'")
        self.assertEqual(FAKE.mxd_terakhir.layers[0].definitionQuery, "")

    def test_gagal_tidak_melempar_exception(self):
        FAKE.dataset_rusak = set(["o.tif"])
        h = self.lam.proses_estate(self.estate, self.cfg_uji, self.opsi,
                                   self.log)
        self.assertEqual(h.status, self.core.GAGAL)
        self.assertIn("Orthophoto", h.keterangan)
        self.assertEqual(FAKE.diexport, [])

    def test_fc_hilang(self):
        FAKE.fc_ada = set()
        h = self.lam.proses_estate(self.estate, self.cfg_uji, self.opsi,
                                   self.log)
        self.assertEqual(h.status, self.core.GAGAL)
        self.assertIn("Batas_Estate", h.keterangan)

    def test_export_gagal(self):
        FAKE.export_gagal = True
        h = self.lam.proses_estate(self.estate, self.cfg_uji, self.opsi,
                                   self.log)
        self.assertEqual(h.status, self.core.GAGAL)
        self.assertIn("exporting", h.keterangan)

    def test_elemen_hilang_jadi_peringatan(self):
        FAKE.elemen_template = ["TXT_JUDUL"]
        h = self.lam.proses_estate(self.estate, self.cfg_uji, self.opsi,
                                   self.log)
        self.assertEqual(h.status, self.core.SUKSES)
        teks = " | ".join(h.peringatan)
        self.assertIn("TXT_SKALA", teks)
        self.assertNotIn("TXT_CATATAN", teks)

    def test_skala_melebihi_daftar(self):
        FAKE.geom = [FakeExtent(0, 0, 40000, 20000)]
        h = self.lam.proses_estate(self.estate, self.cfg_uji, self.opsi,
                                   self.log)
        self.assertEqual(h.status, self.core.SUKSES, h.keterangan)
        self.assertTrue(any("melebihi" in p for p in h.peringatan))

    def test_info_template(self):
        info = self.lam.info_template(self.tpl_l, self.cfg_uji)
        self.assertEqual(info["kesalahan"], [])
        self.assertEqual(info["ukuran_df"], (38.0, 25.0))
        info = self.lam.info_template(os.path.join(self.tmp, "x.mxd"),
                                      self.cfg_uji)
        self.assertIn("tidak ditemukan", info["kesalahan"][0])


if __name__ == "__main__":
    unittest.main()
