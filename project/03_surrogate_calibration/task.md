# 03 — Surrogate-based calibration of the Huang Al keyhole case

## Objective

Calibrate `laserbeamFoam` (case
`../01_Al_keyholePore_validation/case/AL_500W_600mms_50um_bp_lbf`) against
Huang et al. 2022 (Al, 500 W, 0.6 m/s, 50 µm spot) with as few fine-mesh runs
as possible. A fine run of the full 1.5 ms takes ~2 days on 8 cores, and the
result depends on the mesh, so brute-force search is not possible.

Approach: multi-fidelity Bayesian calibration. A surrogate (= cheap statistical
model of the solver output) is trained on many coarse runs and a few fine runs;
it learns the coarse-to-fine difference and proposes the next batch of runs.

Hardware: 72-core workstation (physical core count still to check with
`lscpu`). **Use at most 64 cores at a time** (user, 2026-10-01). Default:
8 jobs × 8 cores, each pinned to its own cores. Many small parallel jobs, not
one large job. Launch: `taskset -c <cpu list> mpirun --oversubscribe --bind-to none
-np 8 laserbeamFoam -parallel` (user's choice: oversubscribe; taskset keeps each
job on its own 8 logical CPUs, CPUs 0–63; 64–71 left free).

## Calibration parameters (user's choice, 2026-10-01)

| # | Parameter | File | Start value | Range (proposed) | Note |
|---|---|---|---|---|---|
| 1 | `laserRadius` | `constant/LaserProperties` | 25e-6 | 20–45e-6 m | "50 µm spot" may be 1/e² diameter (R = 25) or FWHM (1/e² radius ≈ 42) |
| 2 | `Radius_Flavour` | `constant/LaserProperties` | 2 | **fixed at 2** | redundant with #1, see notes |
| 3 | `Elec_conductivity` | `transportProperties` metal | 4e6 | 2e6–5e6 S/m | sets Fresnel absorption per bounce |
| 4 | solid k scale | `poly_kappa_solid` | 1 | 0.8–1.2 | multiplies (248 − 0.0385 T) |
| 5 | liquid k | `poly_kappa_liquid` | 91 | 70–120 W/(m K) | |
| 6 | solid cp scale | `poly_cp_solid` | 1 | 0.9–1.1 | multiplies (762 + 0.44 T) |
| 7 | liquid cp | `poly_cp_liquid` | 1177 | 1060–1300 J/(kg K) | |
| 8 | `sigma` | `transportProperties` | 0.914 | 0.5–1.0 N/m | real σ falls with T; one value stands for the keyhole wall |

Fixed: `Radius_Flavour` 2, `e_num_density` 1.81e29, recoil factor 0.54 (hard-coded, `UEqn.H`),
all other properties.

## Targets (from `../01_Al_keyholePore_validation/reference_paper/huang2022/AL_500W_600mms_50um_bp/`)

- Mean keyhole depth 563 ± 37 µm (steady part).
- Depth fluctuation: standard deviation and period (~200 µs).
- Keyhole length along the scan vs depth (`data/length_vs_depth.csv`), reduced
  to 2–3 numbers (PCA = principal component analysis).
- Later (not for the first round): pore count, size and depth.

## Fidelity levels

| Level | Mesh | Run | Cost |
|---|---|---|---|
| L0 | none: keyhole scaling law (Gan et al. 2021, Nat. Commun.) | — | free |
| L1 | base 20 µm, 1 AMR level → 10 µm | short (~0.5 ms), small domain | hours |
| L2 | base 20 µm, 2 AMR levels → 5 µm | short (~0.5 ms), small domain | ~0.4 day |

## Tasks

1. [x] Depth tracker (`scripts/keyhole_depth.py`, `scripts/foamio.py`): function object or post-processing script that writes
   keyhole depth (and absorbed power) vs time from a run, without changing the
   solver output.
2. [ ] Find the steady-state time: from the running full case, see when depth
   levels off. Sets the short run length (~0.5 ms expected).
3. [x] Case template (`template/`, x = 900 µm, laser 150 → 750 µm, cap 1 ms): shorter domain in x (~800 µm), endTime from task 2,
   few field writes; mesh level and the 8 parameters filled in by a script.
4. [x] `scripts/make_case.py`: parameter set + level → ready case folder.
5. [x] ~~`scripts/launch_batch.sh`~~ done inside `driver.py` (`run.sh` per run): start N cases at once with core pinning
   (`mpirun --bind-to core --cpu-set`), one log each. Run by the user.
6. [x] `scripts/postpro.py` (instead of extract.py): finished run → depth mean, std, period, length
   profile features.
7. [-] ~~Mesh check~~ dropped (user, 2026-10-01). The coarse-to-fine gap is learned
   by the multi-fidelity surrogate from the L1/L2 runs instead.
8. [-] Sensitivity screen: replaced by the GP length scales (relevance per knob) from the first runs, all on the 5 µm mesh. Old plan: Morris on L1: Morris method (= vary one parameter at a time
   along several random paths; ranks parameters by effect). ~4 paths × 9 =
   ~36 coarse runs, two batches on the workstation. Drop parameters with
   little effect.
