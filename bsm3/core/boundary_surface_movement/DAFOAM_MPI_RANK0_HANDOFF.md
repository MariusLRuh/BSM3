# DAFoam MPI rank-0 geometry-to-volume refactor — handoff

Branch: `dafoam-mpi-rank0-refactor` (off `dev`).

This implements the MPI-aware geometry-to-volume CSDL operation coupled to
DAFoam described in `DAFoam_CSDL_MPI_Custom_Operation_Implementation_Instructions.md`
and closes the concrete gaps raised in `DAFoam_CSDL_Derivative_Review_Addendum.md`.
Everything that can be validated without MPI/DAFoam/PETSc/OpenFOAM has been built
and tested locally; the DAFoam-coupled validation ladder (Gates C–D / Levels 3–5)
must be run on TSCC through the provided Slurm scripts.

---

## 1. Architecture summary

From CSDL's perspective the pipeline is now the two-custom-operation chain

```
d  ── GeometryVolumeOperation ──▶  X(d)  ── DAFoamAnalysisOperation ──▶  (CL, CD)
      (runs only on rank 0,               (collective, distributed;
       broadcasts global X)                extracts local volCoord)
```

* **Geometry → surface → volume** (`build_mesh_motion_model`) is wrapped in
  `MeshMotionVolumeBackend`, which lives **only on rank 0**. It builds the
  existing differentiable mesh-motion model once (CAD import, baseline projection
  ownership, seams, elasticity assembly/factorization) and reuses it for every
  forward and reverse evaluation.
* **Forward:** rank 0 deforms the mesh and the `(171981, 3)` global coordinate
  array (~4.1 MB) is broadcast with a typed `MPI.Bcast`. Every rank assigns the
  identical CSDL output.
* **Reverse (matrix-free):** the backend never forms the dense `∂X/∂d`. It
  injects the volume-coordinate seed `X̄` as a constant CSDL input, contracts it
  to a scalar `s = Σ(X · X̄)`, and differentiates `s` w.r.t. the design variables.
  `ds/dd = X̄ᵀ ∂X/∂d` is exactly the VJP, propagated by CSDL through the
  elasticity transpose solve, the surface-motion reverse, and the geometry
  parameterization. Rank 0 broadcasts the small design-variable cotangent vector.
* **DAFoam** stays collective and distributed. It maps the broadcast global
  coordinates to each rank's local OpenFOAM partition (`global[local_to_global]`),
  runs the primal, solves the distributed discrete adjoint, and assembles the
  volume-coordinate cotangent back to global order.

## 2. MPI ownership and communication contract

| Quantity | Owner |
|---|---|
| Geometric design-variable values | Replicated on all ranks |
| CAD/geometry, projection caches, seams, elasticity factorization | Rank 0 only (inside the backend) |
| Global deformed volume coordinates | Computed on rank 0, broadcast (`MPI.Bcast`) |
| OpenFOAM topology, flow state, adjoint ψ | Distributed across DAFoam ranks; ψ never gathered |
| Local volume-coordinate cotangent | Distributed |
| Assembled global volume-coordinate cotangent | Rank 0 (`root` mode) or replicated (`replicated`/Allreduce) |
| Design-variable cotangents | Computed on rank 0, broadcast |

Collectives:

* **Forward scatter** `S`: `local = global[local_to_global]`
  (`extract_local_coordinates`).
* **Reverse scatter-add** `Sᵀ`: `np.add.at(global, local_to_global, local)`
  (`assemble_local_gradient`). This is the exact transpose of `S`; forward
  overwrite / reverse duplication would **not** be a transpose. Proven by the
  dot-product test `⟨Sx, y⟩ = ⟨x, Sᵀy⟩` over duplicated processor-boundary points.
* **Gradient reduction:** `reduce_gradient(..., ownership=...)` — `replicated`
  (`Allreduce`, every rank holds the full gradient, current default) or `root`
  (`Reduce`, only rank 0). Validated equal on the root rank. Switch DAFoam via
  `DAFOAM_VOLUME_GRADIENT_OWNERSHIP` in the driver only after the two match.
