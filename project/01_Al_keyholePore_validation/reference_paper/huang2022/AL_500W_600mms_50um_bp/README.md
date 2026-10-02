# Validation case: Al bare plate, 500 W, 0.6 m/s, 50 µm spot

Source: Huang et al., Nat. Commun. 13:1170 (2022), doi:10.1038/s41467-022-28694-x
(`../huang2022_keyhole_fluctuation_pore_formation_LPBF.pdf`).
This case is Supplementary Movie 4 (segmented); Movie 3 is the raw X-ray of the same run.

"bp" = bare plate (no powder layer).

## Folder layout

| Path | What it is |
|---|---|
| `video/AL_500W_600mms_50um_bp.mp4` | Supplementary Movie 4 as downloaded (was `v4.mp4`). Old MPEG-4 Part 2 codec: play in VLC. |
| `video/AL_500W_600mms_50um_bp.gif` | Same movie as a GIF, plays anywhere. |
| `measure_keyhole.py` | Reads the movie and writes everything in `data/` and `plots/`. |
| `data/keyhole_vs_time.csv` | Depth, mouth length, median and max length, tip position, pore count for each frame. |
| `data/length_vs_depth.csv` | Keyhole length along scan at each depth (20 µm bins), over all frames. |
| `data/length_vs_normdepth.csv` | Same, with depth scaled by each frame's keyhole depth. |
| `data/pores_final.csv` | Size and position of pores left in the last frame. |
| `plots/keyhole_vs_time.png` | Depth and mouth length over time, and final pore map. |
| `plots/keyhole_shape.png` | Average keyhole shape (length along scan vs depth). |

Rebuild with: `~/.venv/venv312/bin/python measure_keyhole.py`

## Words used here

The movie is a side view. Horizontal in the image = scan direction. So:

- **Depth**: from the plate top surface down to the keyhole tip.
- **Length**: horizontal size of the keyhole in the image, i.e. along the scan
  direction. The paper calls this "width".
- **Mouth length**: length at the top of the keyhole (top 3 pixel rows, ~6 µm
  below the surface).
- The true **width** (across the track) lies along the X-ray beam and cannot be
  seen in this movie.

## 1. Set-up (from the paper text)

| Item | Value | Where |
|---|---|---|
| Material | Pure aluminium, 99.99 % (Goodfellow) | Methods |
| Sample | 46 × 17 × 0.5 mm plate, held between two 1 mm glassy carbon plates | Table 1, Methods |
| Powder | none (bare plate) | Movie 4 |
| Laser | CW Yb fibre, 1070 ± 10 nm, max 520 W (IPG YLR-500-AC) | Methods |
| Laser power | 500 W | Movie 4 |
| Scan speed | 0.6 m/s | Movie 4 |
| Spot size | 50 µm diameter (1/e² or not is not stated) | Table 1 |
| Track length | 5 mm | Table 1 |
| Atmosphere | argon, +10 kPa above ambient | Methods |
| AED = P/(v·d) | 16.7 MJ/m² (paper rounds to 17) | text |
| Keyhole regime | III, unstable: pores form at the keyhole bottom | Fig. 1, text |
| Imaging | 1.96 µm/pixel, 50 kHz (20 µs/frame), field of view 1 × 1.33 mm | Methods |

The plate is only 0.5 mm thick in the X-ray direction, and the glassy carbon walls
hold the melt in. A simulation of a thick block of metal is not the same set-up.

## 2. Material values quoted in the paper

| Item | Value |
|---|---|
| Absorptivity at room temperature | ~0.15 |
| Brewster angle | ~85° |
| Enthalpy at melting h_m = ρ c T_l | 2.63 J/mm³ |
| Liquidus temperature T_l | 933.5 K |
| Evaporation temperature T_v | 2753.15 K |
| Latent heat of evaporation | 293.4 kJ/mol, L_v = 1.02e7 J/kg |
| Vapour density (as used in their bubble model) | 1850 kg/m³ |
| H diffusivity in liquid Al | 1.0943e-7 m²/s at T_l, 1.1302e-5 m²/s at T_v |

The full property table is Supplementary Table 3, in the Supplementary Information
PDF (MOESM1). That file is **not** in this folder. `../supplementary/` only has
MOESM3, which is the list of movies.

## 3. Values read from the paper's figures (open circles = Al bare plate)

Normalised enthalpy product ΔH/h_m·L*_th = βP/(h_m √π v r²) ≈ 43 for β = 0.15.
This is the rightmost Al bare-plate point in Figs. 1b and 2. Read by eye, so
± one marker size.

| Quantity | Value | Figure |
|---|---|---|
| Front keyhole wall angle | ~87–88° (paper fit θ = atan[0.29·(x − 0.2)] gives ~85°) | Fig. 1b |
| Keyhole length ("width") fluctuation period | ~340 ± 50 µs (~2.9 kHz) | Fig. 2b |
| Keyhole depth fluctuation period | ~200 µs (~5 kHz) | Fig. 2c |
| Area porosity | ~0.9 % | Fig. 2d |
| Pore location | keyhole bottom (regime III) | text, Supp. Fig. 7 |
| Bubble behaviour | fast growth (~3–5 µs), then shrinks, size steady after ~50–150 µs | Figs. 3–4, text |

## 4. Values measured from the movie (`measure_keyhole.py`)

Method: green outline = keyhole, red outline = bubble/pore (both drawn by the paper's
authors). Outline filled, then measured row by row. 81 frames, 0.02–1.62 ms.
Plate surface at image row 171. Error about ±2 px (±4 µm), plus up to 2–4 µm too
large on lengths because the outline line thickness is included.

| Quantity | Value |
|---|---|
| Keyhole tip speed (check) | 0.59 m/s (matches 0.6 m/s) |
| Keyhole depth | mean 563 µm, std 37, range 470–662 µm |
| Mouth length | mean 32 µm, std 12, range 11–78 µm |
| Median length along depth | mean 31 µm, std 5, range 20–50 µm |
| Depth / median length | ~18 |
| Depth fluctuation period | ~350 µs (only 4–5 peaks, rough) |
| Mouth length fluctuation period | ~200 µs |
| Pores left in view at 1.62 ms | 14 |
| Pore equivalent diameter √(4A/π) | median 15 µm, range 8–54 µm |
| Pore depth below surface | 450–650 µm (most at 500–560 µm) |

Average keyhole shape (`plots/keyhole_shape.png`):

| Depth below surface | Mean length along scan |
|---|---|
| 0–250 µm | ~37–40 µm |
| ~470 µm (neck) | ~25 µm, the narrowest point |
| 510–550 µm (bulb) | ~35 µm |
| tip, ~600 µm | narrows to a point |

The bulb just above the tip matches the paper's regime III picture: a cavity at the
bottom that traps light and vapour and pinches off bubbles.

Notes:
- The keyhole is already fully deep in the first frame. The movie shows the steady
  part of the track, not the start.
- My depth period (~350 µs) is longer than the paper's (~200 µs). The movie is short
  and my filter is close to, but not the same as, theirs. Trust the paper value more.
- Lengths are about 16 pixels across, so ±4 µm is about ±13 %. Depth is more reliable.
