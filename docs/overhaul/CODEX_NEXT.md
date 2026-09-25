# Claude implementation prompt — M1.8 safe polygon asset and pickle boundary

Codex is the planner/reviewer; Claude is the implementer. **M1.6 is accepted.**
Implement M1.8, then hand it back to Codex without self-accepting it.

At the start, record `TURN57_BASE=$(git rev-parse HEAD)`. Do not amend, reset,
rebase, rewrite, push, clean, stash, or touch any pre-existing dirty path.

## Literal allowlist

Only these 14 paths may change after `TURN57_BASE`:

```text
bsm3/core/boundary_surface_movement/mesh_motion_pipeline.py
bsm3/core/boundary_surface_movement/wall_surface.pkl
bsm3/core/boundary_surface_movement/wall_surface.npz
bsm3/core/projections/warm_start_candidate_projection_numpy.py
bsm3/core/projections/warm_start_projections.py
bsm3/preprocessing/mesh_io.py
tests/test_curated_assets.py
tests/test_preprocessing_plotting.py
tests/test_warm_start_retry_regression.py
docs/overhaul/ASSETS.md
docs/overhaul/MANIFEST.md
docs/overhaul/PLAN.md
docs/overhaul/LOG.md
docs/overhaul/CODEX_NEXT.md
```

The `.pkl` path is deletion-only and the `.npz` path is addition-only. A path
need not change merely because it is allowlisted. Stage every path literally;
never stage a directory.

The following are specifically prohibited even though they contain related
legacy code or data:

- the already modified tracked research script
  `movement_test_embraer_175_hex_mesh.py`;
- the dependency-managed
  `stored_files/imports/wing_fuse_test_stored_import.pickle` cache;
- every untracked driver, pickle, cache, and research artifact, including
  `warm_start_candidate_projection_driver.py` and `refitted_fun_set.pkl`;
- workflow, dependency, geometry-stack, configuration, solver, and example
  changes.

If the implementation genuinely requires any path outside the allowlist,
stop and report the exact dependency. Do not widen the list silently.

## 1. Replace the curated executable pickle with a safe NPZ

Convert the trusted tracked `wall_surface.pkl` once, verify it against the
baseline below, add `wall_surface.npz`, and delete `wall_surface.pkl`.

The NPZ schema is exactly three non-object arrays:

- `vertices`: float64, shape `(n_vertices, 3)`;
- `connectivity`: flattened int64 node IDs in the **original face order**;
- `offsets`: int64, shape `(n_faces + 1,)`, starting at zero, with
  `connectivity[offsets[i]:offsets[i + 1]]` equal to original face `i`.

Write the archive with `numpy.savez_compressed`. Never store an object array,
dictionary, pickled metadata, or a second representation of connectivity.
The zip container itself need not have a stable byte hash; its decoded arrays
must be exact.

Trusted legacy baseline measured by Codex:

| Item | Required value |
| --- | --- |
| Legacy file | 2,863,763 bytes; SHA-256 `34165debb2a3dde52dd7380cc1d91e99d829db96042858f710154b201f055b4d` |
| `vertices` | `(79207, 3)`, float64; byte SHA-256 `76ceaadd74a93eeb4153e51b784a4d4ff6dfa7079382510652cf8070ed3aad1a` |
| flattened `connectivity` | `(239385,)`, int64; byte SHA-256 `971e53f7bc46fd694955be2f00b1b4355e513d5e066c5ebe1499b72a463b4ff3` |
| `offsets` | `(40707,)`, int64; byte SHA-256 `eff2e0fe7cd471ab5bac922b5290a0560db4d8d72d4fc3b2917ff70582083509` |
| face counts by width | 3:5, 4:565, 5:7,891, 6:28,190, 7:3,927, 8:126, 9:2 |
| node-ID range | 0 through 79,206 |
| source-order evidence | 40,706 faces and 14,720 adjacent width transitions |

Load the new archive with `numpy.load(path, allow_pickle=False)` during every
verification. Do not retain a conversion script in the repository.

## 2. Make `.npz` a safe generic surface-mesh input

Extend `bsm3.preprocessing.import_mesh`/`read_mesh` so a caller supplies only
the filename/path; `.npz` is suffix-dispatched alongside `.msh` and `.stl`.
Do not add a `mesh_kind` argument or a new public importer.

The NPZ reader must:

- call `numpy.load(..., allow_pickle=False)` explicitly;
- require exactly `vertices`, `connectivity`, and `offsets`;
- validate dimensions, numeric/integer dtypes, finite vertices, offset start
  and end, monotonic face spans of at least three nodes, nonempty faces, and
  node IDs in range;
- raise a clear `ValueError` for malformed archives, including object arrays;
- preserve the decoded face sequence in `MeshData.connectivity` and the
  corresponding per-face labels in `MeshData.cell_types`;
- build deterministic width-grouped `cell_blocks` named `triangle`, `quad`,
  and `polygonN`, in ascending width order; and
- identify the safe reader and source path in `metadata`.

Do not make `.pkl` or `.pickle` part of generic suffix dispatch.
`import_trusted_polygon_pickle` remains as the explicitly dangerous,
opt-in public compatibility API, but no curated asset or retained pipeline may
depend on it. Preserve its warning and add/retain a small synthetic test so the
allowed compatibility boundary is intentional rather than dead code.

Add focused synthetic tests with interleaved polygon widths. They must prove
original order, `cell_types`, grouped blocks, `allow_pickle=False` behavior,
and representative schema/bounds failures—not only cell counts.

## 3. Remove the pipeline's internal pickle branch

In `mesh_motion_pipeline.py`:

