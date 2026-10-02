# 01 — Al keyhole pore validation

## Objective

Check `compressibleLaserbeamFoam` against the in situ X-ray experiment of
Huang et al. 2022 (Nat. Commun. 13:1170): pure aluminium bare plate, 500 W,
0.6 m/s, 50 µm spot (Supplementary Movie 4). Targets: keyhole depth, keyhole
length along the scan, fluctuation periods, and pore size and position.
Guo et al. 2023 simulated the same case in FLOW-3D and is the reference for the
simulation set-up.

## Tasks

1. [x] Collect reference papers into `reference_paper/` and rename them
   `<author><year>_<topic>.pdf`.
2. [x] Convert Huang Supplementary Movie 4 (old MPEG-4 Part 2 codec) to GIF.
3. [x] Extract set-up and target values for the case from the Huang paper.
4. [x] Measure keyhole depth, length along scan, mouth length and final pores
   from Movie 4 (`measure_keyhole.py`), save CSVs and plots.
5. [x] Extract the Guo 2023 domain, mesh, boundary conditions and model
   (`reference_paper/guo2023/README.md`).
6. [ ] Get the Huang Supplementary Information PDF (MOESM1, Supplementary
   Table 3: material properties) and the Guo supplementary (Table s2: laser
   and mesh-study parameters).
7. [x] Set up the simulation case in `case/AL_500W_600mms_50um_bp/` (domain,
   mesh, aluminium properties, laser path and power). See its `README.md`.
   Not yet run.
8. [x] Fix the slow melting loop (21 T solves per step). Solver fix in
   `TEqn.H` (melt-fraction update coefficient) + case T `minIter 1`,
   `nSweeps 2`. Now converges in 7–10 passes; 14 % faster to t = 5 µs.
9. [ ] Profile one time step to find the main cost (pressure solves,
   phase change, ray tracing, AMR).
10. [ ] Run (by the user) and compare with the targets in `results.md`.

## Notes

- "Width" in the Huang paper is the keyhole size along the scan direction
  (side view). Here it is called **length**. Mouth length = length at the top
  of the keyhole.
- Huang sample is a 0.5 mm thick plate between glassy carbon walls. Guo uses
  half a wide plate with a symmetry plane instead.
- Guo uses a fixed absorption of 0.7 and no vapour phase. LaserbeamFoam uses ray
  tracing with Fresnel absorption and solves the vapour.
- The `.gitignore` rule `0*` also matches `project/01_*`, so this folder is not
  tracked by git.

## Code changes

- `applications/solvers/compressibleLaserbeamFoam/TEqn.H`: melt-fraction update
  coefficient changed from `epsilonRel*Cv/L_metal` to
  `epsilonRel/max(dTmush + meltMask*LatentHeat/Cv, 1e-3 K)`, so the MELTING loop
  error shrinks by `1 − epsilonRelaxation` per pass in every cell (old one crept
  ×0.98 per pass in part-metal interface cells). Unused `LatentHeatCond` removed.
  Affects every compressible case.
- Analysis code:
`reference_paper/huang2022/AL_500W_600mms_50um_bp/measure_keyhole.py`.
Case `fvSolution`: own `T`/`TFinal` solver entries (minIter 1, nSweeps 2, tol 1e-8);
MELTING epsilonTolerance 1e-5, maxTempCorrector 10 (melting-loop fix).
Case files: `case/AL_500W_600mms_50um_bp/` (new, built from the
`LPBF_small_vapour` and `multiComponentLaserIrradiation` tutorials).

- `src/laserHeatSource/laserRayParticle.C` `hitWallPatch()`: a ray hitting a wall deposits its remaining power only if the wall cell holds metal (alphaFiltered >= depCutoff). In gas it now leaves the domain. Before, it dumped ~10 W into a 20 um argon cell at the side wall and blew the run up at 2.34 us.
- `applications/solvers/laserbeamFoam/createFields.H`, `updateKappaCp.H`, `TEqn.H`: optional separate solid/liquid metal conductivity and heat capacity (`poly_kappa_solid`, `poly_kappa_liquid`, `poly_cp_solid`, `poly_cp_liquid`), blended linearly in T across the mushy zone. Old single `poly_kappa`/`poly_cp` still works.

## Calibration knobs (user's choice)

Calibrate: `laserRadius`, `Radius_Flavour`, `Elec_conductivity`, metal solid/liquid `kappa` and `cp`, `sigma`.
Fixed: `e_num_density` (1.81e29), recoil factor 0.54 (hard-coded in `UEqn.H`).
