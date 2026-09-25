# Codex review checklist — M1.8 safe polygon asset and pickle boundary

Claude was the implementer. M1.8 is **ready for Codex acceptance and is not
accepted by the implementer**.

## Commits

| Hash | Contents |
| --- | --- |
| `TURN57_BASE` | `eeb2c38` |
| `2449441` | safe NPZ reader, pipeline cleanup, focused tests, asset replacement |
| `4a39fd8` | retained warm-start trusted-pickle API cleanup |
| *(docs commit)* | `ASSETS.md`, `MANIFEST.md`, `PLAN.md`, `LOG.md`, `CODEX_NEXT.md` |

Commit 2 required **no test change**: no tracked test referenced
`load_function_set_from_pickle` or `DEFAULT_FUN_SET_PATH`, so none was invented.

No amend, reset, rebase, rewrite, push, clean, or stash. Paths staged literally
through a Python list.

## Changed paths

```text
bsm3/core/boundary_surface_movement/mesh_motion_pipeline.py   M
bsm3/core/boundary_surface_movement/wall_surface.npz          A
bsm3/core/boundary_surface_movement/wall_surface.pkl          D
bsm3/core/projections/warm_start_candidate_projection_numpy.py M
bsm3/core/projections/warm_start_projections.py               M
bsm3/preprocessing/mesh_io.py                                 M
tests/test_curated_assets.py                                  M
tests/test_preprocessing_plotting.py                          M
docs/overhaul/ASSETS.md                                       M
docs/overhaul/MANIFEST.md                                     M
docs/overhaul/PLAN.md                                         M
docs/overhaul/LOG.md                                          M
docs/overhaul/CODEX_NEXT.md                                   M
```

13 of the 14 allowlisted paths changed; none outside.
`tests/test_warm_start_retry_regression.py` was allowlisted but needed no edit.

## Asset conversion evidence

The legacy file was verified before conversion: **2,863,763 bytes**, sha256
`34165debb2a3dde52dd7380cc1d91e99d829db96042858f710154b201f055b4d`.

| Item | Measured | Matches baseline |
| --- | --- | --- |
| `vertices` | `(79207, 3)` float64, sha256 `76ceaadd74a93eeb4153e51b784a4d4ff6dfa7079382510652cf8070ed3aad1a` | yes |
| `connectivity` | `(239385,)` int64, sha256 `971e53f7bc46fd694955be2f00b1b4355e513d5e066c5ebe1499b72a463b4ff3` | yes |
| `offsets` | `(40707,)` int64, sha256 `eff2e0fe7cd471ab5bac922b5290a0560db4d8d72d4fc3b2917ff70582083509` | yes |
| Face counts by width | 3:5, 4:565, 5:7,891, 6:28,190, 7:3,927, 8:126, 9:2 | yes |
| Node-ID range | 0 through 79,206 | yes |
| Faces | 40,706 | yes |
| **Adjacent width transitions** | **14,720** | yes |
| Per-face round trip in original order | exact, all 40,706 faces | — |
| Object arrays | none | — |

Written with `numpy.savez_compressed`; the conversion script is not retained.

## Boundary proofs

```text
$ git ls-files .../wall_surface.pkl .../wall_surface.npz
bsm3/core/boundary_surface_movement/wall_surface.npz

$ git grep -n -E 'pickle\.load|pickle\.loads' -- <the four scoped modules>
bsm3/core/projections/warm_start_projections.py:693   -> load_function_set_from_trusted_pickle()
bsm3/preprocessing/mesh_io.py:334                     -> import_trusted_polygon_pickle()

$ git grep -n 'DEFAULT_FUN_SET_PATH' -- <the two retained projection modules>
(empty)

$ git grep -n 'wall_surface\.pkl' -- <pipeline, preprocessing, tests, ASSETS.md, MANIFEST.md>
(empty)
```

Both `pickle.load` sites were confirmed by AST to lie inside those two named
functions.

## Test and lint results

| Gate | Result |
| --- | --- |
| Focused implementation tests | **54 passed** |
| Focused suite `-m "not integration"` | **97 passed, 3 deselected** |
| Drivers/volume/MPI suite | **102 passed** |
| Derivative + N-gon guards | **6 passed** |
| Curated integration (40,706-face affine assembly) | **3 passed, 3 deselected** |
| Critical static checks (default Ruff) | All checks passed |
| Surface-motion core `--select D` | All checks passed |
| Projection/preprocessing `--select D` | All checks passed |
| M0 and drivers `--select D` (for completeness) | All checks passed |

The 82 → 97 and 89 → 102 movements are **exactly** the added unit tests: 13 in
`test_preprocessing_plotting.py` and 2 fast checks in `test_curated_assets.py`.
The derivative/N-gon suite is unchanged at 6. No historical count moved on its
own and no numerical result changed.

## Two items needing your attention

**1. A latent defect had to be fixed to consolidate the loaders.**
`warm_start_projections` imported `lsdo_function_spaces` only inside its
`__main__` block, so its retained `load_function_set` raised
`NameError: name 'lfs' is not defined` for any library caller — confirmed by
direct call before editing. The candidate module's duplicate carried the
guarded import that made it usable. The consolidated
`load_function_set_from_trusted_pickle` now has that guarded module-level
import and its `ImportError`. This is the only executable change in commit 2
beyond the removals.

**2. Local callers broken by the intentional clean break.**

- Untracked `bsm3/core/projections/warm_start_candidate_projection_driver.py`
  imports `load_function_set_from_pickle` (line 44) and `DEFAULT_FUN_SET_PATH`
  (lines 48, 117) and calls the old loader (line 206). It will fail to import
  until its owner switches to
  `load_function_set_from_trusted_pickle(<explicit path>)`. Not edited or
  adopted, per the allowlist.
- Tracked-but-prohibited
  `bsm3/core/boundary_surface_movement/movement_test_embraer_175_hex_mesh.py`
  still sets `MESH_PATH = SCRIPT_DIR / "wall_surface.pkl"` at line 33 and will
  break on the deleted asset. The allowlist forbids touching it. It should
  point at `wall_surface.npz`, which the generic importer now reads.

No tracked module, test, or curated asset references either removed name.

## Deviations

- The scoped old-asset-name grep must be empty, so `ASSETS.md` and
  `MANIFEST.md` record the superseded asset's provenance by size and sha256
  rather than by its literal former filename. `PLAN.md` and `LOG.md` sit
  outside that scoped grep and keep their historical mentions.
- The guarded `lsdo_function_spaces` import above is an executable addition
  inside an allowlisted file, reported rather than absorbed silently.

No stop condition was hit; no path outside the allowlist was required.

## Decision requested

Accept M1.8, and rule on whether the two broken local callers above are fixed
under a later allowlist or left to their owner.