- delete `_load_polygon_surface_pickle` and `_cfd_mesh_from_pickle`;
- remove all direct `pickle` imports/loads and `.pkl`/`.pickle` suffix checks;
- always load the surface through `bsm3.preprocessing.import_mesh`; and
- derive `polygon_connectivity` from the imported mesh's ordered
  `connectivity`, preserving the legacy face sequence for fold diagnostics.

Keep `_cfd_surface_cells` for the width-grouped quality/inversion order. Those
are deliberately different orderings for the mixed asset; do not silently
replace one with the other. Do not change solver, projection, regularization,
quality, or derivative behavior.

## 4. Remove the retained warm-start hidden pickle default

The retained projection API must not point by default at the untracked
`bsm3/core/projections/refitted_fun_set.pkl`.

- Delete `DEFAULT_FUN_SET_PATH` and any import that becomes dead.
- Consolidate the duplicate retained function-set loaders into one explicitly
  named `load_function_set_from_trusted_pickle(pickle_path)` entry point in
  `warm_start_projections.py`.
- The path argument is mandatory: no default, package-relative fallback, or
  implicit file lookup.
- Keep the execution warning and all reconstruction behavior.
- Remove the duplicate loader and stale imports from
  `warm_start_candidate_projection_numpy.py`.

This is an intentional clean break. Do **not** edit or adopt the untracked
driver/scripts that import the old names. Report those local incompatibilities
prominently in the handoff and update `MANIFEST.md` to distinguish an
untracked local artifact from a retained default dependency.

## 5. Curated regression and documentation

Update `tests/test_curated_assets.py` to use `wall_surface.npz` through generic
`import_mesh`. Preserve the existing vertex, polygon6, type-set, and 117,267
hourglass-mode assertions. Add exact decoded-array/order evidence using the
hashes and transition count above; do not merely compare aggregate topology.

Update `ASSETS.md`, `MANIFEST.md`, `PLAN.md`, and `LOG.md` to state the safe
format and actual retained boundary. Historical log entries remain historical;
append corrections rather than rewriting old turns. Replace
`CODEX_NEXT.md` with the review checklist and measured results.

## Required acceptance gates

Run all of the following in `bsm3_py312_main` and report exact results.

1. Focused implementation tests:

```bash
conda run -n bsm3_py312_main python -m pytest -q \
  tests/test_preprocessing_plotting.py \
  tests/test_curated_assets.py \
  tests/test_warm_start_retry_regression.py
```

2. The established focused and derivative/N-gon suites:

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

conda run -n bsm3_py312_main python -m pytest -q \
  tests/test_derivative_gate.py \
  tests/test_ngon_affine_operator.py \
  tests/test_ngon_affine_load_step.py
```

The first two historical suites should remain near their 82/3-deselected and
89-pass baselines, adjusted only by the explicitly added unit tests; the final
suite remains exactly 6 passed. Any numerical regression is a defect, not a
new baseline.

3. Run the full curated integration module, including the 40,706-face affine
assembly:

```bash
conda run -n bsm3_py312_main python -m pytest -q \
  tests/test_curated_assets.py -m integration
```

4. Run the literal CI Ruff commands that cover every changed Python file:
the default critical-static command, surface-motion `--select D`, and
projection/preprocessing `--select D` from `.github/workflows/actions.yml`.

5. Prove the asset and code boundary:

```bash
git ls-files \
  bsm3/core/boundary_surface_movement/wall_surface.pkl \
  bsm3/core/boundary_surface_movement/wall_surface.npz

git grep -n -E 'pickle\.load|pickle\.loads' -- \
  bsm3/core/boundary_surface_movement/mesh_motion_pipeline.py \
  bsm3/preprocessing/mesh_io.py \
  bsm3/core/projections/warm_start_candidate_projection_numpy.py \
  bsm3/core/projections/warm_start_projections.py

git grep -n 'DEFAULT_FUN_SET_PATH' -- \
  bsm3/core/projections/warm_start_candidate_projection_numpy.py \
  bsm3/core/projections/warm_start_projections.py

git grep -n 'wall_surface\.pkl' -- \
  bsm3/core/boundary_surface_movement/mesh_motion_pipeline.py \
  bsm3/preprocessing tests docs/overhaul/ASSETS.md \
  docs/overhaul/MANIFEST.md
```

Expected results:

- the file listing contains only `wall_surface.npz`;
- direct pickle loads occur only inside
  `import_trusted_polygon_pickle` and
  `load_function_set_from_trusted_pickle`;
- `DEFAULT_FUN_SET_PATH` is absent from both retained projection modules; and
- the scoped old-asset-name grep is empty.

Also verify `git diff --check "$TURN57_BASE" HEAD` is empty, every changed
path is in the literal allowlist, all eight pre-existing modified files are
byte-identical to the baseline, and the pre-existing untracked set was neither
removed nor adopted.

## Commit structure and handoff

Make exactly three commits, staging paths literally:

1. safe NPZ reader, pipeline cleanup, focused tests, and asset replacement;
2. retained warm-start trusted-pickle API cleanup and its focused test, if a
   test change is required;
3. `ASSETS.md`, `MANIFEST.md`, `PLAN.md`, `LOG.md`, and `CODEX_NEXT.md` only.

If commit 2 needs no test change, say so; do not invent one merely to fill the
allowlist. Hand back **M1.8 ready for Codex acceptance, not self-accepted**.
Report the three commit hashes, exact changed paths, decoded asset hashes and
transition count, all test/Ruff results, exact allowed pickle-load locations,
dirty-tree preservation, untracked local callers broken by the clean rename,
and every deviation or stop.
