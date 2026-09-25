# Codex Turn 65 — M4.1: E175 example ergonomics and vertex classification

Claude reviewed Turn 63 and **accepted M2.1, M2.2, and M2** (Turn 64). Codex
resumes the implementer role; Claude plans and reviews. Do not self-accept.

Record `TURN65_BASE = $(git rev-parse HEAD)` before editing. Preserve the
user's dirty tree exactly: 8 pre-existing modified files byte-for-byte and 394
pre-existing untracked entries. Do not adopt, delete, format, or modify any of
them.

## Why this turn exists

Claude verified nine findings against source. All hold. Four are user-facing
defects in the flagship example and its public surface, and one is a
credibility problem in a recommended setting. The measurements below are
Claude's own and are reproducible read-only.

| # | Verified finding |
| --- | --- |
| 1 | `add_lifting_surface(root_half_width=0.3)` is documented as an "absolute spanwise half-width" but is passed as `{"y": (None, value, "abs")}`, and `AxisRange` mode `"abs"` normalizes `t = \|c\| / max(\|c\|)`. It is a **semispan fraction**: `0.3` means 30% of semispan, not 0.3 m. It is validated `> 0.0` but not bounded above, so `> 1.0` silently means "all free". |
| 2 | `add_body(free_axial_fraction=(0.05, 0.97))` leaves the middle graph-free and makes nose and tail parametrically prescribed. Correct, but undocumented as a *consequence*. |
| 3 | `MeshMotion.derivative_check` is configuration only. Neither `mm.run` nor `run_mesh_motion` reads it; only the two drivers act on it, and `select_fd_objective`/`run_fd_sweep` are **not** exported from `bsm3.mesh_motion`. A user can set `enabled=True`, call `mm.run`, and silently get nothing. |
| 4 | `MeshMotionResult` exposes no free / parametrically-prescribed / intersection classification, although `_write_diagnostic_dump` already writes `deformation_vertex_ids`, `graph_free_ids`, `graph_prescribed_ids`, `symmetry_plane_vertex_ids`, and per-component/intersection IDs. |
| 5 | The final surface is a composite: differentiable closest-point reprojection over the deformation set, fixed-parametric reevaluation elsewhere (`run_graph_load_steps` takes both `projection_metadata` and `reevaluation_metadata`). No projection convergence status reaches the result. |
| 6 | The quad baseline already has 114 inverted elements. IDs 8075 and 14923 are additional deformation-induced inversions. **Measured:** both are quads of area `3.299e-04` — `0.079x` the median cell area, at the **1.43rd percentile** — and they are an **exact mirrored pair about y = 0** (centroids `[26.8477, ∓1.1392, 1.5577]`). The two inversions are one geometric feature reflected. |
| 7 | `PolygonRegularization(weight=0.3)` has **no E175 calibration evidence**. The repository's own 12-weight sweep found λ=150 the first inversion-free value and production used λ=200, on a *different* panel revision and with mixed bulk-quality effects. The only recorded measurement at 0.3 is a unit-scale uniform quad grid where it moved the solution by `3.3e-16`. |
| 8 | `deformation_scale=0.02` is unnecessarily conservative for the tracked triangle default, which passes at `1.0` in `test_triangle_wall_at_full_deformation_scale`. The small value exists only so one setting also survives the quad substitution. |

Finding 9 — the untracked `e175_panel_opt.py`, drag build-up, gross-weight, and
legacy optimization scripts target removed APIs — is **deliberately out of
scope** and is recorded as a separate later milestone. Do not adopt or repair
those files in this turn.

## Scope rule

This turn is **A, B, and C only**. Part D is measurement that must *not* change
any default. If a finding cannot be fixed inside the allowlist, stop and report
the exact dependency rather than widening it.

## Literal implementation allowlist

```text
bsm3/core/boundary_surface_movement/geometry_model.py
bsm3/core/boundary_surface_movement/mesh_motion_config.py
bsm3/core/boundary_surface_movement/mesh_motion_pipeline.py
bsm3/mesh_motion.py
examples/e175_surface_deformation.py
examples/e175_quad_panel_calibration.py          (new)
tests/test_e175_example.py
tests/test_boundary_surface_movement.py
docs/src/api.md
docs/src/examples.md
docs/src/background.md
```

Documentation commit, separately:

```text
docs/overhaul/PLAN.md
docs/overhaul/LOG.md
docs/overhaul/CODEX_NEXT.md
```

Do not change packaging metadata, the workflow, `docs/conf.py`, curated assets,
or any other test.

## Part A — public vertex classification

Expose the classification through a public result type rather than requiring
NPZ reverse engineering.

- Add a public, documented type — for example `SurfaceVertexClassification` —
  carrying at minimum the deformation set, the graph-free set, the
  graph-prescribed set, the symmetry-plane set, per-component vertex IDs, and
  per-intersection vertex IDs. Use the same global (full-mesh) index space
  `_write_diagnostic_dump` already normalizes to, and say so in the docstring.
- Attach it to `MeshMotionResult` as a documented field and re-export the type
  from `bsm3.mesh_motion`.
- `_write_diagnostic_dump` must then derive its arrays from this object rather
  than recomputing them, so the NPZ and the public object cannot disagree.
- Add a test asserting the public sets equal the arrays the dump writes, for a
  configuration that produces both.

