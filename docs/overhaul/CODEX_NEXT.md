# Review prompt for Claude — Turn 25 (M1.5 disposition and backend cleanup)

Paste into a Claude session at the repository root.

---

Review Codex Turn 24 in `docs/overhaul/LOG.md`, the source commit `eb1ed5f`,
and its immediate docs-only successor at the current branch tip. Read the M1.5
row and Turn-23/Turn-24 records in `docs/overhaul/PLAN.md`, plus the new M1.5
disposition in `docs/overhaul/MANIFEST.md`.

## What Codex decided

Codex recommends **no `bsm3.meshgen` adoption in M1.5**. The core already has
zero imports from the candidate Gmsh/OCC scripts. The only credible general
STEP-to-surface path is the untracked circular pair
`gmsh_occ_oml_surface_mesh.py` (2,475 LOC) and
`smooth_existing_tip_cap.py` (2,283 LOC): 4,758 untested LOC. The 502-LOC
`generate_e175_panel_mesh.py` is only an E175-specific wrapper over that pair.
M3 should revisit mesh generation only with a minimal public API, a small
deterministic STEP fixture, and an end-to-end topology/quality test.

Rule explicitly on whether this is an acceptable completion of M1.5 as a
**disposition decision**, despite the original acceptance text asking for an
example that regenerates a surface mesh. Do not accept adoption merely to
satisfy that checkbox; judge whether untested local code belongs in the release
at this stage.

## What Codex changed

Only this implementation file changed in `eb1ed5f`:

```
bsm3/core/boundary_surface_movement/geometry_volume_backend.py
```

It moves the annotation-only `GeometryParameterization` import under
`TYPE_CHECKING` and replaces the false lazy-import comment. It intentionally
does **not** change package `__init__.py`: package re-exports still cause config
and pipeline to load during a normal submodule import.

The docs-only successor may touch only:

```
docs/overhaul/MANIFEST.md
docs/overhaul/PLAN.md
docs/overhaul/LOG.md
docs/overhaul/CODEX_NEXT.md
```

The combined Turn-24 allowlist is therefore exactly five paths. Confirm there
are no staged or committed changes outside it and no mesh-generation file was
adopted.

## Independent checks

Run in `central_geom`:

```bash
git diff --name-status 8ded2dc..HEAD

git grep -nE "gmsh_occ_oml_surface_mesh|smooth_existing_tip_cap|gmsh_quad_hybrid|generate_e175_panel_mesh" -- bsm3/core/boundary_surface_movement/mesh_motion_pipeline.py bsm3/core/boundary_surface_movement/mesh_motion_config.py bsm3/core/boundary_surface_movement/__init__.py

git grep -n "TYPE_CHECKING" -- bsm3/core/boundary_surface_movement/geometry_volume_backend.py
python -c "import bsm3.core.boundary_surface_movement.geometry_volume_backend as g; print(g.__all__)"

python -m pytest -q tests/test_derivative_gate.py
python -m pytest -q tests/test_ngon_affine_operator.py tests/test_ngon_affine_load_step.py
python -m pytest -q tests/test_geometry_volume_mpi.py
python -m pytest -q tests
```

The core-clean grep must be empty. Expected focused counts are 1, 5, and 26
passed; expected dirty-tree count is 171 passed. Codex re-measured the seven
M1.4 quantities as rank 3, retained fraction 1.0, `‖P·1‖ = 0`, 3 hexagon modes,
`obj'(0) = 4`, `obj'(0.3) = 57/13`, and normalized observability `2/13`.

## Genuine-clone verification

Use a fresh temporary directory; do not delete or reuse an uncertain path.

```bash
VERIFY_DIR=$(mktemp -d /tmp/bsm3-m15-claude.XXXXXX)
git clone --no-hardlinks --branch production-ready-overhaul \
  "file:///Users/mariusruh/Documents/Research/nasa_uli/mesh_movement/packages/BSM3" \
  "$VERIFY_DIR/repo"
cd "$VERIFY_DIR/repo"
git status --porcelain
conda run -n central_geom python -m pytest -q tests
```

Expected: empty status and **157 passed / 1 skipped**.

## Deliverable

Append Claude Turn 25 to `docs/overhaul/LOG.md` with the independent evidence
and an explicit accept/reject ruling. Update `PLAN.md` only if the ruling
changes M1.5 status. Then replace this file with the next concrete Codex prompt.

If M1.5 is accepted, audit the remaining M1 work before choosing the next task.
In particular, decide whether M1.8 (removing the internal executable-pickle
path, still visible as two full-suite warnings) should precede the broad M1.6
docstring/lint expansion. Supply a literal per-turn allowlist, executable
acceptance commands, clone commands, and the same stop rule used throughout:
Codex must stop and report rather than widen scope silently.
