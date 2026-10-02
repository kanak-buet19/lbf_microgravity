#!/usr/bin/env python
"""Unattended calibration driver (project 03).

Started once by the user (run_calibration.sh, inside tmux). Every POLL seconds:
  1. For each running job: post-process new writes (X-ray frame every
     xray.frame_us, ML window every write), delete bulk field writes that are
     no longer needed, follow the log (sim time, NaN, FATAL), detect stalls,
     detect steady depth and stop the job once enough steady data exists.
  2. A job that ends gets a summary (steady statistics) or a failure reason.
  3. After each new result: refit the surrogate, update the calibration,
     test convergence.
  4. Fill free CPU slots: initial design first, then surrogate proposals,
     finally one check run at the best parameters.
  5. Write dashboard.html, state.json; back up every few hours.
Stopping the driver (Ctrl+C) leaves running jobs alone; starting it again
re-attaches to them and resumes stopped jobs from their last write.

The driver runs blockMesh, setFields, decomposePar and the solver through a
per-run run.sh. It is started by the user, never by Claude.

Usage: driver.py [--config config.json] [--once] [--stop-all] [--dry]
  --once      one pass, then exit (testing)
  --stop-all  stop every running job and exit
  --dry       no jobs are started (shows what would happen)
"""
import argparse
import datetime as dt
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import traceback

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import foamio      # noqa: E402
import make_case   # noqa: E402
import postpro     # noqa: E402
import surrogate as S  # noqa: E402

POLL = 30            # s between passes
NAN_RE = re.compile(r"(?<![A-Za-z])nan(?![A-Za-z])|FOAM FATAL|Floating point exception|Segmentation fault",
                     re.IGNORECASE)
TIME_RE = re.compile(r"^Time = ([0-9.eE+-]+)", re.M)

RUN_SH = """#!/bin/bash
# Written by driver.py. Fresh start or resume from the latest write.
cd "$(dirname "$0")" || exit 1
unset OMP_NUM_THREADS
latest=$(ls -1 processor0 2>/dev/null | grep -E '^[0-9][0-9.eE+-]*$' | sort -g | tail -1)
if [ -n "$latest" ] && awk -v t="$latest" 'BEGIN {{exit !(t > 0)}}'
then
    echo "resume from $latest" >> run.events
    if [ -f log.{solver} ]
    then
        n=1; while [ -e log.{solver}.$n ]; do n=$((n + 1)); done
        mv log.{solver} log.{solver}.$n
    fi
else
    echo "fresh start" >> run.events
    rm -rf 0 processor[0-9]* && cp -r initial 0
    blockMesh > log.blockMesh 2>&1 \\
 && setFields > log.setFields 2>&1 \\
 && decomposePar > log.decomposePar 2>&1 \\
 || {{ echo 90 > exit_code; exit 90; }}
fi
rm -f exit_code
taskset -c {cpus} mpirun {mpi} -np {np} {solver} -parallel > log.{solver} 2>&1
echo $? > exit_code
"""


# ---------------------------------------------------------------- utilities

def now():
    return dt.datetime.now()


def stamp():
    return now().strftime("%Y-%m-%d %H:%M:%S")


