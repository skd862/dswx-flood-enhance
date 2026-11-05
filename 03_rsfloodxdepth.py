# %% [markdown]
# # 03 - RS-FloodXdepth flood enhancement
#
# RS-FloodXdepth (Tian, Liu, Wang, Cohen & Mandal, 2026, *Water Resources Research* 62, e2025WR042384,
# https://doi.org/10.1029/2025WR042384) corrects omission errors of a remote-sensing flood map and estimates
# flood depth in four steps:
#
# 1. flood objects: 4-connected labelling of the binary seed map and removal of small objects;
# 2. local water-surface elevation (LWSE) at each object centroid, from a KDE of the DEM elevations along the
#    object boundary; outliers are screened against the k nearest centroids;
# 3. a continuous water surface by IDW interpolation of the centroid LWSEs;
# 4. region growing from the seed pixels into 8-connected neighbours whose DEM is below the water surface.
#
# **The RS-FloodXdepth code is not included in this repository.** It belongs to its developers (Surface
# Dynamics Modeling Lab, University of Alabama); please refer to the paper above. This script therefore works
# in one of two modes, chosen automatically:
#
# * **precomputed (default)** - copies the 18 RS-FloodXdepth flood maps produced for the paper
#   (`data/precomputed/rsfloodxdepth/`, made with the parameters in `config.py`) into `outputs/runs/`, so that
#   steps 04 and 05 reproduce every RS-FloodXdepth row of Table 3 and Figs. 10-11;
# * **full run** - if you have obtained the RS-FloodXdepth code from its developers, save it as
#   `third_party/rsfloodxdepth/rsfloodxdepth.py` (it must provide `generate_lwse_layers` and `idw2Flood1`,
#   called as in `run_rsfloodxdepth` below) and install its dependency `ImageObject`
#   (`pip install ImageObject==1.19`; Windows wheel). The script then runs the 18 configurations itself.
#
# Parameters and the values used in the paper: `03_RSFloodXdepth_parameters.md`.
#
# Inputs (per run, from 01_prepare_inputs.py): flood.tif (0/1), dtm.tif
# Output used by 04: FloodClass.tif (0 dry, 1 seed flood, 2 flood added by region growing)

# %%
import importlib.util
import shutil
import time

import config as C

RSFX_CODE = C.ROOT / "third_party" / "rsfloodxdepth" / "rsfloodxdepth.py"


def load_rsfloodxdepth():
    """Import the RS-FloodXdepth code if it has been placed in third_party/rsfloodxdepth/, else None."""
    if not RSFX_CODE.is_file():
        return None
    spec = importlib.util.spec_from_file_location("rsfloodxdepth", RSFX_CODE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# %% [markdown]
# ## Run the 18 configurations of Table 3

# %%
def run_rsfloodxdepth(rsfx, src_dir, out_dir, params):
    """One RS-FloodXdepth run with the developers' code (`rsfx` module)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    flood, dtm = src_dir / "flood.tif", src_dir / "dtm.tif"
    rsfx.generate_lwse_layers(flood, dtm, params["region_row"], params["region_col"], params["front_min"],
                              params["back_min"], params["k_neighbors"],
                              out_dir / "boundary_elevation.shp", out_dir / "centroid_elevation.shp")
    rsfx.idw2Flood1(out_dir / "centroid_elevation.shp", "LWSE_new", dtm, flood,
                    out_dir / "idw_temp.tif", out_dir / "FloodDepth.tif", out_dir / "FloodClass.tif",
                    out_dir / "reprojected_shapefile.shp", out_dir / "alignedSeedRaster.tif",
                    int(params["max_points"]), float(params["power"]), flood_class=1)
    return out_dir / "FloodClass.tif"


def run_all(cases=C.CASES, seeds=C.SEEDS, dems=C.DEMS):
    rsfx = load_rsfloodxdepth()
    if rsfx is None:
        print(f"[03] RS-FloodXdepth code not found ({RSFX_CODE.relative_to(C.ROOT)}): using the precomputed "
              f"flood maps of the paper from {C.RSFX_PRECOMPUTED.relative_to(C.ROOT)}", flush=True)
    for case in cases:
        for seed in seeds:
            for dem in dems:
                out = C.run_dir(case, seed, dem, "rsfloodxdepth")
                if rsfx is None:
                    out.mkdir(parents=True, exist_ok=True)
                    shutil.copy(C.RSFX_PRECOMPUTED / case / f"{seed}_{dem}" / "FloodClass.tif", out / "FloodClass.tif")
                    continue
                params = C.rsfx_params(case, seed, dem)
                print(f"[03] RS-FloodXdepth {case:16s} {seed:16s} {dem:7s} front_min={params['front_min']} "
                      f"k={params['k_neighbors']} region={params['region_row']}x{params['region_col']}", flush=True)
                t0 = time.time()
                run_rsfloodxdepth(rsfx, C.input_dir(case, seed, dem, "rsfloodxdepth"), out, params)
                print(f"     done in {time.time() - t0:.0f} s", flush=True)
    print("[03] RS-FloodXdepth outputs in", C.RUNS)


# %%
if __name__ == "__main__":
    run_all()
