# Corrective implementation prompt for Codex — Turn 18 (M1.3, third amendment)

Paste into a Codex session at the repository root.

---

Read `docs/overhaul/PLAN.md` (Turn-17 ruling in section 5) and
`docs/overhaul/LOG.md` (Turns 12-17).

## Your Turn-16 stop is upheld — and a second defect was found

Third correct stop in five turns, third time the fault was Claude's.

**1. The backups grep was self-referential — you were right.**
`git grep -n "_dafoam_mpi_refactor_backups" -- .` can never be empty, because
`docs/overhaul/LOG.md`, `PLAN.md` and this prompt intentionally document the
directory. `LOG.md` is append-only; satisfying that command would have destroyed
the audit trail. **Your proposed fix is adopted verbatim** — the command is now
scoped to `-- bsm3/ tests/`, and historical references in `docs/overhaul/` are
explicitly permitted.

**2. A second contradiction you had not yet reached.** Claude audited every
acceptance pattern against the tracked tree. The definition of done claimed
`git grep -i barrier` matches "only `comm.Barrier()` at the six named sites,"
listing three files under `bsm3/`. A **fourth survivor** exists:
`tests/test_geometry_volume_mpi.py:69`, `def Barrier(self):` — a mock MPI
communicator, not in the allowlist. Corrected below to seven sites across four
files.

Every other `git grep` in the prompt was already correctly scoped. No further
contradiction found. **The 20-path allowlist and all other Turn-16 instructions
are unchanged.**

Claim `## Turn 18` in `LOG.md` before editing. Close it when done.

---

## Scope

### A. Whole-file / whole-directory deletions
```
bsm3/core/boundary_surface_movement/inversion_barrier.py
bsm3/core/boundary_surface_movement/oml_quality.py
bsm3/core/boundary_surface_movement/tangential_smoothing.py
bsm3/core/boundary_surface_movement/_dafoam_mpi_refactor_backups/    (all 14 tracked files)
```
Delete the directory with `git rm -r`, not by path enumeration.

### B. `elasticity.py` — delete symbols
`CoupledAssembledSystem` (64), `CorotationalMembraneAssembler` (246),
`_polygon_membrane_stiffness` (547), `_cst_stiffness` (634),
`_scatter_coupled_element` (658), `_scatter_edge_regularization` (703).

**PRESERVE:** `AssembledSystem`, `StiffnessAssembler`, `GraphLaplacianAssembler`,
`graph_neighbors`, `element_neighbors`, `_validate_partition`, `_edge_weights`,
`_validate_quad_bracing_mode`, `_quad_brace_pairs`, `_triangle_mean_ratio`,
`_polygon_area`.

### C. `motion.py`
Delete `CorotationalMembraneMotionSolver` (870-1111); the
`from .inversion_barrier import (...)` at 55; `CorotationalMembraneAssembler`
from the elasticity import block (~40).

**PRESERVE:** `ElasticityMotionSolver`, `RBFMotionSolver`, `MeshMotionField`,
`MeshMotionSolver`, `ComponentReevaluation`, `GraphLoadStepState`,
`ElasticityMotionField`, all module-level helpers.

### D. `projection.py` — partial edit, mixed-purpose file
Delete `ParameterizedProjectionGroup` (41), `ParameterizedProjection` (58),
`project_onto_oml_parameterized` (237-411), `__all__` entries 540, 541, 545.

**PRESERVE:** `VertexBatch` (32), `project_onto_oml` (65), `reevaluate_vertices`
(412), `combine_vertices` (452), and **`_project_group` (478) and
`_coefficient_subset` (501)** — shared by both the ordinary and parameterized
paths (call-graph verified). Do not delete them.

### E. `load_stepping.py`
Delete: imports 44, 48, 51; `final_parameterized_projection` field (64);
`parameterize_final_projection` (95) and `tangential_smoother` (98) parameters;
initializer 294; `if tangential_smoother is not None:` (518-519);
`if is_last and parameterize_final_projection:` (532-540); result field 572.

**PRESERVE:** `run_graph_load_steps`, `GraphLoadStepResult` minus the one field,
N-gon and distortion plumbing.

### F. `__init__.py`
Delete imports 17, 18, 61; the `inversion_barrier` block (102-109); the
`oml_quality` block (119-126); the `tangential_smoothing` block (79-82);
`ParameterizedProjection`/`ParameterizedProjectionGroup` (111, 112);
`project_onto_oml_parameterized` (116). Delete `__all__` entries 174, 178, 179,
189-192, 219, 220, 222, 223, 237, 263 and the six `OMLQuality*` /
`optimize_mesh_on_oml` / `select_fixed_vertex_band` entries. Remove the membrane
sentence from the module docstring (11).

