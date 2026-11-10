# Layout Peta Otomatis – Foto Udara UAV per Estate (ArcMap 10.x)

Tool ini membuat layout peta foto udara (orthomosaic UAV) secara otomatis untuk banyak estate kebun sawit sekaligus. Hasilnya PDF 300 dpi, JPG opsional, dan salinan MXD per estate. Data batas estate, divisi, dan blok diambil dari File Geodatabase Aresta.

Alur singkat per estate:

1. Baca extent batas estate. Template **landscape** dipakai bila lebar ≥ tinggi, selain itu **portrait**.
2. Buka template, lalu ganti sumber layer placeholder ke orthomosaic dan GDB estate tersebut.
3. Set extent data frame ke batas estate + buffer 5%. Skala dibulatkan **ke atas** ke skala standar (1:5.000, 1:7.500, 1:10.000, …).
4. Isi elemen teks (judul, estate, skala, tanggal, sumber, pembuat).
5. Export ke `{KODE}_Peta_Foto_Udara_{YYYYMMDD}.pdf` (opsional `.jpg`) dan simpan salinan `.mxd`. Template tidak pernah ditimpa.
6. Bila satu estate error, estate lain tetap diproses. Log dan ringkasan ditulis di akhir.

---

## 1. Struktur proyek

```
layout-peta-otomatis/
├── config.py               # SEMUA pengaturan (template, output, skala, nama layer/elemen)
├── layout_core.py          # logika murni tanpa arcpy (config, validasi, skala, orientasi)
├── layout_arcmap.py        # semua pemanggilan arcpy.mapping
├── run_layout.py           # program utama (CLI)
├── run_layout.bat          # menjalankan run_layout.py dengan Python ArcMap
├── run_tests.bat           # menjalankan tes unit dengan Python ArcMap
├── config_contoh.csv       # contoh format config
├── template/               # (buat sendiri) taruh 2 template MXD di sini
└── tests/
    ├── test_layout_core.py         # tes unit logika inti
    └── test_layout_arcmap_mock.py  # tes alur dengan arcpy tiruan
```

Folder `output/` dibuat otomatis:

```
output/
├── pdf/   SMSE_Peta_Foto_Udara_20260815.pdf
├── jpg/   (bila --jpg)
├── mxd/   SMSE_Peta_Foto_Udara_20260815.mxd
└── log/   layout_20261110_083015.log
```

## 2. Persyaratan

- ArcGIS Desktop (ArcMap) 10.1–10.8, lisensi Basic sudah cukup.
- Python 2.7 bawaan ArcMap (`C:\Python27\ArcGIS10.x\python.exe`). **Tidak perlu memasang library tambahan.**
- Untuk membaca `config.xlsx` dipakai modul `xlrd` yang sudah dibawa ArcMap 10.x. Bila xlrd tidak tersedia, atau versinya ≥ 2.0 (tidak bisa membaca `.xlsx`), tool otomatis memakai `config.csv` dengan nama yang sama.

## 3. Menyiapkan template MXD

Siapkan **dua** template A3:

- `template/Template_A3_Landscape.mxd`
- `template/Template_A3_Portrait.mxd`

Path dan nama file template bisa diubah di `config.py` (`TEMPLATE_LANDSCAPE`, `TEMPLATE_PORTRAIT`).

### 3.1 Data frame

| Nama data frame | Wajib | Keterangan |
|---|---|---|
| `Peta Utama` | Ya | Peta utama; extent dan skala diatur otomatis |
| `Inset` | Tidak | Peta lokasi; diatur ke batas estate + buffer 300% |

Cara mengganti nama data frame: klik kanan data frame di Table of Contents → **Properties** → tab **General** → isi **Name**.

### 3.2 Layer placeholder

Di dalam data frame `Peta Utama` harus ada layer dengan nama **persis** berikut (huruf besar/kecil tidak berpengaruh):

| Nama layer | Jenis | Sumber yang dipasang |
|---|---|---|
| `Orthophoto` | Raster layer | file orthomosaic (`path_ortho`) |
| `Batas Estate` | Feature layer (poligon) | FC `Batas_Estate` di GDB |
| `Batas Divisi` | Feature layer | FC `Batas_Divisi` di GDB |
| `Batas Blok` | Feature layer | FC `Batas_Blok` di GDB |

Tips:

- Buat placeholder dari data **salah satu estate yang asli**: Add Data, rename layer, lalu atur simbologi dan label. Simbologi dan label tetap dipakai setelah sumbernya diganti.
- Layer **jangan** dimasukkan ke dalam group layer dengan nama yang sama. Group layer boleh ada, tetapi yang dicari adalah layer di dalamnya.
- Bila di `Inset` juga ada layer `Batas Estate`, sumbernya ikut diganti.
- Agar label blok/divisi muncul, pastikan field label di FC semua estate **bernama sama**.

