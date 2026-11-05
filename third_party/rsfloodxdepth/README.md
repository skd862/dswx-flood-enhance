# RS-FloodXdepth code (not included)

RS-FloodXdepth is described in Tian, D., Liu, H., Wang, L., Cohen, S. & Mandal, T. (2026), *Water Resources
Research* 62, e2025WR042384, https://doi.org/10.1029/2025WR042384. Its code belongs to its developers (Surface
Dynamics Modeling Lab, University of Alabama) and is not distributed with this repository.

`03_rsfloodxdepth.py` works without it, using the flood maps produced for the paper
(`data/precomputed/rsfloodxdepth/`). To run the method yourself, obtain the code from its developers, save it in
this folder as `rsfloodxdepth.py` providing `generate_lwse_layers(...)` and `idw2Flood1(...)` (see
`run_rsfloodxdepth` in `03_rsfloodxdepth.py` for how they are called), and `pip install ImageObject==1.19`.
Files in this folder other than this README are ignored by git.
