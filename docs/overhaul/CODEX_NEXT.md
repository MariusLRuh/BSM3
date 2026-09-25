# Codex acceptance checklist — M1.7 and final M1

Claude was the implementer and acceptance-run operator. M1.7 and M1 are
**ready for final Codex acceptance and are not accepted by the implementer**.

## Commits

| Hash | Contents |
| --- | --- |
| `TURN58_BASE` | `7b1bee9` |
| `338fde8` | six production paths + the five test files that actually changed |
| *(docs commit)* | `PLAN.md`, `LOG.md`, `CODEX_NEXT.md` |

No amend, reset, rebase, rewrite, push, clean, stash, install, or other-repo
change. Paths staged literally through a Python list.

## Changed paths (11, all allowlisted)

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
```

## Part A — API decisions

| # | Decision |
| --- | --- |
| A1 | `GraphDistanceSummary(TypedDict)` with the eight fields `summary()` returns; `"decay"` removed after confirming the only retained caller prints `distance.decay` from configuration; type exported beside `GraphDistanceWeighting`. Weights, distances, and solver behavior untouched. |
| A2 | `DerivativeComparison.best -> dict[tuple[str, str], tuple[float \| None, float]]`, on both the return and the local result. Selection algorithm unchanged. |
| A3 | `E175DAFoamResult.mesh_motion: MeshMotionResult \| None`; both stale "annotation is non-optional" notes removed. |
| A4 | `nu_tilda_m2_per_s` validated finite and non-negative and wired to the farfield `nuTilda0` primal BC (variable `"nuTilda"`, native-list patches, one-element value list); `primalBC["useWallFunction"]` from `bool(config.use_wall_functions)`; one `--wall-functions` `BooleanOptionalAction` defaulting to `FlowConfig().use_wall_functions`, replacing the inverted flag. |
| A5 | `plot_components(colors=None)` treated as the empty-string no-override sentinel, so components keep their own colors instead of raising `TypeError`. |

## B1 — R4 reproduction, bit-for-bit

Reference taken from a **pristine `git clone` at `TURN58_BASE`** with the
untracked R4 inputs copied in; an earlier pre-edit run reproduced the same
hash, confirming determinism. Cache forced to `/tmp`; nothing written in the
repository.

| Check | Result |
| --- | --- |
| Shape | `(35190, 3)` both |
| Max abs coordinate difference | **0.000e+00** |
| `allclose(rtol=atol=1e-12)` | True |
| `final` sha256 | identical, `15be154795ce5624…` |
| `initial` / `preprojected` | 0.000e+00 / 0.000e+00 |
| Inverted + degenerate IDs ×3 stages | identical, all empty |
| Fold / cell / n-gon-mode counts | 0 / 69,942 / 0 |
| Quality scalars | 13 compared, worst difference **0.000e+00** |
| Runtime | 197.1 s pre, 203.1 s post |

## B2 — flagship and derivative gates

`tests/test_e175_example.py`: **18 passed** in 592.87 s.

| Named case | Outcome |
| --- | --- |
| Real triangle wall | passed; inversions 0/0/0; zero folds |
| Real quad panel | passed; 114/114/114 — baseline preserved, none added |
| External-coefficient analytic vs centered FD | passed; analytic `5.0436177894e-02`, FD identical, **rel. error 4.196e-14** vs 1e-5 threshold, step 1e-5, max displacement 0.3502 |
| Whole-component free regions | passed; inversions 0/0/0 |
| Full-scale triangle | passed; zero folds |

Curated mixed-N-gon integration: **3 passed, 3 deselected** (40,706 faces /
117,267 modes). Derivative + N-gon: **exactly 6 passed**.

## B3 — VortexAD, verified read-only

1. Neither `VortexAD` nor `vortexad` installed in `bsm3_py312_main`; pip lists
   no vortex package.
2. `../VortexAD` on `dev_new_derivs` at `c33828d`, three modified solver files
   (`pfse_solver.py`, `unsteady_panel_solver.py`, `unsteady_vlm_solver.py`).
3. `PYTHONPATH=../VortexAD python -c "import VortexAD"` →
   `ModuleNotFoundError: No module named 'vedo'`.
4. Panel driver and every candidate panel mesh untracked.
5. The driver imports `e175_mesh_motion_config` and
   `e175_mesh_motion_pipeline` — **both removed** — plus `E175ModelFiles`,
   `E175PipelineConfig`, `E175MeshMotionResult`, none tracked anywhere. One
   plotting dependency would not make it supported.

Evidence-backed deferral, not a waived test. **Future task recorded:** a
tracked adapter against a pinned clean VortexAD revision, using the generalized
`mm.run` result and the curated quad mesh.

## B4 — regressions, lint, clean clone

| Suite | Result |
| --- | --- |
| Focused group 1 | **100 passed, 3 deselected** (97 + 3 added) |
| Focused group 2 | **109 passed** (102 + 7 added) |
| Clean clone, full `tests` | **202 passed, 1 skipped**, 617.83 s, `git status --porcelain` empty at `338fde8` |

The single skip is the predicted local R4 check, whose inputs are
intentionally untracked.

All five literal `actions.yml` Ruff commands: **All checks passed**.

**Not clean, and reported as such.** The default Ruff selection over my changed
paths leaves **4 `F821`** findings (`create_geometry_from_variables` in
`cfd_mesh_dafoam_analysis.py`; three `MPI` in `run_dafoam_gmsh.py`), and
`--select D` over those paths leaves **136** findings, all in test files. Both
sets are **pre-existing and identical at `TURN58_BASE`** in count, file, and
name; only line numbers shifted. My added tests introduced none, and the
production paths are clean under `--select D`. No workflow step lists them, so
CI is unaffected.

## Static acceptance checks

All five required greps are empty. Inspection confirms:

```text
GraphDistanceSummary exported: True | is TypedDict: True
DerivativeComparison.best -> dict[tuple[str, str], tuple[float | None, float]]
E175DAFoamResult.mesh_motion -> MeshMotionResult | None
```

## Turn-58 correction to the M1.8 handoff

M1.8 said the excluded `movement_test_embraer_175_hex_mesh.py` "should point at
`wall_surface.npz`". Incomplete: it has its own `_load_polygon_surface_pickle`
calling `pickle.load`, so it needs a **reader** change as well as a path
change — repointing `MESH_PATH` alone would hand an `.npz` to `pickle.load`.
The fix is to read through `bsm3.preprocessing.import_mesh`. Still a prohibited
pre-existing dirty file; not edited.

## Preservation

All eight pre-existing modified files byte-identical to the base snapshot;
untracked 394 before and after with none removed or adopted;
`git diff --check TURN58_BASE HEAD` empty; changed paths a subset of the
allowlist.

## Deviations

None affecting scope. Nothing outside the allowlist changed, no dependency or
environment was touched, no other repository was modified, and no stop
condition was hit. The two pre-existing lint sets above are reported rather
than absorbed.

## Decision requested

Accept M1.7 and close M1. The VortexAD adapter task and the hex-script reader
fix are both recorded for follow-up milestones.
