"""Measure keyhole and pore geometry from Huang et al. (2022) Supplementary Movie 4.

Case: pure Al bare plate (bp), 500 W, 0.6 m/s, 50 um spot.

The movie is a side-view X-ray image. The authors drew the keyhole outline in
green and bubble/pore outlines in red. This script reads those outlines.

Directions in the image:
  - horizontal = scan direction, so the horizontal size of the keyhole is its
    LENGTH along the scan (the paper calls this "width").
  - vertical   = depth below the plate surface.
  - the true keyhole width (across the track) is along the X-ray beam and is
    not visible.

Outputs (written next to this script):
  data/keyhole_vs_time.csv        one row per frame
  data/length_vs_depth.csv        keyhole length at each depth, over all frames
  data/length_vs_normdepth.csv    same, with depth scaled by each frame's depth
  data/pores_final.csv            pores left in the last frame
  plots/keyhole_vs_time.png
  plots/keyhole_shape.png

Run with the venv312 Python (needs numpy, scipy, matplotlib, pillow,
imageio-ffmpeg):
  ~/.venv/venv312/bin/python measure_keyhole.py
"""

import csv
import subprocess
import tempfile
from pathlib import Path

import imageio_ffmpeg
import matplotlib
import numpy as np
from PIL import Image
from scipy import ndimage as nd
from scipy.signal import find_peaks

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
VIDEO = HERE / "video" / "AL_500W_600mms_50um_bp.mp4"
DATA = HERE / "data"
PLOTS = HERE / "plots"

PX = 1.96          # um per pixel (paper, Methods)
DT = 20.0          # us per frame (50 kHz camera)
SURFACE_ROW = 171  # image row of the plate top surface (dark line)
TEXT_ROW = 600     # rows below this hold the caption text box
MOUTH_ROWS = 3     # top rows of the keyhole used for the mouth length
MIN_PORE_PX = 4    # ignore red blobs smaller than this (noise)


def read_frames():
    """Decode every frame of the movie to an RGB array."""
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            [ffmpeg, "-loglevel", "error", "-i", str(VIDEO), f"{tmp}/f%03d.png"],
            check=True,
        )
        files = sorted(Path(tmp).glob("f*.png"))
        return [np.asarray(Image.open(f).convert("RGB")).astype(int) for f in files]


def masks(im):
    """Return filled keyhole mask and filled pore mask for one frame."""
    r, g, b = im[..., 0], im[..., 1], im[..., 2]
    green = (g > 150) & (r < 120) & (b < 120)
    red = (r > 150) & (g < 100) & (b < 100)
    green[TEXT_ROW:] = False
    red[TEXT_ROW:] = False
    keyhole = nd.binary_fill_holes(nd.binary_closing(green, iterations=2))
    pores = nd.binary_fill_holes(nd.binary_closing(red, iterations=1))
    return keyhole, pores


def keyhole_rows(keyhole):
    """Depth (um) and length along scan (um) for each image row of the keyhole."""
    z, length = [], []
    bottom = np.nonzero(keyhole.any(1))[0].max()
    for y in range(SURFACE_ROW, bottom + 1):
        xs = np.nonzero(keyhole[y])[0]
        if xs.size:
            z.append((y - SURFACE_ROW) * PX)
            length.append((xs.max() - xs.min() + 1) * PX)
    return np.array(z), np.array(length)


def pore_list(pores):
    """Equivalent diameter, depth and x position (um) of each pore."""
    lab, n = nd.label(pores)
    out = []
    for k in range(1, n + 1):
        ys, xs = np.nonzero(lab == k)
        if ys.size < MIN_PORE_PX:
            continue
        out.append((np.sqrt(4 * ys.size / np.pi) * PX,
                    (ys.mean() - SURFACE_ROW) * PX,
                    xs.mean() * PX))
    return out


def fluctuation_period(t, a):
    """Mean peak-to-peak period, filtered as in the paper's Methods."""
    s = np.convolve(a, np.ones(3) / 3, mode="same")
    s = s - np.polyval(np.polyfit(t, s, 1), t)
    p, _ = find_peaks(s, distance=5, prominence=s.std())
    return np.diff(t[p]).mean() if len(p) > 1 else np.nan


def write_csv(path, header, rows, nd_=2):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow([round(float(x), nd_) for x in r])


