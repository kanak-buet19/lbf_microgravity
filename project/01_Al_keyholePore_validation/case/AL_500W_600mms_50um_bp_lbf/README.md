# Case: Al bare plate, 500 W, 0.6 m/s, 50 µm spot — laserbeamFoam

Same experiment, geometry, mesh, laser and materials as
`../AL_500W_600mms_50um_bp/` (compressibleLaserbeamFoam), but run with the
incompressible two-phase solver `laserbeamFoam`. Targets:
`../../reference_paper/huang2022/AL_500W_600mms_50um_bp/README.md`.

Built from the old `tutorials/laserbeamFoam/cunninghamValidation` (numerics,
AMR, BC style; restored from git `0e3ee3b0^`) plus the compressible case
(mesh, laser, materials).

## Run

```bash
of2512
./Allrun            # parallel, 8 cores, scotch; dashboard on log.laserbeamFoam
./Allrun -serial
./Allclean
```

Cross-section GIF afterwards (from the project folder):
```bash
~/.venv/venv312/bin/python scripts/crosssection_gif.py case/AL_500W_600mms_50um_bp_lbf --metal metal --xwin 100e-6 --depth 300e-6
```

## Differences from the compressible case

| Item | compressible case | this case |
|---|---|---|
| Phases | aluminium, aluminiumvapour, argon | `metal` (Al), `gas` (argon); the solver needs the name `metal` |
| Density | Al soft-compressible (B = 1e7), gases ideal | constant: Al 2380, argon 1.78 kg/m³ |
| Evaporation | Hertz–Knudsen mass transfer into a vapour phase; recoil emerges from the volume source | no vapour phase; recoil = 0.54·Psat(T) as a surface force; evaporative cooling 0.82·Lv·Psat·√(M/2πRT) |
| Pressure | absolute, top totalPressure 1.11325e5 Pa | gauge, top totalPressure 0 |
| AMR indicator | `refineIndicator` | `alpha_smoothed`, 0.001–0.999 (interface band only), every 10 steps |
| Buoyancy | from density | Boussinesq, beta 1.5e-4 1/K (Al), 3.3e-3 (argon) |
| Time step | maxCo 0.05 | maxCo 0.25, maxAlphaCo 0.25 (tutorial) |

Unchanged: domain 1500 × 1020 × 500 µm, base 20 µm cells, 2 AMR levels → 5 µm,
walls at sides/bottom, laser tables and `LaserProperties` (Fresnel absorption,
720 rays), Al properties (k = 91 W/(m K) liquid value for all metal, Cp 1180,
mu 1.3e-3, sigma 0.914, dsigma/dT −3.5e-4, Tboil 2743 K, Lv 1.08e7 J/kg).

## Known simplifications

1. No vapour or pores filled with vapour: a pore is argon (incompressible), so
   it cannot shrink by condensation or expand with temperature.
2. Recoil factor 0.54 is the evaporation-into-vacuum (Anisimov/Knight) value;
   at 1.1 atm the real recoil is lower near the boiling point.
3. Conductivity is one polynomial in T, blended by alpha (no solid/liquid
   jump), same as the compressible case.
