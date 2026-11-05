# %% [markdown]
# # 05 - Figures
#
# Re-creates, with matplotlib, the map panels and the gauge plot of the paper from the outputs of
# scripts 01-04. (The published figures were styled and assembled in ArcGIS Pro / PowerPoint; the data
# shown here are the same, the cartography is simpler.)
#
# | File | Paper figure |
# |---|---|
# | fig01c_gauge_louisville.png | Fig. 1c - USGS 03294500 gauge height, April 2025 |
# | fig03_dswx_louisville.png | Fig. 3 - HLS false colour, DSWx-HLS BWTR and CONF (Apr 8 / Apr 9) |
# | fig04_dswe_harvey.png | Fig. 4 - Landsat-8 false colour, DSWE INWAM (BWTR) and INTSM (CONF) |
# | fig05_dems.png | Fig. 5 - FABDEM and USGS 3DEP |
# | fig07_agreement_dswx_louisville.png | Fig. 7 - agreement maps, DSWx-HLS vs benchmark (Louisville) |
# | fig09_agreement_dswe_harvey.png | Fig. 9 - agreement maps, DSWE vs benchmark (Sugar Land) |
# | fig10_enhancement_louisville_0409.png | Fig. 10 - FLEXTH / RS-FloodXdepth, Louisville Apr 9 |
# | fig11_enhancement_harvey.png | Fig. 11 - FLEXTH / RS-FloodXdepth, Sugar Land |
#
# Figures 2 and 8 need the NOAA aerial mosaics (tens of GB, https://storms.ngs.noaa.gov/) and Fig. 6 is a
# workflow diagram, so they are not reproduced. The hand-labelled benchmark itself (Fig. 1b / 2b) is plotted
# in fig01_02_benchmarks.png.

# %%
import numpy as np
import pandas as pd
import sys
import matplotlib
if "ipykernel" not in sys.modules:   # headless when run as a script
    matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
from matplotlib.patches import Patch

import config as C
from common import open_da

C.FIGURES.mkdir(parents=True, exist_ok=True)
AGREE = C.RESULTS / "agreement"

# colours of the paper
OUTCOME = {0: ("TN", "#A6A6A6"), 1: ("FN", "#FF0000"), 2: ("FP", "#FFA500"), 3: ("TP", "#5CFF1A"), 10: ("PW", "#0B2A6F")}
CONF_STYLE = {0: ("Non-water | No mask", "#FFFFFF"), 1: ("Water | No mask", "#0000FF"),
              10: ("Non-water | Cloud mask", "#B0B0B0"), 11: ("Open water | Cloud mask", "#5CFF1A"),
              12: ("Partial water | Cloud mask", "#9B30D9"), 20: ("Non-water | Snow/Ice mask", "#00FFFF"),
              21: ("Water | Snow/Ice mask", "#FFFF00")}
BWTR_STYLE = {0: ("Non-water", "#FFFFFF"), 1: ("Water", "#0000FF"), 252: ("Snow/Ice", "#00FFFF"),
              253: ("Cloud/cloud shadow (incl. adjacent)", "#B0B0B0")}
BACKGROUND = "#3A3A3A"


def site_of(da):
    return "harvey" if da.rio.crs.to_epsg() == 3857 else "louisville"


_BBOX = {}


def site_bbox(site):
    """Map extent of the valid benchmark footprint (+1 km), used to zoom every panel of a site."""
    if site not in _BBOX:
        b = open_da(C.ANC[site]["benchmark"])
        ys, xs = np.where(b.values != C.NODATA)
        x, y = b.x.values, b.y.values
        _BBOX[site] = (x[xs.min()] - 1000, x[xs.max()] + 1000, y[ys.min()] - 1000, y[ys.max()] + 1000)
    return _BBOX[site]