def main():
    DATA.mkdir(exist_ok=True)
    PLOTS.mkdir(exist_ok=True)
    frames = read_frames()

    per_frame, profiles, last_pores = [], [], []
    for i, im in enumerate(frames, 1):
        keyhole, pores = masks(im)
        z, length = keyhole_rows(keyhole)
        ys, xs = np.nonzero(keyhole)
        tip_x = xs[ys == ys.max()].mean() * PX
        last_pores = pore_list(pores)
        per_frame.append((
            i * DT,                        # time
            z.max(),                       # depth
            length[:MOUTH_ROWS].mean(),    # mouth length
            np.median(length),             # median length along depth
            length.max(),                  # max length
            tip_x,                         # tip position along scan
            len(last_pores),               # pores in view
        ))
        profiles.append((z, length))

    pf = np.array(per_frame)
    t, depth, mouth, med = pf[:, 0], pf[:, 1], pf[:, 2], pf[:, 3]
    write_csv(DATA / "keyhole_vs_time.csv",
              ["time_us", "depth_um", "mouth_length_um", "median_length_um",
               "max_length_um", "tip_x_um", "n_pores_in_view"], per_frame, 1)

    # Length vs absolute depth, 20 um bins.
    edges = np.arange(0, 700, 20)
    rows_abs = []
    for a, b in zip(edges[:-1], edges[1:]):
        v = np.concatenate([L[(z >= a) & (z < b)] for z, L in profiles])
        frac = np.mean([((z >= a) & (z < b)).any() for z, _ in profiles])
        if v.size:
            rows_abs.append((a + 10, v.mean(), v.std(), np.percentile(v, 10),
                             np.percentile(v, 90), frac))
    write_csv(DATA / "length_vs_depth.csv",
              ["depth_um", "length_mean_um", "length_std_um", "length_p10_um",
               "length_p90_um", "fraction_of_frames"], rows_abs)

    # Length vs depth scaled by each frame's own depth, 25 bins.
    nb = np.linspace(0, 1, 26)
    zn_mid = (nb[:-1] + nb[1:]) / 2
    N = []
    for z, L in profiles:
        zn = z / z.max()
        N.append([L[(zn >= a) & (zn < b)].mean() if ((zn >= a) & (zn < b)).any()
                  else np.nan for a, b in zip(nb[:-1], nb[1:])])
    N = np.array(N)
    rows_norm = list(zip(zn_mid, np.nanmean(N, 0), np.nanpercentile(N, 10, 0),
                         np.nanpercentile(N, 90, 0)))
    write_csv(DATA / "length_vs_normdepth.csv",
              ["depth_over_keyhole_depth", "length_mean_um", "length_p10_um",
               "length_p90_um"], rows_norm, 3)

    write_csv(DATA / "pores_final.csv",
              ["eq_diameter_um", "depth_um", "x_um"], last_pores, 1)

    # Summary printed for the README.
    speed = np.polyfit(t, pf[:, 5], 1)[0]
    d = np.array([p[0] for p in last_pores])
    print(f"tip speed            {speed:.2f} m/s")
    for name, a in (("depth", depth), ("mouth length", mouth),
                    ("median length", med)):
        print(f"{name:20s} mean {a.mean():.0f}  std {a.std():.0f}  "
              f"min {a.min():.0f}  max {a.max():.0f} um  "
              f"period {fluctuation_period(t, a):.0f} us")
    print(f"final pores          n={len(d)}  median {np.median(d):.0f} um  "
          f"range {d.min():.0f}-{d.max():.0f} um")

    plot_time(t, depth, mouth, last_pores)
    plot_shape(rows_abs, rows_norm)


STYLE = {
    "font.size": 10, "axes.edgecolor": "#52514e", "axes.labelcolor": "#0b0b0b",
    "xtick.color": "#52514e", "ytick.color": "#52514e",
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": "#e4e3df", "grid.linewidth": 0.8,
}
BLUE, ORANGE, INK, MUTED = "#2a78d6", "#eb6834", "#0b0b0b", "#52514e"
TITLE = "Al bare plate, 500 W, 0.6 m/s, 50 µm spot (Huang et al. 2022, Supp. Movie 4)"
BOX = dict(boxstyle="round,pad=0.25", fc="white", ec="none", alpha=0.9)