### 3.3 Element Name pada elemen teks

Setiap elemen teks yang diisi otomatis harus diberi **Element Name**:
klik kanan elemen teks di Layout View → **Properties** → tab **Size and Position** → isi **Element Name**.

| Element Name | Isi default (ubah di `config.py`) | Contoh hasil |
|---|---|---|
| `TXT_JUDUL` | `PETA FOTO UDARA` | PETA FOTO UDARA |
| `TXT_ESTATE` | `{nama} ({kode})` | Sawit Mas Estate (SMSE) |
| `TXT_SKALA` | `{skala}` | 1 : 10.000 |
| `TXT_TANGGAL` | `Tanggal Akuisisi: {tanggal}` | Tanggal Akuisisi: 15 Agustus 2026 |
| `TXT_SUMBER` | `Sumber: Foto Udara UAV ({tanggal}); Batas Kebun: Aresta` | … |
| `TXT_PEMBUAT` | `Dibuat oleh: Tim GIS` | … |
| `TXT_CATATAN` *(opsional)* | `{catatan}` | isi kolom catatan |

Placeholder yang bisa dipakai di semua teks: `{kode}`, `{nama}`, `{tanggal}`, `{skala}`, `{catatan}`.

Legend, scale bar, north arrow, dan grid **tidak** diubah oleh tool. Scale bar dan grid otomatis menyesuaikan skala data frame.
> Saran: di Properties scale bar, atur opsi *When resizing* (misalnya *Adjust division value*) lalu cek hasilnya di beberapa skala agar angka pembagian tetap rapi.

### 3.4 Sistem koordinat

Tool mengatur sistem koordinat data frame (`Peta Utama` dan `Inset`) **sama dengan sistem koordinat feature class batas estate**. Estate di zona UTM berbeda (48S/49S/50S) tetap tampil benar. Grid/graticule di template mengikuti CRS data frame. Bila batas estate masih dalam koordinat geografis (derajat), muncul peringatan di log; disarankan memakai proyeksi UTM.

## 4. Format config (`config.xlsx` / `config.csv`)

Satu baris = satu estate. Baris pertama adalah header. Untuk Excel dipakai sheet bernama `config`; bila tidak ada, dipakai sheet pertama.

| Kolom | Wajib | Contoh | Keterangan |
|---|---|---|---|
| `kode_estate` | Ya | `SMSE` | huruf/angka/`_`/`-`, tidak boleh duplikat |
| `nama_estate` | Ya | `Sawit Mas Estate` | |
| `path_ortho` | Ya | `D:\UAV\SMSE\Ortho_SMSE.tif` | GeoTIFF/ECW/IMG/JP2/SID |
| `path_gdb` | Ya | `D:\Aresta\SMSE.gdb` | File Geodatabase |
| `tanggal_akuisisi` | Ya | `15/08/2026` atau `2026-08-15` | sel tanggal Excel juga bisa; format **hari/bulan/tahun** |
| `catatan` | Tidak | `Revisi batas blok` | dicatat di log; tampil di layout bila ada `TXT_CATATAN` |
| `fc_estate` | Tidak | `Batas_Kebun` | override nama FC batas estate untuk estate ini |
| `fc_divisi` | Tidak | | override nama FC divisi |
| `fc_blok` | Tidak | `Blok_2026` | override nama FC blok |

Catatan:

- Header tidak peka huruf besar/kecil, dan spasi dianggap `_` (`Kode Estate` = `kode_estate`).
- CSV boleh memakai pemisah `,` atau `;` (format CSV Excel Indonesia). Encoding UTF-8 atau ANSI.
- Nama default feature class diatur di `config.py` (`FC_ESTATE`, `FC_DIVISI`, `FC_BLOK`). FC boleh berada di dalam feature dataset.
- Bila satu FC berisi **beberapa** estate, isi `FIELD_FILTER_ESTATE` di `config.py` dengan nama field kode estate (misalnya `"KODE_EST"`). Definition query `KODE_EST = 'SMSE'` akan dipasang otomatis.
- Tanggal di nama file adalah **tanggal akuisisi**.

Lihat `config_contoh.csv` sebagai contoh.

## 5. Cara menjalankan

Buka **Command Prompt** di folder tool, lalu:

```bat
:: 1) Validasi dulu (tidak export apa pun)
run_layout.bat --dry-run

:: 2) Proses semua estate
run_layout.bat

:: Satu estate saja / beberapa estate
run_layout.bat --estate SMSE
run_layout.bat --estate SMSE,ABCE

:: PDF + JPG
run_layout.bat --jpg

:: Config dan folder output lain
run_layout.bat --config D:\Data\config_2026.xlsx --output D:\Hasil\Layout

:: Timpa file yang sudah ada (default: diberi akhiran _v2, _v3, ...)
run_layout.bat --timpa

:: Detail proses di konsol
run_layout.bat --estate SMSE --verbose
```

