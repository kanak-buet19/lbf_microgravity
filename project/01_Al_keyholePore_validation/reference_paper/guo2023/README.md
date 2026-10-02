# Guo et al. 2023: simulation set-up

Source: L. Guo et al., "Understanding keyhole induced-porosities in laser powder bed
fusion of aluminum and elimination strategy", Int. J. Mach. Tools Manuf. 184 (2023)
103977 (`guo2023_keyhole_porosity_LPBF_aluminium.pdf`).

They simulate the same case as Huang et al. 2022, Supplementary Movie 4:
pure Al, 500 W, 0.6 m/s, 50 µm spot (see
`../huang2022/AL_500W_600mms_50um_bp/`). Their Section 3 says the parameters
match Huang's experiment.

## Domain (Fig. 1)

| Part | Size |
|---|---|
| Length along scan (x) | 1800 µm |
| Width (y) | 270 µm, half of the track only (symmetry plane at y = 0) |
| Height (z) | 900 µm total: 750 µm metal base + 30 µm powder layer + 120 µm void (empty gas region) on top |

Full track width is 540 µm. Powder particles are 22–50 µm, packed with PFC
(Particle Flow Code) software (Fig. 2).

## Mesh and time step (Section 2.3)

| Item | Value |
|---|---|
| Cells | Uniform cubes, 6 µm (no refinement), chosen after a mesh study |
| Cell count (my estimate) | 300 × 45 × 150 ≈ 2.0 million |
| Time step | ~0.068 µs (set by stability, checked with a time-step study) |
| Output interval | 1 µs |
| Software | FLOW-3D v11.2 |

The mesh and time-step study details are in their supplementary Table s2. That file
is not in this folder.

## Boundary conditions (Fig. 1, Eqs. 13–18)

| Face | Condition |
|---|---|
| Front x–z plane (y = 0, laser path) | Symmetry |
| Left end (x = 0) | "Continuative" (zero gradient: flow and heat leave freely) |
| Bottom | Heat loss by convection + radiation |
| Top | Void at 1 atm and 298 K (gas not solved) |
| Metal free surface | Laser flux + convection + radiation + evaporation loss; recoil pressure and surface tension in the pressure condition |
| Other walls | Convection + radiation only |

## Physics model (Section 2)

- Incompressible Newtonian liquid metal; VOF (volume of fluid) free surface.
- **No ray tracing.** Laser = Gaussian surface heat flux,
  q = (3PA/πr²) exp(−3(x²+y²)/r²), with fixed absorption **A = 0.7**.
- **Vapour and shielding gas are not modelled.** Only their effect is included,
  through the recoil pressure (Clausius–Clapeyron with an ambient-pressure surface
  model, Eq. 10).
- Melting: enthalpy method with a liquid fraction. Mushy zone drag: Darcy-type
  (Eqs. 11–12).
- Temperature-dependent properties from JMatPro software (Fig. 3; plotted, no table).

## Table 1 values

| Property | Value |
|---|---|
| Evaporation coefficient α | 0.01 |
| Latent heat of vaporisation L_v | 1.077e7 J/kg |
| Gas constant R | 308 J/(kg·K) |
| Ambient pressure | 101 300 Pa |
| Convective heat transfer h_c | 80 W/(m²·K) |
| Reference temperature | 298 K |
| Emissivity ε | 0.36 |
| Boiling temperature T_b | 2750 K |
| Melting temperature | 933 K |
| Laser absorption | 0.7 |
| Recondensation coefficient β_R | 0.5795 |
| Mushy zone characteristic length λ1 | 5 µm |

## Comparison with Huang (Fig. 4)

| Source | Keyhole depth |
|---|---|
| Huang X-ray at 1.08 ms (their Fig. 4a) | 506 µm |
| My measurement from Movie 4 at 1080 µs | 510 µm |
| My mean over the whole movie | 563 ± 37 µm |
| Guo simulation (Fig. 4c) | 554 µm |

They report that a pore takes about 40 µs to form, matching the X-ray.

## Not stated in the paper

- Whether the 30 µm powder layer was removed for the bare-plate case. Fig. 4 shows
  a bare plate, so probably yes.
- How long the simulated track was.

## How it differs from LaserbeamFoam

- LaserbeamFoam follows the laser as rays and uses Fresnel absorption instead of a
  fixed 0.7.
- `compressibleLaserbeamFoam` solves the metal vapour and the gas as real phases.
- The Huang experiment uses a 0.5 mm thick plate between glassy carbon walls. Guo
  models half a wide plate with a symmetry plane, not the walls.
