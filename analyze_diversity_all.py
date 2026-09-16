#!/usr/bin/env python3
"""
Full failure-diversity analysis across all 6 algorithms and all 3 benchmarks,
using real per-evaluation trace data (X_all_evaluations_*/Reqs_all_evaluations_*).

Metrics (same formulas as online-step-experiments/ADAS1/analyze_failure_diversity.py):
  - Parameter-space APD: avg pairwise Euclidean distance between normalized
    parameter vectors of failing test cases (higher = more diverse failure scenarios).
  - Hamming APD: avg pairwise normalized Hamming distance between binary
    violation patterns (higher = failures hit different requirements).
  - Severity APD: PF only (only algorithm that logs raw per-eval objective
    scores via F_all_evaluations_*; others only log pass/fail).

Data sources:
  - PF:                  results/{BENCH}/PF/out/           (X_all_evaluations_NSGA3_{run}.csv)
  - FF/MERLOT/SAMOTA*/RS: results_diversity/{BENCH}/{ALGO}/out/

Usage:
  python3.11 analyze_diversity_all.py
"""
import os
from itertools import combinations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.preprocessing import MinMaxScaler

BASE = os.path.dirname(os.path.abspath(__file__))
BENCHMARKS = ["ADAS1", "ADAS2", "RR"]
ALGOS = ["PF", "RS", "FF", "MERLOT", "SAMOTA", "SAMOTA_SW"]
PREFIX = {"PF": "NSGA3", "RS": "RANDOM", "FF": "FOC", "MERLOT": "MORLOT", "SAMOTA": "SAMOTA", "SAMOTA_SW": "SAMOTA"}
DATA_DIR = {"PF": "results", "RS": "results_diversity", "FF": "results_diversity", "MERLOT": "results_diversity",
            "SAMOTA": "results_diversity", "SAMOTA_SW": "results_diversity"}
COLOR = {"PF": "#4C72B0", "RS": "#DD8452", "FF": "#55A868", "MERLOT": "#C44E52", "SAMOTA": "#8172B2", "SAMOTA_SW": "#CCB974"}
OUT_DIR = os.path.join(BASE, "results", "diversity_all")
os.makedirs(OUT_DIR, exist_ok=True)


def load_run(x_path, reqs_path):
    X = pd.read_csv(x_path).values.astype(float)
    reqs_df = pd.read_csv(reqs_path)
    R = (~reqs_df.astype(bool)).values.astype(int)  # 1 = violated
    if X.shape[0] != R.shape[0]:
        n = min(X.shape[0], R.shape[0])
        X, R = X[:n], R[:n]
    return X, R


def load_algorithm(bench, algo):
    out_dir = os.path.join(BASE, DATA_DIR[algo], bench, algo, "out")
    prefix = PREFIX[algo]
    runs = []
    for run in range(30):
        x_path = os.path.join(out_dir, f"X_all_evaluations_{prefix}_{run}.csv")
        reqs_path = os.path.join(out_dir, f"Reqs_all_evaluations_{prefix}_{run}.csv")
        if os.path.exists(x_path) and os.path.exists(reqs_path):
            runs.append(load_run(x_path, reqs_path))
    return runs


def get_failures(X, R):
    return X[np.any(R > 0, axis=1)]


def average_pairwise_distance(X_norm):
    n = X_norm.shape[0]
    if n < 2:
        return 0.0
    dists = [np.linalg.norm(X_norm[i] - X_norm[j]) for i, j in combinations(range(n), 2)]
    return float(np.mean(dists))


def hamming_apd(patterns, n_req):
    n = patterns.shape[0]
    if n < 2:
        return 0.0
    dists = [np.sum(patterns[i] != patterns[j]) / n_req for i, j in combinations(range(n), 2)]
    return float(np.mean(dists))


def severity_apd(F_fail):
    n = F_fail.shape[0]
    if n < 2:
        return 0.0
    F_viol = np.where(F_fail < 0, F_fail, 0.0)
    col_min = F_viol.min(axis=0)
    col_min = np.where(col_min < 0, col_min, -1e-9)
    F_norm = F_viol / np.abs(col_min)
    dists = [np.linalg.norm(F_norm[i] - F_norm[j]) for i, j in combinations(range(n), 2)]
    return float(np.mean(dists))


