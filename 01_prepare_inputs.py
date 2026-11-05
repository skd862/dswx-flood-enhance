# %% [markdown]
# # 01 - Prepare inputs
#
# Builds every raster needed by FLEXTH (02), RS-FloodXdepth (03) and the evaluation (04) from the
# source products in `data/source` and the ancillary layers in `data/ancillary`.
#
# | Site | Satellite product | "BWTR" layer (user-ready) | "CONF" layer (diagnostic) |
# |---|---|---|---|
# | Louisville, KY (Apr 8 / Apr 9 2025) | OPERA DSWx-HLS v1.0 | `B02_BWTR` | `B03_CONF` |
# | Sugar Land, TX (Harvey, Sep 4 2017) | USGS Landsat C2 DSWE | `INWAM` (all masks applied) | `INTSM` (some masks applied: terrain, snow, land cover - no cloud mask) |
#
# For each case it writes, under `outputs/inputs/<case>/`:
#
# * `scene_bwtr.tif`, `scene_conf.tif` - clipped and re-coded DSWx/DSWE layers (Table 2 candidates)
# * `flexth/<seed>_<dem>/{flood,exclusion,permanent_water,dtm}.tif` - FLEXTH inputs
# * `rsfloodxdepth/<seed>_<dem>/{flood,dtm}.tif` - RS-FloodXdepth inputs
#
# with seed in {bwtr, conf, conf_no_partial} and dem in {fabdem, 3dep}.
#
# **Initial flood map, exclusion mask and permanent water**
#
# * flood (seed): `bwtr` = BWTR water; `conf` = every CONF water class (also under cloud/snow masks);
#   `conf_no_partial` = like `conf` but "Partial water | Cloud mask" is treated as non-water.
# * exclusion (FLEXTH only; where flooding may be propagated): cloud / cloud shadow (/ adjacent) pixels +
#   forest (DSWx-HLS land cover class 201 "A variety of forest classes").
# * permanent water: JRC Global Surface Water (Louisville, GEE export) / DSWx-HLS land cover class 200
#   (Harvey); also excluded from every evaluation (see 04).
#
# All data needed are bundled, so this runs offline. `--download` re-fetches the identical source files
# first (Earthdata login needed for DSWx-HLS; USGS ERS login may be needed for DSWE). The DEMs are bundled
# ready to use; `download_dems` shows how to get them again (FABDEM from Google Earth Engine, 3DEP from USGS).
#
# The processing reproduces the original analysis step by step, including some choices that differ
# between runs (they are flagged with **NOTE (as published)**) so the published numbers are recovered.

# %%
import argparse
import glob
import shutil
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
import xarray as xr
from rioxarray.merge import merge_arrays, merge_datasets

import config as C
from common import open_da, warp_to_grid, write_u8

# %% [markdown]
# ## Optional: download the source products

# %%
def download_dswx_hls(dest=C.SOURCE):
    """OPERA DSWx-HLS granules (NASA PO.DAAC, collection OPERA_L3_DSWX-HLS_V1) via earthaccess."""
    import earthaccess
    earthaccess.login()
    wanted = {"louisville/dswx_hls": [(g, b) for d in C.LOUISVILLE_GRANULES for g in C.LOUISVILLE_GRANULES[d]
                                      for b in ("B02_BWTR", "B03_CONF", "B07_LAND")],
              "harvey/dswx_land": [(g, "B07_LAND") for g in C.HARVEY_LAND_GRANULES]}
    for sub, items in wanted.items():
        for granule in sorted({g for g, _ in items}):
            res = earthaccess.search_data(short_name="OPERA_L3_DSWX-HLS_V1", granule_name=granule)
            bands = [b for g, b in items if g == granule]
            links = [l for r in res for l in r.data_links() if any(l.endswith(b + ".tif") for b in bands)]
            earthaccess.download(links, str(dest / sub))


