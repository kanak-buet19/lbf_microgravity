# 02 — Terminal run dashboard

## Objective

Replace the long, repeated per-time-step output of `compressibleLaserbeamFoam`
with a live dashboard (= one fixed screen in the terminal that redraws in
place) showing the run's current state. The full solver log must still be
written to `log.compressibleLaserbeamFoam` unchanged.

## Tasks

1. [x] Collect a sample solver log (short run of
   `01_Al_keyholePore_validation/case/AL_500W_600mms_50um_bp`, run by the user)
   and list every line type printed per time step.
2. [x] Decide which numbers go on the dashboard and how they are grouped.
3. [x] Decide the approach: separate read-only Python script in the repo
   `toolbox/` folder (user's choice), no solver change.
4. [x] Write the dashboard script: `toolbox/rundash.py`.
5. [x] Hook it into the case `Allrun` without making the run depend on it.
6. [ ] Test on the sample log (done) and on a live run started by the new
   `Allrun` (by the user).
7. [x] Document usage in `CLAUDE.md` and the script docstring.

## Notes

### What one time step prints today (from the 2026-10-01 test run)

- `Courant Number mean/max`, `Interface Courant Number mean/max`, `deltaT`, `Time`
- `PIMPLE: iteration N`
- Phase-change accommodation and pairs (repeated every step, constant)
- `MULES: Solving for ...` per phase
- Mass-balance purge, volume closure defect, closure feedback
- Conserved partial mass per phase [kg]
- `alpha min/max/avg` per phase
- Laser: position, power, ray count, `Total Q deposited`
- Linear solver residuals: `U`, `T`, `epsilon1`, `p_rgh` (several correctors)
- `max(U)`, `min,max(p_rgh)`, `min(T)`, `max|vDot|*dt`
- `ExecutionTime` / `ClockTime`
- AMR (adaptive mesh refinement): "Selected N cells for refinement", "Unrefined from A to B cells"
- `time step continuity errors`

### Candidate dashboard panels

- **Run**: sim time / endTime, % done, deltaT, steps, wall time, sim-µs per wall-hour,
  estimated finish
- **Laser**: position, power, absorbed power (Total Q deposited), absorbed %
- **Fields**: max(U), p_rgh range, min/max T, max|vDot|*dt
- **Phases**: mass per phase (and its drift from the start), alpha min/max/avg
- **Mesh**: cell count, last refine/unrefine
- **Numerics**: Courant numbers, residuals, continuity error, closure defect
- **Warnings**: last FOAM Warning / FATAL lines, NaN detection

### Constraints

- Read-only: the dashboard must never change, slow down or stop the run.
- If the dashboard fails (no Python, missing package, output redirected to a
  file), the run carries on. Fall back to plain output.
- The log file stays complete for post-processing.
- Python: `~/.venv/venv312/bin/python`. `rich` (terminal layout library) is
  installed there; the system `python3` may not have it.

## Code changes

- New: `toolbox/rundash.py` (repo root).
- `project/01_Al_keyholePore_validation/case/AL_500W_600mms_50um_bp/Allrun`:
  solver in the background → log; dashboard in the foreground with `--pid`;
  Ctrl+C trap stops the solver; `LBF_DASH=0` for plain output; `LBF_PYTHON`
  to pick the Python.
- `CLAUDE.md`: folder map + "Live run dashboard" section.
