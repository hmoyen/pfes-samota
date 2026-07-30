# SAMOTA Falsification Benchmark Suite

Replication package comparing SAMOTA (Surrogate-Assisted Many-Objective Testing
Approach) against five falsification baselines on three cyber-physical system (CPS)
benchmarks, using a shared MDP-based simulator.

## Overview

Given a CPS modeled as a Markov Decision Process with a continuous/discrete parameter
space (the "semantic space"), the task is **falsification**: search for parameter
assignments that make the system violate its safety requirements, using as few
simulator evaluations as possible. Each algorithm is run 30 times per benchmark with
a fixed evaluation budget, and compared on violations found, requirement coverage,
search diversity, and wall-clock cost.

**Benchmarks** (`online-step-experiments/`):

| Benchmark | Description | Search space | Requirements |
|---|---|---|---|
| ADAS1 | Autonomous driving, base scenario | 6D | 3 |
| ADAS2 | Autonomous driving, extended constraints | 6D | 6 |
| RR | Rescue robot | 9D | 6 |

## Algorithms

| Name | Script | Approach |
|---|---|---|
| PF | `PFES_falsification.py --optalg NSGA3` | Parametric falsification via NSGA-III |
| RS | `PFES_falsification.py --optalg RANDOM` | Random search baseline |
| FF | `FOC_falsification.py` | Focused falsification (sensitivity analysis + per-requirement search) |
| MERLOT | `PFRL_falsification.py` | Reinforcement-learning-based search |
| SAMOTA | `PFES_SAMOTA.py` | Surrogate-assisted many-objective search (ART + global/local search with per-objective surrogate ensembles) |
| SAMOTA+SW | `PFES_SAMOTA.py --window_size 150` | SAMOTA with a sliding window cap on surrogate training data |

SAMOTA runs in two phases: **Adaptive Random Testing** (maximin sampling for an
initial diverse population), then iterated **Global Search** (per-objective GP +
polynomial + RBF surrogate ensembles driving NSGA-III) and **Local Search**
(HDBSCAN-clustered candidates refined with a per-cluster RBF surrogate). Search
effort is reallocated away from already-covered objectives each iteration.

## Project structure

```
run_all_experiments.py         # Entry point: runs all algorithm x benchmark combinations
analyze_all_results.py         # Violation counts, coverage, statistical tests
analyze_aucc_all.py            # Area-under-coverage-curve analysis
analyze_diversity_all.py       # Search diversity metrics (parameter-space spread)
compare_diversity_pf_samota.py # PF vs SAMOTA diversity comparison
plot_coverage_boxplot.py       # Coverage-rate / speed / cost figures
build_final_report_pdf.py      # Renders FINAL_REPORT.md -> FINAL_REPORT.pdf
FINAL_REPORT.md / .pdf         # Full results write-up

online-step-experiments/
  ADAS1/ ADAS2/ RR/
    config.py                  # Search-space variables, bounds, requirements
    PFES_falsification.py      # PF / RS
    FOC_falsification.py       # FF
    PFRL_falsification.py      # MERLOT
    PFES_SAMOTA.py             # SAMOTA / SAMOTA+SW
    SAMOTA_ensemble.py         # Per-objective surrogate ensemble
    RBF.py                     # RBF surrogate model
    utils/helpers.py           # Simulator wrapper (variable assignment, scoring)
    INPUT/                     # MDP model definitions

CPS-simulator/                 # MDP simulator (mdp_simulator package)
tests/                         # pytest suite (CLI checks, unit tests, smoke runs)
results/, results_diversity/   # Raw experiment output (30 runs x algorithm x benchmark)
```

## Installation

Requires **Python 3.11** (the simulator's pinned dependency set, notably `arviz
0.14`, is only compatible with 3.11 — a system `python3.12`/`python3` will resolve
to an incompatible newer `arviz`).

```bash
poetry env use python3.11
poetry install
```

Or with plain `pip`, in a Python 3.11 virtualenv:

```bash
pip install -r CPS-simulator/requirements.txt
pip install numpy scipy scikit-learn pandas matplotlib pymoo click hdbscan pytest reportlab
```

## Dependencies

- **Simulator** (`CPS-simulator/`): numpy, scipy, arviz==0.14, pandas, pymdptoolbox,
  matplotlib, colorama, termcolor. Imported via `sys.path` insertion, not installed
  as a package — every algorithm script adds `CPS-simulator/` to `sys.path` before
  `import mdp_simulator`.
- **Algorithms/analysis**: numpy, scipy, scikit-learn, pandas, matplotlib, pymoo,
  click, hdbscan, reportlab.

## How to run

Each benchmark directory is a self-contained CLI; run scripts with `cwd` set to the
benchmark folder so `config.py` and `utils/` resolve correctly:

```bash
cd online-step-experiments/ADAS1
python3.11 PFES_falsification.py --size 30 --niterations 30 --optalg NSGA3 --nruns 1 --logdir out --seed 1
python3.11 FOC_falsification.py --size 30 --totbudget 900 --nruns 1 --logdir out --seed 1
python3.11 PFRL_falsification.py --nepisodes 900 --nruns 1 --logdir out --seed 1
python3.11 PFES_SAMOTA.py --budget 900 --nruns 1 --logdir out --seed 1
```

Each run writes `reqs_*.csv` (per-requirement violation counts), `score_*.csv`
(best fitness per objective), and `timing_*.csv`/`meta_*.csv` to `--logdir`.

## Reproducing results

```bash
python3.11 run_all_experiments.py --benchmarks ADAS1 ADAS2 RR \
    --algorithms PF RS FF MERLOT SAMOTA SAMOTA_SW \
    --nruns 30 --budget 900 --results_dir results
```

Supports `--resume` to skip already-completed experiments and `--dry_run` to print
commands without executing. This is a long-running, computationally heavy sweep
(30 runs x 6 algorithms x 3 benchmarks); use `--benchmarks`/`--algorithms` to scope
to a subset.

Then regenerate the analysis tables, figures, and report:

```bash
python3.11 analyze_all_results.py --results_dir results --save_tables
python3.11 analyze_aucc_all.py
python3.11 analyze_diversity_all.py
python3.11 plot_coverage_boxplot.py
python3.11 build_final_report_pdf.py
```

## Testing

```bash
python3.11 -m pytest tests/                       # fast: CLI/import checks, unit tests
python3.11 -m pytest tests/ --run-slow             # + real end-to-end smoke runs (~10 min)
```
