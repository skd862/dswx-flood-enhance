"""Regenerate the Jupyter notebooks from the .py scripts (the .py files are the source of truth).

Cells are delimited with `# %%` (code) and `# %% [markdown]` (markdown, lines prefixed with "# ").
Usage:  python tools/make_notebooks.py
"""
import re
from pathlib import Path

import nbformat

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ["01_prepare_inputs.py", "02_flexth.py", "03_rsfloodxdepth.py", "04_evaluate.py", "05_figures.py"]


def convert(py):
    text = py.read_text(encoding="utf-8")
    nb = nbformat.v4.new_notebook()
    nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
    for block in re.split(r"^# %%", text, flags=re.M)[1:]:
        header, _, body = block.partition("\n")
        if "[markdown]" in header:
            md = "\n".join(l[2:] if l.startswith("# ") else l.lstrip("#") for l in body.strip("\n").splitlines())
            nb.cells.append(nbformat.v4.new_markdown_cell(md))
        else:
            code = body.strip("\n")
            # in a notebook, run the main block directly
            code = code.replace('if __name__ == "__main__":\n', "# run everything\nif True:\n")
            if code:
                nb.cells.append(nbformat.v4.new_code_cell(code))
    out = py.with_suffix(".ipynb")
    nbformat.write(nb, out)
    print("wrote", out.name)


if __name__ == "__main__":
    for s in SCRIPTS:
        if (ROOT / s).exists():
            convert(ROOT / s)
