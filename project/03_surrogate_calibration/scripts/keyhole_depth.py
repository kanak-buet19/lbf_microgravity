#!/usr/bin/env python
"""Keyhole depth, mouth length and pores vs time from a laserbeamFoam case.

For every saved time: cells in a box around the laser are painted onto a
uniform voxel grid (alpha.metal). Gas voxels (alpha < 0.5) connected to the
open top form the keyhole; gas pockets inside the metal that are not connected
are pores. Absorbed laser power is the 'Total Q deposited' value from the
solver log closest in time.

Depth is measured from the initial plate surface (y = --ysurf), positive into
the metal (+y). Output: CSV (one row per saved time) and printed table.
With --images also:
  <case>/keyhole_xray.gif   side view like the X-ray movie: gas path length
                            through the plate along z (keyhole dark, pores red)
  <case>/keyhole_depth.png  depth, mouth length and absorbed power vs time,
                            with the Huang target band (563 +- 37 um)

Usage: keyhole_depth.py <case> [--out depth.csv] [--res 2.5e-6] [--images]
"""
import argparse
import os
import re
import sys

import numpy as np
from scipy import ndimage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import foamio  # noqa: E402


def log_power(case):
    """(time, Q deposited) pairs from the solver log(s)."""
    out = []
    for f in sorted(os.listdir(case)):
        if not re.fullmatch(r"log\.(compressibleL|l)aserbeamFoam(\.\d+)?", f):
            continue
        t = None
        for line in open(os.path.join(case, f), errors="replace"):
            if line.startswith("Time = "):
                t = float(line.split()[2])
            elif "Total Q deposited" in line and t is not None:
                out.append((t, float(line.split()[-1])))
    return np.array(sorted(out)) if out else np.zeros((0, 2))


def analyse(case, tname, a):
    t = float(tname)
    xl, _, zl = foamio.laser_position(case, t)
    x0, x1 = xl - a.xback, xl + a.xfront
    z0, z1 = zl - a.zhalf, zl + a.zhalf
    y0, y1 = 0.0, a.ysurf + a.depth
    nx, ny, nz = (int(round((b - c)/a.res)) for b, c in ((x1, x0), (y1, y0), (z1, z0)))
    vox = np.full((nx, ny, nz), np.nan)
    procs = sorted(p for p in os.listdir(case) if p.startswith("processor"))
    for p in procs or ["."]:
        pd = os.path.join(case, p)
        lo, hi = foamio.cell_boxes(foamio.mesh_dir(pd, tname))
        alpha = foamio.field(os.path.join(pd, tname, "alpha.metal"), len(lo))
        sel = np.where((hi[:, 0] > x0) & (lo[:, 0] < x1) & (hi[:, 2] > z0)
                       & (lo[:, 2] < z1) & (lo[:, 1] < y1))[0]
        for c in sel:
            i0 = max(int(round((lo[c, 0] - x0)/a.res)), 0); i1 = int(round((hi[c, 0] - x0)/a.res))
            j0 = max(int(round((lo[c, 1] - y0)/a.res)), 0); j1 = int(round((hi[c, 1] - y0)/a.res))
            k0 = max(int(round((lo[c, 2] - z0)/a.res)), 0); k1 = int(round((hi[c, 2] - z0)/a.res))
            vox[i0:i1, j0:j1, k0:k1] = alpha[c]
    # outside the domain (box sticking out) counts as solid, never as gas
    gas = np.nan_to_num(vox, nan=1.0) < 0.5
    lab, _ = ndimage.label(gas)
    top = np.unique(lab[:, 0, :]); top = top[top > 0]
    open_gas = np.isin(lab, top)
    yc = y0 + (np.arange(ny) + 0.5)*a.res
    # keyhole depth: deepest open-gas voxel
    jj = np.where(open_gas.any(axis=(0, 2)))[0]
    depth = (yc[jj.max()] - a.ysurf)*1e6 if len(jj) else 0.0
    # mouth length along x at the initial surface level (just below it)
    js = int((a.ysurf - y0)/a.res) + 1
    row = open_gas[:, js, :]
    mouth = row.any(axis=1).sum()*a.res*1e6 if js < ny else 0.0
    # pores: closed gas below the initial surface
    closed = gas & ~open_gas
    closed[:, :int((a.ysurf - y0)/a.res), :] = False
    plab, npore = ndimage.label(closed)
    vols = ndimage.sum(np.ones_like(plab), plab, range(1, npore + 1))*a.res**3
    dpore = (6*vols/np.pi)**(1/3)*1e6 if npore else np.array([])
    big = dpore[dpore >= a.minpore]
    # side views (sum along z): gas path length of keyhole and of pores [um]
    proj = (open_gas.sum(axis=2)*a.res*1e6, closed.sum(axis=2)*a.res*1e6,
            (x0 - xl)*1e6, (x1 - xl)*1e6, (y0 - a.ysurf)*1e6, (y1 - a.ysurf)*1e6)
    return t, xl, depth, mouth, len(big), (np.median(big) if len(big) else 0.0), proj


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("case")
    ap.add_argument("--out", default=None, help="CSV (default <case>/keyhole_depth.csv)")
    ap.add_argument("--res", type=float, default=2.5e-6, help="voxel size [m]")
    ap.add_argument("--ysurf", type=float, default=120e-6, help="initial surface y [m]")
    ap.add_argument("--depth", type=float, default=900e-6, help="metal depth searched [m]")
    ap.add_argument("--xback", type=float, default=300e-6, help="box behind laser [m]")
    ap.add_argument("--xfront", type=float, default=80e-6, help="box ahead of laser [m]")
    ap.add_argument("--zhalf", type=float, default=100e-6, help="box half width [m]")
    ap.add_argument("--minpore", type=float, default=5.0, help="smallest pore kept [um]")
    ap.add_argument("--images", action="store_true", help="write X-ray-style GIF and depth plot")
    ap.add_argument("--fps", type=float, default=4)
    a = ap.parse_args()
    case = os.path.abspath(a.case)
    out = a.out or os.path.join(case, "keyhole_depth.csv")
    P = log_power(case)
    rows, frames = [], []
    print(f"{'t_us':>8} {'x_um':>7} {'depth_um':>9} {'mouth_um':>9} {'pores':>6} {'pore_d50':>8} {'Q_W':>7}")
    for tn in foamio.times(case):
        t, xl, d, m, npo, d50, proj = analyse(case, tn, a)
        if a.images:
            frames.append(xray_frame(t, d, proj))
        q = P[np.argmin(abs(P[:, 0] - t)), 1] if len(P) else np.nan
        rows.append((t*1e6, xl*1e6, d, m, npo, d50, q))
        print(f"{t*1e6:8.1f} {xl*1e6:7.1f} {d:9.1f} {m:9.1f} {npo:6d} {d50:8.1f} {q:7.1f}", flush=True)
    np.savetxt(out, np.array(rows), delimiter=",", fmt="%.4g",
               header="t_us,laser_x_um,depth_um,mouth_length_um,n_pores,pore_d50_um,Q_absorbed_W",
               comments="")
    print("wrote", out)
    if a.images and rows:
        from PIL import Image
        gif = os.path.join(case, "keyhole_xray.gif")
        imgs = [Image.fromarray(f) for f in frames]
        imgs[0].save(gif, save_all=True, append_images=imgs[1:], duration=int(1000/a.fps), loop=0)
        print("wrote", gif)
        print("wrote", depth_plot(case, np.array(rows)))


