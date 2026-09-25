# Claude implementation prompt — Turn 59 M1.7 rank-0 chain correction

Codex reviewed `338fde8` and `b60f0c0`. The five intended API corrections are
sound, and the independently rerun changed-file and derivative/N-gon tests pass
150 and 6 respectively. **M1.7 and M1 are not accepted**, because final review
found that M1.1 left the retained rank-0 geometry-to-volume chain on removed API
names.

You are the implementer. Fix only the defects below, run the gates, commit the
implementation and collaboration documents separately, and hand the result
back to Codex without accepting it yourself.

## Base and preservation

- Base: current `HEAD` (`b60f0c0`). Do not rewrite either Turn-58 commit.
- Preserve all eight pre-existing modified files byte-for-byte.
- Preserve the complete untracked set; do not adopt, delete, clean, stash, or
  modify any untracked path.
- Do not install anything, push, or modify another repository.
- Do not run DAFoam, OpenFOAM, VortexAD, or a real MPI job.
- Keep every accepted Turn-58 API correction unchanged.

## Literal allowlist

Implementation commit — only these paths may change:

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

Documentation commit — only:

```text
docs/overhaul/PLAN.md
docs/overhaul/LOG.md
docs/overhaul/CODEX_NEXT.md
```

Stop and report rather than widening either allowlist.

## A. Restore one current E175 parameterization factory

In `cfd_mesh_dafoam_analysis.py`, restore
`create_geometry_parameterization_from_variables(variables)` using the current
`GeometryModel` API. It must accept a mapping of the six caller-owned CSDL
variables and return a `GeometryModel` with the same wing, tail, fuselage, and
two intersection declarations as `create_geometry_model()`.

Do not duplicate the configuration bodies. Factor one private population
helper that both entry points call:

- `create_geometry_model()` still creates/registers the six public driver
  design variables with their existing values, bounds, and scalers, then
  populates that model.
- `create_geometry_parameterization_from_variables()` creates no design
  variables and owns no recorder; it populates a fresh model from the supplied
  variables.
- Validate the mapping's exact required keys and give a useful error for
  missing or unexpected names. Do not silently ignore either.
- `build_cfd_analysis_rank0` must pass this real function, not add an alias for
  the undefined `create_geometry_from_variables` name.

Add an executable test proving the two entry points produce equivalent
component/intersection declarations and that external variables remain the
expressions captured by the factory. A source-text grep alone is not a test.

## B. Finish the backend migration to the current public API

`MeshMotionVolumeBackend` must use the same names as `run_mesh_motion`:

- constructor argument and stored attribute: `input_files`, not `model_files`;
- `_build_model`: call `run_mesh_motion(recorder=..., input_files=...,
  geometry=..., config=..., aerodynamic_analysis=None,
  aerodynamic_volume_method=...)`;
- update both retained call sites, in `cfd_mesh_dafoam_analysis.py` and
  `e175_derivative_ladder.py`.

Do not keep compatibility aliases or accept both keyword spellings; this
overhaul is a clean break.

Add a mock-backed execution test for `MeshMotionVolumeBackend`, not merely an
`inspect.signature` assertion. Patch the imported pipeline function with a
small current-signature fake, construct a backend around a one-variable CSDL
geometry factory, execute its build/forward path, and prove the fake received
`input_files`, `geometry`, and `config` and returned the selected volume output.
This test must fail at `b60f0c0` because of the old keywords and pass after the
fix. It must require no CAD asset, volume mesh, MPI, or DAFoam.

Also add a focused no-DAFoam regression that reaches construction of the
rank-0 backend from `build_cfd_analysis_rank0` far enough to prove the factory
name and constructor keyword are valid. Mock only expensive I/O/downstream
operations; do not replace the function under test wholesale.

## C. Make optional-MPI annotations real

The three `MPI.Comm` annotations in `run_dafoam_gmsh.py` currently refer to no
module-global `MPI`. Replace them with an optional-dependency-safe structural
communicator protocol (private is fine) or an equally precise runtime-resolvable
type. Do not import `mpi4py` eagerly and do not suppress F821 with `noqa`.

Test that `typing.get_type_hints` succeeds for all three affected callables in
the Python-3.12 main environment without relying on a module-global MPI import.

## D. Close the CI coverage hole

The default Ruff selection over every retained production path already listed
in the four workflow documentation steps currently reports exactly the four
F821 findings above and no others. Expand the workflow's **Critical static
checks** so it runs default Ruff over that full retained production manifest,
not only the M0 subset. Keep the lists literal and auditable; do not run Ruff
over the dirty/untracked research tree and do not weaken `ruff.toml` or add
per-file ignores.

After the source fixes, this exact locally reconstructed set must pass:

```bash
rg '^            bsm3/.*\.py' .github/workflows/actions.yml \
  | sed -e 's/^ *//' -e 's/ *\\$//' \
  | sort -u \
  | xargs conda run -n bsm3_py312_main python -m ruff check
```

The five existing literal workflow Ruff commands must also still pass.

## E. Required verification

Run and report:

1. `git diff --check b60f0c0 HEAD`.
2. Changed paths are a subset of the literal allowlist.
3. The new factory-parity, backend-execution, rank-0-construction, and
   runtime-type-hint regressions, each named in the handoff.
4. These five modules together, which Codex measured at 150 before this turn:

   ```bash
   conda run -n bsm3_py312_main python -m pytest -q \
     tests/test_boundary_surface_movement.py \
     tests/test_dafoam_csdl.py \
     tests/test_e175_driver_configuration.py \
     tests/test_geometry_volume_mpi.py \
     tests/test_preprocessing_plotting.py
   ```

5. The exact derivative/N-gon guard remains 6:

   ```bash
   conda run -n bsm3_py312_main python -m pytest -q \
     tests/test_derivative_gate.py \
     tests/test_ngon_affine_operator.py \
     tests/test_ngon_affine_load_step.py
   ```

6. All five literal workflow Ruff commands.
7. Default Ruff over the complete retained production manifest, reconstructed
   by the command in part D: zero findings.
8. A fresh clone at the implementation commit, installed through the existing
   Python-3.12 main environment strategy, running `python -m pytest -q tests`;
   report its exact result and require empty clone status afterward.
9. Confirm the eight pre-existing modified files remain byte-identical and the
   untracked set is unchanged.

The Turn-58 R4 and E175 numerical runs do not need repeating: none of these
changes touches their surface pipeline. DAFoam tests remain unnecessary; the
new mock-backed tests guard the construction/API boundary that was broken.

## Commit and handoff

Make exactly two commits:

1. source, tests, and workflow;
2. `PLAN.md`, `LOG.md`, and `CODEX_NEXT.md`.

In the handoff, lead with whether the rank-0 chain now constructs through the
current API, then give the two hashes, literal changed-path inventory, focused
test counts, 6-test derivative/N-gon result, all Ruff results, clean-clone
result, and preservation proof. Call out every deviation. Mark M1.7 and M1 as
ready for Codex acceptance, never as self-accepted.
