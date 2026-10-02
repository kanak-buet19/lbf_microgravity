# lbf_microgravity

Laser–metal melting, keyhole and pore simulations in OpenFOAM, and the tools
to check them against X-ray experiments and calibrate them automatically.

Built on the [LaserbeamFoam](https://github.com/laserbeamfoam/LaserbeamFoam)
solvers (Flint, Robson, Cardiff, Parivendhan et al.). This repository is a
working copy with fixes and new tooling; see [What is new here](#what-is-new-here).

## Solvers

| Solver | What it models |
|---|---|
| `laserbeamFoam` | Metal + shielding gas, both incompressible (volume of fluid). Melting and solidification, surface tension and Marangoni flow, buoyancy. Evaporation as a recoil pressure 0.54·P_sat(T) and evaporative cooling. Used for the calibration. |
| `compressibleLaserbeamFoam` | Metal, metal vapour and gas as separate compressible phases. Evaporation and condensation by Hertz–Knudsen mass transfer; recoil comes from the vapour volume made. |
| `laserMeltFoam` | Port of the PBFSolvers melt-pool solver. |
| `microstructureFoam` | `laserbeamFoam` flow + a phase-field model for grain growth. |

All solvers share the ray-tracing laser in `src/laserHeatSource`: the beam is
split into rays that are followed through every reflection, and the Fresnel
equations (Drude model) set how much each hit absorbs.

## What is new here

- **Ray fix.** A ray that hits a wall now leaves its remaining power only in a
  metal cell. Before, a reflected ray could put ~10 W into one gas cell at a
  side wall, heat it to 10⁴ K and blow the run up.
- **Melting-loop fix** (`compressibleLaserbeamFoam`). The liquid-fraction loop
  now converges in a few passes instead of always hitting its limit.
- **Solid and liquid properties** (`laserbeamFoam`). Optional
  `poly_kappa_solid` / `poly_kappa_liquid` and `poly_cp_solid` /
  `poly_cp_liquid`, mixed linearly across the melting range. Old single
  `poly_kappa` / `poly_cp` inputs still work.
- **Live run dashboard** (`toolbox/rundash.py`): one terminal screen with
  progress, laser absorption, fields, phase masses, residuals and warnings.
- **Validation and calibration projects** in `project/` (below).

## Build

Needs OpenFOAM v2412, v2506 or v2512 (openfoam.com).

```bash
source /usr/lib/openfoam/openfoam2512/etc/bashrc
./Allwmake -j
```

## Projects

| Folder | Contents |
|---|---|
| `project/01_Al_keyholePore_validation` | Huang et al. 2022 (Nat. Commun.) X-ray experiment: pure Al plate, 500 W, 0.6 m/s, 50 µm spot. Cases for both solvers, depth / keyhole-length / pore data measured from the X-ray movie, Guo et al. 2023 notes. |
| `project/02_terminal_run_dashboard` | Notes for `toolbox/rundash.py`. |
| `project/03_surrogate_calibration` | Unattended calibration of `laserbeamFoam` against the Huang data (see below). |

Each project has `task.md` (plan, decisions, code changes) and `log.md`
(timestamped log of every step).

### Unattended calibration (`project/03_surrogate_calibration`)

Start once, come back to calibrated values:

```bash
tmux new -s calib
source /usr/lib/openfoam/openfoam2512/etc/bashrc
cd project/03_surrogate_calibration
./run_calibration.sh --dry      # check: shows the jobs it would start
./run_calibration.sh            # Ctrl+B, D to leave it running
```

- Runs up to 8 cases × 8 cores at once on the adaptive mesh (10 µm cells at
  the surface; 5 µm with one setting).
- Measures each run like the X-ray camera (side view, 1.96 µm pixels, every
  20 µs) and stops it once the keyhole depth is steady.
- A Gaussian-process surrogate learns from every finished run, estimates the
  7 knobs (beam radius, electrical conductivity, solid/liquid conductivity
  and heat capacity, surface tension) with uncertainties, and picks the next
  runs.
- Handles crashes, NaN and stalled runs, resumes after a restart, backs up its
  state, and stops by itself (converged, 7 days or 50 runs).
- Progress: open `dashboard.html`. Result: `results.md`.
- Sets up its own Python environment (`.venv`) on first start.

Settings are in `config.json`; details in the project `README.md`.

## Running a single case

```bash
cd project/01_Al_keyholePore_validation/case/AL_500W_600mms_50um_bp_lbf
./Allrun          # 8 cores, live dashboard; resumes from the last write if stopped
./Allclean        # wipe all results
```

Keyhole depth, pores and an X-ray-style movie from any case:

```bash
python project/03_surrogate_calibration/scripts/keyhole_depth.py <case> --images
```

## Tutorials

`tutorials/compressiblelaserbeamFoam/`: laser on a plate with vapour
(`LPBF_small_vapour`), multi-component irradiation, boiling and condensation.
Each has `Allrun` / `Allclean`; `tutorials/Alltest` runs one step of each.

## Documentation

`documentation/LaserbeamFoam___V2.pdf`: solver write-up from the original
LaserbeamFoam authors.

## License and credits

GPL v3, like OpenFOAM (see `LICENSE`). The solvers are from
[LaserbeamFoam](https://github.com/laserbeamfoam/LaserbeamFoam) by Tom Flint,
Joe Robson, Philip Cardiff, Gowthaman Parivendhan and co-authors; please cite
their work when using them. Experimental data: Huang et al., *Nat. Commun.* 13:1170 (2022),
doi:10.1038/s41467-022-28694-x. Comparison simulations: Guo et al.,
*Int. J. Mach. Tools Manuf.* 184:103977 (2023).
