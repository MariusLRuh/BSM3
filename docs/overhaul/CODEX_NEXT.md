# Codex Turn 67 — M4.1 corrective: symmetric-mesh diagnostic dump

Claude reviewed M4.1 in Turn 66 and **did not accept it**. Everything else in
`d0d1ff0` was verified and stands. This is one narrow corrective turn; do not
reopen any other part of M4.1, and do not begin M4.2.

```text
TURN67_BASE = 9930dbe
```

Preserve the user's dirty tree exactly: seven pre-existing modified files
byte-for-byte, the eighth
(`visualize_wing_rotation_deformation.py`) with its unstaged `DEFAULT_HDF5` and
`--field` edits left untouched, and 393 untracked entries.

## What was accepted, so you do not redo it

Verified by execution, not by reading your report:

- Exact seams bypass the closest-point operation via
  `~np.isin(ids, exact_seam_ids)` rather than being overwritten afterwards; the
  implicit intersection VJP survives; `enforce_symmetry_plane` runs after
  assembly; the empty-projection case short-circuits correctly; `converged`
  comes from the cached forward state with no second solve.
- The classification partitions the complete mesh on **both** mesh kinds:
  triangle wall 4,547 + 11,853 = 16,400; quad panel likewise, with 4,262
  closest projections, 2,236 n-gon modes, zero inversions.
- The replacement panel independently measures 13,262 vertices, 2,804
  triangles, 11,858 quads, zero inverted elements, zero inverted corners, zero
  degenerate elements, minimum scaled Jacobian 0.1606796.
- All eleven gates reproduced at exactly the numbers you reported.

## The defect

The tracked triangle wall is a **half** mesh (`y` in `[0, 11.96]`), so
`setup.symmetry_split is None` and `_global_surface_ids` takes its
`np.unique(ids)` branch. Every dump-equality assertion in the suite runs on
that mesh. The symmetric branch you added is therefore never tested.

The curated quad panel **is** a full symmetric mesh (`y` in `[-11.96, 11.96]`).
There `_global_surface_ids` mirror-expands — correct and desirable for the
public classification — but `_write_diagnostic_dump` still writes half-mesh
seam coordinates for `{name}_vertices` beside the expanded `{name}_ids`:

| key | before Turn 65 | after Turn 65 |
| --- | ---: | ---: |
| `wing_root_vertices` | 97 | 97 |
| `wing_root_ids` | 97 | **194** |
| `tail_root_vertices` | 67 | 67 |
| `tail_root_ids` | 67 | **134** |

They were aligned 1:1 by construction before. Pairing them is the only reason
the archive carries both arrays. A consumer that zips them now mispairs
coordinates with IDs, or fails, and nothing in the archive announces it.

Reproduce it before fixing it: run the basic example's `main` against
`embraer_175_panel_quad_dominant_high_quality.msh` with a `diagnostic_dump`
path and compare `wing_root_vertices.shape[0]` against `wing_root_ids.size`.

## Literal implementation allowlist

```text
bsm3/core/boundary_surface_movement/mesh_motion_pipeline.py
tests/test_e175_example.py
docs/src/api.md
```

Documentation commit, separately:

```text
docs/overhaul/PLAN.md
docs/overhaul/LOG.md
docs/overhaul/CODEX_NEXT.md
```

Stop and report rather than widening this. In particular, do not change
`_global_surface_ids`, the classification dataclasses, `load_stepping.py`,
`projection.py`, the curated asset, or either example.

## Part A — make the archive self-consistent

Pick one and state which in the handoff:

1. Mirror-expand the seam coordinates so `{name}_vertices` and `{name}_ids`
   are aligned 1:1 again on every mesh, applying the symmetry sign to the
   mirrored rows; or
2. Keep `{name}_vertices` paired with a half-mesh-aligned ID array under an
   explicitly distinct key, and write the mirror-expanded classification IDs
   under their own clearly named key.

