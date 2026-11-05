# RS-FloodXdepth - parameters and the values used in the paper

RS-FloodXdepth: Tian, D., Liu, H., Wang, L., Cohen, S. & Mandal, T. (2026). *RS-FloodXdepth: Enhancing remote
sensing-derived flood extent and estimating flood depth using a hydrologically guided region-growing method and
high-resolution DEMs.* Water Resources Research 62, e2025WR042384. https://doi.org/10.1029/2025WR042384.
The values used in the paper are set in `config.py` (`RSFX_COMMON`, `RSFX_CASE`, `RSFX_HARVEY_K`).

**The RS-FloodXdepth code is not included in this repository** (it belongs to its developers, Surface Dynamics
Modeling Lab, University of Alabama). By default `03_rsfloodxdepth.py` uses the flood maps produced for the paper
(`data/precomputed/rsfloodxdepth/`); with the code obtained from the developers it runs the method itself
(see the header of `03_rsfloodxdepth.py`).

## Inputs / outputs

* `flood.tif` - initial flood map (1 flood, 0 everything else) and `dtm.tif` - DEM on the same grid.
  Unlike FLEXTH there is no exclusion mask: growth can happen anywhere the terrain allows.
* `FloodClass.tif` - 0 dry, 1 initial (seed) flood, 2 flood added by region growing -> classes 1 and 2 are
  evaluated as water in Table 3. `FloodDepth.tif` - depth (m). `centroid_elevation.shp` - flood objects and
  their local water-surface elevation (LWSE); `boundary_elevation.shp` - boundary pixels with DEM elevation.

## Algorithm and parameters

1. **Flood objects** (`ImageObject`): 4-connected labelling of the seed, morphological clean-up and removal of
   small objects. The image is processed in `region_row × region_col` sub-regions.
2. **Local water level**: for each object, a Gaussian KDE of the DEM elevations of its boundary pixels; LWSE =
   highest KDE peak + standard deviation of the boundary elevations above the preceding valley.
3. **Outlier screening**: an LWSE below mean − 2σ or above mean + 3σ of its `k_neighbors` nearest centroids is
   replaced by the inverse-distance mean of those neighbours.
4. **Water surface**: IDW interpolation (`gdal.Grid invdist`, `power`, `max_points`) of the centroid LWSEs.
5. **Region growing** from the seed pixels into 8-connected neighbours with DEM < water surface.

| Code name (`config.py` key) | Meaning | **Value used** |
|---|---|---|
| `front_min` | **flood-object threshold**: minimum size (pixels) of a flood object to be kept and used for water-level estimation - the most influential parameter (smaller -> more objects, more expansion, more risk of spurious spread) | **100** (Louisville), **2000** (Sugar Land) |
| `back_min` | minimum size (pixels) of background (non-flood) objects; smaller dry holes are filled | **100** |
| `region_row`, `region_col` | number of sub-region rows / columns used by `ImageObject` | **8 × 10** (Louisville Apr 8, Sugar Land), **10 × 12** (Louisville Apr 9) |
| `k_neighbors` | neighbouring centroids used in the outlier screen | **3** (Louisville Apr 8), **1** (Louisville Apr 9), Sugar Land: **1** (BWTR), **4** (CONF), **3** (CONF no partial) |
| `max_points` | centroids used by the IDW at each pixel | **12** |
| `power` | IDW power | **2** |

### Final values per case

| Case | front_min | back_min | region | k_neighbors | max_points | power |
|---|---|---|---|---|---|---|
| Louisville, Apr 8 2025 | 100 | 100 | 8 × 10 | 3 | 12 | 2 |
| Louisville, Apr 9 2025 | 100 | 100 | 10 × 12 | 1 | 12 | 2 |
| Sugar Land, Sep 4 2017 | 2000 | 100 | 8 × 10 | 1 / 4 / 3 (BWTR / CONF / CONF no partial) | 12 | 2 |

**How they were chosen.** `front_min` was swept (Louisville: 20, 100, 500; Sugar Land: 500, 1000, 2000, 3000)
together with `k_neighbors` (1-5) and several region tilings (8 × 10, 10 × 12, ...). The flood-object threshold dominates the result; the
value retained gives realistic enhancement without artificial spread and was kept for every run of a case.

### Notes

* For Sugar Land, `front_min` and the region tiling are the same in every run, while `k_neighbors` is
  1 / 4 / 3 for the BWTR / CONF / CONF-no-partial seeds (identical for both DEMs). `k_neighbors` only affects
  the outlier screen of step 3 and its influence is small.
* `k_neighbors` must be smaller than the number of flood objects that receive a water level. If it is too high
  (large `front_min` and/or a sparse seed), the outlier screen fails - lower `k_neighbors` (or `front_min`)
  in `config.py` and run again.

## Code provenance

The flood maps in `data/precomputed/rsfloodxdepth/` were produced by running the inputs written by
`01_prepare_inputs.py` through the RS-FloodXdepth code provided by its developers (FIM-Enhance, Surface Dynamics
Modeling Lab, University of Alabama), unchanged, with the parameters above. Only `FloodClass.tif` (the layer
evaluated in Table 3) is included.
