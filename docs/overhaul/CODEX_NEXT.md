# Review prompt for Claude — Turn 23 (M1.1 + M1.2)

Paste into Claude at the repository root.

---

Review Codex Turn 22 in `docs/overhaul/LOG.md` and independently audit commit
`872c0f1` (`Generalize and decompose mesh motion pipeline`). Claim
`## Turn 23 — Claude, planner/reviewer` in `LOG.md` before making any review
edits and close the turn when finished.

This is an implementation review, not the M1.5 implementation turn. You may
make narrowly necessary corrections within the implementation paths below, but
do not begin mesh-generation work.

## What Codex changed

- Renamed the two E175-named core modules:
  - `e175_mesh_motion_config.py` -> `mesh_motion_config.py`
  - `e175_mesh_motion_pipeline.py` -> `mesh_motion_pipeline.py`
- Replaced the six stale public symbols with `ModelFiles`, `PipelineConfig`,
  `MeshMotionResult`, `GeometryParameterization`, `build_mesh_motion_model`, and
  `MeshMotionVolumeBackend`.
- Added driver-owned `list[ComponentSpec]` and `list[IntersectionSpec]`
  declarations and driver-supplied coefficient builders.
- Added the ruled `parameterization_factory` callback to the generic rank-0
  backend and wired both DAFoam consumers.
- Split the 1,076-LOC builder into five stages. The public builder is 98 LOC;
  no function in the module exceeds 300 LOC.
- Removed the alias block, hardcoded core component search, and orphaned
  `elasticity._validate_partition`.

## Review priorities

1. **API generality.** Confirm the generic config, pipeline, and rank-0 backend
   contain no E175-named type or design-variable dependency. E175-specific
   names may remain in the three driver modules and their filenames.
2. **Protocol boundary.** Confirm `GeometryParameterization`, `ComponentSpec`,
   and `IntersectionSpec` are sufficient for a user-provided configuration;
   the backend must construct one only through its supplied factory.
3. **Numerical equivalence.** Compare the new stages against the parent of
   `872c0f1`. Pay special attention to component ordering, deformation-vertex
   ordering, intersection ordering, free-region selection, graph-distance
   seeds, projection metadata, load-step coefficient maps, symmetry
   reconstruction, volume handoff, and diagnostics. A moved derivative or
   changed operator is a defect, not a result to reconcile.
4. **Module rename.** Confirm every tracked import/export was updated and the
   old modules are genuinely absent. The pipeline appears as delete/add rather
   than a detected rename because the decomposition reduced textual similarity;
   judge content, not Git's similarity label.
5. **Code quality.** Check touched files for dead imports, stale exports,
   orphaned helpers, accidental public aliases, mutable-state hazards, and
   functions over 300 LOC. Judge whether the two driver-local parameterization
   factories are acceptable duplication or require a driver-level shared home;
   do not move E175 logic back into core.
6. **Dirty-tree safety.** Confirm commit `872c0f1` contains only the authorized
   implementation paths and none of the eight excluded dirty files.

## Authorized review paths

```
bsm3/core/boundary_surface_movement/DAFOAM_MPI_RANK0_HANDOFF.md
bsm3/core/boundary_surface_movement/__init__.py
bsm3/core/boundary_surface_movement/cfd_mesh_dafoam_analysis.py
bsm3/core/boundary_surface_movement/cfd_mesh_movement_test.py
bsm3/core/boundary_surface_movement/e175_derivative_ladder.py
bsm3/core/boundary_surface_movement/mesh_motion_config.py
bsm3/core/boundary_surface_movement/mesh_motion_pipeline.py
bsm3/core/boundary_surface_movement/elasticity.py
bsm3/core/boundary_surface_movement/geometry_volume_backend.py
tests/test_e175_driver_configuration.py
docs/overhaul/PLAN.md
docs/overhaul/LOG.md
docs/overhaul/CODEX_NEXT.md
```

The deleted old module paths are authorized only for verifying their absence.
`tests/test_geometry_volume_mpi.py`, derivative-gate tests, M1.4 tests, numerical
kernels, and all unrelated dirty files remain prohibited edit targets. If a
real defect requires one, invoke the stop rule and report it rather than
widening scope silently.

## Required checks

Run in the existing `central_geom` environment; the base environment carries an
incompatible `csdl_alpha` checkout.

```bash
# Stale API and core coupling: all empty.
git grep -nE "E175ModelFiles|E175PipelineConfig|E175GeometryVariables|E175MeshMotionResult|E175GeometryVolumeBackend|build_e175_mesh_motion_model" -- bsm3/ tests/
git grep -n "E175" -- bsm3/core/boundary_surface_movement/geometry_volume_backend.py
git grep -n 'search_names=\["wing"' -- bsm3/
git grep -nE "^\s{4}[A-Z][A-Z0-9_]+ = (surface|volume|config|distance|smoothing|distortion|ngon|final)" -- bsm3/core/boundary_surface_movement/
git grep -n "_validate_partition" -- bsm3/core/boundary_surface_movement/elasticity.py
git grep -n "e175_mesh_motion_config\|e175_mesh_motion_pipeline" -- bsm3/ tests/

# Public exports.
conda run -n central_geom python -c "import bsm3.core.boundary_surface_movement.geometry_volume_backend as g; assert hasattr(g,'GeometryVolumeBackend'); assert hasattr(g,'CSDLRecorderBackend'); assert hasattr(g,'MeshMotionVolumeBackend'); assert not [n for n in g.__all__ if not hasattr(g,n)]"
conda run -n central_geom python -c "import bsm3.core.boundary_surface_movement as m; [getattr(m,n) for n in m.__all__]; print(len(m.__all__))"

# Function-size ceiling.
python - <<'PY'
import ast, glob
for path in glob.glob("bsm3/core/boundary_surface_movement/*mesh_motion_pipeline.py"):
    tree = ast.parse(open(path).read())
    over = [(node.name, node.end_lineno-node.lineno+1) for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
            and node.end_lineno-node.lineno+1 > 300]
    print(path, over if over else "none")
PY

# Numerical guards and read-only MPI tripwire.
conda run -n central_geom python -m pytest -q tests/test_derivative_gate.py
conda run -n central_geom python -m pytest -q tests/test_ngon_affine_operator.py tests/test_ngon_affine_load_step.py
conda run -n central_geom python -m pytest -q tests/test_geometry_volume_mpi.py
conda run -n central_geom python -m pytest -q tests
```

Independently repeat the genuine-clone validation from commit `872c0f1`. The
clone must be clean, the six-symbol grep empty, and the result exactly
**157 passed / 1 skipped**. Codex measured **32.08 s**. The dirty working tree
contains an additional untracked test and should remain **171 passed**; do not
confuse that expected difference with test-count drift.

## Deliverables

- Append the complete review, commands, counts, timings, and any corrections to
  Turn 23 in `LOG.md`.
- If the implementation is sound, mark M1.1 and M1.2 **COMPLETE** in `PLAN.md`.
- If it is not sound, leave them open and write one exact corrective prompt.
- Replace `CODEX_NEXT.md` with one complete, paste-ready next prompt. If the
  review passes, that prompt should open M1.5, but first audit its retained
  mesh-generation roots, tests, assets, and literal allowlist so Codex is not
  forced into another avoidable stop.
- Do not implement M1.5 during this review turn.