def download_dswe(dest=C.SOURCE / "harvey" / "dswe"):
    """USGS Landsat Collection-2 Level-3 DSWE ARD tiles from the LandsatLook STAC (assets inwam/intsm)."""
    import requests
    from pystac_client import Client
    cat = Client.open("https://landsatlook.usgs.gov/stac-server")
    for fname in C.HARVEY_INWAM + C.HARVEY_INTSM:
        item_id = fname.rsplit("_", 1)[0] + "_DSWE"          # e.g. LC08_CU_017017_20170904_20210503_02_DSWE
        item = next(cat.search(collections=["landsat-c2l3-dswe"], ids=[item_id]).items())
        href = item.assets[fname.rsplit("_", 1)[1].split(".")[0].lower()].href
        r = requests.get(href, timeout=600)
        r.raise_for_status()                                   # 401/403 -> log in at ers.cr.usgs.gov / use the S3 href
        (dest / fname).write_bytes(r.content)


def download_dems(dest=C.ANCILLARY):
    """Re-create the bundled 30 m DEMs (optional; the bundled files are the ones used in the paper).

    FABDEM (Hawker et al., 2022; CC BY-NC-SA 4.0) - Google Earth Engine community catalog asset
    `projects/sat-io/open-datasets/FABDEM` (https://gee-community-catalog.org/projects/fabdem/), also
    downloadable as 1-degree tiles from the University of Bristol data repository.
    USGS 3DEP - from the USGS National Map (https://apps.nationalmap.gov/downloader/) or the GEE collection
    `USGS/3DEP/1m`, aggregated to 30 m. Needs `earthengine-api` and `earthengine authenticate`.
    """
    import ee
    ee.Initialize()
    regions = {"louisville": (ee.Geometry.Rectangle([-85.93, 38.11, -85.52, 38.40]), "EPSG:3857", "EPSG:5070"),
               "harvey": (ee.Geometry.Rectangle([-96.08, 29.40, -95.31, 29.80]), "EPSG:3857", "EPSG:3857")}
    fabdem = ee.ImageCollection("projects/sat-io/open-datasets/FABDEM").mosaic()
    dep3 = ee.ImageCollection("USGS/3DEP/1m").mosaic()
    for site, (reg, crs_fab, crs_3dep) in regions.items():
        for name, img, crs in [("fabdem", fabdem, crs_fab), ("3dep", dep3, crs_3dep)]:
            ee.batch.Export.image.toDrive(image=img, description=f"{site}_{name}_30m_gee", region=reg, scale=30,
                                          crs=crs, maxPixels=1e10).start()
    print("GEE export tasks submitted - copy the GeoTIFFs into data/ancillary/<site>/ when they finish.")


# %% [markdown]
# ## Helpers

# %%
def mosaic(paths):
    """Mosaic tiles with rioxarray (first tile wins in overlaps), as in the original notebooks."""
    return merge_datasets([xr.open_dataset(p) for p in paths]).band_data.squeeze("band", drop=True)


def clip(da, shp):
    aoi = gpd.read_file(shp)
    return da.rio.clip(aoi.to_crs(da.rio.crs).geometry, drop=True)


def fill_u8(da):
    """NaN -> 255, cast to uint8."""
    return xr.where(np.isnan(da), C.NODATA, da).astype("uint8").rio.write_crs(da.rio.crs)


def collapse_conf_dswx(conf):
    """Collapse DSWx-HLS B03_CONF (Product Spec D-107395, Table 4-1) to the classes of Fig. 3 of the paper.

    0 not water | 1 water | 10 not water, cloud | 11 OPEN water, cloud | 12 PARTIAL water, cloud |
    20 not water, snow/ice | 21 water, snow/ice | 255 fill. "cloud" = cloud, cloud shadow or adjacent (Fmask).
    """
    v = conf.values
    out = np.full(v.shape, C.NODATA, np.uint8)
    out[v == 0] = 0
    out[np.isin(v, [1, 2, 3, 4])] = 1         # open water high/moderate-confidence + partial surface water conservative/aggressive
    out[v == 10] = 10
    out[np.isin(v, [11, 12])] = 11            # open water high/moderate-confidence, cloud/shadow/adjacent
    out[np.isin(v, [13, 14])] = 12            # partial surface water conservative/aggressive, cloud/shadow/adjacent
    out[v == 20] = 20
    out[np.isin(v, [21, 22, 23, 24])] = 21    # any water class where Fmask marks snow/ice
    return conf.copy(data=out)