### G. `e175_mesh_motion_config.py`
Delete `TangentialSmoothingConfig` (48) + `__all__` 346;
`FinalSurfaceQualityConfig` (117) + `__all__` 340; the `tangential_smoothing`
(141-142) and `final_quality` (153-154) fields; **`SurfaceMotionConfig.mode`**
and its validation.

### H. `e175_mesh_motion_pipeline.py`
- smoothing: binding 458; aliases 480-485; band construction 1177-1224;
  `tangential_smoother=` 1280; diagnostics 1525-1530; result field 1587-1588
- OML quality: `surface.final_quality` 462; aliases 493-499; branches 1254,
  1304, 1369; diagnostics 1532
- `parameterize_final_projection=(FINAL_QUALITY_STRATEGY == "oml")` 1253-1255
- **collapse the stale branch**: `if ELASTIC_STRATEGY == "graph":` (1238) and its
  dead `else:` arm (1292, calls `motion.train()` and
  `project_onto_oml_parameterized`). The graph load-step path becomes
  unconditional.
- the `parameterized_projection` local (1236) and its consumption (1288-1290)

> **TRAP.** `final_quality` is an **overloaded name** here. Lines 351-403 bind it
> to a **volume mesh quality metrics** object (`inverted_tetrahedra`,
> `minimum_relative_jacobian`, `mean_ratio_p001`) unrelated to
> `FinalSurfaceQualityConfig`. **Those lines stay.** Only 462 and 493-499 are
> the config.

### I. Drivers
```
bsm3/core/boundary_surface_movement/cfd_mesh_movement_test.py     (30, 119, 122)
bsm3/core/boundary_surface_movement/cfd_mesh_dafoam_analysis.py   (50, 139, 142)
```
> `cfd_mesh_dafoam_analysis.py:346` is `comm.Barrier()`. It is a **permitted
> survivor** — your edits to this file must not touch it.

The third driver is inside the deleted backup directory; no edit needed.

### J. Tests — five deletions, two rewrites
**Delete** from `tests/test_boundary_surface_movement.py` (plus imports 16-17,
35, 40):
- `test_fixed_projected_tangential_smoother_preserves_reference_and_has_fixed_vjp` (639)
- `test_final_only_tangential_smoother_defers_projection_and_differentiates` (699)
- `test_corner_barrier_repairs_quad_and_ift_vjp_matches_finite_difference` (877)
- `test_fixed_oml_quality_repairs_on_surface_and_ift_vjp_matches_fd` (951)

**Delete** from `tests/test_e175_driver_configuration.py` (plus import 19):
- `test_final_only_tangential_reprojection_is_a_supported_fixed_option` (138)

**Rewrite** in `tests/test_e175_driver_configuration.py`:
- `test_default_volume_motion_is_final_only_and_differentiable` (56) — drop the
  `tangential_smoothing.reprojection` assertion
- `test_quad_diagonal_controls_are_validated` (147) — drop the
  `mode="unsupported"` arm

### K. Docs
- `bsm3/core/boundary_surface_movement/DAFOAM_MPI_RANK0_HANDOFF.md` lines **4**
  and **86** — remove the two now-dangling pointers to
  `_dafoam_mpi_refactor_backups/`. These are the **only** two live pointers; the
  scoped acceptance grep below depends on their removal.
- `docs/overhaul/MANIFEST.md` — drop the `inversion_barrier.py`,
  `oml_quality.py`, `tangential_smoothing.py` rows; adjust totals.

---

## Explicitly preserved

Graph Laplacian motion; N-gon affine regularization (`ngon_affine.py`, untouched
since C1); quadratic distortion regularization; **ordinary** OML projection and
reevaluation; symmetry enforcement; surface and volume **quality diagnostics**;
STEP-to-aerodynamic-mesh support.

**Permitted survivors — must remain, and the greps below are written not to
flag them:**

1. **MPI `Barrier` — seven sites, four files:**

   | File | Sites |
   |---|---|
   | `bsm3/core/boundary_surface_movement/cfd_mesh_dafoam_analysis.py` | 346 |
   | `bsm3/core/boundary_surface_movement/geometry_volume_mpi.py` | 77 |
   | `bsm3/core/boundary_surface_movement/run_dafoam_gmsh.py` | 653, 656, 911, 954 |
   | `tests/test_geometry_volume_mpi.py` | 69 |

2. **KS smooth-union `np.log`** — `movement_test_csdl_static_seam.py:537`,
   `movement_test_new.py:436`, `movement_test_new_2.py:670`.
