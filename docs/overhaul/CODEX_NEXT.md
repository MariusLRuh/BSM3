# Codex Turn 73 — M4.2: tracked VortexAD adapter and fuel-burn example

Claude accepted **M4.1 in Turn 68** and the **GAMMA identity and HTML-only
alpha in Turn 72**. Codex resumes as implementer; Claude plans and reviews.
Do not self-accept.

This prompt is **reissued verbatim** from `38cd0bf`. Only the turn number, the
base hash, and one line superseded by the GAMMA adoption have changed; every
requirement, allowlist entry, and gate is exactly as planned in Turn 68.

Record `TURN73_BASE = a291231` before editing. Preserve the user's dirty tree
exactly: 8 pre-existing modified tracked files byte-for-byte (including the two
unstaged edits in `visualize_wing_rotation_deformation.py`) and 393 untracked
entries. Do not adopt, delete, format, or modify any of them.

## Goal

Replace the "VortexAD — deferred" section of `docs/src/integrations.md` with a
real, supported, **tracked** integration: a differentiable panel-method adapter
driven by the `mm.run` result, plus a fuel-burn objective, plus an optimization
example. The point of the milestone is an end-to-end analytic derivative from
geometry design variables through mesh motion and aerodynamics to a fuel-burn
scalar.

## Hard constraints

1. **Do not install anything.** VortexAD is not in the validated environment
   and this turn does not add it. Everything tracked must import and test
   without VortexAD present.
2. **Do not break the M2 clean-install contract.** `setup.py` keeps
   `install_requires=[]`. VortexAD is documented as an optional extra in the
   requirements files, never a base dependency, and never added to
   `requirements-ci.txt`. M2 cost real effort to make installable; do not
   regress it.
3. **Do not run** DAFoam, OpenFOAM, real MPI, or VortexAD itself.
4. **Do not resurrect the untracked prototypes.** They are reference only.
5. **Do not touch the public identity.** GAMMA, `gamma-mdo`, and version
   `0.2.0a1` were accepted in Turn 72 and are settled. The import namespace is
   still `bsm3`, so every new module lives under `bsm3/`. Write GAMMA, not
   BSM3, in any new user-facing prose.
6. **Do not start M3.** Release pruning stays separate and last.

## Reference material — read, do not adopt

Three untracked prototypes contain the physics worth reusing. They import
`e175_mesh_motion_config`, `E175ModelFiles`, and `E175PipelineConfig`, none of
which still exist, so they do not run:

```text
bsm3/core/boundary_surface_movement/e175_panel_opt.py
bsm3/core/boundary_surface_movement/embraer_175_drag_build_up.py
bsm3/core/boundary_surface_movement/embraer_175_gross_weight_estimation.py
```

`e175_panel_opt.py` already uses the correct deferred-import shape —
`from VortexAD import PanelMethod, TE_detection, find_cell_adjacency` inside a
function — and already routes through a single-objective selector. Reuse the
model, not the file. Leave all three untracked and unmodified.

## Literal implementation allowlist

```text
bsm3/core/boundary_surface_movement/panel_aerodynamics.py     (new)
bsm3/core/boundary_surface_movement/fuel_burn.py              (new)
bsm3/core/boundary_surface_movement/__init__.py
bsm3/mesh_motion.py
examples/e175_fuel_burn_optimization.py                       (new)
tests/test_panel_aerodynamics.py                              (new)
tests/test_fuel_burn.py                                       (new)
docs/src/integrations.md
docs/src/api.md
docs/src/examples.md
requirements.txt
```

Documentation commit, separately:

```text
docs/overhaul/PLAN.md
docs/overhaul/LOG.md
docs/overhaul/MANIFEST.md
docs/overhaul/CODEX_NEXT.md
```

Stop and report rather than widening this. In particular, do not touch
`load_stepping.py`, `projection.py`, `mesh_motion_pipeline.py`,
`mesh_motion_config.py`, `geometry_model.py`, `requirements-ci.txt`,
`setup.py`, the workflow, or any curated asset.

## Part A — pinned external revisions

Record the exact revisions this integration targets, in the same style the
CSDL_alpha and lsdo_function_spaces pins already use: repository URL plus a
full 40-character commit SHA, in `requirements.txt` under a clearly marked
optional section, and in `MANIFEST.md`.

If you cannot obtain a VortexAD revision without installing it or reaching the
network in a way this turn forbids, **stop and report that** rather than
inventing a SHA or pinning a branch name. A wrong pin is worse than a recorded
blocker. In that case, implement Parts B–D against the documented API surface
and leave the pin as an explicit `TODO(pin)` with the reason.

## Part B — the adapter

