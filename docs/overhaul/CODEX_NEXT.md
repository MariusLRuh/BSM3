# Claude Turn 34 — implement the bounded M1.7a correction

You are the **implementer**. Codex is the **planner/reviewer**. Implement this
turn, verify it, commit it in coherent commits, update the handoff documents,
and leave `docs/overhaul/CODEX_NEXT.md` as a concise review checklist for Codex.
Do not review or accept your own work.

## Review ruling

Turn 32 is rejected pending this correction. Preserve its useful results: the
compact five-stage example, the `bsm3.mesh_motion` namespace, intuitive public
names, cache containment, unchanged derivative gates, and M1.4 polygon tests.
Correct these three contract defects:

1. BSM3's core boundary must accept deformed component coefficients produced
   by an external parameterization. `GeometryModel.add_lifting_surface` and
   `add_body` are optional conveniences, not the only way into the pipeline.
2. `GeometryModel` must not start or own global CSDL recorder state. Recorder
   lifecycle must be explicit and caller-owned.
3. The result currently calls the pre-reprojection report a baseline. Report
   the input, preprojection, and final states separately and compare the same
   metric at each state.

## Literal path allowlist

Only these paths may change:

1. `bsm3/core/boundary_surface_movement/geometry_model.py`
2. `bsm3/core/boundary_surface_movement/mesh_motion_pipeline.py`
3. `bsm3/core/boundary_surface_movement/mesh_motion_config.py`
4. `bsm3/mesh_motion.py`
5. `examples/e175_surface_deformation.py`
6. `tests/test_e175_example.py`
7. `tests/test_e175_driver_configuration.py`
8. `docs/overhaul/PLAN.md`
9. `docs/overhaul/LOG.md`
10. `docs/overhaul/CODEX_NEXT.md`

Do not widen this list silently. If the correction genuinely requires another
path, stop and report the exact dependency and proposed path. Do not modify
generated caches or tracked E175 assets.

## 1. Make external coefficients a first-class geometry input

Add a public, configuration-agnostic `GeometryModel.add_component(...)` path.
Its essential inputs are:

- a stable component `name`;
- the STEP importer's `search_name`;
- the component's externally produced `deformed_coefficients`;
- an optional simple free-region declaration;
- optional projection name/mode settings already understood by the pipeline.

The external value may be either:

- one stacked CSDL variable/array of shape `(N, 3)`, using sorted component
  patch-ID order, which is the existing BSM3 convention; or
- a mapping from patch ID to coefficient block, with the same shapes as the
  imported LFS component patches.

Resolve and validate this value after the STEP component is imported, when the
canonical patch IDs and coefficient shapes are known. Reject missing/extra
patch IDs, wrong block shapes, a wrong stacked row count, or a non-3D trailing
dimension with clear errors. Preserve CSDL expressions; do not convert an
external CSDL variable to NumPy.

For load fraction `f`, supply
`baseline_coefficients + f * (target_coefficients - baseline_coefficients)`.
At `f=1`, the exact external target must reach the existing intersection,
graph-Laplacian, and reprojection chain. Derivatives from the final reprojected
mesh to the external coefficient variable must remain analytic.

Keep `add_lifting_surface` and `add_body` working as convenience methods. Do
not expose `_ComponentRecord`, coefficient-builder callbacks, free-region
factories, or polygon helpers. A caller must not need to subclass BSM3.

Use an uncluttered high-level free-region input rather than a callback. `None`
must mean the whole imported component is free. If a restricted region is
provided, accept a mapping whose keys are `x`, `y`, or `z` and whose values are
`(lower, upper, mode)` tuples, then build the existing private `AxisRange` /
`ComponentFreeRegion` objects internally. Bounds may be `None`; mode must use
the existing vocabulary. Avoid adding a new public dataclass for this.

`GeometryModel.validate()` must require at least one component but must no
longer require a variable created by `GeometryModel.design_variable()`.
External variables may be created and owned entirely by another package.

Add focused tests that cover:

- a stacked external CSDL coefficient variable;
- a per-patch mapping;
- key and shape validation failures;
- load-fraction interpolation reaching the target exactly; and
- a nonzero analytic derivative of a scalar made from the final reprojected
  mesh with respect to an external coefficient/design variable, checked
  against centered finite difference with the existing derivative tolerance.

Use a small fixture for focused contract tests; do not make every case run the
full E175 mesh. At least one end-to-end example-path test must exercise the
external-coefficient entry point, even if the main E175 example continues to
show the built-in convenience helpers for readability.

## 2. Make recorder ownership explicit

Remove `_recorder`, `_owns_recorder`, `recorder`, `owns_recorder`, and all
automatic recorder creation/start/stop behavior from `GeometryModel`.
`design_variable()` may return a CSDL variable only when a recorder is already
active; fail immediately with a clear message otherwise.

Make `recorder` a required argument of `bsm3.mesh_motion.run`. `run` must never
start or stop it. It passes the recorder into the pipeline and retains it on
the result. This preserves composition with DAFoam and other caller-owned CSDL
graphs.

