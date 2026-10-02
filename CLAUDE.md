# LaserbeamFoam Project

LaserbeamFoam: OpenFOAM (ESI/openfoam.com) solvers for laser–metal interaction —
melting, boiling, keyholes and pores — written in C++ on top of OpenFOAM.
The ray-tracing laser follows many small rays, including reflections, and uses
the Fresnel equations to decide how much energy each surface absorbs.

Active work is on **`compressibleLaserbeamFoam`** (metal, metal vapour and
shielding gas as separate phases, with density allowed to change). The other
solvers are kept compiling, but they are not the focus.

## Principles

- **First principles**: Understand the physics before writing code. Every equation, source term and boundary condition must have a clear physical basis.
- **Occam's razor**: The simplest correct solution wins. Do not add complexity unless it is proven necessary.
- **Consistency, simplicity, and maintainability over features**: Clean, readable code is more valuable than new functionality. Match the OpenFOAM style of the surrounding code.
- **Conservation first**: Do not add clipping, limiting or "fix-ups" that break mass or energy conservation to make a run survive (see commit `e6a7311a`). Find the cause instead.

## Project Structure

```
LaserbeamFoam/
├── Allwmake / Allwclean            # Build / clean everything (src first, then applications)
├── src/                            # Shared libraries (built into $FOAM_USER_LIBBIN)
│   ├── laserHeatSource/              # Ray-tracing laser: laserHeatSource.{H,C}, laserRayParticle.{H,C}
│   ├── geometricVoF/                 # Interface reconstruction (isoAlpha, plicRDF, ...) + isoAdvection
│   ├── MTHD/                         # Magneto-thermal hydrodynamics model (mthdModel), optional
│   ├── functionObjects/meltPoolHistory/  # Melt-pool size tracking function object
│   ├── transportModels/incompressible/   # Two/three-phase mixtures + viscosity models (incompressible solvers)
│   └── turbulenceModel/
├── applications/
│   ├── solvers/
│   │   ├── compressibleLaserbeamFoam/    # MAIN SOLVER (see below)
│   │   ├── laserbeamFoam/                # Incompressible two-phase version (MULES / isoAdvector)
│   │   ├── laserMeltFoam/
│   │   └── microstructureFoam/
│   └── utilities/
│       ├── setSolidFraction/             # Sets initial metal fraction from a powder-particle "locations" file (e.g. LIGGGHTS); -compressible flag
│       └── TesselateFoam/
├── tutorials/
│   ├── Allclean, Alltest               # Alltest = CI smoke test (1 time step per case)
│   └── compressiblelaserbeamFoam/      # Only tutorial set kept (others removed)
│       ├── LPBF_small_vapour/            # Main case: laser on a plate with vapour
│       ├── multiComponentLaserIrradiation/
│       ├── multiComponentliquidboiling/
│       └── multiComponentVapourCondensation/
├── toolbox/
│   └── rundash.py                      # Live terminal dashboard for a running case (reads the log only)
├── documentation/LaserbeamFoam___V2.pdf  # Solver write-up
├── .github/workflows/build.yml          # CI: Allwmake + tutorials/Alltest in opencfd/openfoam-dev:2506
└── project/                             # Research tasks (one folder per project; NOT in git, see below)
```

### `compressibleLaserbeamFoam` layout

Split-header OpenFOAM style. Keep it that way.

| File | Role |
|---|---|
| `compressibleLaserbeamFoam.C` | Time loop (semi-PIMPLE, see below) |
| `createFields.H` | All fields, laser object, MTHD model, restart flags |
| `update.H` | Property updates after the phase-change step |
| `UEqn.H` / `pEqn.H` / `TEqn.H` | Momentum / pressure / energy |
| `VoF/` | Phase-fraction equations, alpha Courant number, time-step control |
| `setDeltaT_.H`, `readMeltingControls.H` | Extra time-step limits for melting |
| `writeOldTimeStorage.H` | Writes old-time fields so a restart continues exactly |
| `multiphaseMixtureThermo/` | N-phase thermo mixture + phase change. Builds **`libmultiphaseVapMixtureThermo`**. Built by the solver's own `Allwmake` before the solver. |