`panel_aerodynamics.py` exposes a documented, public builder that takes a
`MeshMotionResult` and returns CSDL aerodynamic outputs.

- Import VortexAD **lazily**, inside the call, mirroring
  `MeshMotionVolumeBackend`'s deferred import and raising a clear, actionable
  `ImportError` naming the optional extra when it is absent. The module must
  import cleanly without VortexAD.
- Consume the public result surface only: `surface_coordinates`,
  `surface_mesh`, and the M4.1 `surface_vertex_classification` /
  `surface_projection_status`. Do not reach into `_GeometrySetup`,
  `_SurfaceSystem`, or any other private pipeline object.
- The caller owns the recorder, exactly as `mm.run` does. Never start or stop
  it.
- Return named outputs (at minimum lift and drag coefficients) through a
  documented dataclass so `select_fd_objective` can address them via the
  existing `result.aerodynamic_outputs` mapping.
- Where the panel solve needs connectivity or trailing-edge detection, derive
  it from the curated mesh and state the assumption in the docstring.

## Part C — fuel burn

`fuel_burn.py` holds the Breguet / gross-weight model as a small, pure,
differentiable CSDL function with no VortexAD dependency at all.

- Inputs are aerodynamic coefficients and documented aircraft parameters;
  output is a fuel-burn scalar.
- Every parameter carries units in its docstring. Constants get a cited or
  clearly labelled source; do not bury unexplained magic numbers.
- Because it is VortexAD-free, it is **fully testable now**. Test it properly:
  a known analytic case, and an FD check of the derivative through the model.

## Part D — the tracked example

`examples/e175_fuel_burn_optimization.py` composes geometry → `mm.run` → panel
aerodynamics → fuel burn → objective.

- Follow the basic example's readable structure and its caller-owned recorder
  contract.
- **Manage the FD objective explicitly.** Do not set
  `derivative_check.enabled` inside an optimization: M4.1 documented that the
  convenience path calls `set_as_objective()` and would replace the
  optimization's own objective. Use `mm.select_fd_objective` deliberately, or
  register the fuel-burn objective directly, and say in a comment why.
- The example must degrade honestly: without VortexAD it should fail with the
  actionable `ImportError` from Part B, not a confusing traceback.

## Part E — tests that work without VortexAD

This is the part most likely to be done badly. Tracked tests must be
meaningful, not decorative.

- `test_fuel_burn.py` runs fully: analytic value plus FD derivative check.
- `test_panel_aerodynamics.py` covers everything reachable without VortexAD —
  the lazy import raises the documented error when absent; the adapter rejects
  malformed input; the output dataclass and its registration in
  `aerodynamic_outputs` behave; and the composition with a **fake** panel
  solver produces a differentiable graph whose VJP matches a centered finite
  difference.
- Any test that genuinely needs VortexAD is marked `integration` and skipped
  when the import fails. Do not let a skip masquerade as a pass: report skip
  counts explicitly in the handoff.
- A structural check that the example composes the documented five stages, in
  the style of `test_example_is_small_and_uncluttered`.

## Verification

1. `git diff --check "$TURN73_BASE"..HEAD`; changed paths ⊆ the allowlist.
2. New tests pass, with skip counts stated separately from passes.
3. Full non-integration suite; account for every change against the current
   baseline of **228 passed, 9 deselected**.
4. `tests/test_boundary_surface_movement.py` at **45 passed**;
   `tests/test_e175_example.py -m "not integration"` at **16 passed,
   5 deselected**.
5. The derivative / N-gon three-file guard: **exactly 6**.
6. `test_triangle_wall_at_full_deformation_scale` and
   `test_quad_panel_introduces_no_new_inverted_elements` both still pass —
   M4.1 must not regress.
7. `tests/test_documentation.py` and the strict Sphinx 9.1.0 build.
8. The five literal workflow Ruff commands, plus default Ruff on every changed
   Python path. If new paths belong in a workflow Ruff group, **report that
   rather than editing the workflow**, which is outside the allowlist.
9. Fresh clone: documentation tests, strict build, empty status. Confirm
   `import bsm3` and `import bsm3.core.boundary_surface_movement` still work
   **from outside the source tree** with VortexAD absent — run it from `/tmp`,
   not from the checkout. A Turn-64 false positive came from exactly that
   mistake.
10. Preservation: 8/8 byte-identical, 393 untracked entries.

## Handoff

Two commits: implementation, then the collaboration documents. Report both
hashes, exact changed paths, the Part A pin (or the recorded blocker), all test
results with skips stated separately, Ruff and Sphinx results, the fresh-clone
result, and preservation proof. Mark M4.2 as ready for Claude review, never as
self-accepted.

M3 release pruning remains separate and last.