* **Collective exception handling:** `run_on_root` runs the heavy work on rank 0,
  reduces any exception to a string, and broadcasts it **before** bulk data, so a
  root failure raises symmetrically on all ranks instead of deadlocking.

## 3. Files

**New**

| File | Purpose |
|---|---|
| `geometry_volume_mpi.py` | `SerialComm` fallback, `run_on_root`, typed `broadcast_array`, forward/reverse scatter (`extract_local_coordinates`/`assemble_local_gradient`), `reduce_gradient` (root/replicated), `verify_replicated_values`. mpi4py imported lazily. |
| `geometry_volume_backend.py` | `CSDLRecorderBackend` (matrix-free forward/VJP engine, forward caching + DV-match invalidation), `MeshMotionVolumeBackend`, `read_gmsh_volume_point_count`. |
| `geometry_volume_operation.py` | `GeometryVolumeOperation` (rank-0 forward + broadcast) and `GeometryVolumeVJP` (rank-0 VJP + DV-cotangent broadcast), CustomExplicitOperationBeta contract. |
| `forward_only_fd_checker.py` | FD-first checker; stage markers; fd-level `"Solving Linear Equation"` guard; scale-aware steps; degree/radian check. |
| `e175_derivative_ladder.py` | Levels 0–6, cluster-run. |
| `slurm/env_setup.sh`, `slurm/e175_derivative_ladder.sbatch`, `slurm/e175_mpi_invariance.sbatch` | TSCC batch scaffolding. |
| `tests/test_geometry_volume_mpi.py` | 14 dependency-free / mock-MPI tests. |

**Modified**