Time-step order (per step):
1. First PIMPLE iteration only: `mixture.solve()` (phase change: `mass_dot`, `vDot`), then `update.H`.
2. First PIMPLE iteration only: `laser.updateDeposition(...)` — ray tracing is expensive, run once per step.
3. `UEqn.H` → optional `mthd->solve()` → `TEqn.H` → `pEqn.H` corrector loop → turbulence.
4. `mixture.writeOldTimeValues()` + `writeOldTimeStorage.H`, then write fields and ray-path VTKs.

**Restart rule:** anything that carries state from one step to the next must be written to disk and read back on restart (see commit `369ec6cc`, `bRestartFirstLoop`). If you add such a field, add it to `writeOldTimeStorage.H` and to the restart read in `createFields.H`.

## Build & Run

> **RULE — never compile or run the solver yourself.**
> Claude must **never** execute `Allwmake`, `Allwclean`, `wmake`, `wclean`,
> `Allrun`, `Allclean`, `Alltest`, `blockMesh`, `setSolidFraction`,
> `decomposePar`, `mpirun`, or any solver binary (`compressibleLaserbeamFoam`,
> `laserbeamFoam`, ...) — not in the foreground, not in the background, not
> inside a wrapper script, and not "just to check". This holds even when the
> user has approved the code change; approving a change is **not** approval to
> build or run.
>
> Instead: make the edit, then **print the exact commands** for the user to run,
> and stop. Write helper scripts to disk (e.g. `project/NN_*/scripts/*.sh`) and
> hand over the one-line command — do not launch them.
>
> Reading and analysing existing output (`log.*`, time folders, `postProcessing/`,
> `VTKs/`) is always fine, and is the preferred way to answer a question before
> proposing a new run.

Supported OpenFOAM versions: **v2412, v2506, v2512** (checked in `Allwmake`).
Local install: `/usr/lib/openfoam/openfoam2512`, loaded with the shell alias `of2512`.

```bash
# Load OpenFOAM (every new shell)
of2512        # = source /usr/lib/openfoam/openfoam2512/etc/bashrc

# Build everything (libraries, then solvers and utilities)
./Allwmake -j

# Rebuild only the compressible solver (and its mixture library)
(cd applications/solvers/compressibleLaserbeamFoam && ./Allwmake)

# Clean build + tutorials
./Allwclean

# Run a tutorial
cd tutorials/compressiblelaserbeamFoam/LPBF_small_vapour
./Allrun      # copies initial/ to 0/, blockMesh, setSolidFraction, transformPoints, solver
./Allclean

# Smoke test all tutorials (1 time step each, copied into ../tutorialsTest)
cd tutorials && ./Alltest
```

Build errors are collected in `log.Allwmake` files (`src/`, `applications/`).

## Live run dashboard — `toolbox/rundash.py`

Follows `log.compressibleLaserbeamFoam` (read-only) and redraws one screen:
progress and finish estimate, laser power/absorption, fields (max U, p_rgh,
min T), phase masses and drift, cell count (AMR), residuals, T solves per step,
warnings/errors. Uses `rich` (Python terminal-layout library) when installed and
the output is a terminal; otherwise one plain status line per refresh.

```bash
python3 toolbox/rundash.py -c <case>            # watch a running case
python3 toolbox/rundash.py -c <case> --once     # one snapshot
python3 toolbox/rundash.py --pid <PID>          # exit when that process exits
```

Case `Allrun` scripts start the solver in the background (output to the log
only) and call the dashboard with `--pid`. Ctrl+C stops the solver.
`LBF_DASH=0 ./Allrun` gives the plain full output instead. The dashboard must
never be able to stop a run: call it with `|| echo ...` and `wait` for the
solver afterwards. New `Allrun` scripts should reuse it, not copy a progress display.

## Case Setup (compressible solver)

