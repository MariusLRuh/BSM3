# Claude Turn 66 — Review M4.1 independently

Codex implemented M4.1 and is handing it back without self-acceptance.

```text
TURN65_BASE = 11fb4522f354b56e05ccd1c5795f9f078fcbfe46
TURN65_IMPLEMENTATION = d0d1ff0
```

Review the committed range, reproduce the high-value gates, and either accept
M4.1 or issue one narrow corrective prompt. Do not edit production code during
the first review pass. If accepted, plan M4.2 (tracked VortexAD and fuel-burn
optimization) next; M3 release pruning remains separate and last.

## First rule on the two user-directed scope expansions

The Turn-64 prompt was A/B/C with D measurement-only, but the user separately
directed two changes that require a wider range:

1. Exact bracketed intersection vertices must **not** be reprojected onto the
   driving component. Codex changed `load_stepping.py`, `projection.py`, their
   exports/tests/docs, and surfaced the projection status already computed by
   the custom operation.
2. The clean local panel mesh must replace the old 114-inversion example mesh.
   Codex adopted `embraer_175_panel_quad_dominant_high_quality.msh`, deleted
   `embraer_175_quad_dominant_symmetric_no_winglets.msh`, and updated supported
   references, provenance, and the one tracked visualization default.

These are intentional expansions, not silent allowlist drift. Review whether
their concrete implementation is minimal and correct.

## Committed inventory — exactly 21 paths

```text
bsm3/core/boundary_surface_movement/__init__.py
bsm3/core/boundary_surface_movement/embraer_175_panel_quad_dominant_high_quality.msh  (new)
bsm3/core/boundary_surface_movement/embraer_175_quad_dominant_symmetric_no_winglets.msh  (deleted)
bsm3/core/boundary_surface_movement/geometry_model.py
bsm3/core/boundary_surface_movement/load_stepping.py
bsm3/core/boundary_surface_movement/mesh_motion_config.py
bsm3/core/boundary_surface_movement/mesh_motion_pipeline.py
bsm3/core/boundary_surface_movement/projection.py
bsm3/core/boundary_surface_movement/visualize_wing_rotation_deformation.py
bsm3/mesh_motion.py
docs/overhaul/ASSETS.md
docs/overhaul/MANIFEST.md
docs/src/api.md
docs/src/background.md
docs/src/examples.md
docs/src/getting_started.md
examples/e175_quad_panel_calibration.py  (new)
examples/e175_surface_deformation.py
tests/test_boundary_surface_movement.py
tests/test_curated_assets.py
tests/test_e175_example.py
```

Verify with:

```bash
git diff --check "$TURN65_BASE" "$TURN65_IMPLEMENTATION"
git diff --name-status "$TURN65_BASE" "$TURN65_IMPLEMENTATION"
```

The mesh hash must be exactly:

```text
92feeeda05905a13d23a18c863e76b9596773beccb021148cc2d4e7016cd733c
```

## A. Exact-intersection and projection-status review

Trace one load step from `_set_exact_seams` through final assembly.

- Confirm the union of `state.solutions[*].vertex_ids` is excluded from the
  closest-point operation, not merely overwritten after a redundant solve.
- Confirm the exact seam coordinates remain differentiable through the
  implicit intersection operation and survive symmetry enforcement.
- Confirm non-seam deformation rows still receive closest-point reprojection.
- Confirm `VertexBatch.converged` is populated from the operation's existing
  cached forward state, aligned with its IDs, and causes no second solve.
- Confirm `SurfaceProjectionStatus` reports only vertices actually projected;
  exact seams and fixed-parametric reevaluation vertices must be absent.
- Inspect the synthetic regression: seam IDs must be excluded, the seam must
  satisfy both component planes, and the existing analytic/FD derivative must
  remain green.

Pay particular attention to duplicated seam IDs across intersections,
empty-projection edge cases, metadata coverage, and the inline-recorder
assumption used to read the cached forward state.

## B. Global classification review

Check `SurfaceVertexClassification` against the actual pipeline partitions.

- All arrays must use zero-based IDs in the **complete input mesh**, including
  both sides reconstructed from a symmetric half solve.
- `parametrically_prescribed_vertex_ids` must be the complete-mesh complement
  of the deformation set.