| File | Change |
|---|---|
| `dafoam_csdl.py` | `volume_gradient_ownership` (replicated/root) via shared helpers; deterministic FD mode (`set_deterministic_baseline`, `deterministic_fd_mode`, `reset_primal_state`); adjoint preconditioner invalidation (`invalidate_adjoint_on_primal`). |
| `cfd_mesh_dafoam_analysis.py` | `GEOMETRY_VOLUME_MODE` (`rank0`/`replicated`), `build_cfd_analysis_rank0`, gradient-ownership pass-through, main() dispatch, guards against the legacy CSDL FD paths in rank-0 mode. |
| `geometry_volume_backend.py` | — (retains the last `MeshMotionResult` for the driver's quality JSON). |
| `tests/test_dafoam_csdl.py` | set `volume_gradient_ownership` on the hand-built backend. |

## 4. What was validated locally

`central_geom` env has numpy/scipy/csdl_alpha/lsdo_function_spaces/bsm3/pytest/jax
but **no mpi4py/dafoam/petsc4py/Slurm and no OpenFOAM case**. Validated here:

* 23 tests pass (`tests/test_geometry_volume_mpi.py` + `tests/test_dafoam_csdl.py`).
* Matrix-free VJP dot-product vs central FD on a synthetic CSDL model: rel err ~6e-12.
* `GeometryVolumeOperation` CSDL reverse == backend `compute_vjp` exactly.
* Rank-0-only forward + bit-identical broadcast (scripted 2-rank comm).
* Forward/reverse scatter transpose identity with duplicate points.
* Allreduce vs root-Reduce equivalence; collective exception propagation.
* Forward-cache reuse/invalidation; adjoint-output guard; forward-first ordering.
* `read_gmsh_volume_point_count` == 171981 (matches the real Euler mesh).

## 5. Cluster validation ladder (run on TSCC)

Do **not** start with another full six-derivative end-to-end run. Fill in the
`TODO(TSCC)` lines in `slurm/env_setup.sh` (module loads + venv activation in the
OpenMPI → DAFoam → BSM3 order) and set `CASE.case_directory` in
`cfd_mesh_dafoam_analysis.py` before Levels 0/3/4/5.

```bash
cd bsm3/core/boundary_surface_movement/slurm
# Gate A — mesh-motion VJP only (no DAFoam), np=1:
sbatch --export=ALL,LADDER_LEVEL=2,LADDER_NP=1 e175_derivative_ladder.sbatch
# Gate B — MPI mesh-motion forward invariance (np = 1,2,4,8):
sbatch e175_mpi_invariance.sbatch
# Level 0 — function noise (needs a case):
sbatch --export=ALL,LADDER_LEVEL=0,LADDER_NP=1 e175_derivative_ladder.sbatch
# Gate C — DAFoam-only volume-coordinate VJP, np=1 then np=2:
sbatch --export=ALL,LADDER_LEVEL=3,LADDER_NP=1 e175_derivative_ladder.sbatch
sbatch --export=ALL,LADDER_LEVEL=3,LADDER_NP=2 e175_derivative_ladder.sbatch
# Gate D — chain rule + one-DV end-to-end:
sbatch --export=ALL,LADDER_LEVEL=4,LADDER_NP=2 e175_derivative_ladder.sbatch
sbatch --export=ALL,LADDER_LEVEL=5,LADDER_NP=2 e175_derivative_ladder.sbatch
# Level 6 — primal-only deformation diagnostic (isolated case, no adjoint):
sbatch --export=ALL,LADDER_LEVEL=6,LADDER_NP=1,LADDER_PRIMAL_POINT=plus,\
LADDER_PRIMAL_START=fresh,LADDER_CASE_TEMPLATE=/path/to/case \
  e175_derivative_ladder.sbatch
```

Ladder ↔ addendum-gate mapping:

| Level | What it isolates | Gate | Pass target |
|---|---|---|---|
| 0 | Forward function noise (deterministic repeats) | pre-C | noise ≪ 1% of FD numerator |
| 1 | MPI-independent mesh-motion forward | B | identical checksum for np=1,2,4,8; setup prints once |
| 2 | Mesh-motion custom-op VJP dot-product | A | rel err ≤ 1e-4 with a clear central-FD regime |
| 3 | DAFoam-only volume-coordinate VJP (CL, CD) | C | rel err ~1e-2 → 1e-3; rank-invariant |
| 4 | Chain rule `X̄ᵀJδd` vs `δdᵀd̄` | D | rel err ≤ 1e-3 |
| 5 | One-DV, one-output end-to-end centered FD | D | clear regime; then widen to 3 DVs + CL/CD |
| 6 | Primal-only deformed solve (no adjoint) | primal | primal converges within `primalMinResTolDiff` (1.1 ⇒ ≤10% above tol) |

Level 6 isolates the deformed **primal** from the adjoint: it solves one primal
at the baseline / `+ηd` / `−ηd` point (`LADDER_PRIMAL_POINT`), started either from
a captured converged baseline (`LADDER_PRIMAL_START=baseline`) or cold from the
case's initial fields (`fresh`). It shares Level 3's exact baseline coordinates
and direction, needs an isolated case (`LADDER_CASE_TEMPLATE` → copied per run →
`LADDER_CASE_DIRECTORY`), and never invokes coloring or an adjoint. With
`primal_min_res_tol=1e-9` and `primalMinResTolDiff=1.1`, a deformed solve that
stalls >10% above the target residual is rejected (surfacing deformation-induced
convergence problems that Level 0's baseline-only noise check cannot).

Each level writes `ladder_results/levelN_np*_<stamp>.json` and a `.log` on
Lustre scratch, with `run_metadata.txt` (git commit, rank count, host) and an
`sacct` summary.

## 6. Deterministic FD + adjoint accuracy (addendum findings 1–2)

* **Deterministic FD mode** freezes one converged baseline flow state and
  restores it before every primal, so `+h`, `−h`, and baseline are independent
  (no warm-start chaining). The ladder enables it automatically; production runs
  keep the normal warm start (`deterministic_fd_mode=False`).
* **Preconditioner invalidation** (`invalidate_adjoint_on_primal=True`) resets
  `dRdWTPC`/`ksp`/coloring after every accepted primal so an adjoint never reuses
  a factorization from a different point.
* **Steps are physical/unscaled** (`h = η·s`, η ∈ {1e-2, 3e-3, 1e-3, 3e-4, 1e-4})
  — the ladder does not apply the optimizer scalers while diagnosing.

## 7. Convergence / FD study (do these on the cluster before widening)

* **Primal:** at a fixed mesh, compare `primalMinResTol = 1e-7, 1e-8, 1e-9`
  (`FLOW.primal_min_res_tol`); record CL, CD, residuals, iterations, wall time.
  Outputs must stabilize well below the expected FD change.
* **Adjoint:** at a fixed converged primal, compare `gmresRelTol = 1e-4, 1e-6,
  1e-8` (`FLOW.adjoint_gmres_relative_tolerance`) with the same seed; record
  gradient change and KSP iterations. If the gradient moves a lot between 1e-4
  and 1e-6, the original adjoint was too loose; if it is stable but still
  disagrees with FD, the cause is elsewhere.
* **Degree/radian:** `forward_only_fd_checker.degree_radian_relative_error`
  checks `∂F/∂θ_deg = (π/180)∂F/∂θ_rad`. Confirm the rotation DVs' internal
  convention before trusting rotation gradients.

## 8. Known limitations / follow-ups

1. The surface/volume mesh-quality gate in `build_mesh_motion_model` runs
   once, when the backend recorder is built (at the baseline design point), not
   on every perturbed forward. It still guards the analysis point; perturbed FD
   samples are not re-gated.
2. **Nonsmoothness:** the setup ownership/seam sets are cached and fixed across
   `x±h`, so those cannot change under perturbation. The projection-onto-OML step
   can still change active patches; the Level-2/5 step sweep is the practical
   detector (a non-plateauing sweep flags a nonsmooth branch). Explicit
   projection active-set instrumentation is a future add.
3. Root memory: rank 0 owns mesh motion and participates in DAFoam. Profile peak
   RSS (via the `sacct` summaries) before considering a dedicated geometry rank;
   communicator splitting is intentionally deferred.
4. `read_gmsh_volume_point_count` assumes the `constant/polyMesh` was generated
   from the same `volume_mesh_file` passed to the backend (the existing coupling
   assumption).
5. Do not update stored derivative references to match the new implementation
   until the analytical derivative independently passes Gates A–D.

## 9. Hardening revision (pre-TSCC review fixes)

Applied before any expensive cluster run:

1. **Collective-safe validation.** `verify_replicated_values` now reduces each
   rank's outcome with an `allgather` and raises synchronously on every rank —
   a matching rank still raises if a peer diverges, so no rank is stranded in a
   later collective.
2. **Cotangent ownership enforcement.** New `verify_seed_ownership` +
   `GeometryVolumeOperation(..., seed_ownership=...)`: `replicated` verifies all
   reverse seeds are identical, `root` verifies non-root seeds are zero. The
   driver propagates `DAFOAM_VOLUME_GRADIENT_OWNERSHIP` into the operation so the
   contract matches DAFoam's gradient assembly; a violation fails synchronously.
3. **Coloring vs. adjoint invalidation.** `_invalidate_adjoint_linearization`
   now `destroy()`s the old PETSc `KSP`/`dRdWTPC` and rebuilds only those
   state-dependent objects; coloring (topology-only) is reused. A separate
   `invalidate_topology()` resets coloring for an actual connectivity change.
4. **Deterministic FD is strict.** Enabling `deterministic_fd_mode` without a
   captured baseline now raises instead of silently using a history-dependent
   cached state.
5. **Level-3 direction corrected.** The DAFoam-only direction is now a proper
   normalized central difference `(X(d+h·δd) − X(d−h·δd)) / (2h)`; the sweep
   tests `X ± η·direction` and reports RMS/max coordinate displacement and the
   CL/CD FD numerator at every step.
6. **Ladder is collective-safe.** Every root-only geometry forward/VJP in
   Levels 0–5 is wrapped in `run_on_root`; the CL and CD adjoints reuse one
   converged baseline primal (no rerun between them, preconditioner reused).
7. **Slurm hardening.** `LADDER_NP` must not exceed `SLURM_NTASKS` (no
   `--oversubscribe`); outputs require an explicit Lustre scratch path (no `/tmp`
   fallback); DAFoam shell init is sourced with `set +u`/`set -u` guards.

Local tests: 34 pass (24 mock-MPI/backend + 10 DAFoam), including the
collective-safe validation, root/replicated seed-ownership enforcement, and the
deterministic-baseline guards.
