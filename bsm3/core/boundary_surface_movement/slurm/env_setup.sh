#!/usr/bin/env bash
# Sourced environment for the E175 DAFoam MPI derivative ladder on TSCC.
#
# Source this from the sbatch scripts (`source env_setup.sh`) after the Slurm
# preamble.  Fill in the TODO(TSCC) lines with the site-specific module loads
# and virtual-environment activation in the ESTABLISHED WORKING ORDER
# (OpenMPI -> DAFoam/PETSc -> BSM3).  Everything below the TODO block is fixed by
# the implementation instructions and should not need editing.

set -euo pipefail

# --- One thread per MPI process (required) ---------------------------------
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

# --- Site-specific environment (TODO(TSCC): fill these in) ------------------
# The exact module names / activate scripts depend on the TSCC DAFoam install.
# Source them here in the working order you already use for run_dafoam_gmsh.py.
#
#   module purge
#   module load cpu/0.17.3b gcc/10.2.0 openmpi/4.1.3            # OpenMPI first
#   source /path/to/DAFoam/loadDAFoam.sh                        # DAFoam + PETSc
#   source /path/to/bsm3-venv/bin/activate                     # BSM3 env last
#
# Leave BSM3_PYTHON pointing at the interpreter that can import bsm3 + dafoam.
: "${BSM3_PYTHON:=python}"

# --- Repository + scratch layout -------------------------------------------
# BSM3_REPO must contain the bsm3 package; results/logs go on Lustre scratch.
: "${BSM3_REPO:=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)}"
: "${LADDER_SCRATCH:=${SCRATCH:-/tmp}/e175_dafoam_ladder}"
mkdir -p "${LADDER_SCRATCH}"

export BSM3_PYTHON BSM3_REPO LADDER_SCRATCH
echo "[env] BSM3_PYTHON=${BSM3_PYTHON}"
echo "[env] BSM3_REPO=${BSM3_REPO}"
echo "[env] LADDER_SCRATCH=${LADDER_SCRATCH}"
echo "[env] threads: OMP=${OMP_NUM_THREADS} OPENBLAS=${OPENBLAS_NUM_THREADS} MKL=${MKL_NUM_THREADS} NUMEXPR=${NUMEXPR_NUM_THREADS}"
