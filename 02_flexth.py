# %% [markdown]
# # 02 - FLEXTH flood enhancement
#
# FLEXTH (Betterle & Salamon, 2024, NHESS 24, 2817-2836; https://code.europa.eu/floods/floods-river/flexth)
# extends an initial flood map into cloud-/canopy-obscured (exclusion) pixels wherever the terrain allows it,
# and estimates water level / depth.
#
# This file contains, in one place:
#   1. the FLEXTH v1.3 algorithm (`flood_processing`) - unchanged numerics; the module-level
#      "param_*" globals of the original script were turned into a `params` dict and the tiling / merge
#      options (not used in the paper) were removed;
#   2. the runner that executes the 18 configurations of Table 3
#      (3 cases x 3 initial flood maps x 2 DEMs) with the final parameters from `config.py`.
#
# Parameters and the values used in the paper are explained in `02_FLEXTH_parameters.md`.
#
# Licence: FLEXTH is (C) European Union 2023, licensed under the EUPL v1.2 (see third_party/FLEXTH_LICENCE_EUPL-1.2.txt).
# Modifications in this copy: parameters passed as arguments; added the binary extent output
# `WE_*.tif` (WD > 0, plus every initially flooded pixel) used for the evaluation; tiling removed.
#
# Inputs (per run, written by 01_prepare_inputs.py): flood.tif, dtm.tif, exclusion.tif, permanent_water.tif
# Outputs: WD_*.tif (water depth, cm; 9999 on permanent water) and WE_*.tif (flood extent 0/1)

# %%
import time
import warnings
from pathlib import Path

import cv2
import numpy as np
import rasterio
from astropy.convolution import convolve
from scipy.spatial import cKDTree

import config as C


# %% [markdown]
# ## FLEXTH algorithm

# %%
def ij_neighbors(i, j, n_row, n_col, connectivity):
    """Indices of the neighbours of cell (i, j); out-of-raster neighbours are replaced by (i, j)."""
    if connectivity == 4:
        neighbors = np.array([[i-1, j], [i, j+1], [i+1, j], [i, j-1]])
    elif connectivity == 8:
        neighbors = np.array([[i-1, j-1], [i-1, j], [i-1, j+1], [i, j+1], [i+1, j+1], [i+1, j], [i+1, j-1], [i, j-1]])
    elif connectivity == 24:
        neighbors = np.array([[i-2, j-2], [i-2, j-1], [i-2, j], [i-2, j+1], [i-2, j+2], [i-1, j-2], [i-1, j-1], [i-1, j],
                              [i-1, j+1], [i-1, j+2], [i, j-2], [i, j-1], [i, j+1], [i, j+2], [i+1, j-2], [i+1, j-1],
                              [i+1, j], [i+1, j+1], [i+1, j+2], [i+2, j-2], [i+2, j-1], [i+2, j], [i+2, j+1], [i+2, j+2]])
    else:
        raise ValueError(f"Unsupported connectivity value: {connectivity}")

    for indice in range(len(neighbors)):
        if neighbors[indice, 0] > n_row-1 or neighbors[indice, 0] < 0:
            neighbors[indice, 0] = i
            neighbors[indice, 1] = j
        if neighbors[indice, 1] > n_col-1 or neighbors[indice, 1] < 0:
            neighbors[indice, 0] = i
            neighbors[indice, 1] = j
    return neighbors.astype('uint32')


def weighted_quantile(values, percentile, weights=None):
    """Distance-weighted quantile across the columns of a 2-D array (used by method_B)."""
    values = np.array(values)
    percentile = np.array(percentile)
    if weights is None:
        weights = np.ones(np.shape(values))
    weights = np.array(weights)
    assert np.all(percentile >= 0) and np.all(percentile <= 1), 'percentile should be in [0, 1]'
    sorter = np.argsort(values)
    values = np.take_along_axis(values, sorter, axis=1)
    weights = np.take_along_axis(weights, sorter, axis=1)
    weighted_quantiles = np.cumsum(weights, axis=1) - 0.5 * weights
    weighted_quantiles /= np.sum(weights, axis=1)[:, np.newaxis] * np.ones(np.shape(weighted_quantiles))
    return values[np.array(np.arange(0, np.shape(values)[0], 1)), np.argmin((weighted_quantiles - percentile)**2, axis=1)]