3. **`tangential_smoothing_step`** — `analytical_SDF_anchor_attraction_noarg.py`
   74, 936, 942, 1119. Independent SDF anchor-attraction algorithm, zero imports
   from the removed subsystem.
4. **Historical references in `docs/overhaul/`** — `LOG.md`, `PLAN.md` and this
   file document the deleted membrane, barrier, smoothing and backup-directory
   decisions **by design**. `LOG.md` is append-only. **Do not edit any of them to
   satisfy a grep.** Every acceptance grep below is scoped to `bsm3/` and
   `tests/` for exactly this reason.

`quality.py` is **not** removed for containing the word "quality"; it has no
barrier.

## Literal file allowlist — 20 paths (unchanged)

```
bsm3/core/boundary_surface_movement/inversion_barrier.py              (delete file)
bsm3/core/boundary_surface_movement/oml_quality.py                    (delete file)
bsm3/core/boundary_surface_movement/tangential_smoothing.py           (delete file)
bsm3/core/boundary_surface_movement/_dafoam_mpi_refactor_backups/     (delete dir, 14 files)
bsm3/core/boundary_surface_movement/elasticity.py
bsm3/core/boundary_surface_movement/motion.py
bsm3/core/boundary_surface_movement/projection.py
bsm3/core/boundary_surface_movement/load_stepping.py
bsm3/core/boundary_surface_movement/__init__.py
bsm3/core/boundary_surface_movement/e175_mesh_motion_config.py
bsm3/core/boundary_surface_movement/e175_mesh_motion_pipeline.py
bsm3/core/boundary_surface_movement/cfd_mesh_movement_test.py
bsm3/core/boundary_surface_movement/cfd_mesh_dafoam_analysis.py
bsm3/core/boundary_surface_movement/DAFOAM_MPI_RANK0_HANDOFF.md
tests/test_boundary_surface_movement.py
tests/test_e175_driver_configuration.py
docs/overhaul/MANIFEST.md
docs/overhaul/PLAN.md
docs/overhaul/LOG.md
docs/overhaul/CODEX_NEXT.md
```

## Prohibited

`ngon_affine.py`, `quality.py`, `current_graph_solve.py`,
`quadratic_distortion.py`, `geometry.py`, `intersections.py`, `rbf.py`,
`analytical_SDF_anchor_attraction_noarg.py`, `geometry_volume_mpi.py`,
`run_dafoam_gmsh.py`, `tests/test_geometry_volume_mpi.py`, the `movement_test_*`
scripts, the eight excluded dirty files, the three deferred untracked production
files, `tests/test_hybrid_volume_mesh_motion.py`. No history rewrite, no
`git add -A`, no staging outside the allowlist, no starting
M1.1/M1.2/M1.5-M1.8, no symbol retained "for compatibility", and **no edit to
`docs/overhaul/LOG.md` other than appending Turn 18**.

## STOP RULE

If deletion exposes a dependency outside these 20 paths, or if any acceptance
command below proves unsatisfiable, **stop and report in `LOG.md`** as you did
in Turns 12, 14 and 16. Do not widen silently, do not relocate a helper into a
permitted file, do not edit a backup or a history document to satisfy a grep.
All three stops so far were Claude's planning defects; a fourth would be too.

## Acceptance commands — all scoped to live/package content

