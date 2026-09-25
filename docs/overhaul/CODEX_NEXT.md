# Turn 56 — Claude correction prompt: final M1.6 semantic residue

Codex reproduced every structural and numerical gate from Turn 54, but M1.6 is
**not accepted yet**. Five source docstrings retain seven narrow inaccuracies.
Correct those only; do not reopen the completed lint sweep or change behavior.

Base source comparisons on `139f35c`. Starting `HEAD` is `7777b0f`. Do not
amend, reset, rebase, rewrite, push, clean, or touch pre-existing dirty files.

## Literal allowlist (8 paths)

```text
bsm3/__init__.py
bsm3/core/boundary_surface_movement/cfd_mesh_dafoam_analysis.py
bsm3/core/boundary_surface_movement/rbf.py
bsm3/core/boundary_surface_movement/run_dafoam_gmsh.py
bsm3/core/boundary_surface_movement/volume_mesh_motion.py
docs/overhaul/PLAN.md
docs/overhaul/LOG.md
docs/overhaul/CODEX_NEXT.md
```

No other path may change. If accurate documentation requires executable code,
stop and report it; these defects can all be corrected in prose.

## Required corrections

1. **Regular package, not namespace package — `bsm3/__init__.py`.**
   `bsm3/core/projections/__init__.py` exists, so
   `bsm3.core.projections` is a regular subpackage. It re-exports no helper
   names. Replace only the incorrect “namespace package” terminology; preserve
   the accurate concrete-module guidance.

2. **`mesh_motion` can also be absent on root —
   `cfd_mesh_dafoam_analysis.py`.** `build_cfd_analysis_rank0` snapshots
   `geometry_backend.last_mesh_motion_result` while constructing its return
   object. It is always `None` on non-root ranks because no backend exists
   there, and it can also still be `None` on root when the custom operation has
   not executed inline before that snapshot. Do not promise that root alone
   guarantees a populated value. Keep the non-optional annotation as the
   already-recorded M1.7 carry-in.

3. **State the two omitted RBF value constraints — `rbf.py`.** In both the
   class and `__post_init__` validation prose, state separately that
   `seam_neighbor_blend_radius` must be scalar or one-per-intersection **and
   non-negative**, while `seam_neighbor_component_blend` must be scalar or
   one-per-intersection **and lie in `[0, 1]`**. “Cannot be resolved” documents
   only the length rule and does not cover the explicit value checks at
   `_resolve_seam_neighbor_radii` and `_resolve_per_intersection_fractions`.

4. **Parser defaults — `run_dafoam_gmsh.py`.** `make_parser` still says its
   option defaults come from a default `FlowConfig` “so the two stay
   consistent.” That remains false: many numerical defaults do come from the
   dataclass, but case/path/patch options do not, and the wall-function flag has
   the already-documented contradictory effective default. Replace the blanket
   claim with the precise boundary.

5. **Missing `ValueError` — `run_dafoam_gmsh.py`.** Add the explicit
   `ValueError` from `set_openfoam_patch_types`: a named patch block exists but
   contains no `type` entry. Its `KeyError` remains the absent-block case.

6. **Both `FileExistsError` paths — `run_dafoam_gmsh.py`.** In
   `convert_and_check_mesh`, document that `FileExistsError` is raised either
   when `polyMesh` exists and `overwrite_existing` is false, or when overwrite
   is allowed but the timestamped backup destination already exists.

7. **Raw mean-ratio sign is not relative inversion —
   `volume_mesh_motion.py`.** The mean-ratio sign follows the raw deformed
   determinant. Remove the unconditional conclusion that an “inverted cell”
   scores negative: inversion elsewhere in this report is defined by the
   deformed-to-baseline determinant ratio. With a negative-oriented baseline,
   an unchanged cell has positive relative Jacobian but negative mean ratio.
   State that the signs coincide only under a positive-baseline-orientation
   convention.

Update the Turn-54 checklist/table and the M1.7 carry-in wording so they no
longer repeat the rejected claims. Preserve every other accepted correction.

## Required verification

1. All five literal Ruff commands from `actions.yml` pass: the four
   `--select D` documentation steps and the default critical-static step.
2. Stripped-AST comparison against `139f35c` is identical for every changed
   Python file, for both the working tree and committed blobs.
3. The slice-3 audit remains 17/17 modules, 167/167 definitions, 132 callables
   / 293 parameters at 0 missing and 0 extra, and 22 dataclasses / 148 fields
   at 0 missing and 0 extra.
4. Run the same three regression commands from Turn 54; expected results remain
   **82 passed / 3 deselected**, **89 passed**, and **6 passed**.
5. `git diff --check 7777b0f HEAD` is empty, and the changed paths are a subset
   of the eight-path allowlist.

## Commit and handoff

Create two commits without rewriting history:

1. the five source docstring corrections only;
2. `PLAN.md`, `LOG.md`, and `CODEX_NEXT.md` only.

Stage paths literally. Hand the result back as **M1.6 ready for Codex
acceptance, not self-accepted**. Report the exact changed paths, all five Ruff
results, AST result, coverage audit, three test counts, and any deviation.
