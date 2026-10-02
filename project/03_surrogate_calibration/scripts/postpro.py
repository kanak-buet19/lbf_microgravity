"""Per-write post-processing of a running/finished laserbeamFoam case.

xray_frame()   Simulated X-ray side view, measured like Huang 2022 (see
               01/reference_paper/huang2022/.../measure_keyhole.py):
               alpha.metal painted on voxels (pixel size in x and y), gas
               (alpha < 0.5) connected to the open top is the keyhole, its
               path length along z is projected; a pixel is keyhole if that
               path >= min_path_um. Depth = deepest keyhole pixel below the
               flat initial surface. Row lengths along x give the length
               profile; mouth = mean of the top 3 rows below the surface.
               Closed gas below the surface = pores (3D connectivity).
ml_window()    T, alpha.metal, U on a uniform grid in a box moving with the
               laser (for later ML), saved as compressed .npz.
steady_state() / summary()  Early-stop test and steady statistics.
"""
import os

import numpy as np
from scipy import ndimage, signal

import foamio


def _procs(case):
    ps = sorted(p for p in os.listdir(case) if p.startswith("processor"))
    return [os.path.join(case, p) for p in ps] or [case]


def voxelize(case, tname, lo, hi, res, fields):
    """Paint cell values on a uniform grid.

    lo, hi: box corners [m] (3,), res: voxel size [m] (3,),
    fields: {name: ncomp}. Voxels outside the mesh stay NaN.
    """
    lo = np.asarray(lo, float); hi = np.asarray(hi, float); res = np.asarray(res, float)
    n = np.maximum(np.round((hi - lo)/res).astype(int), 1)
    out = {f: np.full(tuple(n) + ((c,) if c > 1 else ()), np.nan, np.float32)
           for f, c in fields.items()}
    for pd in _procs(case):
        clo, chi = foamio.cell_boxes(foamio.mesh_dir(pd, tname))
        sel = np.where(np.all(chi > lo, axis=1) & np.all(clo < hi, axis=1))[0]
        if not len(sel):
            continue
        vals = {f: foamio.field(os.path.join(pd, tname, f), len(clo), c)
                for f, c in fields.items()}
        i0 = np.clip(np.round((clo[sel] - lo)/res).astype(int), 0, n)
        i1 = np.clip(np.round((chi[sel] - lo)/res).astype(int), 0, n)
        for k, c in enumerate(sel):
            a, b = i0[k], i1[k]
            for f in fields:
                out[f][a[0]:b[0], a[1]:b[1], a[2]:b[2]] = vals[f][c]
    return out


def xray_frame(case, tname, cfg):
    """Huang-style keyhole metrics for one saved time. Returns a dict."""
    xr = cfg["xray"]
    t = float(tname)
    xl, _, zl = foamio.laser_position(case, t)
    px = xr["pixel_um"]*1e-6
    ys = xr["surface_y"]
    depth_max = 900e-6
    lo = (xl - 300e-6, 0.0, zl - 120e-6)
    hi = (xl + 80e-6, ys + depth_max, zl + 120e-6)
    v = voxelize(case, tname, lo, hi, (px, px, 2.5e-6), {"alpha.metal": 1})["alpha.metal"]
    gas = np.nan_to_num(v, nan=1.0) < 0.5          # outside the mesh = solid
    lab, _ = ndimage.label(gas)
    top = np.unique(lab[:, 0, :]); top = top[top > 0]
    open_gas = np.isin(lab, top)
    js = int(round((ys - lo[1])/px))               # first row below the surface
    # projection along z [um]; keyhole pixel = enough gas path
    path = open_gas.sum(axis=2)*2.5
    key = path >= xr["min_path_um"]
    key[:, :js] = False
    # keep only the keyhole blob attached to the surface (2D, like the image)
    lab2, _ = ndimage.label(key)
    attached = np.unique(lab2[:, js]); attached = attached[attached > 0]
    key = np.isin(lab2, attached)
    rows = np.where(key.any(axis=0))[0]
    depth = (rows.max() - js + 1)*xr["pixel_um"] if len(rows) else 0.0
    row_len = key.sum(axis=0)[js:]*xr["pixel_um"]  # length along x per row
    mouth = float(row_len[:3].mean()) if len(row_len) >= 3 else 0.0
    # pores: closed gas below the surface (3D), equivalent diameters
    closed = gas & ~open_gas
    closed[:, :js, :] = False
    plab, npore = ndimage.label(closed)
    if npore:
        vol = ndimage.sum(np.ones(plab.shape, np.float32), plab, range(1, npore + 1))
        dpore = (6*vol*px*px*2.5e-6/np.pi)**(1/3)*1e6
        dpore = dpore[dpore >= 5.0]
    else:
        dpore = np.array([])
    return {"t_us": t*1e6, "laser_x_um": xl*1e6, "depth_um": float(depth),
            "mouth_um": mouth, "n_pores": int(len(dpore)),
            "pore_d_um": [float(d) for d in dpore],
            "row_len_um": row_len.astype(np.float32)}