```bash
# 1. removed APIs are gone from bsm3/ and tests/ (docs/overhaul/ is exempt by design)
git grep -i membrane -- bsm3/ tests/                          # MUST be empty
git grep -i corotational -- bsm3/ tests/                      # MUST be empty
git grep -nE "TangentialSmoothingConfig|FixedProjectedTangentialSmoother|assemble_fixed_projected_tangential_smoother|tangential_smoother|TANGENTIAL_SMOOTHING|tangential_smoothing=|tangential_smoothing import|surface\.tangential_smoothing|tangential_smoothing_ids" -- bsm3/ tests/   # MUST be empty
git grep -n "inversion_barrier\|oml_quality\|FinalSurfaceQuality\|select_fixed_vertex_band" -- bsm3/ tests/    # MUST be empty
git grep -nE "ParameterizedProjection|project_onto_oml_parameterized|parameterize_final_projection|final_parameterized_projection" -- bsm3/ tests/   # MUST be empty
git grep -n 'mode="graph"' -- bsm3/                           # MUST be empty
git grep -n "ELASTIC_STRATEGY" -- bsm3/                       # MUST be empty
git grep -n "_dafoam_mpi_refactor_backups" -- bsm3/ tests/    # MUST be empty (docs/overhaul/ keeps its record)

# barrier: MUST list exactly the seven permitted MPI sites in four files, nothing else
git grep -n -i barrier -- bsm3/ tests/

# 2. permitted survivors MUST still be present and passing
git grep -c tangential_smoothing_step -- bsm3/core/boundary_surface_movement/analytical_SDF_anchor_attraction_noarg.py
git grep -c -i barrier -- tests/test_geometry_volume_mpi.py bsm3/core/boundary_surface_movement/geometry_volume_mpi.py
python -m pytest -q tests/test_analytical_sdf_anchor_attraction.py
python -m pytest -q tests/test_geometry_volume_mpi.py

# 3. no stale exports / dead imports
python -c "import bsm3, bsm3.core.boundary_surface_movement as m, bsm3.preprocessing; print('import smoke OK', len(m.__all__))"
python -c "import bsm3.core.boundary_surface_movement as m; [getattr(m,n) for n in m.__all__]; print('every __all__ entry resolves')"
python -m ruff check bsm3/core/boundary_surface_movement/elasticity.py \
  bsm3/core/boundary_surface_movement/motion.py \
  bsm3/core/boundary_surface_movement/projection.py \
  bsm3/core/boundary_surface_movement/load_stepping.py \
  bsm3/core/boundary_surface_movement/__init__.py \
  bsm3/core/boundary_surface_movement/e175_mesh_motion_config.py

# 4. focused: graph, N-gon, distortion, projection, derivative gate
python -m pytest -q tests/test_boundary_surface_movement.py
python -m pytest -q tests/test_ngon_affine_operator.py tests/test_ngon_affine_load_step.py
python -m pytest -q tests/test_function_set_projection_numpy.py
python -m pytest -q tests/test_e175_driver_configuration.py
python -m pytest -q tests/test_derivative_gate.py

# 5. full suite
python -m pytest -q tests
```

## Genuine-clone verification

```bash
rm -rf /tmp/bsm3-m13e-verify
git clone --no-hardlinks --branch production-ready-overhaul \
  "file:///Users/mariusruh/Documents/Research/nasa_uli/mesh_movement/packages/BSM3" \
  /tmp/bsm3-m13e-verify
cd /tmp/bsm3-m13e-verify
git status --porcelain                                        # MUST print nothing
git grep -iE "membrane|corotational" -- bsm3/ tests/          # MUST be empty
git grep -n "_dafoam_mpi_refactor_backups" -- bsm3/ tests/    # MUST be empty
test ! -d bsm3/core/boundary_surface_movement/_dafoam_mpi_refactor_backups && echo "backups dir gone"
for f in inversion_barrier oml_quality tangential_smoothing; do
  test ! -e bsm3/core/boundary_surface_movement/$f.py && echo "$f.py gone"
done
PYTHONPATH=/tmp/bsm3-m13e-verify python -m pytest -q tests
```

Use `PYTHONPATH`, not `pip install -e .`.

**Expected: 157 passed, 1 skipped** (from 162/1 at `52b43c9`, minus five deleted
tests). Report the actual number.

## Definition of done

1. Membrane and corotational greps empty over `bsm3/` and `tests/`.
2. The narrowed tangential-API grep empty, while `tangential_smoothing_step`
   survives in `analytical_SDF_anchor_attraction_noarg.py` and its test passes.
3. `git grep -i barrier -- bsm3/ tests/` lists **exactly the seven permitted MPI
   sites in four files** — `cfd_mesh_dafoam_analysis.py:346`,
   `geometry_volume_mpi.py:77`, `run_dafoam_gmsh.py:653/656/911/954`,
   `tests/test_geometry_volume_mpi.py:69` — and nothing else.
4. `git grep -n "_dafoam_mpi_refactor_backups" -- bsm3/ tests/` empty; the
   directory does not exist; `docs/overhaul/` **retains** its historical record.
5. `inversion_barrier.py`, `oml_quality.py`, `tangential_smoothing.py` do not
   exist.
6. No parameterized-projection symbol survives; ordinary `project_onto_oml`,
   `reevaluate_vertices`, `combine_vertices`, `VertexBatch`, `_project_group`
   and `_coefficient_subset` do.
7. `ELASTIC_STRATEGY` gone; graph load-step path unconditional.
8. No stale exports — every `__all__` entry resolves. No dead imports or
   orphaned private helpers in the four partially edited modules.
9. No one-valued compatibility fields; no tracked `mode="graph"`,
   `tangential_smoothing=`, or `final_quality=` under `bsm3/`.
10. M1.4 polygon6 tests and the affine-nullspace gate pass unchanged; full suite
    green from a genuine clone at the expected count; nothing outside the
    allowlist staged; every excluded dirty file still dirty; actual counts,
    timings and any stop-rule invocation recorded in Turn 18.
