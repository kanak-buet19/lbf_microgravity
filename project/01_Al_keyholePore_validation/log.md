# Log — 01 Al keyhole pore validation

Entries before `[2026-10-01 19:43:38]` were written after the fact. Their times
come from file modification times, or are marked `~` (approximate) when no file
records them.

## Reference papers

[2026-10-01 19:18:24] Huang 2022 paper in `reference_paper/huang2022/`.
[2026-10-01 19:18:35] Guo 2023 paper in `reference_paper/guo2023/`.
[2026-10-01 19:23:50] Huang supplementary PDF (MOESM3, movie list only) and
Movie 4 (`v4.mp4`) in `reference_paper/huang2022/supplementary/`.

## Movie 4 to GIF

[~2026-10-01 19:25] `v4.mp4` would not play in VS Code or the default player.
Checked the file with a Python parser: the MP4 structure is complete. The codec is
MPEG-4 Part 2 (`mp4v`), which those players do not support.
[~2026-10-01 19:25] System has no ffmpeg or pip. Used the ffmpeg binary bundled
with `imageio-ffmpeg` in `~/.venv/venv312`.
[2026-10-01 19:26:11] Converted to GIF at native size and rate:
`ffmpeg -i v4.mp4 -vf "split[a][b];[a]palettegen[p];[b][p]paletteuse" -loop 0 v4.gif`
(512×680, 5 fps, 81 frames, 13.7 MB). First try at 640 px / 15 fps gave 22 MB
and was replaced.
[~2026-10-01 19:27] Renamed the GIF to `AL_500W_600mms_50um_bp.gif` ("bp" =
bare plate; the supplementary PDF confirms Movie 4 is a bare Al plate, 500 W,
0.6 m/s).
[~2026-10-01 19:28] Renamed the PDFs:
- `1-s2.0-S0890695522001286-main.pdf` → `guo2023_keyhole_porosity_LPBF_aluminium.pdf`
- `s41467-022-28694-x-1.pdf` → `huang2022_keyhole_fluctuation_pore_formation_LPBF.pdf`
- `supplementary.pdf` → `huang2022_supplementary_info.pdf`

## Huang paper: case data

[~2026-10-01 19:29] Read the full paper text. Rendered pages 3–7 to read
Figs. 1–2. Rightmost Al bare-plate point (normalised enthalpy product ≈ 43 for
β = 0.15) read by eye: front wall angle ~87–88°, length period ~340 µs, depth
period ~200 µs, porosity ~0.9 %.
Decision: the local supplementary PDF is MOESM3 (movie list). The property table
(Supp. Table 3) is in MOESM1, which we do not have.

## Movie 4 measurement

[~2026-10-01 19:30] Extracted the 81 frames from the MP4 (not the GIF, which has
fewer colours). Green outline = keyhole, red outline = pores. Surface row 171,
1.96 µm/px, 20 µs/frame. Check: keyhole tip moves at 0.59 m/s, so the scale and
timing are right.
[~2026-10-01 19:31] First plot: depth, length (then called "width") and final
pore map. Fixed the mean label overlapping the data.
[~2026-10-01 19:33] Added the length-vs-depth profile (average keyhole shape).
Found a neck at ~470 µm and a bulb at 510–550 µm.
[~2026-10-01 19:35] User correction: the horizontal size in a side view is the
**length along the scan**, not the width. Renamed everywhere. Added mouth
length (top 3 rows of the keyhole).
[~2026-10-01 19:36] Moved everything into one case folder
`reference_paper/huang2022/AL_500W_600mms_50um_bp/` (`video/`, `data/`,
`plots/`). `v4.mp4` renamed to `AL_500W_600mms_50um_bp.mp4`. Deleted the loose
CSV/PNG files from earlier tries.
[2026-10-01 19:36:47] Wrote `measure_keyhole.py`, which rebuilds all data and
plots from the movie. Run:
`~/.venv/venv312/bin/python measure_keyhole.py`
[2026-10-01 19:36:52] Script output:
```
tip speed            0.59 m/s
depth                mean 563  std 37  min 470  max 662 um  period 350 us
mouth length         mean 32  std 12  min 11  max 78 um  period 200 us
median length        mean 31  std 5  min 20  max 50 um  period 260 us
final pores          n=14  median 15 um  range 8-54 um
```
Fixed the caption of `keyhole_shape.png` overlapping the axis labels
(switched to `fig.supxlabel`).
[2026-10-01 19:37:19] Wrote the case `README.md` (set-up, paper values,
measured values, notes).

