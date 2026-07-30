#!/usr/bin/env python3
"""
Area-Under-Coverage-Curve (AUCC) analysis across all 5 algorithms and all 3
benchmarks, using real per-evaluation trace data (Reqs_all_evaluations_*).
RS excluded (no per-eval traces in this dataset, same caveat as diversity/§4).

For each run: build a step curve of "# reachable requirements violated at
least once so far" over evaluation index, normalize eval index to % of that
run's own budget (handles FF's longer sensitivity-analysis phase) and
normalize the curve to the number of reachable (ever-violatable) requirements
for that benchmark. normalized_aucc = mean of that curve over the whole run
(1.0 = covered everything immediately, 0.0 = never covered anything).

Data sources: same as analyze_diversity_all.py
  - PF:                 results/{BENCH}/PF/out/
  - FF/MERLOT/SAMOTA*:   results_diversity/{BENCH}/{ALGO}/out/

Usage:
  python3.11 analyze_aucc_all.py
"""
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

BASE = os.path.dirname(os.path.abspath(__file__))
BENCHMARKS = ["ADAS1", "ADAS2", "RR"]
ALGOS = ["PF", "FF", "MERLOT", "SAMOTA", "SAMOTA_SW"]
LABEL = {"PF": "PF\n(NSGA3)", "FF": "FF\n(Focused)", "MERLOT": "MERLOT\n(RL)",
         "SAMOTA": "SAMOTA", "SAMOTA_SW": "SAMOTA\n+SW"}
PREFIX = {"PF": "NSGA3", "FF": "FOC", "MERLOT": "MORLOT", "SAMOTA": "SAMOTA", "SAMOTA_SW": "SAMOTA"}
DATA_DIR = {"PF": "results", "FF": "results_diversity", "MERLOT": "results_diversity",
            "SAMOTA": "results_diversity", "SAMOTA_SW": "results_diversity"}
COLOR = {"PF": "#4C72B0", "FF": "#55A868", "MERLOT": "#C44E52", "SAMOTA": "#8172B2", "SAMOTA_SW": "#CCB974"}
OUT_DIR = os.path.join(BASE, "results", "aucc_all")
os.makedirs(OUT_DIR, exist_ok=True)


def load_reqs(bench, algo):
    out_dir = os.path.join(BASE, DATA_DIR[algo], bench, algo, "out")
    prefix = PREFIX[algo]
    runs = []
    for run in range(30):
        reqs_path = os.path.join(out_dir, f"Reqs_all_evaluations_{prefix}_{run}.csv")
        if os.path.exists(reqs_path):
            reqs_df = pd.read_csv(reqs_path)
            R = (~reqs_df.astype(bool)).values.astype(int)  # 1 = violated
            runs.append(R)
    return runs


def detect_reachable(bench):
    """A requirement is reachable if violated at least once by any run of any algorithm."""
    all_R = []
    for algo in ALGOS:
        all_R.extend(load_reqs(bench, algo))
    n_req = all_R[0].shape[1]
    reachable = [req for req in range(n_req) if any(np.any(R[:, req] > 0) for R in all_R)]
    return reachable


def coverage_curve_pct(R, reachable):
    """Curve over % of this run's own budget (0-100, 101 points), normalized to n_reachable."""
    n_evals = R.shape[0]
    fv = []
    for req in reachable:
        idx = np.where(R[:, req] > 0)[0]
        fv.append(idx[0] if len(idx) else np.inf)
    fv = np.array(fv)
    grid = np.linspace(0, 100, 101)
    curve = np.zeros(101)
    for i, pct in enumerate(grid):
        t = pct / 100.0 * (n_evals - 1)
        curve[i] = np.sum(fv <= t)
    return curve / len(reachable)


def main():
    summary = {}
    fig_curve, axes_curve = plt.subplots(1, 3, figsize=(16, 5))
    fig_box, axes_box = plt.subplots(1, 3, figsize=(15, 5.2))

    for bi, bench in enumerate(BENCHMARKS):
        reachable = detect_reachable(bench)
        n_reachable = len(reachable)
        aucc_by_algo = {}
        curves_by_algo = {}

        for algo in ALGOS:
            runs = load_reqs(bench, algo)
            if not runs:
                continue
            curves = np.array([coverage_curve_pct(R, reachable) for R in runs])
            aucc_by_algo[algo] = curves.mean(axis=1)  # per-run normalized AUCC
            curves_by_algo[algo] = curves
            summary[(bench, algo)] = (curves.mean(axis=1).mean(), curves.mean(axis=1).std(), len(runs))

        # Coverage-over-%-budget curve
        ax = axes_curve[bi]
        for algo in ALGOS:
            if algo not in curves_by_algo:
                continue
            mean_c = curves_by_algo[algo].mean(axis=0)
            std_c = curves_by_algo[algo].std(axis=0)
            grid = np.linspace(0, 100, 101)
            ax.plot(grid, mean_c, label=algo, color=COLOR[algo], linewidth=2)
            ax.fill_between(grid, np.clip(mean_c - std_c, 0, 1), np.clip(mean_c + std_c, 0, 1),
                             alpha=0.12, color=COLOR[algo])
        ax.axhline(1.0, color="black", linestyle="--", linewidth=1, alpha=0.5)
        ax.set_title(f"{bench} ({n_reachable} reachable reqs)")
        ax.set_xlabel("% of run's own budget used")
        ax.set_ylabel("Fraction of reachable reqs violated so far")
        ax.set_ylim(-0.05, 1.15)
        ax.grid(True, alpha=0.3)
        if bi == 0:
            ax.legend(fontsize=8, loc="lower right")

        # AUCC boxplot
        ax2 = axes_box[bi]
        data = [aucc_by_algo[a] for a in ALGOS if a in aucc_by_algo]
        labels = [LABEL[a] for a in ALGOS if a in aucc_by_algo]
        colors = [COLOR[a] for a in ALGOS if a in aucc_by_algo]
        bp = ax2.boxplot(data, tick_labels=labels, patch_artist=True, widths=0.55,
                          showmeans=True, meanprops=dict(marker="D", markerfacecolor="black",
                                                          markeredgecolor="black", markersize=5))
        for patch, c in zip(bp["boxes"], colors):
            patch.set_facecolor(c)
            patch.set_alpha(0.75)
        ax2.set_title(bench)
        ax2.set_ylabel("Normalized AUCC [0-1]")
        ax2.set_ylim(0, 1.05)
        ax2.grid(True, alpha=0.3, axis="y")

    fig_curve.suptitle("Coverage-of-Reachable-Requirements Over Run Progress (mean ± std, 30 runs)", fontsize=13)
    fig_curve.tight_layout()
    fig_curve.savefig(os.path.join(OUT_DIR, "coverage_curves.png"), dpi=150, bbox_inches="tight")

    fig_box.suptitle("Normalized Area Under Coverage Curve — higher = covers reachable reqs earlier/more consistently", fontsize=12)
    fig_box.tight_layout()
    fig_box.savefig(os.path.join(OUT_DIR, "aucc_boxplot.png"), dpi=150, bbox_inches="tight")

    print(f"{'Benchmark':<10}{'Algo':<12}{'AUCC mean':>10}{'AUCC std':>10}{'n runs':>8}")
    print("-" * 52)
    for (bench, algo), (m, s, n) in summary.items():
        print(f"{bench:<10}{algo:<12}{m:>10.3f}{s:>10.3f}{n:>8}")

    print(f"\nSaved: {OUT_DIR}/coverage_curves.png")
    print(f"Saved: {OUT_DIR}/aucc_boxplot.png")


if __name__ == "__main__":
    main()