def save_flexth_inputs(folder, flood, exclusion, permanent, dem_src):
    folder.mkdir(parents=True, exist_ok=True)
    write_u8(flood, folder / "flood.tif", nodata=flood.rio.nodata)
    write_u8(exclusion, folder / "exclusion.tif", nodata=exclusion.rio.nodata)
    write_u8(permanent, folder / "permanent_water.tif", nodata=permanent.rio.nodata)
    warp_to_grid(dem_src, folder / "flood.tif", folder / "dtm.tif", "bilinear")


def with_nodata(da, nodata_mask, value=C.NODATA):
    out = xr.where(nodata_mask, value, da).astype("uint8").rio.write_crs(da.rio.crs)
    return out.rio.write_nodata(value)


def no_nodata(da):
    out = da.astype("uint8").rio.write_crs(da.rio.crs)
    out.rio.write_nodata(None, inplace=True)
    return out


# %% [markdown]
# ## Louisville (DSWx-HLS)

# %%
def prepare_louisville():
    src = C.SOURCE / "louisville" / "dswx_hls"
    anc = C.ANC["louisville"]
    root = C.INPUTS / "louisville"

    def tiles(date, band):
        # NOTE (as published): mosaic order differs per layer (first tile wins in the overlap)
        g = C.LOUISVILLE_GRANULES[date]
        return [src / f"{g[i]}_{band}.tif" for i in C.LOUISVILLE_TILE_ORDER[band]]

    # land cover on the large "BWTR" grid (extent of the NOAA aerial mosaic)
    land = fill_u8(clip(mosaic(tiles(C.LOUISVILLE_LAND_DATE, "B07_LAND")), anc["aoi_bwtr"]))

    for date in ("0408", "0409"):
        case = f"louisville_{date}"
        out = C.INPUTS / case

        # --- Table 2 candidates -------------------------------------------------------------------
        # NOTE (as published): the BWTR scene was clipped to the aerial-mosaic footprint (aoi_bwtr_runs),
        # the CONF scene to the analysis AOI (clip_aoi). Both share the native DSWx 30 m UTM grid.
        bwtr = fill_u8(clip(mosaic(tiles(date, "B02_BWTR")), anc["aoi_bwtr"]))
        conf = collapse_conf_dswx(clip(mosaic(tiles(date, "B03_CONF")), anc["aoi"]))
        write_u8(bwtr, out / "scene_bwtr.tif")
        write_u8(conf, out / "scene_conf.tif")

        if date == "0408":
            # JRC permanent water (GEE export) on the large grid; EXCLUDED from the evaluation and FLEXTH input of BWTR runs
            pw_jrc = open_da(anc["permanent_water"]).rio.reproject_match(bwtr, nodata=None)
            write_u8(no_nodata(xr.where(pw_jrc == 1, 1, 0)), root / "permanent_water_eval.tif", nodata=None)
        pw_eval = open_da(root / "permanent_water_eval.tif")

        land_c = land.rio.reproject_match(conf)          # same grid, smaller extent -> exact subset

        for seed in C.SEEDS:
            if seed == "bwtr":
                # NOTE (as published): BWTR runs use the larger grid without nodata and forest only counts as
                # exclusion where BWTR says "not water".
                flood = no_nodata(xr.where(bwtr == C.BWTR_WATER, 1, 0))
                excl = no_nodata(xr.where((bwtr == C.BWTR_CLOUD) | ((land == C.LAND_FOREST) & (bwtr == 0)), 1, 0))
                perm = no_nodata(pw_eval)
            else:
                water = C.CONF_WATER_ALL if seed == "conf" else C.CONF_WATER_NO_PARTIAL
                nod = conf == C.NODATA
                flood = with_nodata(xr.where(conf.isin(water), 1, 0), nod)
                excl = with_nodata(xr.where(conf.isin(C.CONF_CLOUD) | (land_c == C.LAND_FOREST), 1, 0), nod)
                # NOTE (as published): the CONF runs gave FLEXTH the DSWx land-cover permanent water (class 200);
                # the evaluation always uses the JRC mask
                perm = with_nodata(xr.where(land_c == C.LAND_PERMANENT_WATER, 1, 0), nod)

            for dem in C.DEMS:
                fx = C.input_dir(case, seed, dem, "flexth")
                save_flexth_inputs(fx, flood, excl, perm, anc[dem])

                # RS-FloodXdepth: seed with nodata -> 0; DEM taken by nearest neighbour from the GEE export
                rs = C.input_dir(case, seed, dem, "rsfloodxdepth")
                rs.mkdir(parents=True, exist_ok=True)
                f = open_da(fx / "flood.tif")
                if f.rio.nodata is None:
                    f = f.rio.write_nodata(0)
                # NOTE (as published): seeds were clipped to the box aoi_rsfloodxdepth_bwtr (this only
                # trims the larger BWTR grid; the CONF grid lies inside the box)
                f = clip(f, anc["aoi_rsfx_bwtr"])
                f = xr.where(f == f.rio.nodata, 0, f).astype("uint8").rio.write_crs(f.rio.crs).rio.write_nodata(0)
                f.rio.to_raster(rs / "flood.tif", compress="LZW")
                dtm = open_da(anc[dem]).rio.reproject_match(f).rio.write_nodata(np.nan)
                dtm.rio.to_raster(rs / "dtm.tif", compress="LZW")
        print(f"[01] {case}: inputs written to {out}")


