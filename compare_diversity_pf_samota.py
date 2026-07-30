#!/usr/bin/env python3
"""
Diversity of failures: PF vs SAMOTA, across ADAS1 / ADAS2 / RR.

IMPORTANT CAVEAT — this is a coarser proxy than full diversity analysis:
Only PF currently has per-evaluation trace files (X_all_evaluations_*/
Reqs_all_evaluations_*), so it's possible to measure diversity across every
failing test case PF evaluated during a run. SAMOTA's current results/ only
has one aggregate row per run (reqs_SAMOTA_30.csv / score_SAMOTA_30.csv),
i.e. the best/final outcome of that run — not every evaluation.

To compare like-for-like with the data available *today*, this script
treats each run's aggregate row as a single sample and measures diversity
ACROSS THE 30 INDEPENDENT RUNS (30 points per algorithm), rather than
diversity WITHIN a run's full evaluation history. Once results_diversity/
(instrumented rerun) is copied over, re-run analyze_failure_diversity.py's
generalized version for the full within-run picture across all 5 algorithms.

Metrics (formulas match online-step-experiments/ADAS1/analyze_failure_diversity.py):
  - Severity APD: avg pairwise Euclidean distance between per-run best score
    vectors (V0..Vn), each column normalized to [-1, 0] by its global min.
  - Hamming APD: avg pairwise normalized Hamming distance between per-run
    binary violation patterns (R_i > 0).

Usage:
  python3.11 compare_diversity_pf_samota.py --results_dir results --save
"""
import argparse
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

BENCHMARKS = ["ADAS1", "ADAS2", "RR"]
ALGO_PREFIX = {"PF": "NSGA3", "SAMOTA": "SAMOTA"}
ALGO_COLOR = {"PF": "#4C72B0", "SAMOTA": "#8172B2"}


def req_cols(df):
    return [c for c in df.columns if c.startswith("R") and c[1:].isdigit()]


def score_cols(df):
    return [c for c in df.columns if c.startswith("V")]


def severity_apd(F):
    """APD over score vectors, normalized per-column to [-1, 0] by global min (violated <0)."""
    n = F.shape[0]
    if n < 2:
        return 0.0
    F_viol = np.where(F < 0, F, 0.0)
    col_min = F_viol.min(axis=0)
    col_min = np.where(col_min < 0, col_min, -1e-9)
    F_norm = F_viol / np.abs(col_min)
    dists = [np.linalg.norm(F_norm[i] - F_norm[j]) for i, j in combinations(range(n), 2)]
    return float(np.mean(dists))


def hamming_apd(patterns):
    """Average pairwise normalized Hamming distance between binary violation patterns."""
    n = patterns.shape[0]
    if n < 2:
        return 0.0
    n_reqs = patterns.shape[1]
    dists = [np.sum(patterns[i] != patterns[j]) / n_reqs for i, j in combinations(range(n), 2)]
    return float(np.mean(dists))


def load(results_dir, benchmark, algo):
    prefix = ALGO_PREFIX[algo]
    out_dir = results_dir / benchmark / algo / "out"
    reqs_files = list(out_dir.glob(f"reqs_{prefix}_*.csv"))
    score_files = list(out_dir.glob(f"score_{prefix}_*.csv"))
    if not reqs_files or not score_files:
        return None, None
    reqs_df = pd.read_csv(reqs_files[0])
    score_df = pd.read_csv(score_files[0])
    return reqs_df, score_df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results_dir", default="results")
    ap.add_argument("--save", action="store_true")
    args = ap.parse_args()
    results_dir = Path(args.results_dir).resolve()

    rows = []
    for benchmark in BENCHMARKS:
        for algo in ["PF", "SAMOTA"]:
            reqs_df, score_df = load(results_dir, benchmark, algo)
            if reqs_df is None:
                print(f"  [MISSING] {benchmark}/{algo}")
                continue
            rc = req_cols(reqs_df)
            sc = score_cols(score_df)
            patterns = (reqs_df[rc] > 0).values.astype(int)
            F = score_df[sc].values

            h_apd = hamming_apd(patterns)
            s_apd = severity_apd(F)
            n = len(reqs_df)
            rows.append({
                "benchmark": benchmark, "algorithm": algo, "n_runs": n,
                "hamming_apd": round(h_apd, 4), "severity_apd": round(s_apd, 4),
            })
            print(f"  [OK] {benchmark}/{algo}: n={n}  hamming_apd={h_apd:.4f}  severity_apd={s_apd:.4f}")

    df = pd.DataFrame(rows)
    out_csv = results_dir / "diversity_pf_vs_samota.csv"
    df.to_csv(out_csv, index=False)
    print(f"\nSaved: {out_csv}")

    # Plot: 2 panels (hamming, severity), grouped bars per benchmark
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 5))
    x = np.arange(len(BENCHMARKS))
    width = 0.35

    for i, algo in enumerate(["PF", "SAMOTA"]):
        sub = df[df["algorithm"] == algo].set_index("benchmark").reindex(BENCHMARKS)
        offset = (i - 0.5) * width
        ax1.bar(x + offset, sub["hamming_apd"], width, label=algo, color=ALGO_COLOR[algo], alpha=0.85)
        ax2.bar(x + offset, sub["severity_apd"], width, label=algo, color=ALGO_COLOR[algo], alpha=0.85)

    ax1.set_xticks(x); ax1.set_xticklabels(BENCHMARKS)
    ax1.set_ylabel("Hamming APD (violation-pattern diversity)")
    ax1.set_title("Violation-pattern diversity\n(across 30 runs' final outcome)")
    ax1.legend(); ax1.grid(axis="y", alpha=0.3)

    ax2.set_xticks(x); ax2.set_xticklabels(BENCHMARKS)
    ax2.set_ylabel("Severity APD (objective-space diversity)")
    ax2.set_title("Failure-severity diversity\n(across 30 runs' final outcome)")
    ax2.legend(); ax2.grid(axis="y", alpha=0.3)

    fig.suptitle("Diversity of failures: PF vs SAMOTA (per-run aggregate proxy — see script docstring)", fontsize=11)
    fig.tight_layout()

    if args.save:
        out_png = results_dir / "diversity_pf_vs_samota.png"
        fig.savefig(out_png, dpi=150, bbox_inches="tight")
        print(f"Saved: {out_png}")
    else:
        plt.show()


if __name__ == "__main__":
    main()