Option 1 preserves the archive's existing contract and is preferred unless you
find a concrete reason it cannot hold. Whichever you choose, every array pair
in the NPZ that a reader would naturally zip must be aligned, and the choice
must be documented where the dump's contents are described.

## Part B — close the test hole

Add a dump/classification assertion that runs on a **symmetric** mesh, so the
mirror-expansion branch of `_global_surface_ids` is covered. It must assert the
alignment invariant you chose in Part A, not merely that the arrays exist.

Mark it `integration` consistently with the existing quad-panel test. Do not
weaken or delete any existing assertion.

## Part C — two documented residues

Both are one or two sentences on the API page; neither changes behavior.

1. `_project_group` raises `RuntimeError` naming the inline recorder when the
   cached forward state is absent. The pipeline already required an inline
   recorder — it reads `.value` in several places — but the API page never says
   so. State the requirement where the caller-owned recorder is described.
2. `mm.run` calls `set_as_objective()` whenever `derivative_check.enabled` is
   true. Inside a larger optimization graph that already has an objective,
   enabling the debug flag replaces it. Warn about this where the FD workflow
   is documented.

## Verification

1. `git diff --check "$TURN67_BASE"..HEAD`; changed paths ⊆ the allowlist.
2. The new symmetric assertion fails against `d0d1ff0` and passes after the
   fix. Report both results — a test that never saw the bug proves nothing.
3. `tests/test_e175_example.py -m "not integration"`, the full non-integration
   suite (baseline 228 passed / 9 deselected), and
   `tests/test_boundary_surface_movement.py` (baseline 45 passed).
4. The derivative / N-gon guard across all three files: **exactly 6**.
5. `test_triangle_wall_at_full_deformation_scale`: 1 passed, zero folds, zero
   inversions in all three reports, zero projection failures.
6. `tests/test_documentation.py` and the strict Sphinx build.
7. The five literal workflow Ruff commands, plus default Ruff on changed paths.
8. Preservation: 7/8 byte-identical, the eighth's unstaged edits intact, 393
   untracked entries.

No DAFoam, OpenFOAM, VortexAD, or real-MPI run. Do not install dependencies.

## Rulings to record verbatim in LOG.md

**N-gon weight.** The sweep is a null result, not a calibration. The minimum
scaled Jacobian is bit-identical (0.16066206527471977) at all eight weights and
the undeformed panel's own minimum is 0.1606796, so the statistic is pinned by
a pre-existing worst cell the deformation barely touches. The p05 scaled
Jacobian is bit-identical at weights 0, 0.3 and 1. The p05 area ratio degrades
monotonically from 0.982300 at weight 0 to 0.977454 at 150. Increasing the
weight is mildly harmful here and never helpful; the elapsed-time column is
warm-up noise. **Keep `0.3` as the explicitly labeled non-recommendation it
already is. Do not adopt 100–200. Do not adopt 0.** No universal weight follows
from one deformation case; a real calibration needs a deformation that provokes
hourglassing.

**Retired element IDs.** The sweep's `contains_8075` / `contains_14923` columns
are vacuous on the replacement mesh: it has 14,662 cells, so element 14923 does
not exist and element 8075 is an unrelated cell. Correct the Turn-65 LOG
sentence so it cannot be read as continuous with the Turn-64 measurement.

## After this turn

M4.2 — a tracked VortexAD and fuel-burn optimization example against pinned
external revisions — is planned by Claude once M4.1 is accepted. It is not part
of this turn. M3 release pruning stays separate and last. The `GAMMA` naming
question is recorded as guidance in the Turn-66 log and is an M3 concern; do
not rename anything.

## Handoff

Two commits: implementation (pipeline, test, API page), then `PLAN.md`,
`LOG.md`, `CODEX_NEXT.md`. Report both hashes, the Part A choice and its
rationale, the before/after result of the new test, all gate results, and
preservation proof. Mark the M4.1 correction as ready for Claude review, never
as self-accepted.
