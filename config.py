"""
Central configuration for the replication code (dswx-flood-enhance) of

    Do, S.K., Munasinghe, D., Tian, D., Cohen, S., Eylander, J., Crisanti, S., Tran, D., Lakshmi, V. (2027).
    Under cloud and canopy: enhancing the Dynamic Surface Water eXtent - Harmonized Landsat Sentinel-2
    (DSWx-HLS) flood maps with terrain-based flood propagation.
    ISPRS Journal of Photogrammetry and Remote Sensing 243, 840-858.
    https://doi.org/10.1016/j.isprsjprs.2026.10.045

Every path, file name, class code and the final parameter values used in the paper live here, so the
numbered scripts (01_ ... 05_) never hard-code anything.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
SOURCE = DATA / "source"          # products exactly as downloaded (DSWx-HLS, DSWE, DSWx LAND tiles)
ANCILLARY = DATA / "ancillary"    # hand-labelled benchmarks, AOIs, GEE exports (DEMs, JRC permanent water)
OUT = ROOT / "outputs"
INPUTS = OUT / "inputs"           # written by 01_prepare_inputs
RUNS = OUT / "runs"               # written by 02_flexth / 03_rsfloodxdepth
RSFX_PRECOMPUTED = DATA / "precomputed" / "rsfloodxdepth"   # RS-FloodXdepth flood maps of the paper (used by 03)
RESULTS = OUT / "results"         # written by 04_evaluate
FIGURES = OUT / "figures"         # written by 05_figures
REFERENCE = ROOT / "reference"    # Table 2 / Table 3 values as published

# ---------------------------------------------------------------------------------------------
# Study cases
# ---------------------------------------------------------------------------------------------
# Louisville: two DSWx-HLS acquisitions (S2A on Apr 8, Landsat-8 on Apr 9), MGRS tiles 16SEH + 16SFH.
LOUISVILLE_GRANULES = {
    "0408": ["OPERA_L3_DSWx-HLS_T16SEH_20250408T163701Z_20250410T154426Z_S2A_30_v1.0",
             "OPERA_L3_DSWx-HLS_T16SFH_20250408T163701Z_20250410T035845Z_S2A_30_v1.0"],
    "0409": ["OPERA_L3_DSWx-HLS_T16SEH_20250409T161656Z_20250411T111227Z_L8_30_v1.0",
             "OPERA_L3_DSWx-HLS_T16SFH_20250409T161656Z_20250411T111103Z_L8_30_v1.0"],
}
# Land cover (B07_LAND) is taken from the Apr 8 granules for both dates (as in the original analysis).
LOUISVILLE_LAND_DATE = "0408"

# Harvey: USGS Landsat Collection-2 DSWE (ARD tiles h017 v016/v017), acquired 2017-09-04.
HARVEY_INWAM = ["LC08_CU_017016_20170904_20210503_02_INWAM.TIF",
                "LC08_CU_017017_20170904_20210503_02_INWAM.TIF"]
HARVEY_INTSM = ["LC08_CU_017017_20170904_20210503_02_INTSM.TIF"]   # only h017v017 intersects the benchmark
# DSWx-HLS is not available for 2017 (OPERA production began in 2023): land cover for Harvey comes from
# January 2025 DSWx-HLS B07_LAND tiles.
HARVEY_LAND_GLOB = "OPERA_L3_DSWx-HLS_*_B07_LAND.tif"
# The granules bundled in data/source/harvey/dswx_land (used by `01_prepare_inputs.py --download`)
HARVEY_LAND_GRANULES = [
    "OPERA_L3_DSWx-HLS_T14RQS_20250105T170711Z_20250107T023812Z_S2A_30_v1.0",
    "OPERA_L3_DSWx-HLS_T14RQT_20250105T170711Z_20250107T023811Z_S2A_30_v1.0",
    "OPERA_L3_DSWx-HLS_T14RQU_20250105T170711Z_20250107T023815Z_S2A_30_v1.0",
    "OPERA_L3_DSWx-HLS_T14RQV_20250103T171629Z_20250105T011939Z_S2B_30_v1.0",
    "OPERA_L3_DSWx-HLS_T14RQV_20250105T170711Z_20250107T023825Z_S2A_30_v1.0",
    "OPERA_L3_DSWx-HLS_T15RTM_20250105T170711Z_20250107T023804Z_S2A_30_v1.0",
    "OPERA_L3_DSWx-HLS_T15RTN_20250105T170711Z_20250107T023815Z_S2A_30_v1.0",
    "OPERA_L3_DSWx-HLS_T15RTP_20250105T170711Z_20250107T023812Z_S2A_30_v1.0",
    "OPERA_L3_DSWx-HLS_T15RTQ_20250102T165711Z_20250104T022525Z_S2A_30_v1.0",
    "OPERA_L3_DSWx-HLS_T15RTQ_20250105T170711Z_20250107T023816Z_S2A_30_v1.0",
    "OPERA_L3_DSWx-HLS_T15RUN_20250105T170711Z_20250107T023759Z_S2A_30_v1.0",
    "OPERA_L3_DSWx-HLS_T15RUP_20250102T165711Z_20250104T022524Z_S2A_30_v1.0",
    "OPERA_L3_DSWx-HLS_T15RUP_20250105T170711Z_20250107T023804Z_S2A_30_v1.0",
    "OPERA_L3_DSWx-HLS_T15RUQ_20250102T165711Z_20250104T022523Z_S2A_30_v1.0",
    "OPERA_L3_DSWx-HLS_T15RUQ_20250105T170711Z_20250107T033659Z_S2A_30_v1.0",
]

CASES = {
    # case id : (site, date key)   -> "date key" selects the DSWx granules for Louisville
    "louisville_0408": ("louisville", "0408"),
    "louisville_0409": ("louisville", "0409"),
    "harvey":          ("harvey", None),
}
SEEDS = ["bwtr", "conf", "conf_no_partial"]   # the three initial flood maps of Table 3
DEMS = ["fabdem", "3dep"]

# ---------------------------------------------------------------------------------------------
# Ancillary files
# ---------------------------------------------------------------------------------------------
LOU = ANCILLARY / "louisville"
HAR = ANCILLARY / "harvey"
ANC = {
    "louisville": {
        "benchmark": LOU / "benchmark_hand_label.tif",        # NOAA aerial hand label (~10 m, UTM 16N)
        "aoi": LOU / "aoi_analysis.shp",                      # analysis AOI (CONF runs, Table 2 CONF)
        "aoi_bwtr": LOU / "aoi_bwtr_runs.shp",                # footprint of the aerial mosaic (BWTR runs, Table 2 BWTR)
        "aoi_rsfx_bwtr": LOU / "aoi_rsfloodxdepth_bwtr.shp",  # RS-FloodXdepth BWTR runs were clipped to this box
        "permanent_water": LOU / "permanent_water_jrc_gee.tif",  # JRC Global Surface Water permanent water (GEE export, EPSG:3857)
        "fabdem": LOU / "fabdem_30m_gee.tif",                 # GEE export of FABDEM (EPSG:3857)
        "3dep": LOU / "3dep_30m_gee.tif",                     # GEE export of USGS 3DEP aggregated to 30 m (EPSG:5070)
    },
    "harvey": {
        "benchmark": HAR / "benchmark_hand_label_30m.tif",    # NOAA aerial hand label resampled to 30 m (EPSG:3857); defines the grid
        "aoi": HAR / "aoi.shp",
        "fabdem": HAR / "fabdem_30m_gee.tif",
        "3dep": HAR / "3dep_30m_gee.tif",
        # Intermediate layers exactly as used in the paper. They were made from the raw tiles in
        # data/source/harvey with interactive GIS steps (ArcGIS Pro "Clip Raster", which resampled
        # INTSM to ~30.15 m; an earlier mosaic of the 2025 land-cover tiles) that cannot be re-run
        # bit-for-bit in Python. See HARVEY_EXACT below.
        "inwam_30m": HAR / "paper_intermediates" / "dswe_inwam_bwtr_30m.tif",
        "intsm_clipped": HAR / "paper_intermediates" / "dswe_intsm_clipped.tif",
        "land_mosaic": HAR / "paper_intermediates" / "dswx_land_mosaic_2025.tif",
    },
}

# True  -> Harvey layers start from the bundled paper intermediates (reproduces Tables 2-3 exactly)
# False -> everything is rebuilt from the raw DSWE / DSWx tiles in Python. Agreement with the paper's
#          layers is then 99.97 % (BWTR/INWAM), ~94 % (CONF/INTSM) and ~97 % (land cover); Harvey metrics
#          move by <= 0.02, except RS-FloodXdepth with the CONF-no-partial seed (up to 0.16).
HARVEY_EXACT = True

# Tile order of the rioxarray mosaics (first tile wins where tiles overlap) - as in the original runs
LOUISVILLE_TILE_ORDER = {"B02_BWTR": [1, 0],    # 16SFH first
                         "B03_CONF": [0, 1],    # 16SEH first
                         "B07_LAND": [0, 1]}

# ---------------------------------------------------------------------------------------------
# Class codes
# ---------------------------------------------------------------------------------------------
NODATA = 255
# Class codes below follow the OPERA DSWx-HLS Product Specification (JPL D-107395 Rev B, v1.0.1) and the USGS
# Landsat C2 L3 DSWE Data Format Control Book (LSDS-2042 v3.0).
# DSWx-HLS B02_BWTR: 0 not water | 1 water (open water or partial surface water) | 252 snow/ice |
#   253 cloud/cloud shadow and adjacent to cloud/cloud shadow (HLS Fmask) | 254 ocean masked | 255 fill
BWTR_WATER, BWTR_SNOW, BWTR_CLOUD = 1, 252, 253
# DSWx-HLS B03_CONF: 0 not water | 1 open water high-confidence | 2 open water moderate-confidence |
#   3 partial surface water conservative | 4 partial surface water aggressive; the same classes + 10 where the
#   pixel is potentially obstructed by cloud/cloud shadow/adjacent (Fmask), + 20 where Fmask marks snow/ice
#   (and not cloud); 254 ocean masked; 255 fill.
# After collapsing (01_prepare_inputs.collapse_conf_dswx):
#   0 not water | 1 water (unmasked) | 10 not water | cloud | 11 OPEN water | cloud | 12 PARTIAL water | cloud
#   20 not water | snow   | 21 water | snow | 255 fill
CONF_WATER_ALL = [1, 11, 12, 21]          # seed "conf"
CONF_WATER_NO_PARTIAL = [1, 11, 21]       # seed "conf_no_partial" ("Partial water | Cloud mask" treated as non-water)
CONF_CLOUD = [10, 11, 12]
# DSWx-HLS B07_LAND
# (0-99 low intensity developed, 100-199 high intensity developed, 255 fill)
LAND_PERMANENT_WATER = 200                # "Water, wetland, mangrove forest"
LAND_FOREST = 201                         # "A variety of forest classes"
# USGS Landsat C2 DSWE INTSM / INWAM: 0 not water | 1 water - high confidence | 2 water - moderate confidence |
#   3 partial surface water - conservative | 4 partial surface water - aggressive | 9 cloud, cloud shadow
#   (INWAM only) | 255 fill. INTSM = interpreted layer screened for terrain (hillshade), snow and land cover;
#   INWAM = INTSM + cloud and cloud shadow from the Level-2 QA_PIXEL band.

# ---------------------------------------------------------------------------------------------
# Final parameters used in the paper (one set per method and case; see 02_/03_ parameter documents)
# ---------------------------------------------------------------------------------------------
FLEXTH_COMMON = dict(
    wl_method="method_A",            # water level by IDW of smoothed border elevations
    threshold_slope=0.1,             # S_max
    size_gaps_close=0.1,             # A_g (km2)
    max_number_neighbors=200,        # N_max
    inverse_dist_exp=1,              # alpha
    border_subsampling=0,            # Sbs_r
    min_flood_border_size=10,        # N_min
    border_quantile=0.5,             # P   (method_B only)
    inner_quantile=0.98,             # P*
    spread_outside_exclusion=False,  # Sprd
    wd_star=10,                      # WD* (cm)
)
FLEXTH_CASE = {
    # (D_max km, A_1/2 km2)  -> ratio D_max/A_1/2 = 5 for Louisville, 1 for Harvey
    "louisville_0408": dict(max_propagation_distance=5, distance_range=1),
    "louisville_0409": dict(max_propagation_distance=5, distance_range=1),
    "harvey":          dict(max_propagation_distance=5, distance_range=5),
}
RSFX_COMMON = dict(
    back_min=100,        # minimum size (pixels) of non-flood (background) objects
    max_points=12,       # IDW: number of centroids used per pixel
    power=2.0,           # IDW power
)
RSFX_CASE = {
    # front_min = flood-object threshold (pixels); k = neighbours for the LWSE outlier screen;
    # region_row/region_col = sub-region tiling used when labelling flood objects (ImageObject)
    "louisville_0408": dict(front_min=100, k_neighbors=3, region_row=8, region_col=10),
    "louisville_0409": dict(front_min=100, k_neighbors=1, region_row=10, region_col=12),
    "harvey":          dict(front_min=2000, k_neighbors=None, region_row=8, region_col=10),
}
# Harvey: k_neighbors differs between seeds (front_min and region tiling are constant). It only affects the
# LWSE outlier screen; with very few flood objects a large k fails (see 03_rsfloodxdepth.py).
RSFX_HARVEY_K = {("bwtr", "fabdem"): 1, ("bwtr", "3dep"): 1,
                 ("conf", "fabdem"): 4, ("conf", "3dep"): 4,
                 ("conf_no_partial", "fabdem"): 3, ("conf_no_partial", "3dep"): 3}


# ---------------------------------------------------------------------------------------------
# Permanent water
# ---------------------------------------------------------------------------------------------
# Louisville: JRC Global Surface Water permanent-water mask (Google Earth Engine export).
# Sugar Land (Harvey): DSWx-HLS land cover (B07_LAND) class 200 "Water, wetland, mangrove forest".
# This mask is EXCLUDED from every evaluation. As FLEXTH input (permanent_water.tif), Louisville BWTR runs use
# the JRC mask and Louisville CONF runs use DSWx land cover class 200 (as in the original runs).


def flexth_params(case, seed, dem):
    p = dict(FLEXTH_COMMON)
    p.update(FLEXTH_CASE[case])
    return p


def rsfx_params(case, seed, dem):
    p = dict(RSFX_COMMON)
    p.update(RSFX_CASE[case])
    if case == "harvey":
        p["k_neighbors"] = RSFX_HARVEY_K[(seed, dem)]
    return p


def input_dir(case, seed, dem, method):
    """Folder holding flood.tif / dtm.tif (/ exclusion.tif / permanent_water.tif) for one run."""
    return INPUTS / case / method / f"{seed}_{dem}"


def run_dir(case, seed, dem, method):
    return RUNS / case / method / f"{seed}_{dem}"
