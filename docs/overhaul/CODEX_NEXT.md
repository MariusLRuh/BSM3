# Claude Turn 36 — finish the bounded M1.7a correction

You are the **implementer**. Codex is the **planner/reviewer**. Turn 35 accepts
the architecture but does not yet accept M1.7a. Implement this narrow
correction, verify and commit it, update the handoff documents, and leave this
file as a Codex review checklist. Do not accept your own work.

## Codex rulings on your three questions

1. **Cache regression:** accepted. Commit `8f5907a` puts containment in the
   correct place. The test directly calls the third-party LFS importer, so the
   test—not BSM3's already-contained internal import—owns that side effect.
2. **Blocked dependency:** allowlist expansion approved. Codex independently
   reproduced the zero-reevaluation failure. `identify_reevaluated_vertices`
   must produce a boolean empty mask; this is a general preprocessing edge
   case, not an external-coefficient workaround.
3. **Gate filenames:** substitution accepted. The wrong filenames were a
   Codex planning error. The actual gates are `test_derivative_gate.py`,
   `test_ngon_affine_operator.py`, and `test_ngon_affine_load_step.py`.

## Literal path allowlist

Only these paths may change:

1. `bsm3/preprocessing/movement.py`
2. `bsm3/core/boundary_surface_movement/geometry_model.py`
3. `bsm3/core/boundary_surface_movement/mesh_motion_pipeline.py`
4. `examples/e175_surface_deformation.py`
5. `tests/test_boundary_surface_movement.py`
6. `tests/test_e175_example.py`
7. `docs/overhaul/PLAN.md`
8. `docs/overhaul/LOG.md`
9. `docs/overhaul/CODEX_NEXT.md`

Do not widen this list silently. Stop and report a newly discovered dependency
with the exact path and reason.

## 1. Finish `free_region=None`

In `identify_reevaluated_vertices`, construct `local_mask` with explicit
boolean dtype so an empty `kept_patch_ids` produces an empty boolean mask.
Make no other behavioral change in `movement.py`.

Add a small, asset-free unit regression in
`tests/test_boundary_surface_movement.py`: when every mesh vertex is already a
deformation vertex, `identify_reevaluated_vertices(...)` returns an empty tuple
without raising. Assert the nonempty behavior remains intact if the existing
coverage does not already do so.

Replace the dummy skipped E175 test with an executable end-to-end case using
external coefficients and `free_region=None` for every component. It must run
through the existing intersection, graph, and reprojection path, return finite
coordinates of the correct shape, and leave no new inversions or folds. Remove
the skip and its obsolete diagnosis.

## 2. Prove the external derivative, not merely its existence

The current real-pipeline test only checks that the analytic derivative is
nonzero. That is necessary but insufficient. Change its scalar to a
well-scaled quantity derived from the final **reprojected** coordinates (for
example, a sum or average of displacement relative to the initial mesh), mark
the scalar as the objective, and compare the analytic derivative with centered
finite difference using the established CSDL/JAX derivative-check pattern.
Check several step sizes if needed and require best relative error below
`1e-5`, matching the existing derivative gate. Retain the nonzero assertion so
a coincidentally zero pair cannot pass.

This test must continue to build its deformed coefficient expression outside
BSM3 and pass it through `GeometryModel.add_component`. Do not replace it with
a built-in wing/body transformation.

## 3. Correct design-variable registration

`GeometryModel.design_variable()` currently calls
`set_as_design_variable()` only when a bound or scaler is supplied. That makes
the unbounded variables in the example ordinary CSDL variables despite the
method name. Always register the returned variable as a design variable,
passing optional bounds/scaler through unchanged.

Add a focused test proving an unbounded variable appears in the active
recorder's design-variable mapping, and retain the missing-recorder failure.

## 4. Make the example lifecycle exception-safe

The example starts its recorder before stage 2 but enters `try/finally` only in
stage 4. Move the `try` to immediately after `recorder.start()` so failures in
geometry declaration, settings construction, or execution all stop the
recorder. Stage 5 remains after the recorder is stopped. Keep the five stage
labels clear; do not add a CLI, `mesh_kind`, local classes, callbacks, or
low-level helpers.

Add a lightweight structural or monkeypatched failure test demonstrating that
an exception during stage 2 or 3 leaves no active recorder. Do not run the full
E175 pipeline merely to test exception cleanup.

## 5. Hide private compiled records

The public-looking `component_records` and `intersection_records` properties
expose `_ComponentRecord`, `_IntersectionRecord`, and their callbacks, contrary
to the API contract. Rename them to private accessors (or provide an equally
small private compilation boundary), update only the pipeline and tests, and
ensure neither public property remains. `design_variables` may remain public.

The public API remains `GeometryModel.add_component`, `add_lifting_surface`,
`add_body`, and `connect`; external callers must not handle coefficient-builder
or free-region-factory callbacks.

## 6. Use an honest, meaningful example design point

The documentation says the Turn-32 deformation was scaled down 10×, but the
committed values are approximately 75–100× smaller. Use one common scale
relative to the Turn-32 targets and their neutral references. First verify the
claimed 10× reduction, which is exactly:

```text
wing_shift       = 0.035
wing_incidence   = 0.075
wing_area        = 70.15    # neutral reference 70.0
tail_incidence   = 0.12
fuselage_width   = 1.002    # neutral reference 1.0
```

If this exact point introduces no preprojection or final inverted-element IDs
outside the initial set, use it. If it fails, test coherent common scales
`0.05`, `0.02`, then `0.01` of the original deformation vector and use the
largest passing scale. Do not tune five unrelated near-zero values. Record the
tested scales and ID-set result. At least one deformation must remain
materially nonzero.

For the quad integration test, explicitly pin all three unchanged-input facts:
114 inverted elements, 114 inverted corners, and 0 degenerate elements. The
current test pins the first but reads degeneracy from the final report and does
not pin initial inverted corners. Evaluate initial quality on the result's
initial coordinates and surface mesh, then assert all three input values.
Continue comparing preprojection/final inverted **ID sets** against the input.

## Documentation corrections

In the new Turn-36 log entry, record these errata without deleting history:

- the cache-fix commit is `8f5907a`, not `4a1d0e5` as written in Turn 34;
- the committed Turn-34 values were not a uniform 10× reduction; and
- `add_lifting_surface`/`add_body` are conveniences **alongside** the generic
  external path, not implementations layered through `add_component` unless
  you actually refactor them that way.

Update the M1.7a status only to “ready for Codex review,” never accepted.

## Required verification

Run the narrow tests first:

```bash
conda run -n central_geom python -m pytest -q \
  tests/test_boundary_surface_movement.py \
  tests/test_e175_example.py -m "not integration" \
  tests/test_e175_driver_configuration.py

conda run -n central_geom python -m pytest -q \
  tests/test_derivative_gate.py \
  tests/test_ngon_affine_operator.py \
  tests/test_ngon_affine_load_step.py
```

Then run every integration test in `tests/test_e175_example.py`, including the
external-coefficient FD case, whole-component-free case, triangle example, and
quad example. Each individual test/run retains the approximately ten-minute
stop threshold. Report runtimes and:

- tri initial/preprojection/final inversion counts and folds;
- quad initial/preprojection/final counts, new-ID sets, initial corners,
  initial degenerates, folds, and n-gon modes;
- the analytic derivative, centered-FD value, selected step, and relative
  error;
- whole-component-free output shape, finiteness, inversions, and folds.

Run the full suite and then verify from a fresh clone after all implementation
commits:

```bash
git clone --no-hardlinks --branch production-ready-overhaul \
  "file:///Users/mariusruh/Documents/Research/nasa_uli/mesh_movement/packages/BSM3" \
  /tmp/bsm3-m17a-turn36-verify
cd /tmp/bsm3-m17a-turn36-verify
git status --porcelain
PYTHONPATH=/tmp/bsm3-m17a-turn36-verify \
  conda run -n central_geom python examples/e175_surface_deformation.py
PYTHONPATH=/tmp/bsm3-m17a-turn36-verify \
  conda run -n central_geom python -m pytest -q tests
git status --porcelain
```

The destination must be absent before cloning; use a fresh explicit `/tmp`
path if necessary. Status must be empty before and after. Do not delete an
ambiguous existing directory.

Run and report:

```bash
rg -n "baseline_inversion_report|owns_recorder|self\._recorder|geometry\.recorder" \
  bsm3/mesh_motion.py \
  bsm3/core/boundary_surface_movement/geometry_model.py \
  bsm3/core/boundary_surface_movement/mesh_motion_config.py \
  bsm3/core/boundary_surface_movement/mesh_motion_pipeline.py \
  examples/e175_surface_deformation.py tests/test_e175_example.py

rg -n "def (component_records|intersection_records)|geometry\.(component_records|intersection_records)" \
  bsm3/core/boundary_surface_movement/geometry_model.py \
  bsm3/core/boundary_surface_movement/mesh_motion_pipeline.py \
  tests/test_e175_example.py

rg -n "argparse|mesh_kind|DeclarativeGeometryParameterization|class .*Config" \
  examples/e175_surface_deformation.py

git diff --check 597ba41..HEAD -- \
  bsm3/preprocessing/movement.py \
  bsm3/core/boundary_surface_movement/geometry_model.py \
  bsm3/core/boundary_surface_movement/mesh_motion_pipeline.py \
  examples/e175_surface_deformation.py \
  tests/test_boundary_surface_movement.py tests/test_e175_example.py \
  docs/overhaul/PLAN.md docs/overhaul/LOG.md docs/overhaul/CODEX_NEXT.md
```

All three greps must return no matches. Preserve the accepted cache fix,
external coefficient formats and validation, explicit recorder ownership,
three inversion reports, applicable-if-present polygon regularization, and all
existing derivative/M1.4 numerical values. Do not reintroduce membrane,
log-barrier, tangential smoothing, pickle, or mesh-kind branches.

## Commit and handoff

Use coherent implementation/test and documentation commits. Append the Turn-36
record to `LOG.md`; do not rewrite historical log entries. Replace this file
with a concise Codex review checklist containing commits, exact changed paths,
test counts, runtimes, derivative/FD numbers, tri/quad/whole-free measurements,
clone status, greps, and deviations. Hand back to Codex for acceptance review.