9. [x] Surrogate + calibration (`scripts/surrogate.py`, scikit-learn GPs, not BoTorch: no torch needed): multi-fidelity Gaussian process (L1 + L2), Bayesian
   calibration with a model-discrepancy term (Kennedy–O'Hagan), batch
   proposal of next runs (cost-aware, multi-fidelity knowledge gradient).
10. [ ] Rounds: initial design (Latin hypercube) → 2–3 proposal batches → 1–2
    fine check runs at the best parameters.
11. [x] **Automated driver** (`scripts/driver.py`, started once by the user in
    `tmux` via `run_calibration.sh`): asynchronous job queue (max 64 cores,
    8 jobs × 8 cores, `taskset` + `mpirun --oversubscribe`), per-run early stop
    when depth is steady, crash/NaN/stall detection (failed points fed to the
    surrogate as "avoid"), surrogate update after every run, full state in
    `state.json` (restart-safe, resumes half-finished runs), stops when the
    posterior has converged or the budget (time / runs) is spent.
12. [x] **Self-contained Python**: `run_calibration.sh` checks for
    `.venv/` in this project; if missing or broken, finds Python ≥ 3.9 and
    creates it (`uv` → `python -m venv` → `--without-pip` + get-pip.py),
    installs `requirements.txt` (numpy, scipy, matplotlib, pillow, torch CPU,
    gpytorch, botorch), checks all imports, stops with a clear message if it
    cannot. Also checks OpenFOAM v2512 + built `laserbeamFoam`.
13. [x] **HTML dashboard** (`dashboard.html`, regenerated by the driver every
    few minutes, auto-refresh, one self-contained file, Arial):
    - health banner: all good / warnings / errors, with the reason
    - jobs: running / queued / done / early-stopped / failed, cores used,
      sim time, progress, speed, ETA, last log line
    - per-run depth vs time with the Huang band (563 ± 37 µm)
    - calibration progress: best fit so far, parameter estimates with
      uncertainty after each update, how close to the stop criterion
    - errors and warnings list (crashes, NaN, stalls, disk low, missing files)
    - machine: cores in use, disk free, total wall time, runs per day
    - timeline of driver actions (from `driver.log`)
14. [ ] Results in `results.md`: calibrated values with uncertainty, fit to
    each target, coarse/fine gap.

## Run settings (proposed 2026-10-01, to confirm after the steady-state run)

| Item | Value |
|---|---|
| Domain | x ~800 µm (from 1500), y 120 µm argon + 900 µm Al, z 500 µm (real sample thickness) |
| Mesh | AMR, base 20 µm, 2 levels → 5 µm (same as the steady-state run) |
| Run length | until depth steady + ~3 fluctuation periods (~600 µs guess), hard cap ~800 µs, early stop |
| Wall time | ~79 s per simulated µs alone on 8 cores → ~13 h per 600 µs; ~16–20 h with 8 jobs sharing |
| Field writes | every 10 µs for depth; keep every 20 µs + last; rest deleted after extraction |
| ML window | T, alpha.metal, U in a 300 × 600 × 200 µm box moving with the laser, 6 µm grid, every 2 µs, kept (~0.5 GB/run) |
| Logs | full solver log per run (gzipped, incl. resume logs), fieldMinMax, keyhole_depth.csv, driver.log, state.json, surrogate snapshots |
| Disk | ~10–15 GB kept per run + ~10 GB scratch per running job (728 GB free on this PC) |

## Notes

- **`Radius_Flavour` and `laserRadius` are the same knob.** The beam profile is
  `I = F·Q/(πR²)·exp(−F r²/R²)` (`laserHeatSource.C`), which is exactly a
  standard Gaussian with 1/e² radius `w = R·√(2/F)`. Only `w` matters (apart
  from the ray seeding cut-off at r ≤ 1.5 R, which loses ~1 % of power at
  F = 2 and ~11 % at F = 1). Calibrating both gives a ridge of equally good
  pairs and wastes runs. Decision (user, 2026-10-01): fix F = 2, calibrate R only (20–45 µm).
- 8 parameters is many for ~10 fine runs; the screen (task 8) is there to cut
  it to 3–4.
- Material parameters (k, cp, σ) are well known for pure Al. If calibration
  moves them far from literature, that points to a missing physics effect
  rather than a better value. Report it, do not hide it.

## Code changes

None yet.

## Decisions (user, 2026-10-01)

1. Replicates: 2–3 runs at the same parameters in the first batch to measure
   run-to-run noise (chaotic keyhole); the surrogate uses it as noise level.
2. Depth counted from the flat (initial) plate surface. Simulated keyhole is
   measured like the X-ray: side projection along z, 1.96 µm pixels, every
   20 µs (Huang Methods), depth = deepest keyhole pixel below the surface.
3. Score: each target weighted by its tolerance (measurement uncertainty);
   mean depth weighted most. Fluctuation period reported, not scored (paper
   ~200 µs vs ~350 µs from the movie: too uncertain).
4. Budget/stop: 7 days or 50 runs, or each knob's posterior std < 5 % of its
   range.
5. Code changes kept (ray-wall fix, compressible melting-loop fix,
   laserbeamFoam solid/liquid k/cp).
6. User compiles OpenFOAM and solvers on the workstation; not handled here.
7. Max 64 of 72 cores; driver/post-processing run on the rest.
8. Held-out validation case (other power/speed): later, not now.
9. No phone notifications.
10. Back up `state.json` and results every few hours.