def categorical(ax, da, style, title=None):
    """Plot a categorical DataArray in map coordinates, zoomed to the site footprint."""
    arr = da.values
    codes = sorted(style)
    lut = np.full(256, np.nan)
    for i, c in enumerate(codes):
        lut[c] = i
    idx = lut[np.clip(np.nan_to_num(arr, nan=255), 0, 255).astype(int)]
    cmap = ListedColormap([style[c][1] for c in codes])
    l, b, r, t = da.rio.bounds()
    ax.set_facecolor(BACKGROUND)
    ax.imshow(np.ma.masked_invalid(idx), cmap=cmap, norm=BoundaryNorm(np.arange(len(codes) + 1) - 0.5, len(codes)),
              interpolation="nearest", extent=(l, r, b, t))
    x0, x1, y0, y1 = site_bbox(site_of(da))
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1)
    ax.set_xticks([]); ax.set_yticks([])
    if title:
        ax.set_title(title, fontsize=9)


def legend(fig, style, loc, ncol=1, title=None):
    fig.legend(handles=[Patch(facecolor=c, edgecolor="k", label=l) for l, c in style.values()],
               loc=loc, ncol=ncol, fontsize=8, title=title, frameon=True)


def false_colour(ax, path, site, title):
    """SWIR1-NIR-Red composite reprojected to the site grid and zoomed like the other panels."""
    import rioxarray as rxr
    like = open_da(C.ANC[site]["benchmark"])
    da = rxr.open_rasterio(path, masked=True).rio.reproject(like.rio.crs)
    a = da.values.astype(float)
    lo, hi = np.nanpercentile(a, 2), np.nanpercentile(a, 98)
    rgb = np.clip((a - lo) / (hi - lo), 0, 1).transpose(1, 2, 0)
    rgba = np.dstack([np.nan_to_num(rgb), (~np.isnan(a).any(axis=0)).astype(float)])
    l, b, r, t = da.rio.bounds()
    ax.set_facecolor(BACKGROUND)
    ax.imshow(rgba, extent=(l, r, b, t))
    x0, x1, y0, y1 = site_bbox(site)
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_xticks([]); ax.set_yticks([])
    ax.set_title(title, fontsize=9)


def agreement_panel(ax, name, title):
    categorical(ax, open_da(AGREE / f"{name}.tif"), OUTCOME, title)


def metrics_label(df, **keys):
    r = df.loc[np.logical_and.reduce([df[k] == v for k, v in keys.items()])].iloc[0]
    return f"BA {r.BA:.2f}  CSI {r.CSI:.2f}  F1 {r.F1:.2f}"


# %% [markdown]
# ## Fig. 1c - gauge height (and the benchmark maps of Fig. 1b / 2b)

# %%
def fig01():
    g = pd.read_csv(C.ANC["louisville"]["benchmark"].parent / "usgs_03294500_gauge_height_2025-04.csv",
                    parse_dates=["datetime"])
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.plot(g.datetime, g.gauge_height_ft * 0.3048, color="k", lw=1)
    ax.axhline(55 * 0.3048, color="tab:orange", ls="--", lw=1, label="NWS flood stage (55 ft)")
    for d, lab, c in [("2025-04-06", "Sentinel-1", "purple"), ("2025-04-08", "DSWx-HLS", "red"),
                      ("2025-04-09", "DSWx-HLS", "red"), ("2025-04-12", "NOAA aerial", "black")]:
        ax.axvline(pd.Timestamp(d) + pd.Timedelta(hours=16), color=c, lw=1, alpha=.7)
        ax.text(pd.Timestamp(d) + pd.Timedelta(hours=18), ax.get_ylim()[1] * 0.98, lab, rotation=90, va="top", fontsize=7, color=c)
    ax.set_ylabel("Gauge height (m)")
    ax.set_title("USGS 03294500 Ohio River at Louisville, KY - April 2025", fontsize=9)
    ax.legend(fontsize=8, loc="lower right")
    fig.tight_layout(); fig.savefig(C.FIGURES / "fig01c_gauge_louisville.png", dpi=200); plt.close(fig)

    fig, axs = plt.subplots(1, 2, figsize=(11, 3.6))
    style = {0: ("Non-flooded", "#FFFFFF"), 1: ("Flooded", "#1F4FFF")}
    for ax, site, title in [(axs[0], "louisville", "Louisville - hand label (Apr 12 2025)"),
                            (axs[1], "harvey", "Sugar Land - hand label (Sep 3 2017)")]:
        categorical(ax, open_da(C.ANC[site]["benchmark"]), {**style, 255: ("No data", BACKGROUND)}, title)
    legend(fig, style, "lower center", ncol=2)
    fig.savefig(C.FIGURES / "fig01_02_benchmarks.png", dpi=200, bbox_inches="tight"); plt.close(fig)


