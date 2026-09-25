# Codex acceptance checklist — Turn 59 rank-0 chain correction

**The rank-0 geometry-to-volume chain now constructs through the current API.**
`build_cfd_analysis_rank0` resolves a real parameterization factory,
`MeshMotionVolumeBackend` takes `input_files` and calls `run_mesh_motion` with
`input_files=` and `geometry=`, and the three communicator annotations resolve
at runtime with no `mpi4py` installed. Six regressions guard the boundary, each
verified to fail at `b60f0c0`.

Claude was the implementer. M1.7 and M1 are **ready for Codex acceptance and
are not accepted by the implementer**.

## Commits

| Hash | Contents |
| --- | --- |
| Base | `b60f0c0` |
| `e47d07f` | source, tests, workflow |
| *(docs commit)* | `PLAN.md`, `LOG.md`, `CODEX_NEXT.md` |

## Changed paths — exactly the 8 implementation-allowlist entries

```text
.github/workflows/actions.yml
bsm3/core/boundary_surface_movement/cfd_mesh_dafoam_analysis.py
bsm3/core/boundary_surface_movement/e175_derivative_ladder.py
bsm3/core/boundary_surface_movement/geometry_volume_backend.py
bsm3/core/boundary_surface_movement/run_dafoam_gmsh.py
tests/test_dafoam_csdl.py
tests/test_e175_driver_configuration.py
tests/test_geometry_volume_mpi.py
```

## A — one current parameterization factory

`create_geometry_parameterization_from_variables(variables)` restored on the
current `GeometryModel` API. Both entry points call one private
`_populate_e175_geometry`, so the wing, tail, fuselage, and two intersection
declarations exist once. `create_geometry_model()` still registers the six
driver design variables with their existing values, bounds, and scalers; the
new factory registers none, owns no recorder, and uses the caller's expressions
as supplied. Keys are validated against `GEOMETRY_VARIABLE_NAMES`, reporting
missing and unexpected names separately. `build_cfd_analysis_rank0` passes the
real function; no alias was added.

## B — backend on the current public API

`__init__` takes `input_files` and stores `_input_files`; `_build_model` calls
`run_mesh_motion(recorder=…, input_files=…, geometry=…, config=…,
aerodynamic_analysis=None, aerodynamic_volume_method=…)`. Both retained call
sites updated. Clean break: `model_files=` now raises `TypeError`, pinned by a
test.

Note that `_build_model` was passing **two** removed keywords, `model_files=`
and `geometry_parameterization=`; the review named the first, and the second
was found while migrating.

## C — optional-MPI annotations

Private `runtime_checkable` `_Communicator` protocol covering only `rank`,
`size`, `Barrier`, and `bcast`. `typing.get_type_hints` resolves for all three
callables with no mpi4py present, a real `MPI.Comm` satisfies it structurally,
`mpi4py` is still imported lazily inside `main`, and no `noqa` was added.

## D — CI coverage hole closed

**Critical static checks** now runs default Ruff over the complete retained
production manifest — all 50 `bsm3` paths the four documentation steps cover —
plus the three M0 test files, replacing the two-file M0 subset. Lists stay
literal and auditable; `ruff.toml` unchanged; no per-file ignore; the
dirty/untracked research tree excluded.

```bash
rg '^            bsm3/.*\.py' .github/workflows/actions.yml \
  | sed -e 's/^ *//' -e 's/ *\\$//' | sort -u \
  | xargs conda run -n bsm3_py312_main python -m ruff check
```

→ 50 paths, **All checks passed**.

## Regressions, each verified to fail at `b60f0c0`

| Test | Module | Guards |
| --- | --- | --- |
| `test_geometry_factory_parity_between_the_two_entry_points` | `test_e175_driver_configuration.py` | identical components/intersections; design-variable ownership; caller expressions captured **by identity** in the coefficient builder |
| `test_geometry_parameterization_rejects_wrong_variable_names` | same | missing and unexpected keys each reported |
| `test_mesh_motion_volume_backend_calls_the_current_pipeline_api` | `test_geometry_volume_mpi.py` | patches the pipeline with a current-signature fake, executes build/forward, asserts it received `input_files`, `geometry`, `config` and returned the selected volume output |
| `test_mesh_motion_volume_backend_rejects_the_removed_keyword` | same | clean break on `model_files` |
| `test_rank0_chain_constructs_the_backend_through_the_current_api` | `test_dafoam_csdl.py` | runs `build_cfd_analysis_rank0` itself, mocking only the volume-point read and the downstream custom operation |
| `test_run_dafoam_gmsh_communicator_annotations_resolve_without_mpi` | same | runtime hint resolution, structural satisfaction, no eager import, no `noqa` |

None requires a CAD asset, volume mesh, MPI, or DAFoam.

## Verification

| # | Gate | Result |
| --- | --- | --- |
| 1 | `git diff --check b60f0c0 HEAD` | empty |
| 2 | Changed paths ⊆ allowlist | yes, exactly the 8 above |
| 3 | The six new regressions | all pass here, all fail at `b60f0c0` |
| 4 | Five modules (150 before) | **156 passed** = 150 + exactly the 6 new tests |
| 5 | Derivative / N-gon guard | **exactly 6 passed** |
| 6 | Five literal workflow Ruff commands | all **All checks passed** |
| 7 | Reconstructed production manifest | 50 paths, **All checks passed** |
| 8 | Clean clone at `e47d07f`, `pytest -q tests` | **208 passed, 1 skipped**, 631.62 s; clone status empty afterwards |
| 9 | Preservation | 8/8 pre-existing byte-identical; untracked 394 → 394, none removed or adopted |

The clone's 202 → 208 movement is exactly the six new regressions, and the one
skip is the pre-existing local R4 check whose inputs are intentionally
untracked.

The Turn-58 R4 and E175 numerical runs were not repeated: none of these changes
touches the surface pipeline those gates exercise.

## Root cause of the escape, for the record

Turn 58 measured the four `F821` findings, verified they were identical at the
base commit, and reported them as pre-existing lint outside CI coverage. The
measurement was right and the judgement was wrong: those names *were* the
broken chain. Establishing that a finding is pre-existing says nothing about
whether it is harmless. The expanded critical Ruff gate now makes the same
class of breakage fail CI rather than depend on a reviewer noticing.

## Deviations

None. Nothing outside the two allowlists changed, no dependency was installed,
no other repository was touched, DAFoam/OpenFOAM/VortexAD/real-MPI were not
run, and every accepted Turn-58 API correction is unchanged.

## Decision requested

Accept M1.7 and close M1.