def ml_window(case, tname, cfg, out_path):
    """Save T, alpha.metal, U in the laser-following window as .npz."""
    w = cfg["ml_window"]
    t = float(tname)
    xl, _, zl = foamio.laser_position(case, t)
    ys = cfg["xray"]["surface_y"]
    lo = (xl + w["x_um"][0]*1e-6, ys + w["depth_um"][0]*1e-6, zl + w["z_um"][0]*1e-6)
    hi = (xl + w["x_um"][1]*1e-6, ys + w["depth_um"][1]*1e-6, zl + w["z_um"][1]*1e-6)
    r = w["res_um"]*1e-6
    ncomp = {"U": 3}
    v = voxelize(case, tname, lo, hi, (r, r, r), {f: ncomp.get(f, 1) for f in w["fields"]})
    np.savez_compressed(out_path, t=t, laser=np.array([xl, zl]), lo=np.array(lo),
                        res=r, **{f.replace(".", "_"): a for f, a in v.items()})


def steady_state(t_us, depth, st):
    """Time [us] at which depth became steady, or None."""
    t_us = np.asarray(t_us); depth = np.asarray(depth)
    W = st["window_us"]
    for i, t in enumerate(t_us):
        if t < max(st["t_min_us"], 2*W):
            continue
        a = depth[(t_us > t - W) & (t_us <= t)]
        b = depth[(t_us > t - 2*W) & (t_us <= t - W)]
        if len(a) >= 3 and len(b) >= 3 and abs(a.mean() - b.mean()) < st["tol_um"]:
            return float(t - 2*W)            # steady from the start of both windows
    return None


def period_us(t_us, depth):
    """Dominant fluctuation period [us] from peak spacing (None if unclear)."""
    if len(depth) < 8:
        return None
    d = np.asarray(depth) - np.mean(depth)
    pk, _ = signal.find_peaks(d, prominence=max(np.std(d)*0.5, 1.0))
    if len(pk) < 3:
        return None
    return float(np.mean(np.diff(np.asarray(t_us)[pk])))


def summary(frames, t_steady_us):
    """Steady statistics from xray frames with t >= t_steady_us."""
    fr = [f for f in frames if f["t_us"] >= t_steady_us]
    if not fr:
        return None
    t = np.array([f["t_us"] for f in fr]); d = np.array([f["depth_um"] for f in fr])
    px_rows = [np.asarray(f["row_len_um"]) for f in fr]
    pix = 1.96

    def band(a, b):
        vals = []
        for r in px_rows:
            i0, i1 = int(a/pix), int(b/pix)
            seg = r[i0:i1]
            vals += list(seg[seg > 0])
        return float(np.mean(vals)) if vals else 0.0

    pores = fr[-1]["pore_d_um"]
    return {
        "t_steady_us": t_steady_us, "t_last_us": float(t[-1]), "n_frames": len(fr),
        "depth_mean_um": float(d.mean()), "depth_std_um": float(d.std()),
        "mouth_mean_um": float(np.mean([f["mouth_um"] for f in fr])),
        "len_0_200_um": band(0, 200), "len_200_400_um": band(200, 400),
        "len_400_550_um": band(400, 550),
        "depth_period_us": period_us(t, d),
        "n_pores_end": len(pores),
        "pore_d50_um": float(np.median(pores)) if pores else 0.0,
    }