def plot_time(t, depth, mouth, pores):
    plt.rcParams.update(STYLE)
    fig, ax = plt.subplots(3, 1, figsize=(8, 9.5), constrained_layout=True)
    fig.suptitle(TITLE, fontsize=11, color=INK)

    a = ax[0]
    a.plot(t, depth, color=BLUE, lw=2, marker="o", ms=4)
    a.axhline(depth.mean(), color=MUTED, lw=1, ls="--")
    a.set_ylim(690, 450)
    a.text(1640, 685, f"mean {depth.mean():.0f} ± {depth.std():.0f} µm (dashed)",
           ha="right", va="bottom", color=MUTED, bbox=BOX)
    a.set_xlabel("Time (µs)")
    a.set_ylabel("Keyhole depth (µm)")
    a.set_title("a  Keyhole depth below plate surface", loc="left", color=INK)

    a = ax[1]
    a.plot(t, mouth, color=BLUE, lw=2, marker="o", ms=4)
    a.axhline(mouth.mean(), color=MUTED, lw=1, ls="--")
    top = mouth.max() * 1.25
    a.set_ylim(0, top)
    a.text(1640, top * 0.97,
           f"mean {mouth.mean():.0f} ± {mouth.std():.0f} µm (dashed)",
           ha="right", va="top", color=MUTED, bbox=BOX)
    a.set_xlabel("Time (µs)")
    a.set_ylabel("Mouth length (µm)")
    a.set_title("b  Keyhole mouth length along scan direction", loc="left",
                color=INK)

    a = ax[2]
    dm, ds = depth.mean(), depth.std()
    a.axhspan(dm - ds, dm + ds, color=BLUE, alpha=0.12, lw=0)
    a.axhline(dm, color=BLUE, lw=1, ls="--")
    a.text(990, dm + ds + 4, "keyhole depth, mean ± std", color=MUTED,
           ha="right", va="top")
    D = np.array([p[0] for p in pores])
    Z = np.array([p[1] for p in pores])
    X = np.array([p[2] for p in pores])
    a.scatter(X, Z, s=(D * 1.6) ** 1.5, color=ORANGE, edgecolor="white",
              linewidth=1.5, zorder=3)
    for x, z, dd in zip(X, Z, D):
        a.annotate(f"{dd:.0f}", (x, z), xytext=(0, -10), textcoords="offset points",
                   ha="center", va="top", fontsize=8, color=MUTED)
    a.set_xlim(0, 1004)
    a.set_ylim(720, 380)
    a.set_aspect("equal")
    a.set_xlabel("Position along scan (µm)")
    a.set_ylabel("Depth below surface (µm)")
    a.set_title(f"c  Pores left at {t[-1] / 1000:.2f} ms (n = {len(D)}, "
                "label = equivalent diameter in µm)", loc="left", color=INK)
    fig.savefig(PLOTS / "keyhole_vs_time.png", dpi=160, facecolor="white")
    plt.close(fig)


def plot_shape(rows_abs, rows_norm):
    plt.rcParams.update(STYLE)
    fig, ax = plt.subplots(1, 2, figsize=(9, 7), constrained_layout=True)
    fig.suptitle("Keyhole length along scan vs depth — " + TITLE, fontsize=10,
                 color=INK)

    def shape(a, z, m, lo, hi, ylab, title):
        z, m, lo, hi = map(np.array, (z, m, lo, hi))
        a.fill_betweenx(z, -hi / 2, hi / 2, color=BLUE, alpha=0.15, lw=0)
        a.fill_betweenx(z, -lo / 2, lo / 2, color="white", lw=0)
        a.plot(m / 2, z, color=BLUE, lw=2)
        a.plot(-m / 2, z, color=BLUE, lw=2)
        a.set_xlim(-40, 40)
        a.set_xlabel("Distance from keyhole centre, along scan (µm)")
        a.set_ylabel(ylab)
        a.set_title(title, loc="left", color=INK)

    ra = [r for r in rows_abs if r[5] >= 0.5]
    shape(ax[0], [r[0] for r in ra], [r[1] for r in ra], [r[3] for r in ra],
          [r[4] for r in ra], "Depth below plate surface (µm)", "a  Absolute depth")
    ax[0].set_ylim(620, 0)
    shape(ax[1], [r[0] for r in rows_norm], [r[1] for r in rows_norm],
          [r[2] for r in rows_norm], [r[3] for r in rows_norm],
          "Depth / keyhole depth in that frame", "b  Depth scaled per frame")
    ax[1].set_ylim(1.02, 0)
    fig.supxlabel("Line = mean length. Band = 10–90 % range over frames. "
             "Panel a: depths reached in ≥ 50 % of frames.\n"
             "Drawn symmetric: only the total length is measured, "
             "not where each wall sits.",
             color=MUTED, fontsize=8.5)
    fig.savefig(PLOTS / "keyhole_shape.png", dpi=160, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    main()
