#!/usr/bin/env python3
"""Live terminal dashboard for a running compressibleLaserbeamFoam case.

The solver prints a long block of lines every time step. This script follows
the solver log (read-only) and redraws one fixed screen with the latest
values: progress and finish estimate, laser, fields, phase masses, mesh,
numerics and warnings. The log file itself is never changed.

Display:
  - rich (Python terminal-layout library) installed and output is a
    terminal: full panel dashboard, redrawn in place.
  - otherwise (no rich, or output redirected to a file): one plain status
    line per refresh.

Usage (from the case folder):
  python3 rundash.py                       # follow log.compressibleLaserbeamFoam
  python3 rundash.py --pid 12345           # exit when that process exits
  python3 rundash.py --once                # print one snapshot and exit
  python3 rundash.py --plain               # force the plain one-line output
  python3 rundash.py -c <case> -l <log>    # other case folder / log name

Allrun usage: start the solver in the background with its output sent to the
log, then call this script with --pid. See
project/01_Al_keyholePore_validation/case/AL_500W_600mms_50um_bp/Allrun.

The script must never stop or slow down a run: every Allrun call is written
so that a failure here only loses the display.
"""

import argparse
import collections
import os
import re
import sys
import time

FLOAT = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?|[-+]?nan|[-+]?inf"
NUM = re.compile(FLOAT, re.IGNORECASE)


def nums(line):
    """All numbers in a line, as floats."""
    return [float(x) for x in NUM.findall(line)]


# ---------------------------------------------------------------------------
# Case settings read from the case dictionaries (simple regex, no OpenFOAM)
# ---------------------------------------------------------------------------