# %% [markdown]
# ## Figs. 3-5 - inputs

# %%
def fig03():
    fig, axs = plt.subplots(3, 2, figsize=(12, 9))
    for j, (date, sensor, hls) in enumerate([("0408", "Sentinel-2", "HLS_S30_20250408_SWIR1-NIR-Red.tif"),
                                            ("0409", "Landsat 8", "HLS_L30_20250409_SWIR1-NIR-Red.tif")]):
        d = C.INPUTS / f"louisville_{date}"
        false_colour(axs[0, j], C.SOURCE / "louisville" / "hls" / hls, "louisville",
                     f"April {date[2:]} 2025 - HLS {sensor} (SWIR1-NIR-Red)")
        categorical(axs[1, j], open_da(d / "scene_bwtr.tif"), {**BWTR_STYLE, 255: ("", BACKGROUND)}, "DSWx-HLS BWTR")
        categorical(axs[2, j], open_da(d / "scene_conf.tif"), {**CONF_STYLE, 255: ("", BACKGROUND)}, "DSWx-HLS CONF")
    legend(fig, BWTR_STYLE, "lower left", ncol=4, title="BWTR")
    legend(fig, CONF_STYLE, "lower right", ncol=2, title="CONF")
    fig.subplots_adjust(bottom=0.16)
    fig.savefig(C.FIGURES / "fig03_dswx_louisville.png", dpi=200, bbox_inches="tight"); plt.close(fig)


def fig04():
    d = C.INPUTS / "harvey"
    fig, axs = plt.subplots(1, 3, figsize=(15, 4))
    false_colour(axs[0], C.SOURCE / "harvey" / "hls" / "HLS_L30_20170904_SWIR1-NIR-Red.tif", "harvey",
                 "Landsat 8, Sep 4 2017 (SWIR1-NIR-Red)")
    categorical(axs[1], open_da(d / "scene_bwtr.tif"), {**BWTR_STYLE, 255: ("", BACKGROUND)}, "DSWE INWAM (= BWTR)")
    categorical(axs[2], open_da(d / "scene_conf.tif"), {**CONF_STYLE, 255: ("", BACKGROUND)}, "DSWE INTSM (= CONF)")
    legend(fig, {k: v for k, v in CONF_STYLE.items() if k < 20}, "lower center", ncol=5)
    fig.subplots_adjust(bottom=0.18)
    fig.savefig(C.FIGURES / "fig04_dswe_harvey.png", dpi=200, bbox_inches="tight"); plt.close(fig)


def fig05():
    fig, axs = plt.subplots(2, 2, figsize=(12, 7))
    for i, (case, title) in enumerate([("louisville_0408", "Louisville, KY"), ("harvey", "Sugar Land, TX")]):
        das = {dem: open_da(C.input_dir(case, "conf", dem, "flexth") / "dtm.tif") for dem in C.DEMS}
        dtms = {dem: da.values.astype(float) for dem, da in das.items()}
        for v in dtms.values():
            v[(v <= 0) | (v > 1e30)] = np.nan
        lo = np.nanpercentile(np.concatenate([v.ravel() for v in dtms.values()]), 1)
        hi = np.nanpercentile(np.concatenate([v.ravel() for v in dtms.values()]), 99)
        for j, dem in enumerate(C.DEMS):
            ax = axs[i, j]; ax.set_facecolor(BACKGROUND)
            l, b, r, t = das[dem].rio.bounds()
            im = ax.imshow(dtms[dem], cmap="terrain", vmin=lo, vmax=hi, extent=(l, r, b, t))
            x0, x1, y0, y1 = site_bbox("harvey" if case == "harvey" else "louisville")
            ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_xticks([]); ax.set_yticks([]); ax.set_title(f"{title} - {'FABDEM' if dem == 'fabdem' else 'USGS 3DEP'}", fontsize=9)
            fig.colorbar(im, ax=ax, shrink=0.8, label="Elevation (m)")
    fig.tight_layout(); fig.savefig(C.FIGURES / "fig05_dems.png", dpi=200); plt.close(fig)