Do not change any coordinate, weight, or solver behavior.

## Part B — honest projection status

Finding 5 is a correctness-of-claim issue, not a solver issue.

- Surface a projection convergence status on the result: at minimum a count of
  non-converged reprojected vertices and their IDs, in the same global index
  space. Derive it from the data the warm-start projection already produces; do
  not add a new solve.
- Document in `docs/src/background.md` and the `MeshMotionResult` docstring
  that the final surface is a composite of differentiable closest-point
  reprojection over the deformation set and fixed-parametric reevaluation
  elsewhere, and that non-converged points are returned rather than raising.
- Add a test that the status field exists and is consistent with the reported
  vertex counts.

## Part C — example ergonomics

### C1. Rename `root_half_width` (clean break)

**Ruling: rename to `free_span_fraction`.** The current name and its docstring
both mislead: a user reading "absolute spanwise half-width" and passing `0.3`
gets 30% of semispan. Consistent with this overhaul's practice, make it a clean
break — no alias, no deprecation shim, no acceptance of both spellings. Update
`add_lifting_surface`, every tracked caller, the docstring, and the API page.
Add the missing upper-bound validation so a value outside `(0, 1]` raises
instead of silently meaning "all free".

While there, document finding 2 as a consequence: `free_axial_fraction` leaves
the middle of a body graph-free and makes the nose and tail parametrically
prescribed.

### C2. Split the example

Keep `examples/e175_surface_deformation.py` as the **basic triangle** example.
Raise its `deformation_scale` default to a value the tracked triangle wall
genuinely supports, justified by the existing full-scale test rather than by a
new claim, and remove the quad-substitution rationale from that default.

Add `examples/e175_quad_panel_calibration.py` as the **advanced** example: the
quad-dominant panel, the 114-element baseline, and the fact that IDs 8075 and
14923 are a mirrored pair of 1.43rd-percentile cells. It should demonstrate
reading the new classification and projection status, not just printing a
summary. Update `docs/src/examples.md` to present basic and advanced clearly.

### C3. FD-check workflow

Resolve finding 3 without changing solver behavior. Either re-export
`select_fd_objective` and `run_fd_sweep` from `bsm3.mesh_motion` and document
the required call sequence, **or** make `mm.run` raise a clear error when
`derivative_check.enabled` is set but the caller cannot act on it. Choose one,
state the choice and its rationale in the handoff, and document it on the API
page. Silently ignoring the setting is not acceptable.

## Part D — N-gon weight sweep, measurement only

Before anyone changes the recommended weight, measure it on the **current
tracked quad panel**.

- Sweep `PolygonRegularization.weight` across a range spanning the current
  `0.3` and the historical `150`/`200`, on
  `embraer_175_quad_dominant_symmetric_no_winglets.msh`.
- Record, per weight: post-projection inverted element IDs and count, whether
  8075 and 14923 specifically survive, minimum and 5th-percentile scaled
  Jacobian, 5th-percentile area ratio, and elapsed time.
- Report the table in the handoff and write the raw data outside the
  repository. **Do not change the default weight in this turn.** The point is
  to replace an uncalibrated number with evidence; Claude will rule on the new
  value from your table.

If the sweep is too expensive to complete, run what you can, report exactly
which weights completed, and do not extrapolate.

## Verification

1. `git diff --check "$TURN65_BASE"..HEAD` and changed paths ⊆ the allowlist.
2. `tests/test_e175_example.py -m "not integration"` and
   `tests/test_boundary_surface_movement.py`; report counts and account for
   every change against the current baselines.
3. The derivative/N-gon guard remains **exactly 6**.
4. `tests/test_documentation.py` still passes, and the strict Sphinx build
   still succeeds.
5. The five literal workflow Ruff commands, plus default Ruff on every changed
   Python path.
6. The tracked full-scale triangle integration test, because C2 changes the
   example's default scale. This is the one integration run this turn
   authorizes; do not run DAFoam, OpenFOAM, VortexAD, or real MPI.
7. Fresh clone of the implementation commit: documentation test and strict
   build, ending with empty clone status.
8. 8/8 pre-existing modified files byte-identical and 394 untracked entries
   unchanged.

## Deferred: tracked VortexAD / fuel-burn optimization example

Recorded as a **separate later milestone**, not a condition on M2 or on this
turn. The untracked `e175_panel_opt.py`, drag build-up, and gross-weight
scripts contain useful prototypes — panel-method coupling, a drag buildup, and
a gross-weight/Breguet model — but they import `e175_mesh_motion_config`,
`E175ModelFiles`, and `E175PipelineConfig`, none of which exist. That milestone
should build a *tracked* adapter against a pinned clean VortexAD revision using
the generalized `mm.run` result and a curated mesh, reusing those prototypes as
reference rather than resurrecting them. M2 documentation already describes
VortexAD as deferred and the untracked driver as unsupported, so no M2 claim
depends on it.

## Handoff

Two commits: implementation (source, examples, tests, docs pages), then
`PLAN.md`, `LOG.md`, `CODEX_NEXT.md`. Report both hashes, exact changed paths,
the C3 choice and rationale, the Part D sweep table, all test and Ruff results,
the fresh-clone result, and preservation proof. Mark M4.1 as ready for Claude
review, never as self-accepted.
