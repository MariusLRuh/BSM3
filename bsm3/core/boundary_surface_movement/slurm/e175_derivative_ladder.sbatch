#!/usr/bin/env bash
#SBATCH --job-name=e175_ladder
#SBATCH --output=e175_ladder_%j.out
#SBATCH --error=e175_ladder_%j.err
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=4
#SBATCH --time=02:00:00
# TODO(TSCC): set the account/partition you are already approved for. Reuse a
# previously accepted allocation first; optimize only after profiling.
##SBATCH --account=REPLACE_ME
##SBATCH --partition=REPLACE_ME

# Run one level of the E175 DAFoam derivative ladder.
#
#   sbatch --export=ALL,LADDER_LEVEL=2,LADDER_NP=1 e175_derivative_ladder.sbatch
#
# LADDER_LEVEL in {0,1,2,3,4,5}; LADDER_NP is the number of MPI ranks. Levels
# 1 and 2 need only the mesh-motion stack; levels 0 and 3-5 need a configured
# OpenFOAM/DAFoam case (set CASE.case_directory in cfd_mesh_dafoam_analysis.py).

set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${HERE}/env_setup.sh"

LADDER_LEVEL="${LADDER_LEVEL:-2}"
LADDER_NP="${LADDER_NP:-1}"

STAMP="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="${LADDER_SCRATCH}/level${LADDER_LEVEL}_np${LADDER_NP}_${SLURM_JOB_ID:-$STAMP}"
mkdir -p "${RUN_DIR}"
cd "${RUN_DIR}"

# --- Provenance -------------------------------------------------------------
GIT_COMMIT="$(git -C "${BSM3_REPO}" rev-parse HEAD 2>/dev/null || echo unknown)"
{
  echo "level=${LADDER_LEVEL}"
  echo "mpi_ranks=${LADDER_NP}"
  echo "git_commit=${GIT_COMMIT}"
  echo "slurm_job_id=${SLURM_JOB_ID:-none}"
  echo "host=$(hostname)"
  echo "timestamp=${STAMP}"
} | tee "${RUN_DIR}/run_metadata.txt"

# The ladder writes its JSON under ./ladder_results (RUN_DIR is on scratch).
LOG="${RUN_DIR}/ladder_level${LADDER_LEVEL}_np${LADDER_NP}.log"

mpirun --oversubscribe -np "${LADDER_NP}" "${BSM3_PYTHON}" -m \
  bsm3.core.boundary_surface_movement.e175_derivative_ladder "${LADDER_LEVEL}" \
  2>&1 | tee "${LOG}"

# --- Resource summary -------------------------------------------------------
if command -v sacct >/dev/null 2>&1 && [ -n "${SLURM_JOB_ID:-}" ]; then
  sacct -j "${SLURM_JOB_ID}" \
    --format=JobID,JobName,Elapsed,MaxRSS,MaxVMSize,NCPUS,State \
    | tee "${RUN_DIR}/sacct_summary.txt"
fi

echo "[ladder] artifacts in ${RUN_DIR}"
