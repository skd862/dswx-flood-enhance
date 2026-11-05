"""Small helpers shared by the numbered scripts (raster I/O, DEM warping, evaluation metrics)."""
import warnings
from pathlib import Path

import numpy as np
import rasterio
import rioxarray as rxr
import xarray as xr
from osgeo import gdal

import config as C

gdal.UseExceptions()
warnings.filterwarnings("ignore", category=RuntimeWarning)


# ------------------------------------------------------------------------------------------------
# I/O
# ------------------------------------------------------------------------------------------------
def open_da(path):
    """Open a single-band raster as a 2-D DataArray (keeps CRS / transform / nodata)."""
    return rxr.open_rasterio(path).squeeze("band", drop=True)


def write_u8(da, path, nodata=C.NODATA):
    """Write a categorical layer as compressed uint8 GeoTIFF."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = da.astype("uint8")
    out = out.rio.write_nodata(nodata) if nodata is not None else out
    out.rio.to_raster(path, compress="LZW")
    return path


def warp_to_grid(src, template, dst, resampling="bilinear"):
    """Bring a raster onto the grid of `template` (extent, resolution, CRS).

    This is FLEXTH's DTM_2_floodmap.py procedure (gdal.Warp, bilinear for continuous data),
    which is how every DTM used by FLEXTH in the paper was produced.
    """
    with rasterio.open(template) as t:
        T, (nr, nc), crs = t.transform, t.shape, t.crs.to_wkt()
    with rasterio.open(src) as s:
        src_crs = s.crs.to_wkt()
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    gdal.Warp(str(dst), str(src),
              outputBounds=[T.c, T.f + T.e * nr, T.c + T.a * nc, T.f],
              outputBoundsSRS=crs, srcSRS=src_crs, dstSRS=crs,
              xRes=T.a, yRes=T.e, resampleAlg=resampling, targetAlignedPixels=False,
              warpMemoryLimit=5000, creationOptions=["COMPRESS=ZSTD", "BIGTIFF=YES", "TILED=YES"])
    return Path(dst)


# ------------------------------------------------------------------------------------------------
# Evaluation
# ------------------------------------------------------------------------------------------------
# Agreement-map codes written to disk (same codes as the figures in the paper)
TN, FN, FP, TP, PW = 0, 1, 2, 3, 10


def agreement(candidate_water, candidate_valid, benchmark, permanent):
    """Pixel-wise comparison of a binary candidate against the hand-labelled benchmark.

    candidate_water / candidate_valid : boolean arrays on the candidate grid
    benchmark : DataArray already matched to the candidate grid (1 water, 0 dry, NaN no data)
    permanent : DataArray already matched to the candidate grid (1 = permanent water)

    IMPORTANT - PERMANENT WATER IS EXCLUDED: pixels flagged as permanent water are removed from both
    the candidate and the benchmark before any metric is computed (Section 3.1 of the paper), so that
    the scores describe transient flooding only.

    Returns the agreement map (uint8, codes above, 255 = not evaluated) and a dict of metrics.
    """
    b = benchmark.values
    pw = permanent.values == 1
    valid = candidate_valid & ~np.isnan(b) & ~pw
    bw = b == 1
    amap = np.full(b.shape, 255, np.uint8)
    amap[valid & ~candidate_water & ~bw] = TN
    amap[valid & ~candidate_water & bw] = FN
    amap[valid & candidate_water & ~bw] = FP
    amap[valid & candidate_water & bw] = TP
    amap[pw] = PW
    return amap, metrics_from_map(amap)


def metrics_from_map(amap, mask=None):
    a = amap if mask is None else amap[mask]
    tn, fn, fp, tp = [int((a == k).sum()) for k in (TN, FN, FP, TP)]
    div = lambda x, y: x / y if y else np.nan
    rec, tnr, prec = div(tp, tp + fn), div(tn, tn + fp), div(tp, tp + fp)
    return dict(BA=(rec + tnr) / 2 if not (np.isnan(rec) or np.isnan(tnr)) else np.nan,
                CSI=div(tp, tp + fp + fn), F1=div(2 * tp, 2 * tp + fp + fn),
                Precision=prec, Recall=rec, TP=tp, FP=fp, FN=fn, TN=tn)


def load_benchmark(site, like):
    """Hand-labelled benchmark resampled (nearest) onto the candidate grid: 1 water, 0 dry, NaN no data."""
    bm = open_da(C.ANC[site]["benchmark"]).rio.reproject_match(like)
    return bm.where(bm != C.NODATA)


def load_permanent_for_eval(site, like):
    """Permanent-water mask (Louisville: JRC; Harvey: DSWx land cover 200; written by 01) on the grid of `like`.

    These pixels are EXCLUDED from the evaluation.
    """
    return open_da(C.INPUTS / site / "permanent_water_eval.tif").rio.reproject_match(like)
