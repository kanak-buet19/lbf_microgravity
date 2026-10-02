#!/bin/bash
#------------------------------------------------------------------------------
# Start (or restart) the unattended calibration. Run it inside tmux:
#
#   tmux new -s calib
#   of2512                      # load OpenFOAM v2512 (laserbeamFoam built)
#   ./run_calibration.sh        # Ctrl+B then D to detach; tmux attach -t calib
#
# Options are passed to scripts/driver.py:
#   ./run_calibration.sh --dry        show what would start, start nothing
#   ./run_calibration.sh --stop-all   stop every running job and exit
#
# Python: uses .venv/ in this folder. If it is missing or broken it is
# created (uv, else python -m venv, else venv --without-pip + get-pip.py) and
# filled from requirements.txt. Needs internet the first time only.
# The driver itself runs on the CPUs not given to jobs (64-71 by default).
#------------------------------------------------------------------------------
set -u
cd "$(dirname "$(readlink -f "$0")")" || exit 1
here=$(pwd)
venv="$here/.venv"
py="$venv/bin/python"

say() { echo "[run_calibration] $*"; }
die() { echo "[run_calibration] ERROR: $*" >&2; exit 1; }

check_imports() {
    "$py" - <<'EOF' 2>/dev/null
import numpy, scipy, matplotlib, PIL, sklearn
print("numpy", numpy.__version__, "| scipy", scipy.__version__,
      "| matplotlib", matplotlib.__version__, "| scikit-learn", sklearn.__version__)
EOF
}

find_base_python() {
    for c in python3.13 python3.12 python3.11 python3.10 python3.9 python3; do
        if command -v "$c" >/dev/null 2>&1 \
        && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null
        then
            command -v "$c"; return 0
        fi
    done
    return 1
}

make_venv() {
    rm -rf "$venv"
    if command -v uv >/dev/null 2>&1
    then
        say "creating .venv with uv"
        uv venv --python ">=3.9" "$venv" && uv pip install --python "$py" -r requirements.txt && return 0
        say "uv failed, trying python -m venv"
        rm -rf "$venv"
    fi
    base=$(find_base_python) || die "no Python >= 3.9 found. Install python3 (or uv: curl -LsSf https://astral.sh/uv/install.sh | sh)"
    say "base Python: $base ($("$base" --version 2>&1))"
    if "$base" -m venv "$venv" 2>/dev/null && "$py" -m pip --version >/dev/null 2>&1
    then
        :
    else
        say "venv has no pip (python3-venv missing?): creating without pip and fetching get-pip.py"
        rm -rf "$venv"
        "$base" -m venv --without-pip "$venv" || die "python -m venv not available. Install python3-venv or uv."
        gp="$venv/get-pip.py"
        if command -v curl >/dev/null 2>&1; then curl -fsSL https://bootstrap.pypa.io/get-pip.py -o "$gp"
        elif command -v wget >/dev/null 2>&1; then wget -q https://bootstrap.pypa.io/get-pip.py -O "$gp"
        else "$py" -c "import urllib.request as u; u.urlretrieve('https://bootstrap.pypa.io/get-pip.py', '$gp')"
        fi || die "could not download get-pip.py (no internet?)"
        "$py" "$gp" -q || die "get-pip.py failed"
    fi
    "$py" -m pip install -q --upgrade pip
    "$py" -m pip install -q -r requirements.txt || die "pip install -r requirements.txt failed"
}

# 1. Python environment
if [ -x "$py" ] && check_imports >/dev/null
then
    say "using existing .venv"
else
    say ".venv missing or incomplete: setting it up"
    make_venv
    check_imports >/dev/null || die "packages still not importable after install"
fi
say "$(check_imports)"

# 2. OpenFOAM and solver
command -v laserbeamFoam >/dev/null 2>&1 || die "laserbeamFoam not found: load OpenFOAM v2512 (of2512) and build the solver first"
for c in blockMesh setFields decomposePar mpirun taskset; do
    command -v "$c" >/dev/null 2>&1 || die "$c not found on PATH"
done
say "OpenFOAM: ${WM_PROJECT_VERSION:-?}, solver: $(command -v laserbeamFoam)"

# 3. Driver on the CPUs not used by jobs; few BLAS threads for the surrogate
ncpu=$(nproc --all)
spare=$("$py" -c "
import json; c = json.load(open('config.json'))['cores']
first = c['first_cpu'] + c['max_cores']
print(f'{first}-{$ncpu - 1}' if first < $ncpu else '')")
export OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 MKL_NUM_THREADS=4
if [ -n "$spare" ]
then
    say "driver on CPUs $spare"
    exec taskset -c "$spare" "$py" scripts/driver.py "$@"
else
    exec "$py" scripts/driver.py "$@"
fi
