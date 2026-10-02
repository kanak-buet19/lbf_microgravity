# 03 — Unattended keyhole calibration

Calibrates the `laserbeamFoam` Huang case (Al, 500 W, 0.6 m/s) against the
X-ray data, on the adaptive mesh with 10 µm cells at the surface
(`config.json` `case.max_refinement`: 1 = 10 µm, 2 = 5 µm), with up to 8 jobs ×
8 cores at once.
Start it once and leave it: it chooses runs, runs them, stops each one when
the keyhole depth is steady, learns from every result, and stops when the
calibrated values are settled or the budget is spent.

## Start

```bash
tmux new -s calib                  # so it survives logout
of2512                             # OpenFOAM v2512 with laserbeamFoam built
cd <repo>/project/03_surrogate_calibration
./run_calibration.sh               # Ctrl+B then D to leave it running
```

- First start creates `.venv/` here (needs internet once). Later starts reuse it.
- `./run_calibration.sh --dry` shows what would start (writes `runs_dry/`, `state_dry.json`).
- Stopping the driver (Ctrl+C) leaves jobs running. Starting it again re-attaches
  and resumes any job that stopped meanwhile from its last write.
- `./run_calibration.sh --stop-all` stops every job.

## Watch

Open `dashboard.html` in a browser (refreshes every 60 s). Green / yellow /
red banner, running jobs with ETA, depth curves vs the Huang band, calibrated
knob values with uncertainty, failed runs and why, warnings, driver timeline.

## Files

| File | What |
|---|---|
| `config.json` | All settings: knobs and ranges, targets, cores, run length, early stop, budget |
| `template/` | Case template with `@name@` placeholders |
| `scripts/driver.py` | The loop (jobs, early stop, failures, surrogate, dashboard, backups) |
| `scripts/make_case.py` | Parameters → case folder (+ `params.json` with git commit) |
| `scripts/postpro.py` | Huang-style X-ray measurement, ML window, steady test, statistics |
| `scripts/surrogate.py` | Gaussian processes, Bayesian calibration, next-run choice, stop test |
| `scripts/dashboard.py`, `scripts/report.py` | `dashboard.html`, `results.md` |
| `scripts/keyhole_depth.py` | Stand-alone depth/pore tracker for any case |
| `state.json` | Everything the driver knows (restart point) |
| `driver.log` | Every driver action with time |
| `runs/run_NNN/` | One case: logs (gzipped), `summary.json`, `xray_frames.json`, `ml_window/*.npz`, field writes every 20 µs + last |
| `surrogate_history/` | Calibration state after every update |
| `backup/` | Copies of state and results every 3 h (last 8 kept) |
| `results.md` | Final calibrated values and fit (written at the end) |

## How one run goes

1. `run.sh`: `blockMesh`, `setFields`, `decomposePar`, then
   `taskset -c <8 CPUs> mpirun --oversubscribe --bind-to none -np 8 laserbeamFoam -parallel`.
2. Fields are written every 2 µs. The driver measures each write (X-ray frame
   every 20 µs, ML window every write) and deletes it, except every 20 µs and
   the newest.
3. Depth steady (two 100 µs windows agree within 15 µm, after 150 µs) →
   400 µs more → the job is stopped and its statistics saved.
4. NaN / FATAL in the log, or no progress for 45 min → the job is stopped and
   marked failed. The surrogate avoids that region.
