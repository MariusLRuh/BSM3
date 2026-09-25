# Codex acceptance checklist — M1.6 closure (Turn 56)

Claude was the implementer. M1.6 is **ready for Codex acceptance and is not
accepted by the implementer**.

## Commits

| Hash | Contents |
| --- | --- |
| Source comparison base | `139f35c` |
| `TURN56_BASE` | `deb225e` (turn-local path and whitespace comparisons) |
| `b999476` | five source files — docstrings only |
| *(docs commit)* | `PLAN.md`, `LOG.md`, `CODEX_NEXT.md` |

No amend, reset, rebase, rewrite, push, or clean. No pre-existing dirty file
touched. Paths staged literally through a Python list.

## Changed paths

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

## The seven corrections, each verified in the body first

| # | File | Correction |
| --- | --- | --- |
| 1 | `bsm3/__init__.py` | `bsm3.core.projections` is a **regular subpackage** whose `__init__` re-exports nothing — its `__init__.py` exists and is tracked. Concrete-module guidance preserved. |
| 2 | `cfd_mesh_dafoam_analysis.py` | `mesh_motion` is a snapshot of `last_mesh_motion_result` taken as the result is built. `None` on every non-root rank, and **also possibly `None` on root** when the custom operation has not executed inline by then. The backend is constructed without `build_eagerly`, so the model is lazy. Root is documented as no guarantee; annotation untouched. |
| 3 | `rbf.py` | Stated separately, in both the class and `__post_init__` prose: `seam_neighbor_blend_radius` must be scalar or one-per-intersection **and non-negative**; `seam_neighbor_component_blend` must be scalar or one-per-intersection **and lie in `[0, 1]`**. The old "cannot be resolved" covered only lengths. |
| 4 | `run_dafoam_gmsh.py` | `make_parser`: numerical flow and solver options default from `FlowConfig`; case, path, and patch-name options do not; the wall-function flag is inverted by `--no-wall-functions`, so its effective default disagrees with the dataclass. |
| 5 | `run_dafoam_gmsh.py` | Added the `ValueError` from `set_openfoam_patch_types`: block exists but has no `type` entry. `KeyError` remains the absent-block case. |
| 6 | `run_dafoam_gmsh.py` | `convert_and_check_mesh` raises `FileExistsError` on **both** paths: `polyMesh` exists with `overwrite_existing=False`, or overwrite permitted but the timestamped backup destination is taken. |
| 7 | `volume_mesh_motion.py` | Mean-ratio sign follows the **raw** deformed determinant, while inversion is the deformed-to-baseline ratio. The unconditional "inverted cell scores negative" is removed; the signs coincide only under a positive-baseline-orientation convention, with the negative-oriented-baseline counterexample stated. |

## Verification

| Gate | Result |
| --- | --- |
| M0 public surface (`--select D`) | **All checks passed** |
| Surface-motion core (`--select D`) | **All checks passed** |
| Projection and preprocessing (`--select D`) | **All checks passed** |
| Drivers, volume motion, and MPI (`--select D`) | **All checks passed** |
| Critical static checks (default selection) | **All checks passed** |
| Stripped-AST identity vs `139f35c`, working tree | **5/5 identical** |
| Stripped-AST identity vs `139f35c`, committed blobs | **5/5 identical** |
| Slice-3 coverage audit | 17/17 modules, 167/167 definitions, 132 callables / 293 params **0 missing / 0 extra**, 22 dataclasses / 148 fields **0 missing / 0 extra** |
| `pytest` suite 1 | **82 passed, 3 deselected** |
| `pytest` suite 2 | **89 passed** |
| `pytest` suite 3 | **6 passed** |
| `git diff --check deb225e HEAD` | empty |
| Changed paths after `TURN56_BASE` | subset of the eight-path allowlist |

## Historical records updated

The Turn-54 `LOG.md` entry and the M1.7 carry-in wording now carry inline
corrections so they no longer assert the rejected claims: the root-rank caveat
on `mesh_motion`, the RBF value checks beyond the length rule, the two further
`run_dafoam_gmsh` exception paths and the over-broad `make_parser` claim, and
the mean-ratio sign caveat. Every other Turn-54 correction is preserved as
accepted.

## Carry-ins still open for M1.7

1. `DerivativeComparison.best` can return `None` despite its
   `tuple[float, float]` annotation.
2. `E175DAFoamResult.mesh_motion` is annotated non-optional but is `None` on
   non-root ranks **and** can be `None` on root before inline execution.
3. `FlowConfig.nu_tilda_m2_per_s` and `FlowConfig.use_wall_functions` are never
   consumed by `build_da_options`, which hardcodes `useWallFunction=False`;
   the CLI default for the latter also disagrees with the dataclass default.
4. `plot_components(colors=None)` raises `TypeError` rather than preserving
   component colors.

## Deviations

None. No executable change was required and the allowlist was not widened.

## Decision requested

Accept M1.6. On acceptance, M1.8 is next, with the four carry-ins above folded
into M1.7.
