#!/usr/bin/env python
"""Write one calibration case from the template and a parameter set.

The template (project 03 template/) is a copy of the laserbeamFoam Huang case
with @name@ placeholders. This fills them in and writes params.json next to
the case so every run records exactly what it used.

Knobs (config.json "knobs"): laserRadius [m], elecCond [S/m], ks (solid k
scale), kl (liquid k), cs (solid cp scale), cl (liquid cp), sigma [N/m].

Usage (normally called by driver.py):
  make_case.py <out_dir> --set laserRadius=30e-6 --set sigma=0.8 ...
Unset knobs take their "nominal" value.
"""
import argparse
import json
import os
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)

# Solid property fits for pure Al (see template constant/transportProperties)
KS = (248.0, -0.0385)     # k_solid(T) = ks*(KS0 + KS1*T)
CS = (762.0, 0.44)        # cp_solid(T) = cs*(CS0 + CS1*T)


def load_config(path=None):
    with open(path or os.path.join(PROJ, "config.json")) as f:
        return json.load(f)


def git_commit():
    try:
        return subprocess.check_output(
            ["git", "-C", PROJ, "rev-parse", "HEAD"], text=True,
            stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unknown"


def git_dirty():
    try:
        out = subprocess.check_output(
            ["git", "-C", PROJ, "status", "--porcelain", "--", "../../src",
             "../../applications"], text=True, stderr=subprocess.DEVNULL)
        return bool(out.strip())
    except Exception:
        return None


def fmt(v):
    return f"{v:.6g}"


def make_case(out_dir, params, cfg, n_procs=None):
    """Create out_dir from the template. params: dict knob -> value."""
    knobs = {k["name"]: k for k in cfg["knobs"]}
    p = {n: float(params.get(n, k["nominal"])) for n, k in knobs.items()}
    for n, v in p.items():
        if not knobs[n]["low"] <= v <= knobs[n]["high"]:
            raise ValueError(f"{n} = {v} outside [{knobs[n]['low']}, {knobs[n]['high']}]")

    c = cfg["case"]
    t_end = c["end_time_cap"]
    x1 = c["laser_x0"] + c["scan_speed"]*t_end
    if x1 > c["Lx"] - 100e-6:
        raise ValueError(f"laser ends at x = {x1*1e6:.0f} um, too close to the end "
                         f"of the domain (Lx = {c['Lx']*1e6:.0f} um)")
    tokens = {
        "Lx": fmt(c["Lx"]),
        "x0": fmt(c["laser_x0"]),
        "x1": fmt(x1),
        "endTime": fmt(t_end),
        "writeInterval": fmt(c["write_interval"]),
        "nProcs": str(n_procs or cfg["cores"]["cores_per_job"]),
        "maxRefinement": str(int(c.get("max_refinement", 2))),
        "laserRadius": fmt(p["laserRadius"]),
        "elecCond": fmt(p["elecCond"]),
        "ks0": fmt(p["ks"]*KS[0]), "ks1": fmt(p["ks"]*KS[1]),
        "kl": fmt(p["kl"]),
        "cs0": fmt(p["cs"]*CS[0]), "cs1": fmt(p["cs"]*CS[1]),
        "cl": fmt(p["cl"]),
        "sigma": fmt(p["sigma"]),
    }

    if os.path.exists(out_dir):
        raise FileExistsError(out_dir)
    shutil.copytree(os.path.join(PROJ, cfg["template"]), out_dir)
    left = []
    for root, _, files in os.walk(out_dir):
        for f in files:
            fp = os.path.join(root, f)
            s = open(fp).read()
            for k, v in tokens.items():
                s = s.replace(f"@{k}@", v)
            if "@" in s:
                left += [f"{fp}: {w}" for w in set(
                    t for t in s.split() if t.startswith("@") and t.rstrip(";").endswith("@"))]
            open(fp, "w").write(s)
    if left:
        raise RuntimeError("unfilled placeholders: " + ", ".join(left))

    meta = {"params": p, "tokens": tokens, "git_commit": git_commit(),
            "git_dirty_src": git_dirty()}
    with open(os.path.join(out_dir, "params.json"), "w") as f:
        json.dump(meta, f, indent=2)
    open(os.path.join(out_dir, "open.foam"), "w").close()
    return p


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("out_dir")
    ap.add_argument("--set", action="append", default=[], metavar="NAME=VALUE")
    ap.add_argument("--config", default=None)
    a = ap.parse_args()
    cfg = load_config(a.config)
    params = dict(kv.split("=", 1) for kv in a.set)
    p = make_case(a.out_dir, params, cfg)
    print("wrote", a.out_dir, json.dumps(p))


if __name__ == "__main__":
    main()