`run_layout.bat` mencari Python ArcMap otomatis di `C:\Python27\ArcGIS10.8` sampai `10.1`. Bila ArcMap terpasang di lokasi lain, buka `run_layout.bat` dan isi baris `set "PYTHON_ARCMAP=..."`.

Kode keluar (berguna untuk Task Scheduler):

| Kode | Arti |
|---|---|
| 0 | semua estate berhasil / valid |
| 1 | ada estate gagal / tidak valid (estate lain tetap diproses) |
| 2 | kesalahan config (file tidak ada, kolom wajib hilang, kode `--estate` salah) |
| 3 | arcpy tidak tersedia atau template bermasalah |

### Mode `--dry-run`

Yang diperiksa:

- config dan kolom wajib, kode duplikat, format tanggal
- keberadaan file ortho dan GDB, serta ketiga feature class
- pyramids GeoTIFF (peringatan bila belum ada)
- kedua template: data frame, 4 layer placeholder, dan elemen teks
- extent batas estate, beserta pratinjau orientasi landscape/portrait

Contoh ringkasan:

```
==============================================================================
RINGKASAN
==============================================================================
Total: 3 | Berhasil: 2 | Gagal: 1 | Durasi total: 00:04:12
------------------------------------------------------------------------------
KODE  STATUS       DURASI    KETERANGAN
SMSE  SUKSES       00:02:01  1 : 10.000, landscape -> SMSE_Peta_Foto_Udara_20260815.pdf, ...
ABCE  SUKSES       00:02:05  1 : 15.000, portrait -> ABCE_Peta_Foto_Udara_20260901.pdf, ...
XYZE  GAGAL        00:00:00  validasi: file ortho tidak ditemukan: D:\UAV\XYZE.tif
==============================================================================
```

## 6. Pengaturan (`config.py`)

| Pengaturan | Default | Keterangan |
|---|---|---|
| `DAFTAR_SKALA` | 5000 … 50000 | skala standar; hasil dibulatkan ke atas |
| `KELIPATAN_SKALA_LEBIH` | 10000 | bila > skala terbesar, dibulatkan ke kelipatan ini (dicatat sebagai peringatan) |
| `BUFFER_PERSEN` | 5 | margin di sekeliling estate (persen dari sisi terpanjang) |
| `BUFFER_INSET_PERSEN` | 300 | margin untuk data frame Inset |
| `MODE_ORIENTASI` | `"sederhana"` | `"presisi"` = pilih template dengan skala paling detail berdasarkan ukuran data frame |
| `DPI_PDF` / `DPI_JPG` | 300 | resolusi export |
| `TIMPA_OUTPUT` | False | False = akhiran `_v2`, `_v3`, … |
| `SIMPAN_MXD` | True | simpan salinan MXD per estate |
| `TEKS_*` | | isi teks layout (lihat 3.3) |

## 7. Uji manual bagian arcpy (di komputer ArcMap)

Bagian `layout_arcmap.py` hanya bisa diuji di komputer yang terpasang ArcMap. Ikuti langkah berikut sekali saat pertama kali dipakai:

1. **Tes unit.** Jalankan `run_tests.bat`. Semua tes harus `OK`. Tes "mock" otomatis dilewati karena arcpy asli tersedia.
2. **Siapkan 1 estate uji** di `config.csv`, lalu jalankan `run_layout.bat --dry-run --estate SMSE`.
   - Pastikan status `VALID`, orientasi masuk akal, dan tidak ada error template.
3. **Proses satu estate**: `run_layout.bat --estate SMSE --jpg --verbose`, lalu buka PDF-nya dan periksa:
   - orthomosaic tampil (bukan kosong/abu-abu) dan batas estate/divisi/blok tepat di atasnya
   - seluruh estate terlihat dengan margin di semua sisi
   - `TXT_SKALA` sama dengan angka scale bar, dan grid/koordinat sesuai zona UTM estate
   - judul, nama estate, dan tanggal (format Indonesia) benar
   - inset (bila ada) menampilkan posisi estate
4. **Buka MXD hasil** (`output\mxd\SMSE_...mxd`) di ArcMap:
   - tidak ada layer dengan tanda seru merah (broken)
   - skala di toolbar sama dengan `TXT_SKALA`
   - **template asli tidak berubah** (cek tanggal *Modified* file template)
