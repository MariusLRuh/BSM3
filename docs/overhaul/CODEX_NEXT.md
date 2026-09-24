# Turn 54 — Claude implementation prompt: close M1.6 lint and semantic accuracy

Codex reviewed M1.6 slice 3 at `81736be`. The implementation is mechanically
sound, but M1.6 is **not accepted**: two older CI doc-lint steps fail, and the
semantic review found inaccurate new public prose. This turn closes both debts
without changing executable behavior.

## Rulings

1. The 69 pre-existing `D202` removals in `cdcba68` are accepted. They were
   independently reproduced at `29d53a8`, were mechanically fixed, and preserve
   stripped ASTs 17/17.
2. Slice 3's structural evidence is accepted: exact path scope, coverage audit,
   17/17 stripped-AST identity, 89 focused tests, 6 derivative/N-gon guards,
   and the new 17-path Ruff gate all reproduced.
3. M1.6 remains open until **all four** documentation steps in `actions.yml`
   pass under `ruff 0.9.10` and the inaccuracies below are corrected.
4. The M1.9 statement meant the repo's default `ruff check`, not
   `ruff check --select D`. Correct that historical wording explicitly.

Base all comparisons on `81736be`. Do not amend, reset, rebase, rewrite, push,
or clean the dirty tree.

## Literal allowlist (47 paths)

Only these paths may change:

```text
bsm3/mesh_motion.py
bsm3/core/boundary_surface_movement/geometry_model.py
bsm3/core/boundary_surface_movement/mesh_motion_config.py
bsm3/core/boundary_surface_movement/mesh_motion_pipeline.py
bsm3/core/boundary_surface_movement/motion.py
bsm3/core/boundary_surface_movement/elasticity.py
bsm3/core/boundary_surface_movement/load_stepping.py
bsm3/core/boundary_surface_movement/current_graph_solve.py
bsm3/core/boundary_surface_movement/ngon_affine.py
bsm3/core/boundary_surface_movement/quadratic_distortion.py
bsm3/core/boundary_surface_movement/projection.py
bsm3/core/boundary_surface_movement/quality.py
bsm3/core/boundary_surface_movement/graph_distance.py
bsm3/core/boundary_surface_movement/free_region.py
bsm3/core/boundary_surface_movement/constraints.py
bsm3/core/boundary_surface_movement/spd_solve_custom_op.py
bsm3/core/boundary_surface_movement/geometry.py
bsm3/core/boundary_surface_movement/intersections.py
bsm3/core/projections/function_set_closest_distance_custom_op.py
bsm3/core/projections/function_set_evaluation_custom_op.py
bsm3/core/projections/function_set_projection_custom_op.py
bsm3/core/projections/orthogonality_projection_numpy.py
bsm3/core/projections/warm_start_candidate_projection_numpy.py
bsm3/core/projections/warm_start_projections.py
bsm3/preprocessing/__init__.py
bsm3/preprocessing/components.py
bsm3/preprocessing/gmsh.py
bsm3/preprocessing/intersections.py
bsm3/preprocessing/mesh_io.py
bsm3/preprocessing/movement.py
bsm3/preprocessing/quad_conversion.py
bsm3/preprocessing/stl.py
bsm3/preprocessing/symmetry.py
bsm3/__init__.py
bsm3/component_parameters.py
bsm3/core/boundary_surface_movement/cfd_mesh_dafoam_analysis.py
bsm3/core/boundary_surface_movement/cfd_mesh_movement_test.py
bsm3/core/boundary_surface_movement/e175_derivative_ladder.py
bsm3/core/boundary_surface_movement/geometry_volume_mpi.py
bsm3/core/boundary_surface_movement/rbf.py
bsm3/core/boundary_surface_movement/run_dafoam_gmsh.py
bsm3/core/boundary_surface_movement/volume_mesh_motion.py
bsm3/core/weighting_functions.py
bsm3/plotting.py
docs/overhaul/PLAN.md
docs/overhaul/LOG.md
docs/overhaul/CODEX_NEXT.md
```

Do not edit `.github/workflows/actions.yml`; its four documentation commands
already name the intended scopes. Do not touch untracked artifacts. If a
required correction needs executable code or a path outside this allowlist,
stop and report it instead of widening scope.

## Part A — make the two existing documentation gates genuinely green

Codex independently measured in `bsm3_py312_main`:

- M0 public surface: pass.
- surface-motion core: **123** findings (`97 D202`, `15 D105`, `5 D205`,
  `4 D209`, `2 D401`).
- projection/preprocessing: **48** findings (`23 D202`, `16 D204`, `5 D205`,
  `2 D103`, `2 D401`).
- drivers/volume/MPI: pass.

Correct the exact two failing path sets from `actions.yml`. Mechanical
whitespace fixes are allowed only for the reported doc rules; do not run an
unscoped formatter or blanket fixer. Add/correct the missing docstrings and
summaries manually after reading the body. Preserve every executable AST.

## Part B — correct the slice-3 semantic inaccuracies

Correct the public text, not the implementation:

- `bsm3/__init__.py`: `bsm3.core.projections.__init__` exports none of the
  named helpers. Do not recommend importing those names directly from that
  package; name the guarded top-level behavior and concrete defining modules
  accurately.
