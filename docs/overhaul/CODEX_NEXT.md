# Claude implementation prompt — M1.7 final API corrections and acceptance

Codex is the planner/reviewer; Claude is the implementer and acceptance-run
operator. **M1.8 is accepted.** Complete M1.7, then hand it back to Codex
without self-accepting M1 or M1.7.

At the start, record `TURN58_BASE=$(git rev-parse HEAD)`. Preserve the dirty
tree exactly. Do not amend, reset, rebase, rewrite, push, clean, stash, install
packages, or modify another repository.

## Literal allowlist

Only these 14 paths may change after `TURN58_BASE`:

```text
bsm3/core/boundary_surface_movement/__init__.py
bsm3/core/boundary_surface_movement/cfd_mesh_dafoam_analysis.py
bsm3/core/boundary_surface_movement/forward_only_fd_checker.py
bsm3/core/boundary_surface_movement/graph_distance.py
bsm3/core/boundary_surface_movement/run_dafoam_gmsh.py
bsm3/plotting.py
tests/test_boundary_surface_movement.py
tests/test_dafoam_csdl.py
tests/test_e175_driver_configuration.py
tests/test_geometry_volume_mpi.py
tests/test_preprocessing_plotting.py
docs/overhaul/PLAN.md
docs/overhaul/LOG.md
docs/overhaul/CODEX_NEXT.md
```

A path need not change merely because it is allowlisted. Stage paths literally;
never stage a directory.

Specifically prohibited:

- all eight pre-existing modified files, including
  `movement_test_embraer_175_hex_mesh.py`;
- every untracked file, including the panel driver and panel mesh;
- `examples/e175_surface_deformation.py` and `tests/test_e175_example.py` —
  they are acceptance inputs, not implementation targets;
- `../VortexAD`, either source or environment installation;
- dependency pins, workflow files, curated assets, mesh-motion numerics, and
  DAFoam/OpenFOAM execution.

If a required correction needs another path, stop and report it. Do not widen
the allowlist or absorb a nearby cleanup.

## First action: capture the pre-edit R4 reference

Before changing Python source, run the generalized surface-motion chain on the
local R4 STEP and wall assets named by tracked
`cfd_mesh_movement_test.MODEL_FILES`.

- Use `create_geometry_model()` and the tracked current geometry values.
- Override the setup cache to a fresh directory under `/tmp`.
- Keep volume motion off, mesh writing off, and visualization off.
- Do not run DAFoam or mutate the module constants/files.
- Save outside the repository: final surface coordinates; initial,
  preprojection, and final inverted-element ID arrays; fold count; surface
  cell count; and relevant quality scalars.
- Record shape, SHA-256 of contiguous float64 final coordinates, diagnostics,
  and runtime.

This is the reference for the post-edit run. If the surface run exceeds 15
minutes, stop it and report where time was spent; do not silently drop the R4
criterion. Do not create or update any cache/output inside the repository.

## Part A — close the five accumulated API findings

### A1. Typed graph-distance summary; remove dead payload

In `graph_distance.py`, add a documented `GraphDistanceSummary(TypedDict)`
whose fields match the actual returned keys and scalar types. Change
`GraphDistanceWeighting.summary` to return it. Remove the dead `"decay"` entry;
the only retained caller prints `distance.decay` from configuration and never
reads `summary["decay"]`.

Export `GraphDistanceSummary` beside `GraphDistanceWeighting` from the boundary
surface package. Add a test asserting the exact summary keys and representative
types/values, including that `"decay"` is absent. Do not change graph weights,
distances, or solver behavior.

### A2. Correct `DerivativeComparison.best`

The best step is `None` when an analytical key has no recorded finite error.
Change the return and local-result annotations from `tuple[float, float]` to
`tuple[float | None, float]`; make the docstring match. Add a regression that
constructs this empty-error case and obtains `(None, inf)`. Do not change the
selection algorithm or reporting behavior for populated comparisons.

### A3. Correct the optional DAFoam result snapshot

Change `E175DAFoamResult.mesh_motion` to `MeshMotionResult | None`. Its
docstring already explains why both non-root and lazy root construction can
produce `None`; remove the stale note that the annotation is non-optional.
Add a structural/type-hint regression. Do not run or change DAFoam.

### A4. Make both `FlowConfig` fields real inputs

`nu_tilda_m2_per_s` and `use_wall_functions` must no longer be dead payload.

- Validate `nu_tilda_m2_per_s` as finite and non-negative.
- In `build_da_options`, add the standard farfield `nuTilda0` primal-BC entry:
  variable `"nuTilda"`, the native-list farfield patches, and a one-element
  value list containing `config.nu_tilda_m2_per_s`.
- Set `primalBC["useWallFunction"]` from
  `bool(config.use_wall_functions)` rather than a literal.
- Replace the contradictory CLI inversion with one
  `argparse.BooleanOptionalAction` option named `--wall-functions`, defaulting
  to `FlowConfig().use_wall_functions`. Python then supports both
  `--wall-functions` and `--no-wall-functions`; pass `args.wall_functions`
  directly into `FlowConfig`.
- Correct the affected class/parser docstrings and help text.

Add unit tests for option propagation, native containers, invalid `nuTilda`,
and parser default/positive/negative flag behavior. No DAFoam dependency or
case execution is required.

### A5. Make `plot_components(colors=None)` preserve component colors

Treat `colors=None` like the existing empty-string sentinel: broadcast a
no-override value for every component and omit the color keyword. Update the
public docstring and add a test that confirms existing component colors are
preserved for a nonempty component list. Keep all scalar/list length behavior.

## Part B — final numerical acceptance

### B1. R4 reproduction