# %% [markdown]
# ## Hurricane Harvey, Sugar Land (USGS DSWE)

# %%
def prepare_harvey():
    src = C.SOURCE / "harvey"
    anc = C.ANC["harvey"]
    out = C.INPUTS / "harvey"
    grid = open_da(anc["benchmark"])                       # 30 m EPSG:3857 benchmark grid
    outside = grid.values == C.NODATA

    # --- BWTR equivalent: DSWE INWAM, water classes 1-4 (high/moderate confidence + partial surface water)
    #     -> 1, 9 (cloud, cloud shadow) -> 253 ------------------------------------------------------------
    if C.HARVEY_EXACT:
        bwtr = open_da(anc["inwam_30m"]).astype("uint8")
    else:
        inwam = merge_arrays([open_da(src / "dswe" / f) for f in C.HARVEY_INWAM])
        v = inwam.values
        rec = np.full(v.shape, C.NODATA, np.uint8)
        rec[v == 0] = 0
        rec[np.isin(v, [1, 2, 3, 4])] = 1
        rec[v == 9] = C.BWTR_CLOUD
        inwam = inwam.copy(data=rec).rio.write_nodata(C.NODATA)
        bwtr = inwam.rio.reproject_match(grid)
        bwtr = bwtr.copy(data=np.where(outside, C.NODATA, bwtr.values).astype("uint8"))
    bwtr = bwtr.rio.write_nodata(C.NODATA)
    write_u8(bwtr, out / "scene_bwtr.tif")

    # --- CONF equivalent: DSWE INTSM, split by the INWAM cloud mask --------------------------------------
    if C.HARVEY_EXACT:
        intsm = open_da(anc["intsm_clipped"]).rio.reproject_match(bwtr).values
    else:
        intsm = open_da(src / "dswe" / C.HARVEY_INTSM[0]).rio.reproject_match(grid).values
        intsm = np.where(outside, C.NODATA, intsm)
    cloud = bwtr.values == C.BWTR_CLOUD
    conf = np.full(intsm.shape, C.NODATA, np.uint8)
    conf[~cloud & (intsm == 0)] = 0
    conf[~cloud & np.isin(intsm, [1, 2, 3, 4])] = 1
    conf[cloud & (intsm == 0)] = 10
    conf[cloud & (intsm == 1)] = 11               # water - high confidence | cloud
    conf[cloud & np.isin(intsm, [3, 4])] = 12     # partial surface water conservative/aggressive | cloud
    # Deliberate choice: under the cloud mask, INTSM class 2 (moderate-confidence water) was inspected on the
    # Landsat image and found to be cloud shadow everywhere in this scene, so it is coded as not water (0).
    conf[cloud & (intsm == 2)] = 0
    conf = bwtr.copy(data=conf)
    write_u8(conf, out / "scene_conf.tif")

    # --- land cover: January-2025 DSWx-HLS B07_LAND tiles (DSWx-HLS is not available for 2017) --------
    if C.HARVEY_EXACT:
        land = open_da(anc["land_mosaic"])
    else:
        inwam_grid = merge_arrays([open_da(src / "dswe" / f) for f in C.HARVEY_INWAM])
        land = mosaic(sorted(glob.glob(str(src / "dswx_land" / C.HARVEY_LAND_GLOB))))
        land = fill_u8(land.rio.reproject_match(inwam_grid)).rio.write_nodata(C.NODATA)

    # --- crop to the valid footprint (as FLEXTH inputs were) ------------------------------------------
    valid = conf.values != C.NODATA
    rows, cols = np.where(valid.any(axis=1))[0], np.where(valid.any(axis=0))[0]
    sl = dict(y=slice(rows.min(), rows.max() + 1), x=slice(cols.min(), cols.max() + 1))
    bwtr_c, conf_c = bwtr.isel(**sl), conf.isel(**sl)
    land_c = land.rio.reproject_match(bwtr_c)

    nod_b = bwtr_c == C.NODATA
    excl = with_nodata(xr.where((bwtr_c == C.BWTR_CLOUD) | (land_c == C.LAND_FOREST), 1, 0), nod_b)
    perm = with_nodata(xr.where(land_c == C.LAND_PERMANENT_WATER, 1, 0), nod_b)
    write_u8(perm, out / "permanent_water_eval.tif")

    for seed in C.SEEDS:
        if seed == "bwtr":
            flood = with_nodata(xr.where(bwtr_c == C.BWTR_WATER, 1, 0), nod_b)
        else:
            water = C.CONF_WATER_ALL if seed == "conf" else C.CONF_WATER_NO_PARTIAL
            flood = with_nodata(xr.where(conf_c.isin(water), 1, 0), conf_c == C.NODATA)
        for dem in C.DEMS:
            fx = C.input_dir("harvey", seed, dem, "flexth")
            save_flexth_inputs(fx, flood, excl, perm, anc[dem])
            if dem == "fabdem":
                # NOTE (as published): the FABDEM DTM of the Harvey runs was NaN outside the valid footprint
                with rasterio.open(fx / "dtm.tif", "r+") as d:
                    z = d.read(1)
                    z[nod_b.values] = np.nan
                    d.write(z, 1)
                    d.nodata = np.nan
            # RS-FloodXdepth uses the same seed (nodata -> 0) and the same bilinear DTM as FLEXTH
            rs = C.input_dir("harvey", seed, dem, "rsfloodxdepth")
            rs.mkdir(parents=True, exist_ok=True)
            f = xr.where(flood == C.NODATA, 0, flood).astype("uint8").rio.write_crs(flood.rio.crs).rio.write_nodata(0)
            f.rio.to_raster(rs / "flood.tif", compress="LZW")
            shutil.copy(fx / "dtm.tif", rs / "dtm.tif")
    print(f"[01] harvey: inputs written to {out}")


# %%
if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--download", action="store_true", help="re-download the source products first")
    args, _ = ap.parse_known_args()
    if args.download:
        download_dswx_hls()
        download_dswe()
    prepare_louisville()
    prepare_harvey()
