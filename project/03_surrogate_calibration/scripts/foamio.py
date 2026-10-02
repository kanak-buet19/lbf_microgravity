"""Minimal readers for binary OpenFOAM v2512 output of a decomposed case.

Reads processor*/<time>/<field> and the (AMR) mesh in processor*/<time>/polyMesh
directly, so no reconstructPar is needed. Binary format only
(writeFormat binary; label 32 bit, scalar 64 bit).
"""
import os
import re
import numpy as np

_BLOCK = re.compile(rb"\n(\d+)\n\(")


def _blocks(raw, dtype, ncomp=1):
    """All 'N\\n(' binary list blocks in a file, in order."""
    out, pos = [], 0
    while True:
        m = _BLOCK.search(raw, pos)
        if not m:
            return out
        n = int(m.group(1)); s = m.end()
        nb = n*ncomp*np.dtype(dtype).itemsize
        a = np.frombuffer(raw[s:s+nb], dtype=dtype)
        out.append(a.reshape(-1, ncomp) if ncomp > 1 else a)
        pos = s + nb


def field(path, ncells, ncomp=1):
    """Internal field values (uniform fields expanded to ncells)."""
    raw = open(path, "rb").read()
    seg = raw[raw.find(b"internalField"):]
    m = re.match(rb"internalField\s+uniform\s+([^;]+);", seg)
    if m:
        v = m.group(1).strip(b"() ").split()
        return np.tile(np.array(v, float), (ncells, 1)).squeeze()
    return _blocks(seg, "<f8", ncomp)[0]


def cell_boxes(meshdir):
    """Axis-aligned bounding box (lo, hi) of every cell, shape (nCells, 3)."""
    pts = _blocks(open(meshdir+"/points", "rb").read(), "<f8", 3)[0]
    off, data = _blocks(open(meshdir+"/faces", "rb").read(), "<i4")[:2]
    own = _blocks(open(meshdir+"/owner", "rb").read(), "<i4")[0]
    nei = _blocks(open(meshdir+"/neighbour", "rb").read(), "<i4")[0]
    fp = pts[data]
    fmin = np.minimum.reduceat(fp, off[:-1], axis=0)
    fmax = np.maximum.reduceat(fp, off[:-1], axis=0)
    nc = max(own.max(), nei.max() if len(nei) else -1) + 1
    lo = np.full((nc, 3), np.inf); hi = np.full((nc, 3), -np.inf)
    np.minimum.at(lo, own, fmin); np.maximum.at(hi, own, fmax)
    np.minimum.at(lo, nei, fmin[:len(nei)]); np.maximum.at(hi, nei, fmax[:len(nei)])
    return lo, hi


def times(case):
    """Saved times > 0 (names), from processor0 or the case folder."""
    d = os.path.join(case, "processor0")
    d = d if os.path.isdir(d) else case
    ts = [t for t in os.listdir(d) if re.fullmatch(r"[0-9][0-9.eE+-]*", t)]
    return sorted((t for t in ts if float(t) > 0), key=float)


def mesh_dir(procdir, tname):
    """Mesh for this time: the AMR mesh if written, else constant/polyMesh."""
    d = os.path.join(procdir, tname, "polyMesh")
    return d if os.path.isdir(d) else os.path.join(procdir, "constant", "polyMesh")


def laser_position(case, t):
    """Laser (x, y, z) at time t from constant/timeVsLaserPosition."""
    txt = open(os.path.join(case, "constant/timeVsLaserPosition")).read()
    num = r"([-\d.eE+]+)"
    rows = re.findall(r"\(\s*%s\s+\(\s*%s\s+%s\s+%s\s*\)\s*\)" % ((num,)*4), txt)
    a = np.array(rows, float)
    return tuple(np.interp(t, a[:, 0], a[:, k]) for k in (1, 2, 3))