# %% [markdown]
# ## Figs. 7 and 9 - DSWx / DSWE agreement maps

# %%
def fig07_09():
    t2 = pd.read_csv(C.RESULTS / "table2_dswx.csv")
    t2 = t2[t2["class"] == "all"]
    fig, axs = plt.subplots(3, 2, figsize=(12, 7.5))
    for j, date in enumerate(["0408", "0409"]):
        case = f"louisville_{date}"
        panels = [("bwtr", "BWTR"), ("conf", "CONF")] + ([("conf_no_partial", 'CONF ("Partial water | Cloud" as non-water)')] if date == "0409" else [])
        for i, (layer, name) in enumerate(panels):
            agreement_panel(axs[i, j], f"{case}/dswx_{layer}", f"April {date[2:]} - {name}\n{metrics_label(t2, case=case, layer=layer)}")
        if date == "0408":
            axs[2, 0].axis("off")
    legend(fig, OUTCOME, "lower left", ncol=5)
    fig.tight_layout(rect=(0, 0.04, 1, 1)); fig.savefig(C.FIGURES / "fig07_agreement_dswx_louisville.png", dpi=200); plt.close(fig)

    fig, axs = plt.subplots(1, 3, figsize=(15, 4))
    for ax, (layer, name) in zip(axs, [("bwtr", "DSWE BWTR (INWAM)"), ("conf", "DSWE CONF (INTSM)"),
                                       ("conf_no_partial", 'CONF ("Partial water | Cloud" as non-water)')]):
        agreement_panel(ax, f"harvey/dswx_{layer}", f"{name}\n{metrics_label(t2, case='harvey', layer=layer)}")
    legend(fig, OUTCOME, "lower center", ncol=5)
    fig.tight_layout(rect=(0, 0.08, 1, 1)); fig.savefig(C.FIGURES / "fig09_agreement_dswe_harvey.png", dpi=200); plt.close(fig)


# %% [markdown]
# ## Figs. 10 and 11 - FLEXTH and RS-FloodXdepth agreement maps

# %%
def fig10_11():
    t3 = pd.read_csv(C.RESULTS / "table3_enhancement.csv")
    seed_name = {"bwtr": "BWTR", "conf": "CONF", "conf_no_partial": "CONF (no partial water)"}
    for case, fname, figsize in [("louisville_0409", "fig10_enhancement_louisville_0409.png", (11, 13)),
                                 ("harvey", "fig11_enhancement_harvey.png", (10, 20))]:
        fig, axs = plt.subplots(6, 2, figsize=figsize)
        for m, method in enumerate(["flexth", "rsfloodxdepth"]):
            for s, seed in enumerate(C.SEEDS):
                for j, dem in enumerate(C.DEMS):
                    ax = axs[3 * m + s, j]
                    label = f"{'FLEXTH' if method == 'flexth' else 'RS-FloodXdepth'} - {seed_name[seed]}_{dem.upper()}"
                    agreement_panel(ax, f"{case}/{method}_{seed}_{dem}",
                                    f"{label}\n{metrics_label(t3, case=case, method=method, seed=seed, dem=dem)}")
        legend(fig, OUTCOME, "lower center", ncol=5)
        fig.tight_layout(rect=(0, 0.03, 1, 1)); fig.savefig(C.FIGURES / fname, dpi=200); plt.close(fig)


# %%
if __name__ == "__main__":
    for f in (fig01, fig03, fig04, fig05, fig07_09, fig10_11):
        f()
        print("[05]", f.__name__, "done")
    print("figures in", C.FIGURES)