## Guo 2023 paper: simulation set-up

[~2026-10-01 19:42] Read the methods section. Rendered pages 4 and 6 to read
Fig. 1 (domain) and Fig. 4 (comparison with Huang). Domain 1800 × 270 (half,
symmetry) × 900 µm, uniform 6 µm cells (~2.0 M), time step ~0.068 µs,
FLOW-3D v11.2, absorption 0.7, no vapour phase.
Cross-check: Guo Fig. 4a gives 506 µm depth at 1.08 ms in the X-ray; my CSV gives
510 µm at 1080 µs.
[2026-10-01 19:43:13] Wrote `reference_paper/guo2023/README.md`.

## Project files

[2026-10-01 19:43:38] User pointed out that `task.md` / `log.md` were missing
(required by `CLAUDE.md`). Wrote `task.md` and this log. From here on, entries
are written as the work happens.
Note: an empty `case/` folder exists (created 19:41:21, not by Claude).

## Repo changes made in the same session (not part of this project)

Recorded here so they are not lost. None are committed.
- [~2026-10-01 19:15] Deleted `tutorials/laserbeamFoam`, `tutorials/laserMeltFoam`,
  `tutorials/microstructureFoam` (`git rm`), then
  `tutorials/compressiblelaserbeamFoam/mthd`.
- [2026-10-01 19:41:00] Wrote the repo-root `CLAUDE.md`.
- [~2026-10-01 19:42] Removed `.agents/skills/laserbeamfoam/` (`SKILL.md`,
  `agents/openai.yaml`) and every reference to it in `CLAUDE.md`.

## Case set-up (task 7)

[2026-10-01 19:45:14] User asked to set up the simulation case for the Huang experiment. Started by reading the `LPBF_small_vapour` tutorial and the laser code.
[2026-10-01 19:48:54] Read the case and solver code. Findings that set the case design:
- Ray tracing (`src/laserHeatSource`) assumes the beam travels along +y and the beam
  position is in the x–z plane. Rays start from cells next to the patch with
  `Laser_boundary = 1` (cell mode) or from a disc at the laser position (polar mode).
  So: x = scan, y = depth (+y into the metal), z = across the plate. Gravity (0 9.81 0).
  Built directly in that orientation, like `multiComponentLaserIrradiation`
  (no `transformPoints`).
- The rays have no symmetry-plane handling (`laserRayParticle` only handles walls and
  processors). So model the full 0.5 mm plate width, not half.
- Phase change: Hertz–Knudsen with P_sat = P0 exp(M L_v/(R T_b) (1 − T_b/T)), where
  M is the liquid metal `molWeight`. So `molWeight` must be the real 26.98 g/mol.
- Surface tension is one constant per phase pair; Marangoni comes from `dsigmadT`.
- No phase names are hard-coded: phases named `aluminium`, `aluminiumVapour`, `argon`.
- `meltPoolHistory` function object does not track keyhole depth: not used.
[2026-10-01 19:51:53] Wrote case `case/AL_500W_600mms_50um_bp/`:
- `system/blockMeshDict`: x 1500 µm (scan) × y 120 µm argon + 900 µm Al × z 500 µm
  (full plate thickness), uniform `dx = 6e-6` via `#eval` → 250 × (20+150) × 83 ≈ 3.5 M cells.
  First version had every boundary face pointing inward; checked against the tutorial
  convention (right-hand rule outward) and reversed all faces. Rechecked: all outward.
- `system/fvSchemes`, `system/fvSolution`: copied unchanged from `LPBF_small_vapour`.
- `system/controlDict`: endTime 1.5 ms, write every 20 µs (= X-ray frame), maxCo 0.05,
  maxAlphaCo 0.05, maxDeltaT 1e-7, binary output.
- `constant/`: phases (aluminium aluminiumVapour argon); literature properties for
  pure Al (Huang Supp. Table 3 not available); polar ray seeding 20 × 36; laser
  500 W ramped over 1 µs, x 200 → 1100 µm at 0.6 m/s, z = 250 µm.
- `initial/`: open `top` (totalPressure 1.11325e5 Pa = 1 atm + 10 kPa), all other
  patches no-slip walls, adiabatic. `Laser_boundary` = 1 on `top`.
