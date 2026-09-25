# Claude Turn 68 — Review the M4.1 symmetric-dump correction

Codex completed the single corrective turn and did not self-accept it.

```text
TURN67_BASE = 9930dbe
TURN67_IMPLEMENTATION = bc40560
```

Review the committed implementation independently. Do not reopen the M4.1
work Claude accepted in Turn 66 unless this correction regressed it, and do not
implement M4.2 during the review.

## Exact implementation scope

```text
bsm3/core/boundary_surface_movement/mesh_motion_pipeline.py
tests/test_e175_example.py
docs/src/api.md
```

The following collaboration documents form the separate handoff commit:

```text
docs/overhaul/PLAN.md
docs/overhaul/LOG.md
docs/overhaul/CODEX_NEXT.md
```

Across Claude's `ad3099a` prompt commit and Codex's two corrective commits, the
changed-path union must be exactly these six paths; no other path may differ
from `TURN67_BASE`.

## Review the archive contract

Codex chose option 1: preserve the existing NPZ contract by mirror-expanding
intersection coordinates into the same complete-mesh order as `{name}_ids`.
Trace `_global_intersection_vertices` and confirm:

- nonsymmetric input keeps coordinates aligned with sorted global IDs;
- symmetric input maps each global ID through `gather_index` to the retained
  half and applies the corresponding global row of `mirror_sign`;
- symmetry-plane coordinates remain exact;
- missing or misaligned retained-half data fails rather than silently pairing
  the wrong rows; and
- no classification, projection, seam, or mesh coordinate changes were made.

Inspect the quad-panel regression. It must be marked integration, exercise the
actual full symmetric panel, and assert both equal row counts and coordinate
identity against `initial_vertices[vertex_ids]` for every intersection.

Codex recorded the required before/after evidence:

```text
before: FAIL, wing_root (97, 3) versus 194 IDs
after:  PASS, 1 passed in 65.73 s
```

Reproduce the passing case. The historical failure is already preserved in
Turn 67; do not revert production code merely to see it again unless desired in
a disposable clone.

## Review the two documentation residues

Confirm the API page now says:

1. the caller-owned recorder must use inline execution because the pipeline
   consumes forward values and cached projection state; and
2. the convenience derivative-check path calls `set_as_objective()`, so it can
   replace an objective already registered in a larger optimization graph.

Also confirm the NPZ intersection arrays are documented as complete-mesh,
row-aligned pairs.

## Recorded rulings

Confirm Turn 67 records the N-gon ruling verbatim and corrects the Turn-65
element-ID sentence: on the replacement 14,662-cell mesh, 14923 does not exist
and 8075 is unrelated. No regularization default changed.

## Required gates

At minimum reproduce:

```text
tests/test_e175_example.py::test_quad_panel_introduces_no_new_inverted_elements  1 passed
tests/test_e175_example.py -m "not integration"                              16 passed, 5 deselected
tests -m "not integration"                                                   228 passed, 9 deselected
tests/test_boundary_surface_movement.py                                      45 passed
derivative + n-gon three-file guard                                          exactly 6 passed
test_triangle_wall_at_full_deformation_scale                                 1 passed
tests/test_documentation.py                                                  12 passed
strict Sphinx 9.1.0                                                          build succeeded
five literal workflow Ruff groups                                            all passed
```

Verify `git diff --check`, the exact allowlist, seven untouched dirty files,
the visualization script's same two unstaged user edits, and 393 untracked
entries. No DAFoam, OpenFOAM, VortexAD, or real-MPI run is required.

## Handoff

If the correction is sound, accept M4.1, update `PLAN.md` and `LOG.md`, and
replace this file with the next literal Codex prompt for M4.2: a tracked
VortexAD and fuel-burn optimization example against pinned external revisions.
Keep M3 release pruning separate and last. If the correction is not sound,
issue one narrowly scoped prompt with executable acceptance criteria.

The `GAMMA` name remains M3 guidance only; do not rename the package here.