print("=" * 70)
print("Loading experiment data (all runs, all algorithms, all benchmarks)...")
print("=" * 70)

all_data = {}  # (bench, algo) -> list of (X, R)
for bench in BENCHMARKS:
    for algo in ALGOS:
        runs = load_algorithm(bench, algo)
        all_data[(bench, algo)] = runs
        print(f"  {bench:6s} {algo:10s}: {len(runs)} runs loaded")

# ------------------------------------------------------------------
# Compute per-run metrics
# ------------------------------------------------------------------
summary_rows = []
param_apd = {}    # (bench, algo) -> list of per-run APD
hamming_apd_d = {}  # (bench, algo) -> list of per-run hamming APD
viol_rate = {}     # (bench, algo) -> per-req violation rate array

for bench in BENCHMARKS:
    # fit a per-benchmark scaler on pooled X across all algorithms
    pool = [X for algo in ALGOS for X, R in all_data[(bench, algo)]]
    if not pool:
        continue
    scaler = MinMaxScaler()
    scaler.fit(np.vstack(pool))

    n_req = None
    for algo in ALGOS:
        runs = all_data[(bench, algo)]
        if runs and n_req is None:
            n_req = runs[0][1].shape[1]

    for algo in ALGOS:
        runs = all_data[(bench, algo)]
        p_apds, h_apds, n_fails_list = [], [], []
        all_patterns = []

        for X, R in runs:
            X_fail = get_failures(X, R)
            R_fail = R[np.any(R > 0, axis=1)].astype(float)
            n_fail = X_fail.shape[0]
            n_fails_list.append(n_fail)

            if n_fail >= 2:
                X_norm = scaler.transform(X_fail)
                p_apds.append(average_pairwise_distance(X_norm))
                h_apds.append(hamming_apd(R_fail, n_req))
                all_patterns.append(R_fail)
            else:
                p_apds.append(0.0)
                h_apds.append(0.0)

        param_apd[(bench, algo)] = p_apds
        hamming_apd_d[(bench, algo)] = h_apds
        if all_patterns:
            viol_rate[(bench, algo)] = np.vstack(all_patterns).mean(axis=0)

        summary_rows.append({
            "benchmark": bench, "algorithm": algo, "n_runs": len(runs),
            "mean_failures_per_run": round(np.mean(n_fails_list), 2) if n_fails_list else 0,
            "mean_param_apd": round(np.mean(p_apds), 4) if p_apds else None,
            "std_param_apd": round(np.std(p_apds), 4) if p_apds else None,
            "mean_hamming_apd": round(np.mean(h_apds), 4) if h_apds else None,
            "std_hamming_apd": round(np.std(h_apds), 4) if h_apds else None,
        })

df_summary = pd.DataFrame(summary_rows)

# severity APD, PF only
sev_rows = []
for bench in BENCHMARKS:
    out_dir = os.path.join(BASE, "results", bench, "PF", "out")
    s_apds = []
    for run in range(30):
        f_path = os.path.join(out_dir, f"F_all_evaluations_NSGA3_{run}.csv")
        reqs_path = os.path.join(out_dir, f"Reqs_all_evaluations_NSGA3_{run}.csv")
        if not (os.path.exists(f_path) and os.path.exists(reqs_path)):
            continue
        F = pd.read_csv(f_path).values.astype(float)
        reqs_df = pd.read_csv(reqs_path)
        R = (~reqs_df.astype(bool)).values.astype(int)
        n = min(F.shape[0], R.shape[0])
        F, R = F[:n], R[:n]
        mask = np.any(R > 0, axis=1)
        F_fail = F[mask]
        if F_fail.shape[0] >= 2:
            s_apds.append(severity_apd(F_fail))
    sev_rows.append({"benchmark": bench, "algorithm": "PF",
                      "mean_severity_apd": round(np.mean(s_apds), 4) if s_apds else None})
