# Script: jenks_and_reclass.py

from osgeo import gdal
from qgis.core import QgsClassificationJenks
import numpy as np
import os

# ------- USER PARAMETERS -------
raster_path = r"C:\Users\FZ\UTS data spasial\KDE_10km_500px.tif"
out_reclass = r"C:\Users\FZ\UTS data spasial\KDE_10km_500px_Reclass.tif"
num_classes = 3
# ---------------------------------

# 1. Buka raster dengan GDAL
ds = gdal.Open(raster_path)
if ds is None:
    raise SystemExit(f"Failed to open raster: {raster_path}")
band = ds.GetRasterBand(1)

# 2. Baca array numpy (cepat & aman)
arr = band.ReadAsArray().astype(float)

# 3. Filter nilai valid: hilangkan NaN, NoData, dan nol
nodata = band.GetNoDataValue()
vals = arr.flatten()
mask = np.ones_like(vals, dtype=bool)

if nodata is not None:
    mask &= (vals != nodata)
mask &= ~np.isnan(vals)
mask &= (vals > 0)   # hapus nol; ubah sesuai kebutuhan

values = vals[mask]

if values.size == 0:
    raise SystemExit("Tidak ada nilai >0 yang ditemukan dalam raster.")

print(f"Jumlah nilai valid (non-zero): {values.size:,}")

# 4. Hitung Jenks breaks menggunakan QgsClassificationJenks
jenks = QgsClassificationJenks()

# QgsClassificationJenks expects a Python list
values_list = values.tolist()
classes = jenks.classes(values_list, num_classes)

# 5. Ekstrak batas sebagai floats (robust)
breaks = []
for idx, c in enumerate(classes):
    numeric = None
    # Banyak versi mengembalikan object QgsClassificationRange atau angka.
    # Coba beberapa atribut / metode umum:
    if isinstance(c, (int, float, np.floating, np.integer)):
        numeric = float(c)
    else:
        # Coba atribut upperBound(), upperValue(), upper(), value, or .upper
        for attr in ("upperBound", "upperValue", "upper", "upper_bound", "value"):
            if hasattr(c, attr):
                try:
                    numeric = float(getattr(c, attr)())
                    break
                except TypeError:
                    try:
                        numeric = float(getattr(c, attr))
                        break
                    except Exception:
                        pass
        # beberapa implementasi punya metode 'upper' tanpa panggilan
        if numeric is None:
            # terakhir, coba cast langsung (fallback)
            try:
                numeric = float(str(c))
            except Exception:
                numeric = None
    if numeric is None:
        raise RuntimeError(f"Tidak bisa ekstrak numeric break dari Jenks class object: {c!r}")
    breaks.append(numeric)

# Pastikan breaks terurut dan terakhir jadi max
breaks = sorted(breaks)
print("===================================")
print("Hasil Jenks Natural Breaks (upper bounds):")
for i, b in enumerate(breaks):
    print(f"Kelas {i+1}: ≤ {b:.6f}")
print("===================================")

# 6. Opsional: buat raster reclass (1..num_classes) dan simpan
# Kita gunakan bins = breaks[:-1] sebagai threshold untuk numpy.digitize
# contoh: breaks = [b1, b2, b3] -> bins = [b1, b2] -> classes 1..3
bins = breaks[:-1]  # semua kecuali batas teratas terakhir
print("Menggunakan bins:", bins)

# Hitung kelas per piksel (tetap mempertahankan NoData)
reclass_arr = np.zeros_like(arr, dtype=np.uint8)  # default 0 = background/NoData

# Buat mask valid (area yang bukan nodata)
valid_mask = np.ones_like(arr, dtype=bool)
if nodata is not None:
    valid_mask &= (arr != nodata)
valid_mask &= ~np.isnan(arr)

# gunakan digitize hanya pada nilai valid
vals_all = arr[valid_mask]
# kelas: numpy.digitize returns indices 1..len(bins)+1 -> we want 1..num_classes
class_idx = np.digitize(vals_all, bins, right=False) + 1  # +1 in case bins start at 0
# but digitize yields 0..N; verify range and clip
class_idx = np.clip(class_idx, 1, num_classes)

# tulis kembali ke array reclass
reclass_arr[valid_mask] = class_idx.astype(np.uint8)

# simpan ke GeoTIFF
driver = gdal.GetDriverByName("GTiff")
# hapus file output bila ada
if os.path.exists(out_reclass):
    try:
        os.remove(out_reclass)
    except Exception as e:
        print("Warning: tidak dapat menghapus file lama:", e)

out_ds = driver.Create(out_reclass, ds.RasterXSize, ds.RasterYSize, 1, gdal.GDT_Byte, options=["COMPRESS=LZW"])
if out_ds is None:
    raise SystemExit("Gagal membuat raster output.")

# set geotransform & projection sama seperti input
out_ds.SetGeoTransform(ds.GetGeoTransform())
out_ds.SetProjection(ds.GetProjection())

out_band = out_ds.GetRasterBand(1)
out_band.WriteArray(reclass_arr)
out_band.SetNoDataValue(0)
out_band.FlushCache()
out_ds = None  # close

print("Selesai: raster reclass disimpan di:", out_reclass)