class Driver:
    def __init__(self, cfg_path, dry=False):
        self.cfg_path = os.path.abspath(cfg_path)
        self.cfg = json.load(open(self.cfg_path))
        self.dry = dry
        # --dry keeps its own runs folder and state, so a real start later
        # never sees the fake "queued" jobs
        sfx = "_dry" if dry else ""
        self.runs_dir = os.path.join(PROJ, self.cfg["runs_dir"] + sfx)
        self.state_path = os.path.join(PROJ, f"state{sfx}.json")
        self.log_path = os.path.join(PROJ, "driver.log")
        os.makedirs(self.runs_dir, exist_ok=True)
        self.state = self.load_state()
        self.offsets = {}          # log read offsets (memory only)
        self.procs = {}            # Popen handles of jobs started by this driver
        self.sur = None
        self.post = None
        self.last_dash = 0.0

    # ------------------------------------------------------------ state
    def load_state(self):
        if os.path.exists(self.state_path):
            return json.load(open(self.state_path))
        st = {"started": stamp(), "status": "running", "stop_reason": "",
              "runs": {}, "queue": [], "history": [], "warnings": [],
              "n_proposed": 0, "last_backup": "", "check_run": None}
        for p, tag in S.initial_design(self.cfg):
            st["queue"].append({"params": p, "tag": tag})
        return st

    def save_state(self):
        tmp = self.state_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.state, f, indent=1, default=float)
        os.replace(tmp, self.state_path)

    def log(self, msg, level="INFO"):
        line = f"[{stamp()}] {level:5s} {msg}"
        print(line, flush=True)
        with open(self.log_path, "a") as f:
            f.write(line + "\n")
        if level in ("WARN", "ERROR"):
            self.state["warnings"].append({"time": stamp(), "level": level, "msg": msg})
            self.state["warnings"] = self.state["warnings"][-200:]

    # ------------------------------------------------------------ checks
    def preflight(self):
        missing = [c for c in (self.cfg["solver"], "blockMesh", "setFields", "decomposePar",
                               "mpirun", "taskset") if not shutil.which(c)]
        if missing:
            raise SystemExit("not found on PATH: " + ", ".join(missing)
                             + "  (load OpenFOAM v2512 and build the solver first)")
        tmpl = os.path.join(PROJ, self.cfg["template"])
        if not os.path.isdir(tmpl):
            raise SystemExit(f"template folder missing: {tmpl}")

    def free_disk_gb(self):
        return shutil.disk_usage(PROJ).free/1e9

    # ------------------------------------------------------------ slots
    def slots(self):
        c = self.cfg["cores"]
        n = c["max_cores"]//c["cores_per_job"]
        return [f"{c['first_cpu'] + i*c['cores_per_job']}-{c['first_cpu'] + (i + 1)*c['cores_per_job'] - 1}"
                for i in range(n)]

    def running(self):
        return {k: r for k, r in self.state["runs"].items() if r["status"] in ("running", "stopping")}

    # ------------------------------------------------------------ jobs
    def new_run_id(self):
        return f"run_{len(self.state['runs']) + 1:03d}"

    def start_run(self, rid, cpus):
        r = self.state["runs"][rid]
        d = os.path.join(self.runs_dir, rid)
        c = self.cfg["cores"]
        if not os.path.isdir(d):
            make_case.make_case(d, r["params"], self.cfg, c["cores_per_job"])
            with open(os.path.join(d, "run.sh"), "w") as f:
                f.write(RUN_SH.format(solver=self.cfg["solver"], cpus=cpus,
                                      mpi=" ".join(c["mpirun_extra"]), np=c["cores_per_job"]))
            os.chmod(os.path.join(d, "run.sh"), 0o755)
        if self.dry:
            self.log(f"{rid}: DRY, would start on CPUs {cpus}")
            return
        p = subprocess.Popen(["bash", os.path.join(d, "run.sh")], cwd=d,
                             stdout=open(os.path.join(d, "run.out"), "a"),
                             stderr=subprocess.STDOUT, start_new_session=True)
        self.procs[rid] = p
        r.update(status="running", cpus=cpus, pgid=p.pid, last_progress=stamp(),
                 started=r.get("started") or stamp())
        self.offsets[rid] = 0
        self.log(f"{rid}: started on CPUs {cpus} ({r['tag']}) "
                 + ", ".join(f"{k}={v:.4g}" for k, v in r["params"].items()))

    def alive(self, r, rid=None):
        """Job still running? Own children are polled (reaps them, so they
        never linger as zombies); jobs from an earlier driver are looked up
        in /proc (zombie = ended)."""
        p = self.procs.get(rid)
        if p is not None:
            return p.poll() is None
        pid = r.get("pgid")
        if not pid:
            return False
        try:
            st = open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split()[0]
            return st != "Z"
        except (FileNotFoundError, IndexError, ProcessLookupError):
            return False

    def kill(self, rid, why):
        r = self.state["runs"][rid]
        r["status"] = "stopping"; r["stop_why"] = why
        try:
            os.killpg(r["pgid"], signal.SIGTERM)
        except ProcessLookupError:
            pass
        self.log(f"{rid}: stopping ({why})")

    # ------------------------------------------------------------ per run
    def times(self, d):
        try:
            return foamio.times(d)
        except FileNotFoundError:
            return []

    def follow_log(self, rid, d):
        """New log text since last pass: update sim time, catch NaN/FATAL."""
        lp = os.path.join(d, f"log.{self.cfg['solver']}")
        if not os.path.exists(lp):
            return None
        size = os.path.getsize(lp)
        off = self.offsets.get(rid, 0)
        if size < off:
            off = 0
        with open(lp, errors="replace") as f:
            f.seek(off); chunk = f.read()
        self.offsets[rid] = size
        r = self.state["runs"][rid]
        ts = TIME_RE.findall(chunk)
        if ts:
            t = float(ts[-1])*1e6
            if t > r.get("t_sim_us", 0) + 1e-6:
                r["last_progress"] = stamp()
                r["progress_t_us"] = t
            r["t_sim_us"] = t
        m = NAN_RE.search(chunk)
        if m:
            i = chunk.rfind("\n", 0, m.start())
            j = chunk.find("\n", m.end())
            return chunk[i + 1:j if j > 0 else None].strip()[:200]
        return None

    def process_writes(self, rid, d, final=False):
        """Post-process saved times (all but the newest unless final)."""
        cfg = self.cfg
        done_file = os.path.join(d, "processed.txt")
        done = set(open(done_file).read().split()) if os.path.exists(done_file) else set()
        ts = self.times(d)
        todo = [t for t in (ts if final else ts[:-1]) if t not in done]
        fr_path = os.path.join(d, "xray_frames.json")
        frames = json.load(open(fr_path)) if os.path.exists(fr_path) else []
        ml_dir = os.path.join(d, "ml_window")
        fu = cfg["xray"]["frame_us"]; ku = cfg["keep_fields_every_us"]
        for tn in todo:
            t_us = float(tn)*1e6
            try:
                if cfg["ml_window"]["enabled"]:
                    os.makedirs(ml_dir, exist_ok=True)
                    postpro.ml_window(d, tn, cfg, os.path.join(ml_dir, f"w_{t_us:09.3f}us.npz"))
                if abs(t_us/fu - round(t_us/fu)) < 1e-3:
                    f = postpro.xray_frame(d, tn, cfg)
                    f["row_len_um"] = [round(float(v), 2) for v in f["row_len_um"]]
                    frames.append(f)
            except Exception as e:
                self.log(f"{rid}: post-processing {tn} failed: {e}", "WARN")
            done.add(tn)
            keep = abs(t_us/ku - round(t_us/ku)) < 1e-3 or tn == ts[-1]
            if not keep:
                for pd in [os.path.join(d, p) for p in os.listdir(d) if p.startswith("processor")]:
                    shutil.rmtree(os.path.join(pd, tn), ignore_errors=True)
        if todo:
            frames.sort(key=lambda f: f["t_us"])
            with open(fr_path, "w") as f:
                json.dump(frames, f)
            with open(done_file, "w") as f:
                f.write("\n".join(sorted(done, key=float)))
        return frames

    def finish_run(self, rid, d, frames):
        """Job ended: decide done / failed, write summary.json."""
        r = self.state["runs"][rid]
        ec_path = os.path.join(d, "exit_code")
        ec = open(ec_path).read().strip() if os.path.exists(ec_path) else "?"
        st = self.cfg["steady"]
        ts = postpro.steady_state([f["t_us"] for f in frames], [f["depth_um"] for f in frames], st)
        why = r.get("stop_why", "")
        # exit code 0 = the solver reached endTime by itself (the cap)
        if why.startswith("steady") or (ec == "0" and not why):
            if ts is None:
                ts = max(0.0, frames[-1]["t_us"] - st["stats_us"]) if frames else 0.0
                r["flag"] = "never steady (stats from the last stats_us)"
            summ = postpro.summary(frames, ts) if frames else None
            if summ:
                r["status"] = "done"; r["summary"] = summ
                with open(os.path.join(d, "summary.json"), "w") as f:
                    json.dump(summ, f, indent=1)
                self.log(f"{rid}: done, depth {summ['depth_mean_um']:.0f} ± {summ['depth_std_um']:.0f} um "
                         f"(steady from {summ['t_steady_us']:.0f} us)")
            else:
                r["status"] = "failed"; r["reason"] = "no X-ray frames"
                self.log(f"{rid}: failed (no X-ray frames)", "ERROR")
        else:
            reason = why or r.get("fail_hint") or f"solver exit code {ec}"
            if ec == "90":
                reason = "mesh/setFields/decomposePar failed (see log.blockMesh etc.)"
            r["status"] = "failed"; r["reason"] = reason
            self.log(f"{rid}: failed at t = {r.get('t_sim_us', 0):.1f} us: {reason}", "ERROR")
        r["ended"] = stamp()
        self.gzip_logs(d)
        return r["status"] == "done"

    def gzip_logs(self, d):
        for f in os.listdir(d):
            if f.startswith(f"log.{self.cfg['solver']}") and not f.endswith(".gz"):
                subprocess.run(["gzip", "-f", os.path.join(d, f)], check=False)

    def check_run(self, rid):
        """One pass for one running job. Returns True if a new result arrived."""
        r = self.state["runs"][rid]
        d = os.path.join(self.runs_dir, rid)
        alive = self.alive(r, rid)
        bad = self.follow_log(rid, d)
        frames = self.process_writes(rid, d, final=not alive)
        if frames:
            r["depth_now_um"] = frames[-1]["depth_um"]
        if bad:
            r["fail_hint"] = bad[:200]
        if not alive:
            return self.finish_run(rid, d, frames)
        if r["status"] == "stopping":
            return False
        if bad:
            self.kill(rid, f"NaN/FATAL in log: {bad[:120]}")
            return False
        last = dt.datetime.strptime(r["last_progress"], "%Y-%m-%d %H:%M:%S")
        if (now() - last).total_seconds() > 60*self.cfg["stall_minutes"]:
            self.kill(rid, f"stalled: no progress for {self.cfg['stall_minutes']} min")
            return False
        st = self.cfg["steady"]
        ts = postpro.steady_state([f["t_us"] for f in frames], [f["depth_um"] for f in frames], st)
        if ts is not None:
            r["t_steady_us"] = ts
            if frames[-1]["t_us"] >= ts + st["stats_us"]:
                self.kill(rid, f"steady since {ts:.0f} us, {st['stats_us']:.0f} us of steady data collected")
        return False

    # ------------------------------------------------------------ surrogate
    def done_data(self):
        names = S.target_names(self.cfg)
        rs = [r for r in self.state["runs"].values() if r["status"] == "done" and r.get("tag") != "check"]
        if not rs:
            return None, None
        X = S.scale(self.cfg, [r["params"] for r in rs])
        Y = np.array([[r["summary"][n] for n in names] for r in rs])
        return X, Y

    def failed_U(self):
        rs = [r for r in self.state["runs"].values() if r["status"] == "failed"
              and not str(r.get("reason", "")).startswith("mesh")]
        return S.scale(self.cfg, [r["params"] for r in rs]) if rs else []

    def update_surrogate(self):
        X, Y = self.done_data()
        if X is None or len(X) < 6:
            return
        self.sur = S.Surrogate(self.cfg).fit(X, Y)
        self.post = self.sur.posterior(self.failed_U())
        rel = self.sur.relevance()
        ok, msg = S.converged(self.cfg, self.post, rel, len(X))
        if msg.startswith("no knob"):
            self.log(msg, "WARN")
        # must hold for 3 updates in a row (guards against an early, wrong fit)
        prev = [hh["converged_raw"] for hh in self.state["history"][-2:]]
        raw = ok
        ok = raw and len(prev) == 2 and all(prev)
        if raw and not ok:
            msg += " (needs 3 updates in a row)"
        h = {"time": stamp(), "n_done": int(len(X)),
             "mean": self.post["mean"].tolist(), "std": self.post["std"].tolist(),
             "best": self.post["best"].tolist(), "best_params": S.unscale(self.cfg, self.post["best"]),
             "best_pred": self.post["best_pred"].tolist(),
             "best_pred_std": self.post["best_pred_std"].tolist(),
             "ess": self.post["ess"], "relevance": rel, "noise": self.sur.noise(),
             "converged": ok, "converged_raw": raw, "msg": msg}
        self.state["history"].append(h)
        snap = os.path.join(PROJ, "surrogate_history"); os.makedirs(snap, exist_ok=True)
        with open(os.path.join(snap, f"update_{len(self.state['history']):03d}.json"), "w") as f:
            json.dump(h, f, indent=1)
        self.log(f"surrogate updated ({len(X)} runs): {msg}")
        if ok and not self.state.get("check_run"):
            self.state["check_run"] = "queued"
            self.state["queue"].insert(0, {"params": h["best_params"], "tag": "check"})
            self.log("converged: check run at the best parameters queued")

    def next_job(self):
        """Pop or propose the next job (dict) or None."""
        if self.state["queue"]:
            return self.state["queue"].pop(0)
        if self.state.get("check_run"):
            return None                      # converged: no more proposals
        if self.sur is None:
            return None                      # wait for enough finished runs
        taken = [S.scale(self.cfg, r["params"])[0] for r in self.state["runs"].values()]
        k = self.state["n_proposed"]
        explore = (k % 8 == 7)
        u = self.sur.propose(self.post, taken, explore=explore, seed=k)
        self.state["n_proposed"] += 1
        return {"params": S.unscale(self.cfg, u), "tag": "explore" if explore else "proposed"}

    def budget_left(self):
        st = self.cfg["stop"]
        started = dt.datetime.strptime(self.state["started"], "%Y-%m-%d %H:%M:%S")
        days = (now() - started).total_seconds()/86400
        n = sum(1 for r in self.state["runs"].values() if r.get("tag") != "check")
        if days >= st["max_days"]:
            return False, f"time budget reached ({days:.1f} d)"
        if n >= st["max_runs"]:
            return False, f"run budget reached ({n} runs)"
        return True, ""

    def fill_slots(self):
        if self.state["status"] != "running":
            return
        if self.free_disk_gb() < self.cfg["min_free_disk_gb"]:
            self.log(f"disk low ({self.free_disk_gb():.0f} GB free): no new jobs", "WARN")
            return
        busy = {r["cpus"] for r in self.running().values()}
        for cpus in self.slots():
            if cpus in busy:
                continue
            ok, why = self.budget_left()
            job = None
            if ok or (self.state["queue"] and self.state["queue"][0]["tag"] == "check"):
                job = self.next_job()
            if job is None:
                return
            rid = self.new_run_id()
            self.state["runs"][rid] = {"params": job["params"], "tag": job["tag"],
                                       "status": "queued", "created": stamp()}
            if job["tag"] == "check":
                self.state["check_run"] = rid
            try:
                self.start_run(rid, cpus)
            except Exception as e:
                self.state["runs"][rid].update(status="failed", reason=f"could not start: {e}")
                self.log(f"{rid}: could not start: {e}", "ERROR")
            busy.add(cpus)

    # ------------------------------------------------------------ end
    def maybe_finish(self):
        if self.state["status"] != "running" or self.running():
            return
        cr = self.state.get("check_run")
        ok, why = self.budget_left()
        if cr and cr != "queued" and self.state["runs"][cr]["status"] in ("done", "failed"):
            self.state["status"] = "finished"; self.state["stop_reason"] = "converged, check run finished"
        elif not ok and not self.state["queue"]:
            self.state["status"] = "finished"; self.state["stop_reason"] = why
        else:
            return
        self.log(f"calibration finished: {self.state['stop_reason']}")
        self.write_results()

    def write_results(self):
        import report
        report.write_results(self.state, self.cfg, PROJ)
        self.log("wrote results.md")

    def backup(self):
        h = self.cfg["backup_every_hours"]
        last = self.state.get("last_backup")
        if last and (now() - dt.datetime.strptime(last, "%Y-%m-%d %H:%M:%S")).total_seconds() < 3600*h:
            return
        dst = os.path.join(PROJ, self.cfg["backup_dir"], now().strftime("%Y%m%d_%H%M%S"))
        os.makedirs(dst, exist_ok=True)
        for f in ("state.json", "driver.log", "results.md", "dashboard.html", "config.json"):
            if os.path.exists(os.path.join(PROJ, f)):
                shutil.copy2(os.path.join(PROJ, f), dst)
        for rid in self.state["runs"]:
            for f in ("params.json", "summary.json", "xray_frames.json"):
                src = os.path.join(self.runs_dir, rid, f)
                if os.path.exists(src):
                    os.makedirs(os.path.join(dst, rid), exist_ok=True)
                    shutil.copy2(src, os.path.join(dst, rid))
        old = sorted(os.listdir(os.path.join(PROJ, self.cfg["backup_dir"])))
        for o in old[:-8]:
            shutil.rmtree(os.path.join(PROJ, self.cfg["backup_dir"], o), ignore_errors=True)
        self.state["last_backup"] = stamp()
        self.log(f"backup written to {dst}")

    def dashboard(self, force=False):
        if not force and time.time() - self.last_dash < 60*self.cfg["dashboard_every_minutes"]:
            return
        import dashboard
        try:
            dashboard.write(self.state, self.cfg, PROJ, self.slots(), self.free_disk_gb())
        except Exception as e:
            self.log(f"dashboard failed: {e}", "WARN")
        self.last_dash = time.time()

    # ------------------------------------------------------------ loop
    def one_pass(self):
        new = False
        for rid in list(self.running()):
            try:
                new |= bool(self.check_run(rid))
            except Exception as e:
                self.log(f"{rid}: check failed: {e}\n{traceback.format_exc()}", "ERROR")
        if new or (self.sur is None and self.done_data()[0] is not None):
            try:
                self.update_surrogate()
            except Exception as e:
                self.log(f"surrogate update failed: {e}\n{traceback.format_exc()}", "ERROR")
        # resume jobs that were running when the driver stopped (no process now)
        self.fill_slots()
        self.maybe_finish()
        self.save_state()
        self.dashboard(force=new)
        self.backup()

    def reattach(self):
        """On start: running jobs whose process is gone are resumed."""
        for rid, r in self.running().items():
            if not self.alive(r, rid):
                d = os.path.join(self.runs_dir, rid)
                if os.path.exists(os.path.join(d, "exit_code")) or r["status"] == "stopping":
                    continue          # ended while the driver was away: finished next pass
                self.log(f"{rid}: process gone while driver was down, resuming")
                r.setdefault("resumes", 0); r["resumes"] += 1
                self.start_run(rid, r["cpus"])
            else:
                self.log(f"{rid}: still running, re-attached")

    def stop_all(self):
        for rid in list(self.running()):
            self.kill(rid, "stopped by user (--stop-all)")
        self.save_state()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", default=os.path.join(PROJ, "config.json"))
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--stop-all", action="store_true")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    drv = Driver(a.config, dry=a.dry)
    if a.stop_all:
        drv.stop_all(); return
    if not a.dry:
        drv.preflight()
    drv.log(f"driver start (status {drv.state['status']}, {len(drv.state['runs'])} runs so far, "
            f"{len(drv.slots())} slots: {', '.join(drv.slots())})")
    drv.reattach()
    try:
        drv.update_surrogate()
    except Exception as e:
        drv.log(f"surrogate update failed: {e}", "ERROR")
    while True:
        drv.one_pass()
        if a.once or drv.state["status"] != "running":
            drv.dashboard(force=True)
            break
        time.sleep(POLL)


if __name__ == "__main__":
    main()
