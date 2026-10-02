"""dashboard.html for the calibration driver (one self-contained file).

Written by driver.py every few minutes. Open it in a browser; it reloads
itself every 60 s and shows a red banner if the driver stops updating it.
"""
import base64
import datetime as dt
import html
import io
import json
import os

import numpy as np

import surrogate as S

FMT = "%Y-%m-%d %H:%M:%S"


def _age_min(s):
    try:
        return (dt.datetime.now() - dt.datetime.strptime(s, FMT)).total_seconds()/60
    except Exception:
        return None


def _png(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    import matplotlib.pyplot as plt
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _score(summ, cfg):
    """Sum of squared misses in tolerance units (lower = closer to Huang)."""
    if not summ:
        return None
    return float(sum(((summ[n] - cfg["targets"][n]["value"])/cfg["targets"][n]["tol"])**2
                     for n in S.target_names(cfg)))


def _frames(proj, cfg, rid):
    p = os.path.join(proj, cfg["runs_dir"], rid, "xray_frames.json")
    try:
        return json.load(open(p))
    except Exception:
        return []


def _charts(state, cfg, proj):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    out = {}
    tgt = cfg["targets"]["depth_mean_um"]
    # depth vs time, all runs
    fig, ax = plt.subplots(figsize=(8, 3.6))
    ax.axhspan(tgt["value"] - 36.6, tgt["value"] + 36.6, color="#2a9d8f", alpha=0.15,
               label="Huang 563 ± 37 µm")
    col = {"running": "#1f77b4", "stopping": "#1f77b4", "done": "#555555", "failed": "#d62728"}
    for rid, r in sorted(state["runs"].items()):
        fr = _frames(proj, cfg, rid)
        if not fr:
            continue
        t = [f["t_us"] for f in fr]; d = [f["depth_um"] for f in fr]
        lw = 2.0 if r.get("tag") == "check" else 1.0
        ax.plot(t, d, color=col.get(r["status"], "#999"), lw=lw,
                alpha=0.9 if r["status"] in ("running", "stopping") else 0.45)
        ax.annotate(rid[-3:], (t[-1], d[-1]), fontsize=6, color="#444")
    ax.set_xlabel("time [µs]"); ax.set_ylabel("keyhole depth [µm]")
    ax.grid(alpha=0.3); ax.legend(loc="lower right", fontsize=8)
    ax.set_title("Depth vs time (blue running, grey done, red failed)", fontsize=10)
    out["depth"] = _png(fig)
    # calibration progress
    hist = state["history"]
    if hist:
        names = [k["name"] for k in cfg["knobs"]]
        fig, axs = plt.subplots(1, 2, figsize=(10, 3.4), gridspec_kw={"width_ratios": [1.4, 1]})
        n = [h["n_done"] for h in hist]
        for j, nm in enumerate(names):
            m = np.array([h["mean"][j] for h in hist]); s = np.array([h["std"][j] for h in hist])
            axs[0].plot(n, m, "o-", ms=3, label=nm); axs[0].fill_between(n, m - s, m + s, alpha=0.12)
        axs[0].set_ylim(0, 1); axs[0].set_xlabel("finished runs")
        axs[0].set_ylabel("knob (0 = low, 1 = high end of range)")
        axs[0].set_title("Calibrated knob values ± std over time", fontsize=10)
        axs[0].legend(fontsize=7, ncol=2); axs[0].grid(alpha=0.3)
        h = hist[-1]
        y = np.arange(len(names))
        axs[1].errorbar(h["mean"], y, xerr=h["std"], fmt="o", color="#1f77b4", label="posterior")
        axs[1].plot(h["best"], y, "x", color="#d62728", label="best")
        axs[1].axvspan(0, 1, color="#eee", zorder=-1)
        axs[1].set_yticks(y); axs[1].set_yticklabels(names, fontsize=8); axs[1].set_xlim(-0.05, 1.05)
        axs[1].set_title("Now (scaled to range)", fontsize=10); axs[1].legend(fontsize=7)
        out["calib"] = _png(fig)
    return out


def write(state, cfg, proj, slots, disk_gb):
    runs = state["runs"]
    by = lambda st: {k: r for k, r in runs.items() if r["status"] in st}
    running, done, failed = by(("running", "stopping")), by(("done",)), by(("failed",))
    queued = len(state["queue"])
    warns = state.get("warnings", [])
    recent_err = [w for w in warns if w["level"] == "ERROR" and (_age_min(w["time"]) or 1e9) < 360]
    recent_warn = [w for w in warns if (_age_min(w["time"]) or 1e9) < 360]
    # health
    if state["status"] == "finished":
        health, hcls = f"Finished: {state.get('stop_reason', '')}", "fin"
    elif len(recent_err) >= 2 or disk_gb < cfg["min_free_disk_gb"]:
        health, hcls = (f"Problems: {len(recent_err)} errors in the last 6 h"
                        + (f", disk low ({disk_gb:.0f} GB)" if disk_gb < cfg["min_free_disk_gb"] else "")), "bad"
    elif recent_warn:
        health, hcls = f"Running, with {len(recent_warn)} warnings in the last 6 h", "warn"
    else:
        health, hcls = "All good: running normally", "ok"
    started = dt.datetime.strptime(state["started"], FMT)
    days = (dt.datetime.now() - started).total_seconds()/86400
    n_runs = sum(1 for r in runs.values() if r.get("tag") != "check")
    h = state["history"][-1] if state["history"] else None
    scores = {k: _score(r.get("summary"), cfg) for k, r in done.items()}
    best_run = min(scores, key=scores.get) if scores else None
    charts = _charts(state, cfg, proj)
    E = html.escape

    def tile(label, value, sub=""):
        return f'<div class="tile"><div class="tl">{E(label)}</div><div class="tv">{E(str(value))}</div><div class="ts">{E(sub)}</div></div>'

    rows = []
    for k, r in sorted(running.items()):
        t = r.get("t_sim_us", 0.0)
        age = _age_min(r.get("started", "")) or 0
        speed = t/(age/60) if age > 1 else 0
        steady = f"since {r['t_steady_us']:.0f} µs" if r.get("t_steady_us") is not None else "not yet"
        target = (r["t_steady_us"] + cfg["steady"]["stats_us"]) if r.get("t_steady_us") is not None \
            else cfg["case"]["end_time_cap"]*1e6
        eta = (target - t)/speed if speed > 0 else float("nan")
        prog_age = _age_min(r.get("last_progress", "")) or 0
        stale = ' class="warncell"' if prog_age > 15 else ""
        rows.append(f"<tr><td>{k}</td><td>{E(r.get('tag', ''))}</td><td>{r['status']}</td><td>{r.get('cpus', '')}</td>"
                    f"<td>{t:.1f}</td><td>{r.get('depth_now_um', 0):.0f}</td><td>{steady}</td>"
                    f"<td>{speed:.1f}</td><td>{eta:.1f} h</td><td{stale}>{prog_age:.0f} min ago</td></tr>")
    run_tbl = "".join(rows) or '<tr><td colspan="10">no running jobs</td></tr>'

    drows = []
    names = S.target_names(cfg)
    for k, r in sorted(done.items(), key=lambda kv: scores.get(kv[0], 1e9)):
        s = r["summary"]
        drows.append(f"<tr><td>{k}{' ★' if k == best_run else ''}</td><td>{E(r.get('tag', ''))}</td><td>{scores[k]:.1f}</td>"
                     + "".join(f"<td>{s[n]:.1f}</td>" for n in names)
                     + f"<td>{s['t_steady_us']:.0f}</td><td>{s.get('n_pores_end', 0)}</td></tr>")
    tgt_row = "<tr class='tgt'><td>Huang</td><td></td><td>0</td>" + "".join(
        f"<td>{cfg['targets'][n]['value']} ± {cfg['targets'][n]['tol']}</td>" for n in names) + "<td></td><td></td></tr>"
    done_tbl = tgt_row + ("".join(drows) or f'<tr><td colspan="{len(names) + 5}">none yet</td></tr>')

    frows = "".join(f"<tr><td>{k}</td><td>{E(r.get('tag', ''))}</td><td>{r.get('t_sim_us', 0):.1f}</td>"
                    f"<td>{E(str(r.get('reason', '')))}</td><td>{E(r.get('ended', ''))}</td></tr>"
                    for k, r in sorted(failed.items())) or '<tr><td colspan="5">none</td></tr>'
    wrows = "".join(f"<li class='{w['level'].lower()}'><b>{E(w['time'])}</b> {E(w['level'])}: {E(w['msg'][:300])}</li>"
                    for w in reversed(warns[-40:])) or "<li>none</li>"
    try:
        tl = open(os.path.join(proj, "driver.log")).read().splitlines()[-60:]
    except Exception:
        tl = []
    timeline = E("\n".join(reversed(tl)))

    if h:
        rngs = [(k["low"], k["high"]) for k in cfg["knobs"]]
        krows = "".join(
            f"<tr><td>{E(k['label'])} <code>{k['name']}</code></td><td>{k['low']:.4g} – {k['high']:.4g} {E(k['unit'])}</td>"
            f"<td>{h['best_params'][k['name']]:.4g}</td>"
            f"<td>{lo + m*(hi - lo):.4g} ± {s*(hi - lo):.2g}</td>"
            f"<td>{max(rv[j] for rv in h['relevance'].values()):.2f}</td></tr>"
            for j, (k, (lo, hi), m, s) in enumerate(zip(cfg["knobs"], rngs, h["mean"], h["std"])))
        calib = (f"<p>{E(h['msg'])}. Last update {E(h['time'])} with {h['n_done']} finished runs. "
                 f"Effective sample size {h['ess']:.0f}.</p>"
                 f"<table><tr><th>Knob</th><th>Range</th><th>Best</th><th>Estimate ± std</th><th>Relevance</th></tr>{krows}</table>"
                 + "<p class='note'>Relevance: how strongly the targets react to the knob over its range. "
                   "Below ~1 the knob barely matters and cannot be pinned down.</p>"
                 + "<table><tr><th>Target</th><th>Huang</th><th>Predicted at best</th></tr>"
                 + "".join(f"<tr><td>{n}</td><td>{cfg['targets'][n]['value']}</td><td>{p:.1f} ± {ps:.1f}</td></tr>"
                           for n, p, ps in zip(names, h["best_pred"], h["best_pred_std"])) + "</table>")
    else:
        calib = "<p>No surrogate yet: needs 6 finished runs.</p>"

    img = lambda k: f'<img src="{charts[k]}" alt="{k}">' if k in charts else ""
    gen = dt.datetime.now().strftime(FMT)
    doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="60">
<title>Keyhole Calibration</title>
<style>
:root {{ --bg:#f6f7f9; --card:#fff; --ink:#1d2330; --mute:#5b6475; --line:#dde1e8;
  --ok:#1f7a4d; --okbg:#e3f4ea; --warn:#8a5a00; --warnbg:#fff3d6; --bad:#a1161b; --badbg:#fde4e4; --fin:#1d4ed8; --finbg:#e0e9ff; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --bg:#14171c; --card:#1d2128; --ink:#e7eaf0; --mute:#9aa3b2;
  --line:#2c323c; --okbg:#173a28; --ok:#7fd8a6; --warnbg:#3d3010; --warn:#ffd27a; --badbg:#47181a; --bad:#ff9a9e; --finbg:#1b2a4d; --fin:#9dbbff; }} }}
:root[data-theme="dark"] {{ --bg:#14171c; --card:#1d2128; --ink:#e7eaf0; --mute:#9aa3b2; --line:#2c323c; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font-family: Arial, Helvetica, sans-serif; font-size:14px; }}
main {{ max-width:1200px; margin:0 auto; padding:16px; }}
h1 {{ font-size:20px; margin:4px 0 2px; }} h2 {{ font-size:16px; margin:22px 0 8px; }}
.sub {{ color:var(--mute); }}
.banner {{ padding:12px 14px; border-radius:8px; font-weight:bold; margin:12px 0; }}
.ok {{ background:var(--okbg); color:var(--ok); }} .warn {{ background:var(--warnbg); color:var(--warn); }}
.bad {{ background:var(--badbg); color:var(--bad); }} .fin {{ background:var(--finbg); color:var(--fin); }}
.tiles {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; }}
.tile {{ background:var(--card); border:1px solid var(--line); border-radius:8px; padding:10px; }}
.tl {{ color:var(--mute); font-size:12px; }} .tv {{ font-size:22px; font-weight:bold; margin-top:4px; }} .ts {{ color:var(--mute); font-size:12px; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:8px; padding:12px; overflow-x:auto; }}
table {{ border-collapse:collapse; width:100%; font-size:13px; }}
th, td {{ border-bottom:1px solid var(--line); padding:5px 8px; text-align:left; white-space:nowrap; }}
th {{ color:var(--mute); font-weight:normal; }}
tr.tgt td {{ font-weight:bold; }} td.warncell {{ color:var(--warn); font-weight:bold; }}
img {{ max-width:100%; height:auto; background:#fff; border-radius:6px; }}
ul.w {{ margin:0; padding-left:18px; }} li.error {{ color:var(--bad); }} li.warn {{ color:var(--warn); }}
pre {{ font-size:12px; white-space:pre-wrap; margin:0; max-height:420px; overflow:auto; }}
.note {{ color:var(--mute); font-size:12px; }}
#stale {{ display:none; }}
</style></head><body><main>
<h1>Keyhole calibration — Huang Al 500 W</h1>
<div class="sub">Updated {gen} · driver status: {E(state['status'])} · started {E(state['started'])} ({days:.1f} days ago)</div>
<div id="stale" class="banner bad">This page has not been updated for over 10 minutes: the driver may have stopped.</div>
<div class="banner {hcls}">{E(health)}</div>
<div class="tiles">
{tile("Running", len(running), f"of {len(slots)} slots")}
{tile("Done", len(done), "finished runs")}
{tile("Failed", len(failed), "crash / NaN / stall")}
{tile("Queued", queued, "waiting to start")}
{tile("Budget", f"{days:.1f} / {cfg['stop']['max_days']:.0f} d", f"{n_runs} / {cfg['stop']['max_runs']} runs")}
{tile("Best run", best_run or "—", f"score {scores[best_run]:.1f}" if best_run else "")}
{tile("Disk free", f"{disk_gb:.0f} GB", f"min {cfg['min_free_disk_gb']} GB")}
{tile("Cores in use", len(running)*cfg['cores']['cores_per_job'], f"max {cfg['cores']['max_cores']}")}
</div>
<h2>Running jobs</h2>
<div class="card"><table><tr><th>Run</th><th>Tag</th><th>Status</th><th>CPUs</th><th>Sim time [µs]</th><th>Depth now [µm]</th>
<th>Steady</th><th>Speed [µs/h]</th><th>ETA</th><th>Last progress</th></tr>{run_tbl}</table></div>
<h2>Keyhole depth</h2><div class="card">{img("depth")}</div>
<h2>Calibration</h2><div class="card">{img("calib")}{calib}</div>
<h2>Finished runs (best first; score = sum of squared misses in tolerance units)</h2>
<div class="card"><table><tr><th>Run</th><th>Tag</th><th>Score</th>{"".join(f"<th>{n}</th>" for n in names)}<th>Steady from [µs]</th><th>Pores</th></tr>{done_tbl}</table></div>
<h2>Failed runs</h2>
<div class="card"><table><tr><th>Run</th><th>Tag</th><th>Stopped at [µs]</th><th>Reason</th><th>When</th></tr>{frows}</table></div>
<h2>Warnings and errors</h2><div class="card"><ul class="w">{wrows}</ul></div>
<h2>Driver timeline (newest first)</h2><div class="card"><pre>{timeline}</pre></div>
<p class="note">Files: state.json, driver.log, runs/run_NNN/, surrogate_history/, results.md (at the end). Config: config.json.</p>
</main>
<script>
const gen = new Date("{gen.replace(' ', 'T')}");
if ((Date.now() - gen.getTime()) > 10*60*1000) document.getElementById("stale").style.display = "block";
</script>
</body></html>"""
    tmp = os.path.join(proj, "dashboard.html.tmp")
    with open(tmp, "w") as f:
        f.write(doc)
    os.replace(tmp, os.path.join(proj, "dashboard.html"))