| File | What it sets |
|---|---|
| `constant/thermophysicalProperties` | `phases (metal1 metal1vapour air)`, surface tension `sigmas`, `dsigmadT` (Marangoni), boiling temperature `boils`, `LatentHeatGas`, interface compression |
| `constant/thermophysicalProperties.<phase>` | OpenFOAM `thermoType` + `mixture`, plus `TSolidus`, `TLiquidus`, `LatentHeat`, electrical/magnetic properties |
| `constant/LaserProperties` | Beam radius, direction `V_incident`, wavelength, `N_sub_divisions` (N×N rays per cell), electron density for Fresnel absorption |
| `constant/timeVsLaserPosition`, `timeVsLaserPower` | Laser path and power over time |
| `constant/dynamicMeshDict` | Adaptive mesh refinement |
| `initial/` | Initial fields; `Allrun` copies it to `0/` |

Check that `endTime` in `system/controlDict` matches the end of `timeVsLaserPosition` before any run.

**Vapour naming rule:** the vapour of a metal phase must be named
`<metal>vapour`, lower-case (e.g. `aluminium` → `aluminiumvapour`). The solver
finds each evaporation pair by that name (`multiphaseMixtureThermo.C`,
`vapName = liq.name() + "vapour"`). Any other spelling gives no evaporation, with
no error. Check the log: the line `Phase-change pairs:` must list the pair.

## Projects & Validation Work

- Each project: `project/NN_<name>/` (e.g. `project/01_Al_keyholePore_validation/`), where `NN` is the next number, zero-padded to 2 digits, never reused.
- `task.md`: objective, numbered tasks, notes. Every code change made for the project is recorded here.
- `log.md`: every step with **system timestamps** (e.g. `[2026-10-01 14:23:05]`): commands, errors, decisions.
- `results.md`: final results and comparison with experiment.
- Reference papers go in `project/NN_*/reference_paper/<author><year>/`, renamed `<author><year>_<short_topic>.pdf`. Data taken from a paper for one case goes in its own folder with `README.md`, `video/`, `data/`, `plots/` and the script that made them (see `reference_paper/huang2022/AL_500W_600mms_50um_bp/`).
- **Git warning:** the `.gitignore` rule `0*` (meant for OpenFOAM time folders) also matches `project/01_*`, so project folders are silently untracked. Do not "fix" this by force-adding without asking the user.

Python for analysis: `~/.venv/venv312/bin/python` (numpy, scipy, matplotlib, pillow, imageio-ffmpeg; ffmpeg binary comes from `imageio_ffmpeg.get_ffmpeg_exe()`). System `python3` has no pip.

**Check results by looking at them.** After a run, plot or render the fields the task touched (temperature, `alpha.*`, melt-pool shape, keyhole), read the images, and confirm they are physical **before** reporting numbers.

## Language

- **Terminal replies**: plain, simple English, short and organised. This is a hard rule (see the user's global `CLAUDE.md`):
    - Use the everyday word ("the run", "the settings file", "checked", "wrong").
    - Explain every project-specific term the first time it appears in a reply, in one short bracket, e.g. "keyhole (= the deep vapour-filled hole the laser drills into the melt)".
    - No stacked-up noun phrases. Short sentences, one idea each.
- **"What's the problem" questions**: answer with three short headings — **Context**, **The problem**, **Proposed solution**.
- **Everything on disk** (code comments, commit messages, `.md` files, logs, reports) is in English. Precise technical terms are fine there, but say what each means the first time it is used in a file.

## Code Conventions

- New runtime-selectable class (e.g. a viscosity model): `TypeName("...")` in the header, `addToRunTimeSelectionTable(...)` in the source, and the dictionary `type` string must match the registered name.
- Keep the split-header solver layout (`createFields.H`, `UEqn.H`, `pEqn.H`, `TEqn.H`, `update.H`, ...).
- Ray-tracing and deposition logic belongs in `src/laserHeatSource`, not in solver loops.
- Do not put solver-specific logic into `src/geometricVoF`.
- New source file → add it to the module's `Make/files`; new include path or library → `Make/options`.
- Do not change dictionary keywords or their meaning silently. If a case-file interface changes, update every tutorial that uses it and say so.
- Do not reformat unrelated code. Do not change license header blocks.
- Prefer editing existing files over creating new ones.
- Commit or push only when the user asks. Branch off `OpenFoam_com_main` for new work.
- All generated HTML reports use Arial: `font-family: Arial, Helvetica, sans-serif`.
