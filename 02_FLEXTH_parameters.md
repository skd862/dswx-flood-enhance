# FLEXTH - parameters and the values used in the paper

FLEXTH: Betterle, A. & Salamon, P. (2024). *Water depth estimate and flood extent enhancement for
satellite-based inundation maps.* NHESS 24, 2817-2836. Code: https://code.europa.eu/floods/floods-river/flexth
(v1.3, EUPL-1.2). The implementation is in `02_flexth.py`; the values are set in `config.py`
(`FLEXTH_COMMON`, `FLEXTH_CASE`).

## Inputs (one folder per run, written by `01_prepare_inputs.py`)

| File | Meaning | How it was built in this study |
|---|---|---|
| `flood.tif` | initial flood map (1 flood, 0 dry, 255 no data -> treated as dry) | BWTR water; CONF water classes (all or without "Partial water \| Cloud mask") |
| `dtm.tif` | terrain model on the flood-map grid | FABDEM or USGS 3DEP (30 m, GEE exports), bilinear `gdal.Warp` onto the flood grid |
| `exclusion.tif` | where flooding may be propagated (1), i.e. pixels the satellite could not see; 255 -> treated as 1 | cloud / cloud shadow / adjacent to cloud (BWTR 253, CONF 10-14; DSWE INWAM 9) + forest (DSWx land cover 201) |
| `permanent_water.tif` | permanent water bodies (1) | Louisville BWTR runs: JRC Global Surface Water (GEE export); Louisville CONF runs and Sugar Land: DSWx land cover 200 "Water, wetland, mangrove forest" |

## Outputs

`WD_*.tif` water depth (cm, 9999 on permanent water), `WE_*.tif` flood extent (1 where WD > 0 plus every
initially flooded pixel). The extent `WE` is what is evaluated in Table 3.

## Parameters

| Code name (`config.py` key) | Symbol | Meaning | Default | **Value used** |
|---|---|---|---|---|
| `wl_method` | - | water level inside a flooded area: `method_A` = inverse-distance-weighted (IDW) mean of the smoothed border elevations; `method_B` = IDW quantile | method_A | **method_A** |
| `threshold_slope` | S_max | border pixels steeper than this (dz/dx) are not used to estimate the water level | 0.1 | **0.1** |
| `size_gaps_close` | A_g (km²) | holes in the initial flood map smaller than this are filled | 0.01-0.1 | **0.1** |
| `max_number_neighbors` | N_max | number of border pixels used for the water level at each flooded pixel | 200 | **200** |
| `inverse_dist_exp` | α | IDW exponent (water level inside flooded areas) | 1 | **1** |
| `border_subsampling` | Sbs_r | sub-sampling of border pixels of large flooded areas (0 = use all) | 0 | **0** |
| `min_flood_border_size` | N_min | if fewer valid border pixels, use quantile P* of the elevations inside the area | 10 | **10** |
| `border_quantile` | P | quantile of border elevations (method_B only) | 0.5 | 0.5 (unused) |
| `inner_quantile` | P* | quantile used when there are < N_min border pixels | 0.98 | **0.98** |
| `spread_outside_exclusion` | Sprd | allow propagation outside the exclusion mask | False | **False** |
| `max_propagation_distance` | **D_max (km)** | maximum distance flooding can propagate from the initial border, reached by arbitrarily large flooded areas | 10 | **5** (all cases) |
| `distance_range` | **A_1/2 (km²)** | size of a flooded area that may propagate to half of D_max; controls how fast D_max is approached as the flooded area grows | 10 | **1** (Louisville), **5** (Sugar Land) |
| `wd_star` | WD* (cm) | dummy depth for initially flooded pixels where WL < DTM | 10 | **10** |

The propagation limit of a flooded area of size A is

    d_max(A) = D_max · (1 − 2^(−A / A_1/2))

and the water level decays linearly from the border value to the ground over that distance, so water never
flows uphill and is never spread farther than `d_max`.

### Final values

| Case | D_max (km) | A_1/2 (km²) | ratio D_max / A_1/2 |
|---|---|---|---|
| Louisville, Apr 8 2025 | 5 | 1 | 5 |
| Louisville, Apr 9 2025 | 5 | 1 | 5 |
| Sugar Land (Harvey), Sep 4 2017 | 5 | 5 | 1 |

All other parameters were left at the developer's defaults for every run (Section 3.2 of the paper: most parameters only
have a minor influence; D_max and A_1/2 - and in particular their ratio - dominate the extent).
Minor exception: the two original Louisville BWTR + FABDEM runs used S_max = 1 and A_g = 1 km²; this repository
uses the defaults for them too (effect <= 0.02; README, Sections 5-6). The border elevations are smoothed with
FLEXTH's 5 x 5 window (the paper text says 3 x 3; the published results used the 5 x 5 code).

**How they were chosen.** D_max and A_1/2 were swept over {1, 5, 10, 20, 50, 100} with A_1/2 ≤ D_max
(21 combinations) for every case / initial flood map / DEM. A large ratio spreads water over large areas
(more true positives and recall, but unrealistic expansion); the retained pair is the most stable one that did
not create artificial flooding, and it was then kept fixed for every run of a case so that differences in
Table 3 come only from the initial flood map and the DEM.

### Notes

1. FLEXTH treats 255 (no data) in the **exclusion** mask as "excluded" (propagation allowed) and in the
   **flood** map as dry.
2. The binary extent output `WE` and the passing of parameters as arguments are the only changes to the
   FLEXTH v1.3 code; the tiling option was removed because it was not used.

## Code provenance

The FLEXTH algorithm in `02_flexth.py` is copied from the official FLEXTH v1.3 release by its authors
(https://code.europa.eu/floods/floods-river/flexth, EUPL-1.2). Only the interface was changed (parameters
passed as arguments, binary extent output `WE` added, unused tiling option removed); the computations are
unchanged.