- `component_parameters.py`: when only one of `area` or `aspect_ratio` is
  supplied, the other retains its resolved reference value; when both are
  `None`, planform scaling is skipped. `reference_area` and
  `reference_aspect_ratio` are inferred from control-point extents when absent.
  `spanwise_scaling_root` is measured about the spanwise pivot, not
  unconditionally from the symmetry plane. `TailParameters` expresses intent
  but is currently transformed by the generic `ComponentParameters` path; it
  has no distinct dispatch.
- `cfd_mesh_movement_test.py`: configured mesh writes and visualization are
  conditional side effects of calling `run_deformation_test`; do not say they
  are not side effects of the function.
- `cfd_mesh_dafoam_analysis.py`: `resolve_comm(None)` selects
  `MPI.COMM_WORLD` when `mpi4py` is available and `SerialComm` otherwise.
  `E175DAFoamResult.mesh_motion` may be `None` on non-root ranks in the rank-0
  path; document that fact without changing the annotation this turn.
- `e175_derivative_ladder.py`: Level 3 and Level 6 use identical directions
  only when Level 3 uses its default `seed_index=0`; Level 6 exposes no seed
  argument.
- `geometry_volume_mpi.py`: tolerance zero means zero numeric difference for
  finite values, not bit-for-bit identity. The current max-absolute-difference
  check does not reject NaNs; do not claim that it does.
- `rbf.py`: document every validation performed by
  `DisplacementInterpolationParameters.__post_init__`, including nonnegative
  counts/weights, positive optional support width, sequence lengths, and the
  all-or-none distance rule. `exact_interpolation` is softened when
  `regularization` is nonzero. `DisplacementSurrogate.evaluate` returns
  **deformed positions**, not displacements.
- `run_dafoam_gmsh.py`: `run_command` contains no rank check; callers decide
  where it runs. `nu_tilda_m2_per_s` and `use_wall_functions` are presently
  carried by configuration/CLI but not consumed by `build_da_options`, which
  hardcodes `useWallFunction=False`. The parser's wall-function default is not
  the default-constructed `FlowConfig` value. `run_dafoam` returns the mapping
  from `evalFunctions`, not a metadata payload. Also make the documented
  `Raises` sections match the visible validation in
  `set_control_dict_max_iterations`, `set_openfoam_patch_types`, and
  `convert_and_check_mesh`.
- `volume_mesh_motion.py`: percentiles characterize lower-tail metric values;
  they do not report how many cells are near the worst value. Inversion is a
  non-positive **relative Jacobian** (orientation reversal relative to the
  baseline), not simply a non-positive raw signed volume. Mean ratio is an
  absolute current-cell shape metric with a regular tetrahedron at one, not a
  similarity-to-baseline metric.
- `weighting_functions.py`: the truncated Gaussian has a mathematical jump at
  `d == 1` for every finite `sharpness`; large sharpness can make the jump
  numerically small but does not remove it.
- `plotting.py`: `plot_components(colors=None)` currently fails in
  `_broadcast`; only the empty string means preserve component colors. For
  `highlight_mesh_nodes`, only `node_color is None` consults `node_colore`; an
  empty explicit `node_color` falls through to red rather than to the alias.

Record, but do not fix in this doc-only turn, these public/API carry-ins for
M1.7: `DerivativeComparison.best` can return `None` despite its return
annotation, `E175DAFoamResult.mesh_motion` is annotated non-optional, the two
unused DAFoam configuration fields, and `plot_components(colors=None)`.

Correct the Turn-50 M1.9 log wording to say the five migrated projection files
passed the repo's **default** Ruff selection (`E9,F63,F7,F82`). Do not rewrite
the historical result as if `--select D` had been run then.

## Required gates

Use `bsm3_py312_main` and reproduce all of these:

1. The four literal `ruff check --select D` commands from `actions.yml` all
   pass. Also run the workflow's literal default `Critical static checks` Ruff
   command.
2. Re-run the slice-3 coverage audit: 17/17 modules, 167/167 public
   definitions, 132 callables / 293 parameters with 0 missing and 0 extra, and
   22 dataclasses / 148 fields with 0 missing and 0 extra.
3. For every changed Python file, compare `81736be` with both the working tree
   and the final source commit after recursively stripping docstrings. Both
   comparisons must be identical. Comments and doc-rule whitespace are the
   only permitted non-docstring changes.
4. Run:

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

Expected: **82 passed / 3 deselected**, **89 passed**, and **6 passed**.

5. `git diff --check 81736be HEAD` is empty. The final changed-path set is a
   subset of the literal allowlist, with no disappearance or modification of
   pre-existing dirty/untracked entries.

## Commit and handoff

Make two new commits without rewriting history:

1. source docstrings/comments/doc-rule whitespace only;
2. `PLAN.md`, `LOG.md`, and `CODEX_NEXT.md` only.

Stage every path literally; do not stage directories or consume a newline-
sensitive path loop. Update M1.6 as **ready for Codex acceptance**, not
self-accepted. Report exact changed paths, Ruff results for all four steps,
coverage, AST identity, test counts, deviations, and any carry-in discovered.
