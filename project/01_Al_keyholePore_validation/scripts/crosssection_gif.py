#!/usr/bin/env python
"""Cross-section GIF of a decomposed compressibleLaserbeamFoam case.

Reads the binary processor*/<time> fields and AMR meshes directly (no
reconstructPar), rasterises the cells cut by two planes and writes a GIF:
  left : along the scan (x-y plane through the laser line z = zLaser)
  right: across the scan (z-y plane through the current laser x)
Colour = temperature; white line = metal surface (alpha.<metal> = 0.5);
cyan line = vapour (alpha.<metal>vapour = 0.5).

Usage: python crosssection_gif.py <case> [--out file.gif] [--metal aluminium]
"""
import argparse, glob, os, re, sys
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image


def _blocks(raw, dtype, ncomp=1):
    out, pos = [], 0
    pat = re.compile(rb"\n(\d+)\n\(")
    while True:
        m = pat.search(raw, pos)
        if not m:
            break
        n = int(m.group(1)); s = m.end()
        nb = n*ncomp*np.dtype(dtype).itemsize
        a = np.frombuffer(raw[s:s+nb], dtype=dtype)
        out.append(a.reshape(-1, ncomp) if ncomp > 1 else a)
        pos = s + nb
    return out


def field(path, ncells, ncomp=1):
    raw = open(path, "rb").read()
    seg = raw[raw.find(b"internalField"):]
    m = re.match(rb"internalField\s+uniform\s+([^;]+);", seg)
    if m:
        return np.full(ncells, float(m.group(1)))
    return _blocks(seg, "<f8", ncomp)[0]


def cell_boxes(md):
    pts = _blocks(open(md+"/points", "rb").read(), "<f8", 3)[0]
    off, data = _blocks(open(md+"/faces", "rb").read(), "<i4")[:2]
    own = _blocks(open(md+"/owner", "rb").read(), "<i4")[0]
    nei = _blocks(open(md+"/neighbour", "rb").read(), "<i4")[0]
    fp = pts[data]
    fmin = np.minimum.reduceat(fp, off[:-1], axis=0)
    fmax = np.maximum.reduceat(fp, off[:-1], axis=0)
    nc = max(own.max(), nei.max() if len(nei) else -1) + 1
    lo = np.full((nc, 3), np.inf); hi = np.full((nc, 3), -np.inf)
    for c, f in ((own, slice(None)), (nei, slice(0, len(nei)))):
        np.minimum.at(lo, c, fmin[f]); np.maximum.at(hi, c, fmax[f])
    return lo, hi