In `examples/e175_surface_deformation.py`, explicitly create and start the
recorder before stage 2, pass it in during stage 4, and stop it in a `finally`
block after the run. Keep the five stages visibly distinct and the script
compact. Four module imports (`Path`, `tempfile`, `csdl_alpha`, and
`bsm3.mesh_motion`) are acceptable; do not restore a CLI, `mesh_kind`, local
dataclasses, callbacks, or low-level geometry/polygon helpers.

Test that:

- `GeometryModel()` alone does not alter recorder state;
- `design_variable()` without an active recorder raises clearly;
- `mm.run` neither starts nor stops the supplied recorder; and
- exceptions from `mm.run` do not change caller ownership.

## 3. Correct inversion accounting

Replace the misleading `baseline_inversion_report` result field with these
three unambiguous fields:

- `initial_inversion_report`, evaluated from `setup.initial_full_vertices`;
- `preprojection_inversion_report`, evaluated from the deformed surface before
  reprojection; and
- `surface_inversion_report`, the final reprojected surface report.

Update docstrings and `print_summary()` labels accordingly. There must be no
compatibility alias for `baseline_inversion_report`; this overhaul permits a
clean break. Compute the polygon fold count only once.

For the unchanged tracked quad asset, the initial reference is:

- 114 inverted **elements**;
- 114 inverted corners;
- 0 degenerate elements.

Pin those values in the relevant integration test. The Turn-32 `118 -> 118`
values were preprojection -> final, not input -> final. Turn 30's logged 116
also included 116 inverted elements, so this was not merely a corner/element
metric mismatch.

Tune the example's high-level design values, keeping at least one deformation
strictly nonzero, until both the preprojection and final inverted-element ID
sets introduce no IDs outside the initial set. Compare ID sets, not only
counts. The triangle wall must remain at zero initial/preprojection/final
inversions and zero folds. If the unchanged asset does not reproduce the
114/114/0 input reference, stop and report rather than changing the asset or
the threshold.

## Required regression gates

Run the narrow tests first, then all affected integration and established
numerical guards. At minimum:

```bash
conda run -n central_geom python -m pytest -q \
  tests/test_e175_example.py \
  tests/test_e175_driver_configuration.py

conda run -n central_geom python -m pytest -q \
  tests/test_e175_boundary_surface_movement_derivatives.py \
  tests/test_polygon_regularization.py \
  tests/test_ngon_affine_regularization.py
```

After committing the implementation, use this exact clean-clone procedure.
The destination must not already exist; if it does, choose a new explicit
`/tmp` path rather than deleting an ambiguous directory.

```bash
git clone --no-hardlinks --branch production-ready-overhaul \
  "file:///Users/mariusruh/Documents/Research/nasa_uli/mesh_movement/packages/BSM3" \
  /tmp/bsm3-m17a-turn34-verify
cd /tmp/bsm3-m17a-turn34-verify
git status --porcelain
PYTHONPATH=/tmp/bsm3-m17a-turn34-verify \
  conda run -n central_geom python examples/e175_surface_deformation.py
PYTHONPATH=/tmp/bsm3-m17a-turn34-verify \
  conda run -n central_geom python -m pytest -q tests
git status --porcelain
```

Run the example against the tracked triangle wall and tracked quad-dominant
wall. Report each runtime. Stop and report if either exceeds approximately ten
minutes; do not hide a runtime regression by weakening the test. Status must
be empty both before and after the example and suite.

The existing derivative reference values, M1.4 thresholds, and Turn-32 clean
clone count (`161 passed, 1 skipped` before this turn's intentional test
additions) are guards, not values to reconcile. Any unexpected numerical
change is a bug to explain.

Run these mechanical checks and report their output:

```bash
rg -n "baseline_inversion_report|owns_recorder|self\._recorder|geometry\.recorder" \
  bsm3/mesh_motion.py \
  bsm3/core/boundary_surface_movement/geometry_model.py \
  bsm3/core/boundary_surface_movement/mesh_motion_config.py \
  bsm3/core/boundary_surface_movement/mesh_motion_pipeline.py \
  examples/e175_surface_deformation.py tests/test_e175_example.py \
  tests/test_e175_driver_configuration.py

rg -n "argparse|mesh_kind|DeclarativeGeometryParameterization|class .*Config" \
  examples/e175_surface_deformation.py

git diff --check
git status --short
```

The first two greps must return no matches. Keep the existing applicable-if-
present polygon regularization behavior and do not reintroduce membrane,
log-barrier, tangential-smoothing, pickle, or mesh-kind branches.

## Commit and handoff

Use small coherent commits (API/contract, example/tests, then documents is a
reasonable split). Update `PLAN.md` and append a concise implementation record
to `LOG.md`; do not rewrite prior entries. Replace this file with the exact
Codex review checklist: commits, changed paths, API signatures, external-
coefficient derivative evidence, recorder lifecycle evidence, the three
inversion reports and ID-set comparisons for tri/quad, runtimes, test counts,
clone commands/results, greps, and any deviations. Then hand back for Codex
review. Do not mark M1.7a accepted yourself.
