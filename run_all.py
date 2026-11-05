"""Run the whole replication (steps 01-05) in order.   python run_all.py [--download]"""
import runpy
import sys
import time

STEPS = ["01_prepare_inputs.py", "02_flexth.py", "03_rsfloodxdepth.py", "04_evaluate.py", "05_figures.py"]

if __name__ == "__main__":
    t0 = time.time()
    for step in STEPS:
        print(f"\n{'=' * 80}\n{step}\n{'=' * 80}", flush=True)
        sys.argv = [step] + (["--download"] if "--download" in sys.argv and step.startswith("01") else [])
        runpy.run_path(step, run_name="__main__")
    print(f"\nAll steps finished in {(time.time() - t0) / 60:.1f} min. Results: outputs/results, figures: outputs/figures")