def laser_x(case, t):
    txt = open(os.path.join(case, "constant/timeVsLaserPosition")).read()
    rows = re.findall(r"\(\s*([-\d.eE+]+)\s+\(\s*([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s*\)\s*\)", txt)
    a = np.array(rows, float)
    return np.interp(t, a[:, 0], a[:, 1]), np.interp(t, a[:, 0], a[:, 3])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("case")
    ap.add_argument("--out", default=None)
    ap.add_argument("--metal", default="aluminium")
    ap.add_argument("--res", type=float, default=1.25e-6, help="pixel size [m]")
    ap.add_argument("--xwin", type=float, default=200e-6, help="half window along x [m]")
    ap.add_argument("--depth", type=float, default=200e-6, help="metal depth shown [m]")
    ap.add_argument("--fps", type=float, default=5)
    a = ap.parse_args()
    case = os.path.abspath(a.case)
    procs = sorted(glob.glob(os.path.join(case, "processor*")))
    times = sorted((d for d in os.listdir(procs[0]) if re.fullmatch(r"[\d.eE+-]+", d) and float(d) > 0), key=float)
    yTop = 120e-6        # plate surface at t = 0 (Hgas)
    ymin, ymax = 0.0, yTop + a.depth
    frames = []
    for tn in times:
        t = float(tn)
        xl, zl = laser_x(case, t)
        planes = {"along": (2, zl, 0, (xl - a.xwin, xl + a.xwin)),
                  "across": (0, xl, 2, (zl - a.xwin, zl + a.xwin))}
        img = {k: [np.full((int((ymax-ymin)/a.res), int((v[3][1]-v[3][0])/a.res)), np.nan) for _ in range(3)] for k, v in planes.items()}
        for pd in procs:
            d = os.path.join(pd, tn)
            md = d + "/polyMesh" if os.path.isdir(d + "/polyMesh") else os.path.join(pd, "constant/polyMesh")
            lo, hi = cell_boxes(md)
            n = len(lo)
            fv = d+f"/alpha.{a.metal}vapour"     # absent in laserbeamFoam cases
            F = [field(d+"/T", n), field(d+f"/alpha.{a.metal}", n),
                 field(fv, n) if os.path.exists(fv) else np.zeros(n)]
            for k, (nax, pos, hax, (h0, h1)) in planes.items():
                sel = np.where((lo[:, nax] <= pos) & (hi[:, nax] > pos) & (hi[:, hax] > h0) & (lo[:, hax] < h1) & (hi[:, 1] > ymin) & (lo[:, 1] < ymax))[0]
                for c in sel:
                    j0 = max(int(round((lo[c, hax]-h0)/a.res)), 0); j1 = int(round((hi[c, hax]-h0)/a.res))
                    i0 = max(int(round((lo[c, 1]-ymin)/a.res)), 0); i1 = int(round((hi[c, 1]-ymin)/a.res))
                    for q in range(3):
                        img[k][q][i0:i1, j0:j1] = F[q][c]
        fig, axs = plt.subplots(1, 2, figsize=(11, 5.2), constrained_layout=True)
        for ax, (k, (nax, pos, hax, (h0, h1))) in zip(axs, planes.items()):
            T, aM, aV = img[k]
            ext = [(h0-xl if k == "along" else h0-zl)*1e6, (h1-xl if k == "along" else h1-zl)*1e6, (ymin-yTop)*1e6, (ymax-yTop)*1e6]
            im = ax.imshow(T, extent=ext, origin="lower", cmap="inferno", vmin=300, vmax=3500, aspect="equal")
            ax.set_ylim((ymax-yTop)*1e6, (ymin-yTop)*1e6)
            yy = (ymin + (np.arange(T.shape[0])+0.5)*a.res - yTop)*1e6
            hh = ext[0] + (np.arange(T.shape[1])+0.5)*a.res*1e6
            ax.contour(hh, yy, np.nan_to_num(aM), [0.5], colors="white", linewidths=1.2)
            if np.nanmax(aV) > 0.5:
                ax.contour(hh, yy, np.nan_to_num(aV), [0.5], colors="cyan", linewidths=1.0)
            ax.contour(hh, yy, np.where(np.nan_to_num(aM) > 0.5, np.nan_to_num(T), 300), [933], colors="lime", linewidths=0.8, linestyles="--")
            ax.set_title("along scan (x, z = laser line)" if k == "along" else "across scan (z, x = laser)")
            ax.set_xlabel(("x" if k == "along" else "z") + " relative to laser [µm]")
            ax.set_ylabel("depth below initial surface [µm]")
        fig.colorbar(im, ax=axs, label="T [K]", shrink=0.8)
        fig.suptitle(f"t = {t*1e6:.2f} µs   white: metal surface   cyan: vapour   green dashed: melt line in metal (933 K)")
        fig.canvas.draw()
        frames.append(Image.fromarray(np.asarray(fig.canvas.buffer_rgba())[..., :3]))
        plt.close(fig)
        print(f"frame t = {tn}", flush=True)
    out = a.out or os.path.join(case, "crosssection.gif")
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=int(1000/a.fps), loop=0)
    frames[-1].save(out.replace(".gif", "_last.png"))
    print("wrote", out)


if __name__ == "__main__":
    main()