def _read_binary(path, transform, crs, other_value):
    """Read an optional 0/1 mask; values other than 0/1 (e.g. 255 nodata) are set to `other_value`."""
    with rasterio.open(path) as src:
        arr = src.read(1).astype('uint8')
        arr[(arr != 1) & (arr != 0)] = other_value
        if transform != src.transform or crs != src.crs:
            raise TypeError(f"Flood map and {Path(path).name} don't share the same projections and/or grid!")
    return arr


def flood_processing(flood_path, dtm_path, exclusion_path, obswater_path, permanent_water_path, output_dir, params):
    """Run FLEXTH on one set of inputs. `params` keys are those of config.FLEXTH_COMMON/FLEXTH_CASE."""
    p = params
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # IMPORT FLOOD MAP AND DTM
    with rasterio.open(flood_path) as src:
        flood = src.read(1).astype('uint8')
        flood[(flood != 1) & (flood != 0)] = 0          # nodata in the flood map -> not flooded
        transform = src.transform
        crs = src.crs
    with rasterio.open(dtm_path) as src:
        dtm = src.read(1)
        transform_dtm = src.transform
        crs_dtm = src.crs
        dtm_nodata = src.nodata
        dtm[dtm == dtm_nodata] = np.nan
    if transform != transform_dtm or crs != crs_dtm:
        raise TypeError("Flood map and DTM don't share the same projections and/or grid!")

    # OPTIONAL INPUTS (nodata in the exclusion mask -> excluded, i.e. flooding may propagate there)
    has_exclusion = Path(exclusion_path).is_file()
    exclusion = _read_binary(exclusion_path, transform, crs, 1) if has_exclusion else np.full_like(flood, 0)
    obswater = _read_binary(obswater_path, transform, crs, 0) if Path(obswater_path).is_file() else np.copy(flood)
    has_permanent = Path(permanent_water_path).is_file()
    permanent_water = _read_binary(permanent_water_path, transform, crs, 0) if has_permanent else np.full_like(flood, 0)

    # GEOTRANSFORMATION
    n_row, n_col = flood.shape
    L = transform.a                                       # pixel size in m (square pixels)

    # LOCAL SLOPE
    slope_max = np.gradient(dtm, L)
    slope_max = np.sqrt(slope_max[0]**2 + slope_max[1]**2)
    slope_steep = np.array(slope_max > p["threshold_slope"]).astype('uint8')

    # CONNECTED COMPONENTS ANALYSIS - IDENTIFIES CONTIGUOUS FLOODED AREAS
    kernel_1 = np.ones((3, 3), np.uint8)
    kernel_1_cross = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=np.uint8)
    kernel_2 = np.ones((5, 5), np.uint8)

    # MORPHOLOGICAL CLOSING TO REMOVE SMALL HOLES AND VERY IRREGULAR BORDERS
    flood = cv2.morphologyEx(flood, cv2.MORPH_CLOSE, kernel_1_cross, iterations=2)
    obswater = cv2.morphologyEx(obswater, cv2.MORPH_CLOSE, kernel_1_cross, iterations=2)
    exclusion = cv2.dilate(exclusion, kernel_1)

    # CLOSES SMALL HOLES IN FLOOD MAP
    print('Closing small gaps in flood map...')
    threshold_n_pixels = int(p["size_gaps_close"] * 1e6 / L**2)
    binary_map_complementary_flood = np.logical_not(flood).astype('uint8')
    z_num_labels, z_labels, z_stats, z_centroids = cv2.connectedComponentsWithStats(binary_map_complementary_flood, connectivity=8)
    for i in range(len(z_stats)):
        if np.abs(z_stats[i, 4]) < threshold_n_pixels:
            win = (slice(z_stats[i, 1], z_stats[i, 1] + z_stats[i, 3]), slice(z_stats[i, 0], z_stats[i, 0] + z_stats[i, 2]))
            flood[win][z_labels[win] == i] = 1
            obswater[win][z_labels[win] == i] = 1

    if has_permanent:
        permanent_water = cv2.morphologyEx(permanent_water, cv2.MORPH_CLOSE, kernel_1_cross, iterations=2)
    else:
        permanent_water = obswater - flood
        permanent_water[(permanent_water != 0) & (permanent_water != 1)] = 0

    # z_stats: [xtop, ytop, xwidth, ywidth, #pixels]; first row = background
    z_num_labels, z_labels, z_stats, z_centroids = cv2.connectedComponentsWithStats(flood, connectivity=8)

    flood_dilated = cv2.dilate(flood, kernel_1)
    flood_eroded = cv2.erode(flood, kernel_1_cross)
    exclusion_dilated = cv2.dilate(exclusion, kernel_1)
    permanent_water_dilated = cv2.dilate(permanent_water, kernel_1)

    flood_border = flood_dilated - flood_eroded
    flood_border_inner = flood - flood_eroded
    slope_steep_dilated = cv2.dilate(slope_steep, kernel_1)

    exclusion_dilated[(exclusion == 0) & (exclusion_dilated == 1) & (flood == 0) & (flood_dilated == 1)] = 0
    permanent_water_dilated[(permanent_water == 0) & (permanent_water_dilated == 1) & (flood == 0) & (flood_dilated == 1)] = 0
    slope_steep_dilated[(slope_steep == 0) & (slope_steep_dilated == 1) & (flood == 0) & (flood_dilated == 1)] = 0

    # valid border pixels: not touching the exclusion mask, permanent water or steep terrain
    flood_border = flood_border * np.logical_not(exclusion_dilated) * np.logical_not(permanent_water_dilated) * np.logical_not(slope_steep_dilated)
    dtm_border_flood = dtm * flood_border

    # AVERAGES THE DEM ALONG THE BORDER
    dtm_border_flood_smooth = convolve(dtm_border_flood, kernel_2, mask=flood_border == 0, preserve_nan=True)
    dtm_border_flood_smooth[flood_border == 0] = np.nan
    flood_border = flood_border * flood_border_inner

    # WATER LEVEL ESTIMATION IN INITIALLY FLOODED AREAS
    z_water_level = np.full([n_row, n_col], np.nan, dtype='float32')
    ROW, COL = np.mgrid[0:n_row, 0:n_col].astype('uint32')

    row_flood = np.ma.masked_array(ROW, z_labels == 0).compressed()
    col_flood = np.ma.masked_array(COL, z_labels == 0).compressed()
    flood_labels_compressed = np.ma.masked_array(z_labels, z_labels == 0).compressed()

    row_flood_border = np.ma.masked_array(ROW, flood_border == 0).compressed()
    col_flood_border = np.ma.masked_array(COL, flood_border == 0).compressed()
    flood_borders_labels_compressed = np.ma.masked_array(z_labels, flood_border == 0).compressed()
    dtm_border_flood_smooth_compressed = np.ma.masked_array(dtm_border_flood_smooth, flood_border == 0).compressed()

    param_border_subsampling_sill = 100000   # Sbs_s: max number of border pixels of one flooded area used for WL

    print('Assigning water elevation to initial flooded areas...')
    for i in range(1, len(z_stats)):
        temp_position_flood = np.stack((row_flood[flood_labels_compressed == i], col_flood[flood_labels_compressed == i]), axis=1)
        temp_position_border = np.copy(np.stack((row_flood_border[flood_borders_labels_compressed == i], col_flood_border[flood_borders_labels_compressed == i]), axis=1))
        temp_dtm_border_flood_smooth = np.copy(dtm_border_flood_smooth_compressed[flood_borders_labels_compressed == i])
        len_border = len(temp_position_border)

        # too few valid border pixels -> quantile P* of the DTM inside the flooded area
        if len_border < p["min_flood_border_size"]:
            with warnings.catch_warnings():
                warnings.filterwarnings('ignore')
                z_water_level[temp_position_flood[:, 0], temp_position_flood[:, 1]] = np.nanquantile(
                    dtm[temp_position_flood[:, 0], temp_position_flood[:, 1]], p["inner_quantile"])
        else:
            # SUBSAMPLING OF THE BORDER
            tt = len_border / param_border_subsampling_sill
            param_border_subsampling_ = 2 - p["border_subsampling"]
            param_border_subsampling_ = param_border_subsampling_ if param_border_subsampling_ != 0 else (param_border_subsampling_ + 0.0001)
            border_sampling = len_border / (param_border_subsampling_sill / param_border_subsampling_ * (1 + tt - np.sqrt((tt + 1)**2 - 2 * param_border_subsampling_ * tt)))
            temp_position_border = temp_position_border[::np.round(border_sampling).astype(int)]
            temp_dtm_border_flood_smooth = temp_dtm_border_flood_smooth[::np.round(border_sampling).astype(int)]
            len_border = len(temp_position_border)

            tree_BORDER = cKDTree(temp_position_border)
            distances, indices = tree_BORDER.query(temp_position_flood, k=p["max_number_neighbors"], workers=8)
            distances = distances.astype('float32')
            distances[distances == 0] = 1
            indices = indices.astype('uint32')
            if distances.ndim == 1:
                distances = np.expand_dims(distances, axis=1)
                indices = np.expand_dims(indices, axis=1)
            if p["max_number_neighbors"] > len_border:
                indices = indices[:, :len_border]
                distances = distances[:, :len_border]

            weights = 1 / (distances ** p["inverse_dist_exp"]).astype('float32')     # inverse distance weighting

            if p["wl_method"] == 'method_A':      # IDW of border elevations
                dtm_temp_statistic = (np.sum((temp_dtm_border_flood_smooth[indices] * weights).astype('float32'), axis=1) / np.sum(weights, axis=1)).astype('float32')
            elif p["wl_method"] == 'method_B':    # distance-weighted quantile of border elevations
                dtm_temp_statistic = weighted_quantile(temp_dtm_border_flood_smooth[indices], p["border_quantile"], weights=weights)
            z_water_level[temp_position_flood[:, 0], temp_position_flood[:, 1]] = dtm_temp_statistic

    # FLOOD EXPANSION
    z_water_level_augmented = np.copy(z_water_level)
    if has_exclusion or p["spread_outside_exclusion"]:
        print('Augmenting flooded areas...')
        if p["spread_outside_exclusion"]:
            exclusion = np.full_like(exclusion, 1)
        param_connectivity = 8

        z_water_level_masked_compressed = np.ma.masked_array(z_water_level, flood_border_inner == 0).compressed()
        z_water_level_masked_compressed_initial = np.ma.masked_array(z_water_level, flood_border_inner == 0).compressed()
        row_flood_border = np.ma.masked_array(ROW, flood_border_inner == 0).compressed()
        col_flood_border = np.ma.masked_array(COL, flood_border_inner == 0).compressed()
        flood_labels_border = np.ma.masked_array(z_labels, flood_border_inner == 0).compressed()

        FLOOD = np.array([flood_labels_border, row_flood_border, col_flood_border, z_water_level_masked_compressed, z_water_level_masked_compressed_initial]).T
        FLOOD_sort_descending = np.flipud(FLOOD[FLOOD[:, 3].argsort()])   # decreasing water elevation

        dim_flooded_area = z_stats[:, 4] * L**2
        dim_flooded_area[dim_flooded_area < 0] = 0

        # MAX EXPANSION DISTANCE: D_max * (1 - 2^(-A / A_1/2)), per flooded area
        threshold_distance = p["max_propagation_distance"] * 1000 * (1 - pow(2, - dim_flooded_area / (p["distance_range"] * 1e6)))
        threshold_distance = threshold_distance + 1

        FLOOD_sort_descending_list = list(FLOOD_sort_descending)
        z_water_level_augmented = np.copy(z_water_level)
        z_labels_augmented = np.copy(z_labels)
        temp_dist_from_border = np.zeros(z_labels.shape, dtype='float16')

        i = 0
        i_counter = len(FLOOD_sort_descending_list)
        i_stop = len(FLOOD_sort_descending_list)
        while i < i_counter:
            if i == i_stop:
                FLOOD_sort_descending = np.vstack(FLOOD_sort_descending_list)
                FLOOD_sort_descending = FLOOD_sort_descending[i_stop:, :]
                FLOOD_sort_descending = np.flipud(FLOOD_sort_descending[FLOOD_sort_descending[:, 3].argsort()])
                FLOOD_sort_descending_list = list(FLOOD_sort_descending)
                i = 0
                i_stop = len(FLOOD_sort_descending)
                i_counter = len(FLOOD_sort_descending)

            vicini = ij_neighbors(FLOOD_sort_descending[i, 1], FLOOD_sort_descending[i, 2], n_row, n_col, param_connectivity)
            label = FLOOD_sort_descending[i, 0].astype('uint32')
            initial_wl = FLOOD_sort_descending[i, 4]

            temp_ = (L + temp_dist_from_border[FLOOD_sort_descending[i, 1].astype('uint32'), FLOOD_sort_descending[i, 2].astype('uint32')]) / threshold_distance[label]
            # water level decays linearly towards the DTM with distance from the initial border
            wl = (initial_wl - (initial_wl - dtm[vicini[:, 0], vicini[:, 1]]) * temp_) * np.heaviside(1 - temp_, 0) + dtm[vicini[:, 0], vicini[:, 1]] * (1 - np.heaviside(1 - temp_, 0))
            wl[wl > FLOOD_sort_descending[i, 3]] = FLOOD_sort_descending[i, 3]

            condition = (
                np.heaviside((exclusion[vicini[:, 0], vicini[:, 1]] > 0) + (obswater[vicini[:, 0], vicini[:, 1]] > 0) + (permanent_water[vicini[:, 0], vicini[:, 1]] > 0), 0).astype('bool')  # 1. exclusion / observed / permanent water
                * (dtm[vicini[:, 0], vicini[:, 1]] < (wl - 0.01))                                                        # 2. terrain below the water level
                * np.heaviside(np.isnan(z_water_level_augmented[vicini[:, 0], vicini[:, 1]]), 0).astype('bool')          # 3. not assigned yet
            )

            temp_dist_from_border[vicini[:, 0][condition], vicini[:, 1][condition]] = L * np.array([1.414, 1, 1.414, 1, 1.414, 1, 1.414, 1])[condition] + temp_dist_from_border[FLOOD_sort_descending[i, 1].astype('uint32'), FLOOD_sort_descending[i, 2].astype('uint32')]
            z_water_level_augmented[vicini[:, 0][condition], vicini[:, 1][condition]] = wl[condition]
            FLOOD_sort_descending_list.append(np.array([label * (condition[condition]), vicini[:, 0][condition], vicini[:, 1][condition], wl[condition], initial_wl * (condition[condition])]).T)
            z_labels_augmented[vicini[:, 0][condition], vicini[:, 1][condition]] = label
            i_counter += np.sum(condition)
            i += 1

        # SMOOTHING EXPANDED WL
        print('Smoothing...')
        param_number_smoothings = 20
        z_water_level_augmented_initial = np.copy(z_water_level_augmented)
        z_water_level_augmented[np.isnan(z_water_level_augmented_initial)] = dtm[np.isnan(z_water_level_augmented_initial)]
        target_i, target_j = np.where((~np.isnan(z_water_level_augmented_initial)) & (flood == 0))
        target_i = target_i.astype(np.int32)
        target_j = target_j.astype(np.int32)
        connectivity = 24                                     # 5x5 smoothing kernel
        neighbors_i = np.zeros((target_i.shape[0], connectivity)).astype(np.uint32)
        neighbors_j = np.zeros((target_i.shape[0], connectivity)).astype(np.uint32)
        for i in range(target_i.shape[0]):
            neighbors = ij_neighbors(target_i[i], target_j[i], n_row, n_col, connectivity)
            neighbors_i[i, :] = neighbors[:, 0]
            neighbors_j[i, :] = neighbors[:, 1]
        mask_1 = np.where(~np.isnan(z_water_level))
        for v in range(param_number_smoothings):
            z_water_level_augmented[target_i, target_j] = np.mean(z_water_level_augmented[neighbors_i, neighbors_j], axis=1)
            z_water_level_augmented[mask_1] = z_water_level[mask_1]
        z_water_level_augmented[np.isnan(z_water_level_augmented_initial)] = np.nan
    else:
        z_water_level_augmented = np.copy(z_water_level)

    # WATER DEPTH (cm)
    WD = ((z_water_level_augmented - dtm) * 100).astype('float32')
    WD[WD < 0] = 0
    WD[WD > 0] = WD[WD > 0] + p["wd_star"]
    WD[(WD == 0) & (flood > 0)] = p["wd_star"]
    WD[permanent_water == 1] = 9999                          # dummy depth on permanent water
    WD[np.isnan(WD)] = 0

    # EXTENT (added for this study): every pixel with depth, plus all initially flooded pixels
    WE = np.where(WD > 0, 1, 0).astype('uint8')
    WE[(flood == 1) & (WE != 1)] = 1

    # SAVING
    tag = (f"{p['wl_method']}_Smax_{p['threshold_slope']}_Nmax_{p['max_number_neighbors']}_a_{p['inverse_dist_exp']}"
           f"_Sbs_{p['border_subsampling']}_Dmax_{p['max_propagation_distance']}_A12_{p['distance_range']}"
           f"_gaps_{p['size_gaps_close']}_unrestricted_{p['spread_outside_exclusion']}")
    prof = dict(driver="GTiff", compress='deflate', height=n_row, width=n_col, count=1,
                dtype=rasterio.uint16, crs=crs, transform=transform, nodata=0)
    with rasterio.open(output_dir / f'WD_flood_{tag}.tif', "w", **prof) as dst:
        dst.write(WD, 1)
    with rasterio.open(output_dir / f'WE_flood_{tag}.tif', "w", **prof) as dst:
        dst.write(WE, 1)
    print('Finish!')
    return output_dir / f'WE_flood_{tag}.tif'


# %% [markdown]
# ## Run the 18 configurations of Table 3

# %%
def run_all(cases=C.CASES, seeds=C.SEEDS, dems=C.DEMS):
    for case in cases:
        for seed in seeds:
            for dem in dems:
                params = C.flexth_params(case, seed, dem)
                src = C.input_dir(case, seed, dem, "flexth")
                out = C.run_dir(case, seed, dem, "flexth")
                print(f"\n[02] FLEXTH  {case:16s} {seed:16s} {dem:7s} "
                      f"D_max={params['max_propagation_distance']} A_1/2={params['distance_range']}")
                t0 = time.time()
                for old in out.glob("W[DE]_*.tif"):
                    old.unlink()
                flood_processing(src / "flood.tif", src / "dtm.tif", src / "exclusion.tif",
                                 src / "obswater.tif", src / "permanent_water.tif", out, params)
                print(f"     done in {time.time() - t0:.0f} s -> {out}")


# %%
if __name__ == "__main__":
    run_all()