After the source commit, rerun the same isolated R4 surface probe with a fresh
`/tmp` cache. Compare against the pre-edit record:

- coordinate shape identical;
- maximum absolute coordinate difference `<= 1e-12` and
  `allclose(rtol=atol=1e-12)`;
- identical inversion ID arrays at all three stages;
- identical fold count, cell count, and quality scalars to `1e-12`.

The five API corrections should not move the mesh. A moved output is a defect,
not a new baseline.

### B2. Flagship E175 and large-deformation gates

Run the complete tracked E175 example module, including integration tests:

```bash
conda run -n bsm3_py312_main python -m pytest -q tests/test_e175_example.py
```

Report separately the real triangle, real quad, external-coefficient analytic
versus centered-FD, whole-component-free, and full-scale triangle outcomes.
The established requirements remain: no new inversion IDs, zero folds,
nontrivial large displacement, and external derivative relative error below
the existing threshold. Do not weaken or rewrite those tests.

Run the safe mixed-N-gon asset assembly and the true polygon6 derivative gates:

```bash
conda run -n bsm3_py312_main python -m pytest -q \
  tests/test_curated_assets.py -m integration

conda run -n bsm3_py312_main python -m pytest -q \
  tests/test_derivative_gate.py \
  tests/test_ngon_affine_operator.py \
  tests/test_ngon_affine_load_step.py
```

The second command remains exactly 6 passed. The curated command retains the
40,706-face / 117,267-mode assembly.

### B3. VortexAD disposition — verify, do not mutate

Re-confirm these read-only facts and record them as the formal reason the
STEP-to-VortexAD path is impractical in M1:

- neither `VortexAD` nor `vortexad` is installed in `bsm3_py312_main`;
- sibling `../VortexAD` is on `dev_new_derivs` at `c33828d` with three modified
  solver files;
- a `PYTHONPATH=../VortexAD` import fails on missing `vedo`;
- the panel driver and its high-quality mesh are untracked; and
- that driver imports removed pre-generalization modules/types, so installing
  one missing plotting dependency would still not make it a supported test.

Do not install `vedo`, alter the environment, modify VortexAD, or adopt the
untracked driver/assets. This is an evidence-backed deferral, not a waived
test. Record a future task: build a tracked adapter against a pinned clean
VortexAD revision using the generalized `mm.run` result and the curated quad
mesh.

### B4. Regression suites, lint, and clean clone

Run the focused groups after implementation:

```bash
conda run -n bsm3_py312_main python -m pytest -q \
  tests/test_function_set_projection_numpy.py \
  tests/test_warm_start_retry_regression.py \
  tests/test_preprocessing_plotting.py \
  tests/test_curated_assets.py \
  tests/test_boundary_surface_movement.py -m "not integration"

conda run -n bsm3_py312_main python -m pytest -q \
  tests/test_dafoam_csdl.py \
  tests/test_geometry_volume_mpi.py \
  tests/test_volume_mesh_motion.py \
  tests/test_preprocessing_plotting.py \
  tests/test_e175_driver_configuration.py
```

Counts may increase only by the explicitly added tests. Any old-test failure or
numerical drift is a defect.

Run all five literal Ruff commands from `.github/workflows/actions.yml`.
Additionally run the default Ruff selection on every changed Python path,
including test files; do not claim the workflow covers a file it does not list.

After committing source and tests, make a genuine local clone in a new
`mktemp -d` directory under `/tmp`, check out the current branch tip, and run:

```bash
conda run -n bsm3_py312_main python -m pytest -q tests
```

Run from the clone so its checkout is first on `sys.path`; do not reinstall or
change the environment. The clone must finish with empty
`git status --porcelain`. Report exact pass/skip counts and runtime. The local
R4-only check may skip there because those inputs are intentionally untracked.

## Static acceptance checks

The final tree must satisfy:

```bash
git grep -n '"decay": self.decay' -- \
  bsm3/core/boundary_surface_movement/graph_distance.py

git grep -n 'tuple\[float, float\]' -- \
  bsm3/core/boundary_surface_movement/forward_only_fd_checker.py

git grep -n 'mesh_motion: MeshMotionResult$' -- \
  bsm3/core/boundary_surface_movement/cfd_mesh_dafoam_analysis.py

git grep -n '"useWallFunction": False' -- \
  bsm3/core/boundary_surface_movement/run_dafoam_gmsh.py

git grep -n 'use_wall_functions=not args' -- \
  bsm3/core/boundary_surface_movement/run_dafoam_gmsh.py
```

All five are empty. Also demonstrate through tests or an inspection command
that `GraphDistanceSummary` is exported, `DerivativeComparison.best` exposes
the optional step, and `E175DAFoamResult` exposes an optional mesh result.

Verify `git diff --check "$TURN58_BASE" HEAD` is empty, changed paths are a
subset of the literal allowlist, all eight pre-existing modified files are
byte-identical, and no pre-existing untracked artifact was removed or adopted.

## Documentation, commits, and handoff

Append the M1.7 results to `LOG.md`; mark M1.7 ready for Codex acceptance in
`PLAN.md`; and replace `CODEX_NEXT.md` with the review checklist. Preserve
history. Include the Turn-58 correction that the excluded dirty hex research
script needs a reader change as well as a path change.

Make exactly two commits without rewriting history:

1. the six production/API paths and only the tests that actually changed;
2. `PLAN.md`, `LOG.md`, and `CODEX_NEXT.md` only.

Hand back **M1.7 and M1 ready for final Codex acceptance, not self-accepted**.
Report both commits, exact paths, every API decision, pre/post R4 numbers,
flagship and derivative metrics, mixed-N-gon result, focused/full-clone counts,
all Ruff results, VortexAD evidence, dirty-tree preservation, and every
deviation or stop.
