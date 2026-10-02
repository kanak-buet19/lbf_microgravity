"""results.md writer for the calibration (called by driver.py at the end)."""
import os

import numpy as np

import surrogate as S


def _phys(cfg, u_list):
    return [S.unscale(cfg, u) for u in u_list]


def write_results(state, cfg, proj):
    names = S.target_names(cfg)
    knobs = cfg["knobs"]
    h = state["history"][-1] if state["history"] else None
    runs = state["runs"]
    done = [r for r in runs.values() if r["status"] == "done"]
    failed = {k: r for k, r in runs.items() if r["status"] == "failed"}
    L = ["# 03 — Calibration results", "",
         f"Started {state['started']}. Finished: {state.get('stop_reason', '')}.",
         f"Runs: {len(runs)} total, {len(done)} done, {len(failed)} failed.", ""]
    if h:
        rng = np.array([k["high"] - k["low"] for k in knobs])
        lo = np.array([k["low"] for k in knobs])
        mean = lo + np.array(h["mean"])*rng
        std = np.array(h["std"])*rng
        best = h["best_params"]
        rel = np.max(np.array(list(h["relevance"].values())), axis=0)
        L += ["## Calibrated knobs", "",
              "Posterior = calibrated estimate with its uncertainty (1 std). "
              "Relevance = how strongly any target reacts to the knob over its range "
              "(< 1: weak, cannot be pinned down).", "",
              "| Knob | Range | Nominal | Best | Posterior mean ± std | Relevance |",
              "|---|---|---|---|---|---|"]
        for k, m, s, rv in zip(knobs, mean, std, rel):
            L.append(f"| {k['label']} (`{k['name']}`, {k['unit']}) | {k['low']:.4g} – {k['high']:.4g} "
                     f"| {k['nominal']:.4g} | **{best[k['name']]:.4g}** | {m:.4g} ± {s:.2g} | {rv:.2f} |")
        L += ["", "## Fit to Huang 2022", "",
              "| Target | Huang | Tolerance | Surrogate at best | Check run |", "|---|---|---|---|---|"]
        cr = state.get("check_run")
        chk = runs.get(cr, {}).get("summary") if cr and cr in runs else None
        for n, p, ps in zip(names, h["best_pred"], h["best_pred_std"]):
            t = cfg["targets"][n]
            c = f"{chk[n]:.1f}" if chk else "—"
            L.append(f"| {n} | {t['value']} | {t['tol']} | {p:.1f} ± {ps:.1f} | {c} |")
        L += ["", f"Convergence: {h['msg']}. Effective sample size {h['ess']:.0f}.", "",
              "Run-to-run noise (fitted): " + ", ".join(f"{k} {v:.1f}" for k, v in h["noise"].items()), ""]
    L += ["## All runs", "", "| Run | Tag | Status | Depth mean ± std [µm] | Steady from [µs] | Note |",
          "|---|---|---|---|---|---|"]
    for k, r in sorted(runs.items()):
        s = r.get("summary") or {}
        dm = f"{s['depth_mean_um']:.0f} ± {s['depth_std_um']:.0f}" if s else "—"
        L.append(f"| {k} | {r.get('tag', '')} | {r['status']} | {dm} | "
                 f"{s.get('t_steady_us', 0):.0f} | {r.get('reason', r.get('flag', ''))} |")
    L += ["", "Files: `state.json` (everything), `runs/run_NNN/` (case, logs, `summary.json`, "
          "`xray_frames.json`, `ml_window/`), `surrogate_history/`, `driver.log`, `dashboard.html`.", ""]
    with open(os.path.join(proj, "results.md"), "w") as f:
        f.write("\n".join(L))
