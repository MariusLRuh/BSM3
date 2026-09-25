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
# LADDER_LEVEL in {0,1,2,3,4,5,6}; LADDER_NP is the number of MPI ranks. Levels
# 1 and 2 need only the mesh-motion stack. Levels 0,3,4,5,6 run DAFoam and each
# get their OWN isolated case copy: set DAFOAM_CASE_TEMPLATE to an OpenFOAM case
# template and this script copies only 0/, constant/, system/ into the per-run
# scratch directory and exports DAFOAM_CASE_DIRECTORY.
#
# Level 6 (DAFoam primal-only deformation diagnostic) additionally reads:
#   LADDER_PRIMAL_POINT = baseline|plus|minus   (default baseline)
#   LADDER_PRIMAL_START = fresh|baseline        (default baseline)
#   LADDER_PRIMAL_ETA   = directional step      (default 1e-2)
#
#   sbatch --export=ALL,LADDER_LEVEL=6,LADDER_NP=1,\
#     LADDER_PRIMAL_POINT=plus,LADDER_PRIMAL_START=fresh,\
#     DAFOAM_CASE_TEMPLATE=/path/to/case e175_derivative_ladder.sbatch

set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${HERE}/env_setup.sh"

LADDER_LEVEL="${LADDER_LEVEL:-2}"
LADDER_NP="${LADDER_NP:-1}"

# Do not oversubscribe: the requested rank count must fit the allocation.
NTASKS="${SLURM_NTASKS:-${LADDER_NP}}"
if [ "${LADDER_NP}" -gt "${NTASKS}" ]; then
  echo "ERROR: LADDER_NP=${LADDER_NP} exceeds SLURM_NTASKS=${NTASKS};" \
       "increase --ntasks or lower LADDER_NP." >&2
  exit 1
fi

STAMP="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="${LADDER_SCRATCH}/level${LADDER_LEVEL}_np${LADDER_NP}_${SLURM_JOB_ID:-$STAMP}"
mkdir -p "${RUN_DIR}"
cd "${RUN_DIR}"

# --- Isolated OpenFOAM case for the DAFoam levels (0,3,4,5,6) ----------------
# Copy ONLY the case definition (0/, constant/, system/) into a per-run case, so
# ladder_runs/, processor*/ dirs and prior solution times in the template are
# never dragged in (a full copy can recurse into the destination and destroys
# the meaning of a fresh start). Each level then owns its case, so parallel and
# repeated solves -- and the adjoint levels' coloring cache -- never collide.
# Level 6 is primal-only and never invokes coloring or an adjoint.
case "${LADDER_LEVEL}" in
  0|3|4|5|6)
    : "${DAFOAM_CASE_TEMPLATE:?Levels 0/3/4/5/6 require DAFOAM_CASE_TEMPLATE=<OpenFOAM case template dir>}"
    CASE_COPY="${RUN_DIR}/case"
    mkdir -p "${CASE_COPY}"
    cp -a "${DAFOAM_CASE_TEMPLATE}/0" "${CASE_COPY}/"
    cp -a "${DAFOAM_CASE_TEMPLATE}/constant" "${CASE_COPY}/"
    cp -a "${DAFOAM_CASE_TEMPLATE}/system" "${CASE_COPY}/"
    # Match the decomposition to the requested rank count.
    if [ -f "${CASE_COPY}/system/decomposeParDict" ]; then
      sed -i "s/^numberOfSubdomains.*/numberOfSubdomains ${LADDER_NP};/" \
        "${CASE_COPY}/system/decomposeParDict"
    fi
    export DAFOAM_CASE_DIRECTORY="${CASE_COPY}"
    echo "[ladder] isolated case: ${DAFOAM_CASE_DIRECTORY}"
    ;;
esac

# --- Provenance -------------------------------------------------------------
GIT_COMMIT="$(git -C "${BSM3_REPO}" rev-parse HEAD 2>/dev/null || echo unknown)"
{
  echo "level=${LADDER_LEVEL}"
  echo "mpi_ranks=${LADDER_NP}"
  echo "git_commit=${GIT_COMMIT}"
  echo "slurm_job_id=${SLURM_JOB_ID:-none}"
  echo "host=$(hostname)"
  echo "timestamp=${STAMP}"
  echo "isolated_case=${DAFOAM_CASE_DIRECTORY:-none}"
  if [ "${LADDER_LEVEL}" = "6" ]; then
    echo "primal_point=${LADDER_PRIMAL_POINT:-baseline}"
    echo "primal_start=${LADDER_PRIMAL_START:-baseline}"
    echo "primal_eta=${LADDER_PRIMAL_ETA:-1e-2}"
  fi
} | tee "${RUN_DIR}/run_metadata.txt"

# The ladder writes its JSON under ./ladder_results (RUN_DIR is on scratch).
LOG="${RUN_DIR}/ladder_level${LADDER_LEVEL}_np${LADDER_NP}.log"

mpirun -np "${LADDER_NP}" "${BSM3_PYTHON}" -m \
  bsm3.core.boundary_surface_movement.e175_derivative_ladder "${LADDER_LEVEL}" \
  2>&1 | tee "${LOG}"

# --- Resource summary -------------------------------------------------------
if command -v sacct >/dev/null 2>&1 && [ -n "${SLURM_JOB_ID:-}" ]; then
  sacct -j "${SLURM_JOB_ID}" \
    --format=JobID,JobName,Elapsed,MaxRSS,MaxVMSize,NCPUS,State \
    | tee "${RUN_DIR}/sacct_summary.txt"
fi

echo "[ladder] artifacts in ${RUN_DIR}"
