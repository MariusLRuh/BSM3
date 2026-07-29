#!/usr/bin/env bash
#SBATCH --job-name=e175_mpi_inv
#SBATCH --output=e175_mpi_inv_%j.out
#SBATCH --error=e175_mpi_inv_%j.err
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=8
#SBATCH --time=03:00:00
# TODO(TSCC): set account/partition.
##SBATCH --account=REPLACE_ME
##SBATCH --partition=REPLACE_ME

# Level 1 MPI-independence sweep: run the rank-0 mesh-motion forward at
# np = 1, 2, 4, 8 and compare the global volume-coordinate checksums. The
# expensive setup/forward-deformation messages must appear only once (from
# rank 0); the checksum must be identical across rank counts.
#
#   sbatch e175_mpi_invariance.sbatch

set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${HERE}/env_setup.sh"

STAMP="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="${LADDER_SCRATCH}/mpi_invariance_${SLURM_JOB_ID:-$STAMP}"
mkdir -p "${RUN_DIR}"
cd "${RUN_DIR}"

GIT_COMMIT="$(git -C "${BSM3_REPO}" rev-parse HEAD 2>/dev/null || echo unknown)"
echo "git_commit=${GIT_COMMIT}" | tee "${RUN_DIR}/run_metadata.txt"

NTASKS="${SLURM_NTASKS:-8}"
for NP in 1 2 4 8; do
  if [ "${NP}" -gt "${NTASKS}" ]; then
    echo "=== skip np=${NP}: exceeds SLURM_NTASKS=${NTASKS} (not oversubscribing) ==="
    continue
  fi
  echo "=== Level 1 at np=${NP} ==="
  mpirun -np "${NP}" "${BSM3_PYTHON}" -m \
    bsm3.core.boundary_surface_movement.e175_derivative_ladder 1 \
    2>&1 | tee "${RUN_DIR}/level1_np${NP}.log"
done

echo "=== checksums across rank counts (must match) ==="
grep -h "checksum=" "${RUN_DIR}"/level1_np*.log || true

if command -v sacct >/dev/null 2>&1 && [ -n "${SLURM_JOB_ID:-}" ]; then
  sacct -j "${SLURM_JOB_ID}" \
    --format=JobID,JobName,Elapsed,MaxRSS,MaxVMSize,NCPUS,State \
    | tee "${RUN_DIR}/sacct_summary.txt"
fi
echo "[ladder] artifacts in ${RUN_DIR}"