def read_entry(path, key):
    """First scalar value of `key` in an OpenFOAM dictionary file, or None."""
    try:
        with open(path) as f:
            text = re.sub(r"//.*", "", f.read())
    except OSError:
        return None
    m = re.search(r"^\s*" + re.escape(key) + r"\s+(" + FLOAT + r")\s*;",
                  text, re.MULTILINE)
    return float(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# Log state
# ---------------------------------------------------------------------------

class RunState:
    """Latest values parsed from the solver log."""

    def __init__(self, case):
        self.case = case
        self.end_time = read_entry(os.path.join(case, "system/controlDict"), "endTime")
        self.write_interval = read_entry(os.path.join(case, "system/controlDict"),
                                         "writeInterval")
        self.max_T_corr = read_entry(os.path.join(case, "system/fvSolution"),
                                     "maxTempCorrector")

        self.header = {}            # Exec, Case, nProcs, PID, Date, Time
        self.started = False        # "Starting time loop" seen
        self.finished = False       # "End" seen
        self.fatal = []             # FOAM FATAL lines (and the next few)
        self.warnings = collections.deque(maxlen=4)
        self.nan_seen = None

        self.steps = 0
        self.t = None
        self.dt = None
        self.co = (None, None)      # mean, max
        self.alpha_co = (None, None)
        self.clock = None           # ClockTime [s]
        self.exec_time = None
        self.history = collections.deque(maxlen=200)    # (clock, t)

        self.laser_pos = None
        self.laser_power = None
        self.laser_q = None
        self.n_rays = None

        self.max_U = None
        self.p_rgh = (None, None)
        self.min_T = None
        self.max_T = None           # only with a fieldMinMax function object on T
        self.vdot_dt = None

        self.mass = collections.OrderedDict()
        self.mass0 = {}
        self.alpha = collections.OrderedDict()   # name -> (min, max, avg)
        self.closure_dev = None
        self.capped_cells = None

        self.cells = None
        self.last_amr = None

        # Evaporation: "(liquid,vapour)  Tboil=..." and "integrated evap = ..."
        self.pairs = []
        self.evap = None            # [kg/s]
        self.cond = None            # [kg/s], <= 0
        self.clamped = None         # ENERGY/MASS/VOLUME clamped cells

        self.res = collections.OrderedDict()     # field -> first initial residual of step
        self.n_T_solves = 0
        self.T_corr_last = None
        self.eps_max_res = None
        self.cont_cum = None

        self._in_mass = False
        self._fatal_lines = 0

    # -- parsing -----------------------------------------------------------

    def feed(self, line):
        s = line.strip()
        if not s:
            self._in_mass = False
            return

        if self._fatal_lines > 0:
            self.fatal.append(s)
            self._fatal_lines -= 1
            return
        if "FOAM FATAL" in s:
            self.fatal.append(s)
            self._fatal_lines = 6
            return
        if "FOAM Warning" in s or s.startswith("--> FOAM Warning"):
            self.warnings.append(s)
            return

        if not self.started:
            m = re.match(r"^(Exec|Case|nProcs|PID|Date|Time)\s*:\s*(.*)$", s)
            if m:
                self.header[m.group(1)] = m.group(2)
            if s.startswith("Starting time loop"):
                self.started = True
            m = re.match(r"^Number of cells\s*=?\s*(\d+)", s)
            return

        if s == "End":
            self.finished = True
            return

        # Mass block: "Conserved partial-mass(...):" then "    name = x kg"
        if s.startswith("Conserved partial-mass"):
            self._in_mass = True
            return
        if self._in_mass:
            m = re.match(r"^(\S+)\s*=\s*(" + FLOAT + r")\s*kg", s)
            if m:
                name, val = m.group(1), float(m.group(2))
                self.mass[name] = val
                self.mass0.setdefault(name, val)
                return
            self._in_mass = False

        if s.startswith("Time = "):
            self.steps += 1
            self.t = nums(s)[0]
            if self.n_T_solves:
                self.T_corr_last = self.n_T_solves
            self.n_T_solves = 0
            self.res = collections.OrderedDict()
            return
        if s.startswith("deltaT = "):
            self.dt = nums(s)[0]
            return
        if s.startswith("Courant Number"):
            v = nums(s)
            self.co = (v[0], v[1])
            return
        if s.startswith("Interface Courant Number"):
            v = nums(s)
            self.alpha_co = (v[0], v[1])
            return
        if s.startswith("ExecutionTime"):
            v = nums(s)
            self.exec_time, self.clock = v[0], v[1]
            if self.t is not None:
                self.history.append((self.clock, self.t))
            return

        # Laser (laserHeatSource prints these with leading spaces)
        if s.startswith("mean position"):
            self.laser_pos = nums(s)[:3]
            return
        if s.startswith("power ="):
            self.laser_power = nums(s)[0]
            return
        if s.startswith("Total Q deposited"):
            self.laser_q = nums(s)[0]
            return
        if s.startswith("Total rays"):
            self.n_rays = int(nums(s)[0])
            return

        if s.startswith("max(U)"):
            self.max_U = nums(s)[0]
            return
        if s.startswith("min,max(p_rgh)"):
            v = nums(s)
            self.p_rgh = (v[0], v[1])
            return
        m = re.match(r"^max\(T\) = (" + FLOAT + r")", s)
        if m:
            self.max_T = float(m.group(1))
            return
        if s.startswith("min(T)"):
            self.min_T = nums(s)[0]
            return
        if s.startswith("max|vDot|*dt"):
            self.vdot_dt = nums(s)[0]
            return

        m = re.match(r"^(\S+) alpha min/max/avg = (.*)$", s)
        if m:
            v = nums(m.group(2))
            self.alpha[m.group(1)] = tuple(v[:3])
            return
        if s.startswith("volume closure defect"):
            self.closure_dev = nums(s)[-1]
            return
        if s.startswith("closure feedback"):
            m = re.search(r"capped cells = (\d+)", s)
            if m:
                self.capped_cells = int(m.group(1))
            return

        # Evaporation pair and rates (multiphaseMixtureThermo::solve)
        m = re.match(r"^\((\w+),(\w+)\)\s+Tboil=", s)
        if m:
            pair = "%s -> %s" % (m.group(1), m.group(2))
            if pair not in self.pairs:
                self.pairs.append(pair)
            c = re.search(r"(\d+)/(\d+)/(\d+)\s*$", s)
            if c:
                self.clamped = "/".join(c.groups())
            return
        if s.startswith("integrated evap"):
            v = nums(s)
            self.evap, self.cond = v[0], v[1]
            return

        # Mesh refinement (dynamicRefineFvMesh)
        m = re.match(r"^Selected (\d+) cells for refinement out of (\d+)", s)
        if m:
            self.cells = int(m.group(2))
            self.last_amr = "refine %s cells (t = %s)" % (m.group(1), fmt_time(self.t))
            return
        m = re.match(r"^(Refined|Unrefined) from (\d+) to (\d+) cells", s)
        if m:
            self.cells = int(m.group(3))
            self.last_amr = "%s %s -> %s (t = %s)" % (
                m.group(1).lower(), m.group(2), m.group(3), fmt_time(self.t))
            return

        # Linear solvers: keep the first initial residual of each field per step
        m = re.match(r"^\S+:\s+Solving for (\S+), Initial residual = (" + FLOAT +
                     r"), Final residual = (" + FLOAT + r"), No Iterations (\d+)", s)
        if m:
            field = m.group(1)
            if field == "T":
                self.n_T_solves += 1
            self.res.setdefault(field, float(m.group(2)))
            return
        if s.startswith("Correcting epsilon1"):
            self.eps_max_res = nums(s)[-1]
            return
        if s.startswith("time step continuity errors"):
            self.cont_cum = nums(s)[-1]
            return

        if self.nan_seen is None and re.search(r"\bnan\b", s, re.IGNORECASE):
            self.nan_seen = s

    # -- derived values ----------------------------------------------------

    def rate(self):
        """Simulated seconds per wall second, over the recent history."""
        if len(self.history) < 2:
            return None
        (c0, t0), (c1, t1) = self.history[0], self.history[-1]
        if c1 <= c0:
            return None
        return (t1 - t0)/(c1 - c0)

    def eta(self):
        r = self.rate()
        if not r or self.end_time is None or self.t is None:
            return None
        return max(self.end_time - self.t, 0.0)/r

    def status(self, pid_alive):
        if self.fatal:
            return "CRASHED"
        if self.finished:
            return "FINISHED"
        if pid_alive is False:
            return "STOPPED"
        if not self.started:
            return "STARTING"
        return "RUNNING"


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def fmt_time(t):
    """Simulated time in the most readable unit."""
    if t is None:
        return "-"
    a = abs(t)
    if a >= 1:
        return "%.4g s" % t
    if a >= 1e-3:
        return "%.4g ms" % (t*1e3)
    if a >= 1e-6:
        return "%.4g µs" % (t*1e6)
    return "%.4g ns" % (t*1e9)


def fmt_wall(sec):
    if sec is None:
        return "-"
    sec = int(sec)
    d, sec = divmod(sec, 86400)
    h, sec = divmod(sec, 3600)
    m, sec = divmod(sec, 60)
    if d:
        return "%dd %02dh %02dm" % (d, h, m)
    if h:
        return "%dh %02dm" % (h, m)
    return "%dm %02ds" % (m, sec)


def g(x, spec="%.4g"):
    return "-" if x is None else spec % x


def pid_alive(pid):
    if pid is None:
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    # A zombie still answers kill(0): check /proc where available.
    try:
        with open("/proc/%d/stat" % pid) as f:
            return f.read().split()[2] != "Z"
    except OSError:
        return True


# ---------------------------------------------------------------------------
# Plain output
# ---------------------------------------------------------------------------

def plain_line(st, alive):
    pct = (100.0*st.t/st.end_time) if (st.t is not None and st.end_time) else None
    parts = [
        st.status(alive),
        "t=%s/%s" % (fmt_time(st.t), fmt_time(st.end_time)),
        "(%s%%)" % g(pct, "%.2f"),
        "dt=%s" % g(st.dt, "%.3g"),
        "step=%d" % st.steps,
        "maxU=%s" % g(st.max_U, "%.3g"),
        "Q=%s/%sW" % (g(st.laser_q, "%.3g"), g(st.laser_power, "%.3g")),
        "cells=%s" % g(st.cells, "%d"),
        "evap=%s" % g(st.evap, "%.3g"),
        "wall=%s" % fmt_wall(st.clock),
        "ETA=%s" % fmt_wall(st.eta()),
    ]
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Rich dashboard
# ---------------------------------------------------------------------------

def build_rich(st, alive, log_path):
    from rich.console import Group
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.progress_bar import ProgressBar

    def kv_table():
        t = Table.grid(padding=(0, 2))
        t.add_column(style="bold")
        t.add_column()
        return t

    status = st.status(alive)
    colour = {"RUNNING": "green", "FINISHED": "cyan", "STARTING": "yellow",
              "STOPPED": "yellow", "CRASHED": "red"}[status]

    # Run
    run = kv_table()
    frac = (st.t/st.end_time) if (st.t is not None and st.end_time) else 0.0
    run.add_row("Status", Text(status, style="bold " + colour))
    run.add_row("Sim time", "%s / %s  (%.2f %%)" % (
        fmt_time(st.t), fmt_time(st.end_time), 100*frac))
    run.add_row("", ProgressBar(total=1.0, completed=min(frac, 1.0), width=34))
    run.add_row("deltaT", g(st.dt, "%.4g s"))
    run.add_row("Steps", str(st.steps))
    run.add_row("Wall time", fmt_wall(st.clock))
    r = st.rate()
    run.add_row("Speed", "-" if not r else "%s per wall hour" % fmt_time(r*3600))
    eta = st.eta()
    run.add_row("Remaining", fmt_wall(eta))
    run.add_row("Finish at", "-" if eta is None else
                time.strftime("%a %H:%M", time.localtime(time.time() + eta)))
    if st.write_interval and st.t is not None:
        nxt = (int(st.t/st.write_interval) + 1)*st.write_interval
        run.add_row("Next write", fmt_time(nxt))

    # Laser
    laser = kv_table()
    if st.laser_pos:
        laser.add_row("Position [µm]", "x %.1f  y %.1f  z %.1f" % tuple(
            v*1e6 for v in st.laser_pos))
    laser.add_row("Power", g(st.laser_power, "%.4g W"))
    laser.add_row("Absorbed", g(st.laser_q, "%.4g W"))
    if st.laser_q is not None and st.laser_power:
        laser.add_row("Absorptivity", "%.1f %%" % (100*st.laser_q/st.laser_power))
    laser.add_row("Rays", g(st.n_rays, "%d"))

    # Fields
    fields = kv_table()
    fields.add_row("max |U|", g(st.max_U, "%.4g m/s"))
    fields.add_row("p_rgh min / max", "%s / %s Pa" % (
        g(st.p_rgh[0], "%.6g"), g(st.p_rgh[1], "%.6g")))
    fields.add_row("min T", g(st.min_T, "%.5g K"))
    if st.max_T is not None:
        fields.add_row("max T", g(st.max_T, "%.5g K"))
    fields.add_row("max |vDot|·dt", g(st.vdot_dt, "%.3g"))

    # Phases
    phases = Table(box=None, padding=(0, 1))
    phases.add_column("phase", style="bold")
    phases.add_column("mass [kg]", justify="right")
    phases.add_column("drift", justify="right")
    phases.add_column("alpha avg", justify="right")
    phases.caption = "evaporation %s kg/s   condensation %s kg/s" % (
        g(st.evap, "%.3g"), g(st.cond, "%.3g"))
    for name in (st.mass or st.alpha):
        m = st.mass.get(name)
        m0 = st.mass0.get(name)
        drift = "-" if (m is None or not m0) else "%+.2e" % ((m - m0)/m0)
        a = st.alpha.get(name)
        phases.add_row(name, g(m, "%.5g"), drift, "-" if a is None else "%.5g" % a[2])

    # Mesh and numerics
    num = kv_table()
    num.add_row("Cells", g(st.cells, "%d") if st.cells else "(no refinement yet)")
    if st.last_amr:
        num.add_row("Last AMR", st.last_amr)
    num.add_row("Courant mean / max", "%s / %s" % (g(st.co[0], "%.3g"), g(st.co[1], "%.3g")))
    num.add_row("Interface Co max", g(st.alpha_co[1], "%.3g"))
    if st.res:
        num.add_row("Residuals (initial)", "  ".join(
            "%s %.1e" % (k, v) for k, v in st.res.items()))
    if st.T_corr_last is not None:
        # One T solve per melting corrector loop (MELTING maxTempCorrector)
        # plus the first one. Yellow when the loop hits its limit.
        cap = "" if st.max_T_corr is None else "  (maxTempCorrector %d)" % st.max_T_corr
        style = "yellow" if (st.max_T_corr and st.T_corr_last > st.max_T_corr) else ""
        num.add_row("T solves per step", Text("%d%s" % (st.T_corr_last, cap), style=style))
    num.add_row("Closure defect max|dev|", g(st.closure_dev, "%.3g"))
    num.add_row("Continuity (cumulative)", g(st.cont_cum, "%.3g"))

    # Messages
    msgs = []
    if st.nan_seen:
        msgs.append(Text("NaN in log: " + st.nan_seen[:100], style="bold red"))
    if st.started and st.steps >= 3 and not st.pairs:
        msgs.append(Text(
            "No evaporation pair in the log (\"Phase-change pairs:\" is empty). "
            "Check the vapour phase is named <metal>vapour.", style="bold red"))
    for line in st.fatal[:6]:
        msgs.append(Text(line[:110], style="red"))
    for line in st.warnings:
        msgs.append(Text(line[:110], style="yellow"))
    if not msgs:
        msgs.append(Text("none", style="dim"))

    head = Text.assemble(
        ("compressibleLaserbeamFoam  ", "bold"),
        (os.path.basename(os.path.abspath(st.case)), "bold cyan"),
        ("   nProcs %s  PID %s  log %s" % (
            st.header.get("nProcs", "-"), st.header.get("PID", "-"),
            os.path.basename(log_path)), "dim"),
    )

    top = Table.grid(expand=True, padding=(0, 1))
    top.add_column(ratio=1)
    top.add_column(ratio=1)
    top.add_row(Panel(run, title="Run", border_style=colour),
                Group(Panel(laser, title="Laser"), Panel(fields, title="Fields")))
    mid = Table.grid(expand=True, padding=(0, 1))
    mid.add_column(ratio=1)
    mid.add_column(ratio=1)
    mid.add_row(Panel(phases, title="Phases"), Panel(num, title="Mesh and numerics"))

    return Group(head, top, mid, Panel(Group(*msgs), title="Warnings / errors"))


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

class LogFollower:
    """Reads new complete lines from a growing file."""

    def __init__(self, path):
        self.path = path
        self.pos = 0
        self.partial = ""

    def read(self):
        try:
            with open(self.path, errors="replace") as f:
                f.seek(self.pos)
                data = f.read()
                self.pos = f.tell()
        except FileNotFoundError:
            return []
        if not data:
            return []
        data = self.partial + data
        lines = data.split("\n")
        self.partial = lines.pop()
        return lines


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("-c", "--case", default=".", help="case folder (default .)")
    ap.add_argument("-l", "--log", default="log.compressibleLaserbeamFoam",
                    help="solver log, relative to the case folder")
    ap.add_argument("--pid", type=int, help="exit when this process exits")
    ap.add_argument("--interval", type=float, default=2.0, help="refresh [s]")
    ap.add_argument("--once", action="store_true", help="one snapshot, then exit")
    ap.add_argument("--plain", action="store_true", help="plain one-line output")
    args = ap.parse_args()

    log_path = os.path.join(args.case, args.log)
    st = RunState(args.case)
    follower = LogFollower(log_path)

    use_rich = not args.plain and sys.stdout.isatty()
    if use_rich:
        try:
            from rich.console import Console
            from rich.live import Live
        except ImportError:
            use_rich = False

    def update():
        for line in follower.read():
            st.feed(line)
        return pid_alive(args.pid)

    def done(alive):
        return st.finished or bool(st.fatal) or alive is False

    try:
        if args.once:
            alive = update()
            if use_rich:
                Console().print(build_rich(st, alive, log_path))
            else:
                print(plain_line(st, alive))
            return 0

        if use_rich:
            console = Console()
            with Live(console=console, refresh_per_second=4, screen=False,
                      transient=False) as live:
                while True:
                    alive = update()
                    live.update(build_rich(st, alive, log_path))
                    if done(alive):
                        break
                    time.sleep(args.interval)
        else:
            tty = sys.stdout.isatty()
            while True:
                alive = update()
                line = plain_line(st, alive)
                if tty:
                    sys.stdout.write("\r\033[K" + line)
                else:
                    sys.stdout.write(line + "\n")
                sys.stdout.flush()
                if done(alive):
                    break
                time.sleep(args.interval)
            if tty:
                sys.stdout.write("\n")
    except KeyboardInterrupt:
        pass

    if st.fatal:
        print("\nSolver crashed. See %s" % log_path)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