TARGET = (563.0, 37.0)   # Huang 2022 mean keyhole depth +- std [um]


def xray_frame(t, depth, proj):
    """One RGB frame: keyhole path length (grey) and pores (red) along z."""
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    key, pore, xa, xb, ya, yb = proj
    # only below the initial surface: the argon above would saturate the scale
    js = int(round(-ya/(yb - ya)*key.shape[1]))
    key = key.copy(); key[:, :js] = 0
    fig, ax = plt.subplots(figsize=(5, 7.5), constrained_layout=True)
    ax.set_facecolor("white")
    im = ax.imshow(np.ma.masked_equal(key.T, 0), extent=[xa, xb, yb, ya], cmap="Greys",
                   vmin=0, vmax=max(np.percentile(key[key > 0], 99) if (key > 0).any() else 1, 1), aspect="equal", interpolation="nearest")
    if pore.max() > 0:
        ax.imshow(np.ma.masked_equal(pore.T, 0), extent=[xa, xb, yb, ya], cmap="Reds",
                  vmin=0, vmax=pore.max(), aspect="equal", interpolation="nearest")
    ax.axhline(0, color="tab:blue", lw=0.8, ls=":")
    ax.axhspan(TARGET[0] - TARGET[1], TARGET[0] + TARGET[1], color="tab:green", alpha=0.12)
    ax.axvline(0, color="tab:orange", lw=0.8, ls="--")
    ax.set_ylim(yb, ya)
    ax.set_xlabel("x relative to laser [µm]  (scan →)")
    ax.set_ylabel("depth below initial surface [µm]")
    ax.set_title(f"t = {t*1e6:.0f} µs   depth = {depth:.0f} µm\n"
                 "grey: keyhole, red: pores, green band: Huang 563 ± 37 µm", fontsize=9)
    fig.colorbar(im, ax=ax, shrink=0.5, label="gas path length along z [µm]")
    fig.canvas.draw()
    rgb = np.asarray(fig.canvas.buffer_rgba())[..., :3].copy()
    plt.close(fig)
    return rgb


def depth_plot(case, r):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axs = plt.subplots(3, 1, figsize=(7, 7), sharex=True, constrained_layout=True)
    axs[0].plot(r[:, 0], r[:, 2], "o-", ms=3)
    axs[0].axhspan(TARGET[0] - TARGET[1], TARGET[0] + TARGET[1], color="tab:green", alpha=0.15,
                   label="Huang 563 ± 37 µm")
    axs[0].set_ylabel("keyhole depth [µm]"); axs[0].legend(loc="lower right")
    axs[1].plot(r[:, 0], r[:, 3], "o-", ms=3)
    axs[1].axhline(32, color="tab:green", ls="--", label="Huang mouth ~32 µm")
    axs[1].set_ylabel("mouth length [µm]"); axs[1].legend(loc="upper right")
    axs[2].plot(r[:, 0], r[:, 6], "o-", ms=3)
    axs[2].set_ylabel("absorbed power [W]"); axs[2].set_xlabel("time [µs]")
    for ax in axs:
        ax.grid(alpha=0.3)
    out = os.path.join(case, "keyhole_depth.png")
    fig.savefig(out, dpi=120); plt.close(fig)
    return out


if __name__ == "__main__":
    main()
