# Codex acceptance checklist — M1.6 closure (Turn 54)

Claude was the implementer. M1.6 is **ready for Codex acceptance and is not
accepted by the implementer**.

## Commits

| Hash | Contents |
| --- | --- |
| Base for all comparisons | `81736be` |
| Starting `HEAD` | `0e980d0` (Codex's review commit, docs only) |
| `139f35c` | 38 source files — docstrings, comments, doc-rule whitespace |
| *(docs commit)* | `PLAN.md`, `LOG.md`, `CODEX_NEXT.md` |

No amend, reset, rebase, rewrite, push, or clean. Every path staged literally
through a Python list rather than a newline-sensitive shell loop.
`.github/workflows/actions.yml` was **not** edited.

## Part A — all four documentation gates green

Codex's pre-edit measurements reproduced exactly: surface-motion core **123**
(97 `D202`, 15 `D105`, 5 `D205`, 4 `D209`, 2 `D401`); projection/preprocessing
**48** (23 `D202`, 16 `D204`, 5 `D205`, 2 `D401`, 2 `D103`).

`D202`/`D204`/`D209` were fixed with `ruff check --select D202,D204,D209 --fix`
scoped to exactly those two path sets. The other 31 were hand-written after
reading each body.

| Step | Before | After |
| --- | --- | --- |
| M0 public surface | pass | **pass** |
| Surface-motion core | 123 | **pass** |
| Projection and preprocessing | 48 | **pass** |
| Drivers, volume motion, and MPI | pass | **pass** |
| Critical static checks (default selection) | — | **pass** |

## Part B — semantic corrections, each verified in the body

| File | Correction |
| --- | --- |
| `bsm3/__init__.py` | `bsm3.core.projections` re-exports nothing; the three defining modules are named instead |
| `component_parameters.py` | one-of-two holds the other at its reference; both `None` skips scaling; references inferred from control-point extents; `spanwise_scaling_root` measured about the spanwise **pivot**; `TailParameters` has no distinct dispatch |
| `cfd_mesh_movement_test.py` | mesh writes and visualization are conditional side effects **of the call** |
| `cfd_mesh_dafoam_analysis.py` | `resolve_comm(None)` prefers `MPI.COMM_WORLD`; `mesh_motion` is `None` on non-root ranks |
| `e175_derivative_ladder.py` | Levels 3 and 6 share a direction only at Level 3's default seed; Level 6 exposes no seed |
| `geometry_volume_mpi.py` | zero tolerance means zero numeric difference for finite values, not bit-for-bit; `NaN` is not rejected |
| `rbf.py` | all eleven `__post_init__` validations; `exact_interpolation` softened by nonzero `regularization`; `evaluate` returns **deformed positions** |
| `run_dafoam_gmsh.py` | `run_command` has no rank check; `nu_tilda_m2_per_s` and `use_wall_functions` unused, `useWallFunction` hardcoded `False`; parser default disagrees with the dataclass; `run_dafoam` returns the `evalFunctions` mapping; three `Raises` sections corrected |
| `volume_mesh_motion.py` | percentiles are lower-tail metric **values**; inversion is a non-positive **relative** Jacobian; mean ratio is an absolute current-cell shape metric, regular tetrahedron at one |
| `weighting_functions.py` | truncated Gaussian jumps by `exp(-sharpness)` at `d == 1` for every finite `sharpness` |
| `plotting.py` | `plot_components(colors=None)` raises `TypeError`; only an exactly-`None` `node_color` consults `node_colore` |

## M1.9 historical wording

The Turn-50 entry now carries an inline correction: its Ruff line meant the
repository's **default** selection (`E9,F63,F7,F82` from `ruff.toml`), not
`ruff check --select D`. The original measurement is left as recorded.

## Gates

| Gate | Result |
| --- | --- |
| Four documentation commands + default critical-static command | **all pass** |
| Slice-3 coverage audit | 17/17 modules, 167/167 definitions, 132 callables / 293 params at **0/0**, 22 dataclasses / 148 fields at **0/0** |
| Stripped-AST identity vs `81736be`, working tree | **38/38** |
| Stripped-AST identity vs `81736be`, committed blobs | **38/38** |
| `pytest` suite 1 | **82 passed, 3 deselected** |
| `pytest` suite 2 | **89 passed** |
| `pytest` suite 3 | **6 passed** |
| `git diff --check 81736be HEAD` | empty |
| Changed-path set | subset of the 47-path allowlist |
| Pre-existing dirty/untracked entries | none removed or altered |

## Carry-ins for M1.7 — recorded, deliberately not fixed

Each needs an executable or annotation change, so all are out of scope here:

1. `DerivativeComparison.best` can return `None` despite its
   `tuple[float, float]` annotation.
2. `E175DAFoamResult.mesh_motion` is annotated non-optional but is `None` on
   non-root ranks.
3. `FlowConfig.nu_tilda_m2_per_s` and `FlowConfig.use_wall_functions` are
   never consumed by `build_da_options`, which hardcodes
   `useWallFunction=False`; the CLI default for the latter also disagrees with
   the dataclass default.
4. `plot_components(colors=None)` raises `TypeError` rather than preserving
   component colors.

## Deviations

None. No executable change was required, the allowlist was not widened, and
the workflow file was not touched.

## Decision requested

Accept M1.6. If accepted, the carry-ins above should be folded into the M1.7
scope.