5. **Estate portrait.** Uji satu estate yang memanjang utara–selatan; pastikan template portrait yang terpakai.
6. **Isolasi error.** Tambahkan baris estate palsu dengan `path_ortho` salah, lalu jalankan semua estate. Estate lain harus tetap `SUKSES`, dan estate palsu `GAGAL` dengan alasan yang jelas.
7. **Nama ganda.** Jalankan ulang estate yang sama; file baru harus bernama `_v2`. Dengan `--timpa`, file lama ditimpa.
8. **(Bila dipakai)** FC di dalam feature dataset, kolom `fc_*` override, dan `FIELD_FILTER_ESTATE`.

Untuk men-debug satu langkah, fungsi bisa dicoba langsung dari **Python window** ArcMap:

```python
import sys; sys.path.insert(0, r"D:\Tools\layout-peta-otomatis")
import layout_arcmap as lam, config
print(lam.info_template(config.TEMPLATE_LANDSCAPE, config))
fc = lam.cari_fc(r"D:\Aresta\SMSE.gdb", "Batas_Estate"); print(fc)
print(lam.baca_extent(fc))
```

## 8. Troubleshooting

**"layer 'Batas Divisi' tidak ada di template"**
Nama layer di Table of Contents harus sama dengan `LAYER_*` di `config.py`. Periksa spasi berlebih dan pastikan layer berada di dalam data frame (bukan hanya group layer bernama sama).

**"feature class batas blok 'Batas_Blok' tidak ditemukan"**
Buka GDB di ArcCatalog dan cek nama FC yang sebenarnya. Bila hanya satu estate yang berbeda, isi kolom `fc_blok` di config. Bila semua estate berbeda, ubah `FC_BLOK` di `config.py`.

**"replaceDataSource gagal" / layer masih broken (tanda seru merah)**
- Pastikan path di config benar dan file/GDB bisa dibuka dengan Add Data di ArcMap.
- Layer placeholder `Orthophoto` harus **raster layer**, dan layer batas harus **feature layer** dengan tipe geometri yang sama (poligon ke poligon).
- ECW: pastikan ArcMap bisa membuka file ECW tersebut secara manual.
- GDB dari versi ArcGIS yang lebih baru kadang tidak terbaca di ArcMap lama. Coba buka di ArcCatalog.
- Path di jaringan (`\\server\...`): pastikan akses baca tersedia untuk user yang menjalankan tool.

**Export sangat lambat / PDF sangat besar → Build Pyramids**
Orthomosaic GeoTIFF besar tanpa pyramids membuat ArcMap membaca resolusi penuh. Bangun pyramids dan statistik **sekali** per file:
- ArcToolbox → *Data Management Tools → Raster → Raster Properties → Build Pyramids And Statistics*, atau
- Python window: `arcpy.BuildPyramidsandStatistics_management(r"D:\UAV\SMSE")`

Saran lain: kompres ortho ke ECW/JPEG-compressed TIFF, atau pakai `PDF_KUALITAS_GAMBAR = "NORMAL"` di `config.py`.

**"export ... Error in exporting" / PDF gagal ditulis**
File PDF mungkin sedang dibuka di PDF reader. Tutup file tersebut, atau biarkan tool membuat `_v2`. Pastikan juga ruang disk cukup.

**Skala selalu terlalu kecil (misalnya 1:50.000 untuk estate kecil)**
Biasanya batas estate dalam koordinat geografis atau berisi fitur nyasar jauh dari estate. Cek extent FC di ArcCatalog (*Properties → Extent*), dan periksa peringatan di log.

**Config Excel tidak terbaca ("modul xlrd tidak tersedia")**
Simpan config sebagai CSV (`File → Save As → CSV`) dengan nama yang sama di folder yang sama. Tool otomatis memakai CSV tersebut.

**Tanggal salah (bulan dan hari tertukar)**
Tool membaca teks tanggal sebagai **hari/bulan/tahun**. Gunakan format `YYYY-MM-DD` atau format sel *Date* di Excel agar tidak ambigu.

**Teks kosong / elemen tidak berubah**
Periksa Element Name (bukan teks isinya). Elemen yang tidak ditemukan dicatat sebagai peringatan di log dan ringkasan.

**Python ArcMap tidak ditemukan**
Isi `PYTHON_ARCMAP` di `run_layout.bat` dengan path lengkap `python.exe` ArcMap. Gunakan versi **32-bit** bawaan ArcMap, bukan Python 64-bit Background Geoprocessing atau Python 3 ArcGIS Pro.

## 9. Pengembangan

- Logika murni ada di `layout_core.py` dan bisa dites tanpa ArcMap:
  `python -m unittest discover -s tests -v`
- `tests/test_layout_arcmap_mock.py` menguji alur `layout_arcmap.py` dan `run_layout.py` dengan arcpy tiruan (hanya berjalan bila arcpy **tidak** tersedia).
- Kode wajib kompatibel Python 2.7: tanpa f-string, type hints, atau pathlib.
