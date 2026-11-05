# %% [markdown]
# # 04 - Evaluation against the hand-labelled NOAA aerial benchmarks (Tables 2 and 3)
#
# Metrics (Table 1 of the paper): Balanced Accuracy, CSI (IoU), F1, Precision, Recall.
#
# > **IMPORTANT - permanent water is excluded.** Every pixel flagged as permanent water is removed from
# > BOTH the candidate and the benchmark before computing any metric, so the scores describe transient
# > (event) flooding only and no method gets credit for "filling in" rivers and lakes
# > (Section 3.1 of the paper; Cohen et al., 2025).
# > Permanent water = JRC Global Surface Water mask (Louisville, Google Earth Engine export) and DSWx-HLS
# > land cover class 200 "Water, wetland, mangrove forest" (Sugar Land); shown as "PW"
# > (dark blue) in the agreement maps. Scores are therefore lower than scores that include permanent water.
#
# How a candidate is compared (identical to the original gval-based notebooks):
# 1. the benchmark is resampled (nearest neighbour) onto the candidate grid; 255 = no data;
# 2. candidate water: BWTR == 1 | collapsed CONF in the selected water classes | FLEXTH WE == 1 |
#    RS-FloodXdepth FloodClass in {1, 2};
# 3. permanent-water pixels are dropped; TP/FP/FN/TN are counted over the remaining valid pixels.
#
# Outputs (outputs/results/): table2_dswx.csv, table3_enhancement.csv, comparison_with_paper.csv and
# agreement maps (0 TN, 1 FN, 2 FP, 3 TP, 10 permanent water, 255 not evaluated) used by 05_figures.py.

# %%
import glob

import numpy as np
import pandas as pd
import rasterio

import config as C
from common import agreement, load_benchmark, load_permanent_for_eval, metrics_from_map, open_da

AGREE = C.RESULTS / "agreement"
METRICS = ["BA", "CSI", "F1", "Precision", "Recall"]


def save_map(amap, like, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    prof = dict(driver="GTiff", height=amap.shape[0], width=amap.shape[1], count=1, dtype="uint8",
                crs=like.rio.crs, transform=like.rio.transform(), nodata=255, compress="lzw")
    with rasterio.open(path, "w", **prof) as d:
        d.write(amap, 1)


def evaluate(site, candidate_da, water, valid, name=None):
    bm = load_benchmark(site, candidate_da)
    pw = load_permanent_for_eval(site, candidate_da)
    amap, m = agreement(water, valid, bm, pw)
    if name:
        save_map(amap, candidate_da, AGREE / f"{name}.tif")
    return amap, m


# %% [markdown]
# ## Table 2 - DSWx-HLS / DSWE layers

# %%
def table2():
    rows = []
    for case, (site, _) in C.CASES.items():
        d = C.INPUTS / case
        bwtr = open_da(d / "scene_bwtr.tif")
        _, m = evaluate(site, bwtr, bwtr.values == C.BWTR_WATER, bwtr.values != C.NODATA, f"{case}/dswx_bwtr")
        rows.append(dict(case=case, layer="bwtr", **{"class": "all"}, **m))

        conf = open_da(d / "scene_conf.tif")
        for layer, classes in [("conf", C.CONF_WATER_ALL), ("conf_no_partial", C.CONF_WATER_NO_PARTIAL)]:
            amap, m = evaluate(site, conf, np.isin(conf.values, classes), conf.values != C.NODATA, f"{case}/dswx_{layer}")
            rows.append(dict(case=case, layer=layer, **{"class": "all"}, **m))
            if layer == "conf":
                # class-specific scores inside the cloud mask (Table 2, "Open/Partial water | Cloud mask")
                for cls, code in [("open_water_cloud", 11), ("partial_water_cloud", 12)]:
                    rows.append(dict(case=case, layer=layer, **{"class": cls},
                                     **metrics_from_map(amap, conf.values == code)))
    return pd.DataFrame(rows)


# %% [markdown]
# ## Table 3 - FLEXTH and RS-FloodXdepth

# %%
def table3():
    rows = []
    for case, (site, _) in C.CASES.items():
        for method in ("flexth", "rsfloodxdepth"):
            for seed in C.SEEDS:
                for dem in C.DEMS:
                    rd = C.run_dir(case, seed, dem, method)
                    if method == "flexth":
                        f = glob.glob(str(rd / "WE_*.tif"))
                        if not f:
                            print(f"missing FLEXTH output {rd}"); continue
                        cand = open_da(f[0]); water = cand.values == 1
                    else:
                        if not (rd / "FloodClass.tif").exists():
                            print(f"missing RS-FloodXdepth output {rd}"); continue
                        cand = open_da(rd / "FloodClass.tif"); water = np.isin(cand.values, [1, 2])
                    _, m = evaluate(site, cand, water, np.ones_like(water), f"{case}/{method}_{seed}_{dem}")
                    rows.append(dict(case=case, method=method, seed=seed, dem=dem, **m))
    return pd.DataFrame(rows)


# %% [markdown]
# ## Compare with the published values

# %%
def compare(ours, paper, keys):
    m = paper.merge(ours, on=keys, how="left", suffixes=("_paper", ""))
    for k in METRICS:
        m[f"d{k}"] = (m[k].round(2) - m[f"{k}_paper"]).round(2)
    d = m[[f"d{k}" for k in METRICS]].abs()
    m["max_abs_diff"] = d.max(axis=1)
    return m


# %%
if __name__ == "__main__":
    C.RESULTS.mkdir(parents=True, exist_ok=True)
    t2 = table2()
    t3 = table3()
    t2.round(4).to_csv(C.RESULTS / "table2_dswx.csv", index=False)
    t3.round(4).to_csv(C.RESULTS / "table3_enhancement.csv", index=False)

    c2 = compare(t2, pd.read_csv(C.REFERENCE / "paper_table2.csv"), ["case", "layer", "class"])
    c3 = compare(t3, pd.read_csv(C.REFERENCE / "paper_table3.csv"), ["case", "method", "seed", "dem"])
    # one row per published row: identifiers first, then |difference|, published and reproduced values
    comp = pd.concat([c2.assign(table="Table 2"), c3.assign(table="Table 3")])
    ids = ["table", "case", "method", "layer", "seed", "class", "dem", "max_abs_diff"]
    pairs = [c for k in METRICS for c in (f"{k}_paper", k, f"d{k}")]
    comp[ids + pairs + ["TP", "FP", "FN", "TN"]].round(4).to_csv(C.RESULTS / "comparison_with_paper.csv", index=False)

    pd.set_option("display.width", 200)
    show = lambda c, keys: print(c[keys + METRICS + ["max_abs_diff"]].round(2).to_string(index=False))
    print("\nTable 2 (reproduced; max_abs_diff = largest |reproduced - published| over the five metrics)")
    show(c2, ["case", "layer", "class"])
    print("\nTable 3 (reproduced)")
    show(c3, ["case", "method", "seed", "dem"])
    d = pd.concat([c2["max_abs_diff"].fillna(0), c3["max_abs_diff"]])
    print(f"\nPublished rows reproduced within 0.01: {(d <= 0.01).sum()}/{len(d)}; within 0.02: {(d <= 0.02).sum()}/{len(d)}; "
          f"largest difference: {d.max():.2f}")