df_sev = pd.DataFrame(sev_rows)
df_summary = df_summary.merge(df_sev, on=["benchmark", "algorithm"], how="left")

out_csv = os.path.join(BASE, "results", "diversity_all_summary.csv")
df_summary.to_csv(out_csv, index=False)
print(f"\nSaved summary: {out_csv}\n")
print(df_summary.to_string(index=False))

# ------------------------------------------------------------------
# Plot: 3 rows (benchmarks) x 2 cols (param-space APD, Hamming APD)
# ------------------------------------------------------------------
fig, axes = plt.subplots(len(BENCHMARKS), 2, figsize=(13, 4.2 * len(BENCHMARKS)))

for i, bench in enumerate(BENCHMARKS):
    ax_p, ax_h = axes[i]
    present = [a for a in ALGOS if param_apd.get((bench, a))]

    data_p = [param_apd[(bench, a)] for a in present]
    bp = ax_p.boxplot(data_p, patch_artist=True, widths=0.5)
    for patch, a in zip(bp["boxes"], present):
        patch.set_facecolor(COLOR[a]); patch.set_alpha(0.6)
    ax_p.set_xticks(range(1, len(present) + 1))
    ax_p.set_xticklabels(present, rotation=15, ha="right", fontsize=9)
    ax_p.set_ylabel("Parameter-space APD")
    ax_p.set_title(f"{bench}: parameter-space diversity of failures")
    ax_p.grid(axis="y", alpha=0.3)

    data_h = [hamming_apd_d[(bench, a)] for a in present]
    bp2 = ax_h.boxplot(data_h, patch_artist=True, widths=0.5)
    for patch, a in zip(bp2["boxes"], present):
        patch.set_facecolor(COLOR[a]); patch.set_alpha(0.6)
    ax_h.set_xticks(range(1, len(present) + 1))
    ax_h.set_xticklabels(present, rotation=15, ha="right", fontsize=9)
    ax_h.set_ylabel("Hamming APD")
    ax_h.set_title(f"{bench}: violation-pattern diversity of failures")
    ax_h.grid(axis="y", alpha=0.3)

fig.suptitle("Diversity of Failures — all 6 algorithms, per-run distribution (30 runs each)", fontsize=13)
fig.tight_layout()
out_png = os.path.join(OUT_DIR, "diversity_all_boxplots.png")
fig.savefig(out_png, dpi=150, bbox_inches="tight")
print(f"\nSaved: {out_png}")

# ------------------------------------------------------------------
# Plot: per-requirement violation rate, one row per benchmark
# ------------------------------------------------------------------
fig2, axes2 = plt.subplots(1, len(BENCHMARKS), figsize=(6 * len(BENCHMARKS), 5))
for i, bench in enumerate(BENCHMARKS):
    ax = axes2[i]
    present = [a for a in ALGOS if (bench, a) in viol_rate]
    n_req = len(next(iter(viol_rate.values())))  # not exact per-bench but fine for shape ref
    for a in present:
        n_req = len(viol_rate[(bench, a)])
        break
    x = np.arange(len(present))
    width = 0.8 / max(n_req, 1)
    for r in range(n_req):
        vals = [viol_rate[(bench, a)][r] if r < len(viol_rate[(bench, a)]) else 0 for a in present]
        ax.bar(x + r * width, vals, width, label=f"R{r}")
    ax.set_xticks(x + width * (n_req - 1) / 2)
    ax.set_xticklabels(present, rotation=15, ha="right", fontsize=9)
    ax.set_ylabel("Fraction of failures violating this req")
    ax.set_ylim(0, 1.05)
    ax.set_title(bench)
    ax.legend(fontsize=7, ncol=2)
    ax.grid(axis="y", alpha=0.3)
fig2.suptitle("Per-requirement violation rate among failures (all 6 algorithms)", fontsize=13)
fig2.tight_layout()
out_png2 = os.path.join(OUT_DIR, "diversity_all_violation_rates.png")
fig2.savefig(out_png2, dpi=150, bbox_inches="tight")
print(f"Saved: {out_png2}")

print("\nDone.")