- `Allrun` (blockMesh, checkMesh, setFields, solver; `-parallel` option), `Allclean`,
  `README.md` (design, values, known simplifications, comparison targets).
[2026-10-01 19:51:53] Parse check with `foamDictionary` (reads files only, runs
nothing): all files parse. `#eval` gives nx 250, nyGas 20, nyMet 150, nz 83.
`timeVsLaserPosition`/`timeVsLaserPower` fail in `foamDictionary`, but so do the
tutorial's own files (bare lists, not dictionaries); brackets checked balanced.
Not run: per CLAUDE.md, the user runs blockMesh / the solver.

[2026-10-01 19:53:17] User asked: can we use a dynamic mesh (AMR)? Checked: solver computes `refineIndicator` each step in `update.H` (metal surface band + vapour + gas/metal minority); laser code recomputes `yDim` per cell each step; `multiComponentLaserIrradiation` uses `dynamicRefineFvMesh` (tuned in commit 0bea7ea1). Polar ray seeding does not depend on cell size. Decision: base 20 µm, maxRefinement 2 → 5 µm at interfaces. 20 µm divides every length (1500, 120, 900, 500 µm) exactly.
[2026-10-01 19:53:38] Switched case to AMR: `dx 20e-6` (95,625 base cells), `constant/dynamicMeshDict` = `dynamicRefineFvMesh` on `refineIndicator`, maxRefinement 2 → 5 µm, refineInterval 5, nBufferLayers 6, correctFluxes copied from `multiComponentLaserIrradiation`. Parse-checked (nx 75, nyGas 6, nyMet 45, nz 25). README mesh section updated (expected ~1 M cells; melt pool interior stays 20 µm; no parallel load balancing).
[2026-10-01 19:54:14] decomposeParDict: numberOfSubdomains 32 → 8 (method scotch, unchanged). README run line updated.
[2026-10-01 19:54:57] User approved a one-off short test run (exception to the CLAUDE.md run rule). Copied case to scratch folder `/tmp/claude-1000/-home-rakibul-work-research-LaserbeamFoam/a5e94309-5093-4365-9d15-d0e10bad6970/scratchpad/testrun/AL_500W_600mms_50um_bp`; case folder untouched.
[2026-10-01 19:56:44] Test run stopped by user request after 64 steps (t = 0.92 µs, 67 s wall on 8 cores). No errors, no NaN. Laser OK: ~9.5% absorbed (8.07 W of 85 W during the power ramp). Phase masses constant. AMR working: 95,625 → 358,125 → 226,875 cells. Open point: max(U) rose to ~10 m/s before any melting (start-up pressure transient?); not yet checked in the fields. Scratch run folder deleted; case folder untouched.
[2026-10-01 19:56:57] Allrun: solver now runs through `tee`, so output shows live in the terminal and is still saved to log.compressibleLaserbeamFoam. Parallel uses `mpirun -np $(getNumberOfProcessors)` (= 8 from decomposeParDict).
[2026-10-01 20:02:42] Case `Allrun` rewritten for the live dashboard (toolbox/rundash.py, project 02): solver in background → log, dashboard in foreground, Ctrl+C stops solver, `LBF_DASH=0` for plain output. Seen in the user's run log: T is solved 21 times every step (first solve + all 20 `maxTempCorrector` loops), i.e. the melting corrector never meets its tolerance; max(U) 8–14 m/s at t ≈ 1 µs before melting. Both to look into.
[2026-10-01 20:03:25] Allrun: parallel is now the default; `./Allrun -serial` for serial. README updated.
[2026-10-01 20:07:35] Committed repo changes on new branch `compressible-cleanup-and-run-dashboard`: 0e3ee3b0 (remove non-compressible tutorials + .agents), 741c63cd (CLAUDE.md + toolbox/rundash.py). project/ not included (ignored by `0*`). Not pushed.
[2026-10-01 20:12:53] Diagnosed slow T loop (21 T solves/step): late in the melting loop the T linear solver (tol 1e-8) does 0 iterations, so T is frozen and epsilon1 only creeps (error ×0.93–0.97 per pass = 1 − Cv·ΔT/L). Needs ~100 passes to reach epsilonTolerance 1e-6 → always hits maxTempCorrector. Loop condition `iter <= maxTCorr` also allows maxTCorr+1 passes (TEqn.H:165). Run had stopped at t = 10.4 µs (no process).
[2026-10-01 20:13:28] Fix (settings only, case `system/fvSolution`): exact `T`/`TFinal` solver entries (smoothSolver, tolerance 1e-10, minIter 1) so T responds on every MELTING pass; checked OpenFOAM smoothSolver honours minIter (smoothSolver.C:162,208). MELTING: epsilonTolerance 1e-6 → 1e-5, maxTempCorrector 20 → 10. Parse-checked. Not run.
[2026-10-01 20:13:28] Saved the old run's log as `baseline_log.compressibleLaserbeamFoam_beforeTfix` (project 01 folder) to compare against.
[2026-10-01 20:16:49] Test of the settings fix (user's run, at t = 1.9 µs): loop still not converging; now stops at 11 passes (maxTempCorrector 10 + 1). epsilon1 max residual still creeps ×0.978 per pass even with T iterating every pass (0.0174 → 0.0170 → 0.0166). Speed about equal to baseline (135 s at 1.9 µs vs 142 s at 2 µs); early steps slower (50 vs 33 s at 0.2 µs) from the 1e-10 T tolerance.
Revised diagnosis (not yet confirmed in field data, no write yet): meltCoeff = 0.9 Cv/L_metal (TEqn.H:35-39) but the latent term in TEqn is meltMask*LatentHeat = meltMask*condensate*L_metal (TEqn.H:54). In part-metal interface cells the update is too small by ~meltMask*condensate, so it creeps; max-residual check (TEqn.H:156) is set by these near-gas cells. Options proposed to user: A scale meltCoeff by the metal fraction (with floor), B weight the residual by metal fraction, C settings only. Waiting for the user's choice.
[2026-10-01 20:18:19] Checkpoint t = 5 µs: new 248 s vs baseline 266 s (7% faster); T solves/step (cumulative) 7.6 vs 15.7. Conclusion: halving T solves saved only 7% → the melting loop is a small share of step cost. Revised plan proposed to user: keep settings, hold option A, profile one step to find the real bottleneck.
[2026-10-01 20:20:24] User chose to fix it in the solver (and stopped the run). Changed `applications/solvers/compressibleLaserbeamFoam/TEqn.H`: melt-fraction update coefficient
  meltCoeff = epsilonRelaxation / max(dTmush + meltMask*LatentHeat/Cv, 1e-3 K)
(was epsilonRel*Cv/L_metal). Derivation: one pass changes the error by 1 − meltCoeff*(dTmush + meltMask*LatentHeat/Cv), so the new choice gives 1 − epsilonRelaxation (= 0.1) in every cell, metal or interface. Bulk Al: 2.49e-3 vs old 2.67e-3 1/K (almost unchanged). Removed now-unused `LatentHeatCond`. Assumes T reacts on every pass, so case keeps T `minIter 1`; T tolerance set back to 1e-8 (1e-10 slowed pre-melt steps). Not built or run.
[2026-10-01 20:23:15] User rebuilt the solver (binary 20:21:12) and started a run with the TEqn.H fix. Melting loop now converges below epsilonTolerance 1e-5 in 9 passes per step (error ×~0.2 per pass, e.g. 0.0102 → 0.0022 → 4.2e-4 → 7.2e-5 → 1.3e-5 → 2.5e-6); before it never converged. Early speed: 69 s at t = 1 µs vs baseline 74 s. Waiting for t = 5 µs to compare.
[2026-10-01 20:25:21] Live change in the running case: T/TFinal nSweeps 1 → 2 (fuller T response per MELTING pass). Before: loop factor ~×0.37/pass, 11 passes (cap) in 38 of last 40 steps. Edited at step 202.
[2026-10-01 20:25:53] Result of nSweeps 2 (steps 205–216): 7–10 T solves per step (was 11 = cap in 38/40 steps); loop factor ~×0.22/pass, converges below 1e-5 before the cap (e.g. 0.085 → 0.018 → 0.0039 → 8.4e-4 → 1.8e-4 → 4.0e-5 → 8.7e-6). Step cost unchanged ~1.1 s (every 5th step ~1.8 s = AMR). Wall time to t = 5 µs (solver fix, nSweeps 1): 229 s vs 266 s original (-14%) and 248 s settings-only. Task 8 done. Next: profile a step (p_rgh, mixture.solve, ray tracing, AMR).
[2026-10-01 20:28:24] Melting check: liquid fraction first changes at t = 0.39 µs (consistent with a hand estimate). But zero Al vapour by 8.3 µs although the surface should pass boiling within ~1 µs. Cause found: solver pairs metal and vapour by name, vapName = liq.name() + "vapour" (multiphaseMixtureThermo.C:1834). Case uses "aluminiumVapour" (capital V) → no phase-change pair → no evaporation, no recoil, no keyhole. Log shows "Phase-change pairs:" with nothing after it. My setup error (earlier hard-coded-name check only searched "air"/"metal"). Fix planned: rename phase to "aluminiumvapour" in the case; asked the user to stop the run first. Secondary risk noted: plate top on a cell face → no part-metal cells at start → evaporation gate gInt = 0 until the melt moves.
[2026-10-01 20:29:58] User stopped the run (log last written 20:28:41). Renamed vapour phase aluminiumVapour → aluminiumvapour: constant/thermophysicalProperties (phases + pair tables), constant/thermophysicalProperties.aluminiumvapour, initial/alpha.aluminiumvapour, initial/T.aluminiumvapour, system/setFieldsDict, README. Grep: none left. All parse. Added naming warning comment above `phases` and a "Vapour naming rule" note in CLAUDE.md. Old 0/ and processor*/ still have the old names: run ./Allclean before ./Allrun.
[2026-10-01 20:32:48] Restarted run (after rename): pair (aluminium,aluminiumvapour) found; evaporation starts at t = 0.62 µs (matches 0.5–1 µs estimate). At t = 2.0 µs: evap 3.0e-10 kg/s, cond -5.5e-13 kg/s, vapour alpha max 0.48, max(U) 28.6 m/s (vapour jet), dt 1.1e-8 s (was ~3e-8), ETA ~27 h. No warnings. The cell-face worry did not block evaporation.
[2026-10-01 20:34:16] max(U) rise explained: tracks evaporation (t 1.6 → 2.25 µs: maxU 9 → 242 m/s, evap 9e-13 → 2.6e-9 kg/s, vapour alpha max 0.002 → 0.93). Physical vapour jet (liquid/vapour density ratio ~2e4; sound speed in Al vapour ~1200 m/s). Earlier 6–14 m/s was start-up noise (no vapour because of the naming bug). Consequence: maxCo 0.05 on 5 µm cells → dt ~1e-9 s, ~30× smaller; full run would take weeks. Proposed: try maxCo 0.2 live.
[2026-10-01 20:34:51] Set controlDict maxCo 0.05 → 0.5 (user asked). The run had already been stopped and the case cleaned by the user (no log, no processes), so the change applies to the next run. maxAlphaCo stays 0.05, maxDeltaT 1e-7.
[2026-10-01 20:35:18] controlDict maxCo 0.5 → 0.2 (user asked, no run in between). maxAlphaCo still 0.05.
[2026-10-01 20:39:49] Run with maxCo 0.2: before evaporation dt grew to 9e-8 s (Co 0.196). After evaporation Co = interface Co = 0.050 → maxAlphaCo 0.05 limits dt (6.2e-10 s at t = 2.27 µs, max U 446 m/s, evap 3.5e-9 kg/s). Interface Co counts vapour/argon mixing cells too. Velocities ~1.5x the previous run at the same t (39 vs 27 m/s at 2.0 µs): possibly larger pre-evaporation dt lets the surface overheat (time-step dependence; check later). A few "implicit coupling ceiling: N cell(s) capped" messages. Proposed: maxAlphaCo 0.2 live, or solver change to count only the metal interface in the interface Courant number.
[2026-10-01 20:40:21] controlDict maxAlphaCo 0.05 → 0.2 (user asked). No solver running at the time; applies to the next run. Now maxCo 0.2, maxAlphaCo 0.2.
[2026-10-01 20:44:15] Run blew up after maxAlphaCo 0.2: once evaporation took off (t ≈ 2.2–2.4 µs) max U rose 38 → 3,680 → 13,500 → 50,800 m/s (far above the ~1,200 m/s sound speed in Al vapour), dt collapsed to 4e-10 s, absorbed 9.5 → 21% (surface torn up), 15 "implicit coupling ceiling" messages. User asked to undo both: controlDict back to maxCo 0.05, maxAlphaCo 0.05. Conclusion: the phase-change step needs the small interface Courant number; speed-up must come from a solver change (metal-only interface Courant) or the incompressible solver for calibration.
[2026-10-01 20:49:52] Git history review (user asked):
- setDeltaT_.H (physics-based dt limiter: acoustic Co, maxPhaseChangeFraction on vDot*dt, maxDeltaTK) added by T. Flint in c72c17c3 (2026-07-24), trimmed in 12317ab2; never included by compressibleLaserbeamFoam.C in any commit (main loop uses VoF/setDeltaT.H). Phase-change code still refers to maxPhaseChangeFraction.
- Only LPBF-with-vapour case in history: P. Cosic Ti64 (ba1fdbd4, 2026-08-14, removed 147e70ca "until its validated"): maxCo/maxAlphaCo 0.02, maxDeltaT 1e-8, endTime 100 µs, 16 cores / 40 h SLURM job; physical vapour (perfectFluid rho0 0, R 186.4).
- LPBF_small_vapour heavy vapour (perfectFluid rho0 5, R 8.314) dates from 48cbbbd5 (2025-11-12), before the 2026 rewrite.
- P. Cardiff fixed the T corrector off-by-one in laserbeamFoam (origin/codex/fix-temp-corrector-off-by-one, 02ee63a4); the compressible TEqn.H still has `iter <= maxTCorr`.
- Comment removed in fd006316 ("DONT MERGE", merged anyway): growing volume-closure defect in keyhole cells → investigate before trusting porosity results.
Conclusion: enabling setDeltaT_.H is the author's own design for this problem but untested in any commit; 0.02–0.05 Courant limits are this solver's normal range.
[2026-10-01 20:52:07] Correction: run with original maxCo 0.05 / maxAlphaCo 0.05 blows up the same way at t ≈ 2.35 µs (max U 338 → 801 → 4,930 m/s; dt 2e-10 s; ETA 29 days). So the earlier blow-up was NOT caused by maxAlphaCo 0.2. Coincides with the first pure-vapour cells (vapour alpha max reaches 1.00 at ~2.33 µs); absorbed 9.5 → 14.6%. Proposed: stop; short diagnostic run (endTime 2.6e-6) with fieldMinMax (with locations) on U, T, p, alpha.aluminiumvapour to find where the velocity peak starts.
[2026-10-01 20:53:01] Diagnostic set-up (run stopped by user): controlDict endTime 1.5e-3 → 2.6e-6, writeInterval 2e-5 → 1e-7 (both marked DIAGNOSTIC; revert for production), added fieldMinMax (U, T, p, p_rgh, alpha.aluminiumvapour, alpha.aluminium; magnitude; with locations; log + postProcessing/minMax). Parse-checked.

## [2026-10-01 21:13:21] Diagnostic run analysed: blow-up cause found (stray ray into a gas wall cell)
- Read postProcessing/minMax/0/fieldMinMax.dat and processor4 fields at 2.2, 2.3, 2.4 us (binary reader in scratchpad).
- Up to 2.34 us max|U| (~330 m/s), max T (~3300 K) and max p (~0.7-0.9 MPa) all sit at the laser spot (202.5, 122.5, 247.5) um: physical, vapour jet.
- At t = 2.34129 us max p jumps to the argon corner cell (10, 10, 250) um (xMin wall / top), 190 um from the laser. Then T there 3400 -> 14000 K in ~7 steps, rho drops 1.78 -> 0.3, p -> 4 MPa, |U| -> 1e4 m/s. At 2.3 us this cell was calm (T 300 K, |U| 0.12 m/s).
- Heating rate there ~8-10 W, matching a single reflected ray: rayQ = 11.6 W in argon cell (30, 10, 250) um at 2.3 us.
- Cause: src/laserHeatSource/laserRayParticle.C hitWallPatch() deposits the whole remaining ray power into the wall-adjacent cell, even when it is pure gas. Side walls xMin/zMin/zMax run through the 120 um argon layer, so reflected rays hit them in gas. 20 um argon cell heat capacity ~4e-12 J/K -> thousands of K per ns.
- Not caused by Courant limits, melting loop, closure feedback (corner cell is closure-masked, vDot = 0) or the group flux limiter (steady ~30 faces before and after).
- Fix (code, not yet built): hitWallPatch deposits only if alphaFiltered >= depCutoff (metal at the wall); in gas the ray leaves the domain (wall absorbs it outside). Matches the existing comment "or simply kill the ray if the wall is outside the material".
- Next: user rebuilds src/laserHeatSource + solver, reruns the 2.6 us diagnostic.

## [2026-10-01 21:26:17] Rerun with ray-wall fix: blow-up gone; cross-section GIF
- User rebuilt liblaserHeatSource (21:13) and reran the 2.6 us diagnostic: finished, 553 s wall, no FATAL, no T floor/ceiling hits.
- max|U| peaks 354 m/s at 2.3 us at the laser spot (vapour jet), falls to 168 m/s by 2.6 us. max T 3433 K. No corner heating. dt at end 1.7e-9 s.
- Total Q deposited ~49.1 W (was ~52.5 W): ~3 W that used to be dumped into gas wall cells now leaves the domain.
- New issue: p in metal cell (202.5, 127.5, 247.5) um (alpha.aluminium 0.999, vapour ~1e-4..1e-3, T 1450-2000 K, below Tboil) falls 8.7e4 -> 1e3 Pa = pMin floor by 2.49 us and stays there. vDot = -1e4..-8e4 1/s (condensation of the trace vapour pulls volume out of a liquid cell). Not yet fixed.
- New script scripts/crosssection_gif.py (reads binary processor fields + AMR mesh directly, rasterises x-y plane through laser line and z-y plane through laser x). Output case/AL_500W_600mms_50um_bp/crosssection.gif (+ _last.png). Checked image: surface dent ~5 um, melt pool ~10 um deep at 2.6 us, hot vapour cloud above spot.

## [2026-10-01 21:50:23] Second case: laserbeamFoam (incompressible), user's choice
- User asked to try the incompressible solver (chose "whole solver: laserbeamFoam" over rhoConst metal in the compressible solver).
- Restored tutorials/laserbeamFoam/cunninghamValidation from git 0e3ee3b0^ into the scratchpad (read only, not restored into the repo).
- New case case/AL_500W_600mms_50um_bp_lbf: blockMesh, decomposeParDict, laser tables, LaserProperties, g, U/T/Laser_boundary from the compressible case; fvSchemes, fvSolution, dynamicMeshDict, turbulenceProperties from cunninghamValidation; new transportProperties (Al/argon), setFieldsDict, alpha.metal (inletOutlet on top), gauge p_rgh, controlDict (laserbeamFoam, binary, fieldMinMax), Allrun/Allclean (dashboard on log.laserbeamFoam), README.
- Conductivity key: Elec_conductivity 4e6 (elec_resistivity is deprecated, mthdModel::lookupElectricalConductivity).
- All dictionaries parse with foamDictionary. Not run (user runs).
- scripts/crosssection_gif.py: vapour field now optional (laserbeamFoam has none).

## [2026-10-01 22:16:47] Allrun scripts made resumable (both cases)
- If processor0/ (parallel) or the case folder (serial) has a saved time > 0: skip 0/ copy, blockMesh, checkMesh, setFields, decomposePar; solver continues via startFrom latestTime; old solver log renamed log.<solver>.N (no overwrite).
- Otherwise: same fresh setup as before. bash -n passes; detection tested on the running lbf case (finds 2e-05 -> would resume).

## [2026-10-01 22:30:52] Calibration knobs chosen; solid/liquid k and cp in laserbeamFoam
- User's calibration set: laserRadius, Radius_Flavour, Elec_conductivity, metal solid/liquid kappa and cp, sigma. Fixed: e_num_density, recoil factor 0.54.
- Code (laserbeamFoam, not built): createFields.H reads optional poly_kappa_solid/poly_kappa_liquid and poly_cp_solid/poly_cp_liquid (metal); if absent, poly_kappa/poly_cp as before. Blend linear in T across Tsolidus..Tliquidus (lambdas metalLiquidFraction, metalKappa, metalCp). updateKappaCp.H and the thermal damper in TEqn.H use them. Prints which mode at start-up. microstructureFoam (own copy) untouched.
- Case lbf transportProperties: pure Al solid k 248-0.0385T (237 at 300 K, 212 at 933 K), liquid k 91; solid cp 762+0.44T (894 -> 1173), liquid cp 1177. Parses.
- The running lbf case keeps the old values (constants read at start). Needs rebuild before any restart: the new keys are unknown to the old binary.

## [2026-10-01 23:15:33] lbf run stopped by user at 60 us; set up to resume with original physics
- Last save 6e-05 (depth 234 um). laserbeamFoam binary is from 19:10 (before the solid/liquid k/cp change), so transportProperties restored to single poly_kappa 91 / poly_cp 1180 for this run; solid/liquid lines kept as comments. Resume: ./Allrun (auto-resume, old log -> log.laserbeamFoam.1).
