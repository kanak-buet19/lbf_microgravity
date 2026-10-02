# Case: Al bare plate, 500 W, 0.6 m/s, 50 µm spot

`compressibleLaserbeamFoam` set-up of Huang et al. 2022, Supplementary Movie 4.
Targets to compare against: `../../reference_paper/huang2022/AL_500W_600mms_50um_bp/README.md`.

Built from `tutorials/compressiblelaserbeamFoam/LPBF_small_vapour` (numerics)
and `multiComponentLaserIrradiation` (bare plate, no rotation). Not yet run.

## Run

```bash
of2512                    # load OpenFOAM v2512
./Allrun                  # parallel, 8 cores, scotch (default)
./Allrun -serial          # serial
./Allclean
```

For a quick test, set `maxRefinement 1;` in `constant/dynamicMeshDict`
(finest cells 10 µm) and lower `endTime` in `system/controlDict`.

## Geometry and mesh

Axes are fixed by the ray-tracing code: the beam travels along +y, and the beam
position is given in the x–z plane.

| Axis | Meaning | Size |
|---|---|---|
| x | scan direction | 1500 µm |
| y | depth (+y into the metal, gravity +y) | 120 µm argon + 900 µm Al = 1020 µm |
| z | across the plate | 500 µm (the plate thickness in the experiment) |

- **Adaptive mesh refinement (AMR)**, `constant/dynamicMeshDict`: base 20 µm cubes
  (75 × 51 × 25 = 95,625 cells), split twice to **5 µm** where the solver's
  `refineIndicator` is high: the band around the metal surface, metal vapour, and
  cells where gas and metal mix (keyhole, bubbles). Settings copied from
  `multiComponentLaserIrradiation`.
- Finest cells (5 µm) are finer than Guo et al. 2023 (uniform 6 µm). A uniform
  5 µm mesh would be ~6.1 M cells.
- The whole flat plate top is refined from the start, so expect roughly 1 M cells,
  not 0.1 M.
- The melt pool interior (away from any surface) stays at 20 µm. Melt flow and the
  solidification front are resolved more coarsely than the keyhole.
- No load balancing in parallel: refined cells gather along the laser path, so
  some processors will do more work than others.
- Two blocks in y so the plate top lies on a cell face for any `dx`.
- Full plate width is modelled. The rays have no symmetry-plane handling, so half
  the width with a symmetry plane is not safe.

| Patch | Type | Meaning |
|---|---|---|
| `top` | patch | Open to the argon chamber. Laser enters here. `totalPressure` 1.11325e5 Pa |
| `zMin`, `zMax` | wall | Glassy carbon plates holding the sample (no-slip, adiabatic) |
| `xMin`, `xMax`, `bottom` | wall | Cut-off ends of the plate (no-slip, adiabatic) |

## Laser

| Item | Value | Source |
|---|---|---|
| Power | 500 W (ramped 0→500 W over 1 µs) | Huang |
| Scan | +x at 0.6 m/s, x = 200 → 1100 µm, z = 250 µm | Huang |
| Spot | 50 µm diameter → `laserRadius 25e-6` (1/e² radius) | Huang (definition not stated) |
| Wavelength | 1070 nm | Huang, Methods |
| Absorptivity | computed per ray (Fresnel, Drude model) from `e_num_density` and `elec_conductivity` | — |
| Ray seeding | polar disc, 20 × 36 = 720 rays | — |
| Run time | 1.5 ms, written every 20 µs (= one X-ray frame) | — |

## Materials

Huang et al. Supplementary Table 3 was not available, so these are typical
literature values. Check them before the production run.

| Aluminium | Value |
|---|---|
| Density (liquid, at melting) | 2380 kg/m³ |
| Cp | 1180 J/(kg K) |
| Viscosity | 1.3e-3 Pa s |
| Thermal conductivity | 91 W/(m K) via Pr = 0.01686 |
| Melting | 921–946 K band around 933.5 K; latent heat 3.97e5 J/kg |
| Boiling | 2743 K at 1 atm; latent heat 1.08e7 J/kg; M = 26.98 g/mol |
| Surface tension | 0.914 N/m, dσ/dT = −3.5e-4 N/(m K) |
| Electrical conductivity | 4.0e6 S/m (liquid) |
| Free-electron density | 1.81e29 m⁻³ |

| Gas | Model |
|---|---|
| Argon | ideal gas, M = 39.95, Cp = 520, μ = 2.27e-5, Pr = 0.67 |
| Al vapour | ideal monatomic gas, M = 26.98, Cv = 462, μ = 1e-5, Pr = 1 |

Ambient pressure 1.11325e5 Pa (1 atm + 10 kPa argon over-pressure, Huang Methods).
`P0 = 1.01325e5` is only the reference pressure of the boiling point.

## Known simplifications

1. **One conductivity for solid and liquid.** k = 91 (liquid). Solid Al near
   melting is ~210 W/(m K), so heat leaves the melt pool too slowly: expect the
   pool to be too big. The `const` transport model cannot change k with phase.
2. **One surface tension value** (at the melting point). The keyhole wall is near
   boiling, where real σ is lower, so the keyhole walls are held a bit too strongly.
3. **Soft liquid.** `adiabaticPerfectFluid` with B = 1e7 Pa, γ = 1.2 gives a sound
   speed of ~70 m/s instead of ~4.6 km/s, as in the tutorial. This keeps the time
   step usable. Melt speeds are ~1–5 m/s, so the Mach number stays below ~0.1.
4. **Vapour is a real ideal gas** (ρ ≈ 0.12 kg/m³ at boiling). The tutorial instead
   uses `perfectFluid` with ρ0 = 5 kg/m³, which is heavier and may be easier to run.
   If the vapour causes instability, try the tutorial form.
5. **Condensation slowed** (`accommodationCoeffCond 0.05`, as in
   `multiComponentLaserIrradiation`). Bubble shrinkage by condensation is one of the
   things Huang measured, so this value matters for pore size.
6. **Plate ends and bottom are walls.** The real plate is 46 × 17 mm. The domain
   is cut at 1.5 mm × 0.9 mm metal depth.

## What to compare after the run

- Keyhole depth vs time (target mean 563 ± 37 µm).
- Keyhole length along the scan, at the mouth and vs depth (target ~32 µm mouth,
  neck ~25 µm at ~470 µm depth, bulb ~35 µm at 510–550 µm).
- Depth fluctuation period (~200 µs in the paper).
- Pore count, size (median ~15 µm) and depth (450–650 µm).