- `closest_projection_vertex_ids` must equal
  `surface_projection_status.reprojected_vertex_ids`.
- Component and intersection mappings must keep declaration names.
- The NPZ dump must consume the public classification rather than independently
  recompute equivalent arrays.
- Do not assume graph-prescribed, intersection, and symmetry categories are
  disjoint; review/document their intended overlap instead.

## C. API and example ergonomics review

- `root_half_width` is a clean-break removal from the supported API;
  `free_span_fraction` has the truthful semispan meaning and rejects values
  outside `(0, 1]`.
- `free_axial_fraction` explains that the middle is graph-free and nose/tail
  are fixed-parametric.
- The basic triangle example remains one readable five-stage script, defaults
  to full scale, has no CLI, and exposes final visualization and FD checking.
- The advanced example uses the replacement panel, keeps its regularization
  weight explicit, and reads the public classification/status rather than
  private pipeline objects.
- `MeshMotion.derivative_check.enabled` is no longer ignored: `mm.run`
  registers the configured objective; the caller-owned recorder is still not
  stopped; `mm.run_fd_sweep` runs afterward. Confirm this composes with an
  external recorder and does not register duplicate objectives.
- The docs' three-path description must match the implementation: exact seam,
  closest projection, fixed-parametric reevaluation.

## D. Replacement asset and calibration ruling

Independently load the replacement panel and confirm 13,262 vertices, 2,804
triangles, 11,858 quads, and zero baseline inversions/corners/degeneracies.
Confirm all tracked supported references use it and the old filename is absent
outside historical collaboration prose. Untracked research scripts are outside
the supported surface and may still name the retired file; report, do not edit.

Codex measured full deformation at weights 0, 0.3, 1, 10, 50, 100, 150, 200.
Every case had zero inversions; minimum scaled Jacobian stayed 0.160662. The p05
scaled Jacobian moved from 0.540688 at 0/0.3 to 0.540430 at 200, and p05 area
ratio from 0.982300 at 0 to 0.977684 at 200. Raw data remains outside the repo
at `/tmp/bsm3_turn65_ngon_sweep.json` if available.

Rule explicitly on the interpretation. Codex's provisional reading is that
this one clean-mesh/full-deformation point provides no evidence for 100–200 and
does not establish that 0.3 is optimal either. Decide whether the advanced
example should keep 0.3 pending a broader deformation suite, use zero, or defer
any recommendation. Do not infer a universal value from this one sweep.

## E. Dirty-tree overlap

At Turn-65 start there were eight modified tracked files and 394 untracked
status entries. The replacement mesh itself was one of those untracked paths,
so adoption intentionally changes the count to 393. Seven modified files must
remain byte-identical. The eighth,
`visualize_wing_rotation_deformation.py`, already carried user changes; only
the committed `DEFAULT_MESH` line belongs to Turn 65. Verify its unrelated
`DEFAULT_HDF5` and `--field` changes remain unstaged and were not committed.

## Reproduce the gates

Use the existing Python-3.12 compatibility environment. Minimum results Codex
reported:

```text
tests/test_boundary_surface_movement.py                         45 passed
tests/test_e175_example.py -m "not integration"                16 passed, 5 deselected
tests -m "not integration"                                    228 passed, 9 deselected
derivative + n-gon trio                                        exactly 6 passed
test_triangle_wall_at_full_deformation_scale                   1 passed
tests/test_documentation.py                                    12 passed
strict Sphinx 9.1.0                                            build succeeded
all five literal workflow Ruff commands                        passed
```

The full-scale triangle run must show zero folds, zero input/pre/final
inversions, zero projection failures, exact classification/dump equality, and
no seam ID in the closest-projection set. Also verify a fresh clone of
`d0d1ff0` builds the docs, passes documentation tests, and ends clean.

No DAFoam, OpenFOAM, VortexAD, or real-MPI run is required in this review.

## Handoff

Record the independent findings in `LOG.md`, update `PLAN.md`, and replace this
file with the next literal Codex prompt. If M4.1 is accepted, the next prompt
should plan M4.2 as a tracked VortexAD/fuel-burn optimization milestone against
pinned external revisions, while keeping M3 release pruning separate. Include
any ruling on the `GAMMA` repository name only as naming guidance; do not rename
the package during review.
