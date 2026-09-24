# Claude implementation prompt — M1.6 slice 3 (Turn 48)

You are the **implementer**. Codex is the planner/reviewer. Implement this
bounded documentation slice, verify it, commit it, and hand it back to Codex
without accepting your own work.

This prompt follows Codex's Turn-47 acceptance of M1.6 slice 2. The exact code
baseline for all stripped-AST and path-range checks is:

```text
SLICE3_BASE = c4f2e69
```

The Codex planning commit containing this prompt may sit after that hash; it
changes collaboration docs only. Record the actual starting `HEAD` before
editing. Do not amend, reset, rebase, or rewrite history.

## Objective

Complete M1.6 slice 3: accurate NumPy-style public documentation for the
remaining **tracked** release surface (drivers, volume motion, MPI/DAFoam,
RBF, weighting, and plotting), plus one CI doc-lint step over exactly those
modules.

This is documentation-only in Python. Read implementations and tests before
describing behavior. A mechanically complete but semantically invented
contract is a failed turn.

## Literal 21-path allowlist

Only these paths may change:

1. `bsm3/__init__.py`
2. `bsm3/component_parameters.py`
3. `bsm3/core/__init__.py`
4. `bsm3/core/boundary_surface_movement/__init__.py`
5. `bsm3/core/boundary_surface_movement/cfd_mesh_dafoam_analysis.py`
6. `bsm3/core/boundary_surface_movement/cfd_mesh_movement_test.py`
7. `bsm3/core/boundary_surface_movement/dafoam_csdl.py`
8. `bsm3/core/boundary_surface_movement/e175_derivative_ladder.py`
9. `bsm3/core/boundary_surface_movement/forward_only_fd_checker.py`
10. `bsm3/core/boundary_surface_movement/geometry_volume_backend.py`
11. `bsm3/core/boundary_surface_movement/geometry_volume_mpi.py`
12. `bsm3/core/boundary_surface_movement/geometry_volume_operation.py`
13. `bsm3/core/boundary_surface_movement/rbf.py`
14. `bsm3/core/boundary_surface_movement/run_dafoam_gmsh.py`
15. `bsm3/core/boundary_surface_movement/volume_mesh_motion.py`
16. `bsm3/core/weighting_functions.py`
17. `bsm3/plotting.py`
18. `.github/workflows/actions.yml`
19. `docs/overhaul/PLAN.md`
20. `docs/overhaul/LOG.md`
21. `docs/overhaul/CODEX_NEXT.md`

Every other path is prohibited. Preserve the existing dirty tree and all
untracked artifacts. Stage literal files only; never stage a directory.

In particular, **do not touch or commit** the untracked
`bsm3/core/boundary_surface_movement/e175_panel_opt.py`. Turn 5 deliberately
deferred adopting that VortexAD root until M1.7 gives it an end-to-end test.
Documentation is not a reason to adopt an otherwise untracked production
module. The two deferred mesh-generation candidates remain equally out of
scope.

## Permitted changes by path class

- The 17 Python paths: docstrings and comments only.
- `.github/workflows/actions.yml`: add one doc-lint step listing exactly the 17
  Python paths. Do not alter existing steps, dependencies, triggers, or test
  commands.
- The three collaboration docs: record the work, measurements, deviations,
  and handoff.

In Python, do **not** change imports, annotations, decorators, signatures,
defaults, assignments, constants, branches, expressions, executable strings,
exports, or formatting outside docstrings/comments. Do not rename a symbol,
fix a typo in an API, introduce a type, remove dead payload, or refactor.

## Measured pre-edit inventory

The 17 Python paths total **8,763 LOC**. Under the established audit convention
(public top-level classes/functions and public methods, where the name does
not start with `_`):

- module docstrings: **15/17**; missing in `bsm3/__init__.py` and
  `bsm3/plotting.py`;
- public-definition docstrings: **108/167**; **59 missing**;
- public callables: **132** with **293** signature parameters;
- NumPy `Parameters` coverage: **293 missing / 0 extra**;
- dataclasses: **22** with **148** locally declared public fields;
- NumPy `Attributes` coverage: **148 missing / 0 extra**.

These counts deliberately exclude the untracked `e175_panel_opt.py`.

The missing public-definition docstrings are:

| Path | Missing definitions at the baseline |
| --- | --- |
| `cfd_mesh_dafoam_analysis.py` | `OpenFOAMCaseConfig` (266), `E175DAFoamResult` (339), `create_dafoam_backend` (404), `main` (649) |
| `cfd_mesh_movement_test.py` | `run_deformation_test` (221) |
| `dafoam_csdl.py` | `DAFoamAnalysisOperation.evaluate` (77), `.compute` (102), `DAFoamAnalysisVJP.evaluate` (132), `.compute` (146), `PYDAFoamBackend.run_primal` (383), `.compute_vjp` (499) |
| `e175_derivative_ladder.py` | `level0_forward_repetition` (231), `level1_mesh_motion_forward` (275), `level2_mesh_motion_vjp` (303), `level3_dafoam_volume_vjp` (364), `level4_chain_rule` (439), `level5_end_to_end` (502), `main` (689) |
| `forward_only_fd_checker.py` | `DerivativeComparison` (238) |
| `geometry_volume_backend.py` | `CSDLRecorderBackend.design_variable_names` (162), `.output_shape` (167), `.design_variable_shapes` (172), `.forward` (210), `.compute_vjp` (229) |
| `geometry_volume_mpi.py` | `SerialComm.bcast` (53), `.gather` (56), `.scatter` (59), `.allgather` (64), `.Bcast` (68), `.Reduce` (71), `.Allreduce` (74), `.Barrier` (77), `comm_rank` (98), `comm_size` (102), `is_root` (106) |
| `geometry_volume_operation.py` | `GeometryVolumeOperation.evaluate` (98), `.compute` (121), `GeometryVolumeVJP.evaluate` (197), `.compute` (208) |
| `rbf.py` | `DisplacementSurrogate.evaluate` (457) |
| `run_dafoam_gmsh.py` | `rank0_print` (140), `csv_names` (145), `validate_case_template` (190), `backup_existing_polymesh` (302), `validate_patch_names` (359), `validate_reused_mesh` (439), `make_parser` (677), `main` (856) |
| `volume_mesh_motion.py` | `TetraVolumeMesh.is_hybrid` (86), `.aircraft_triangles` (90), `.aircraft_quadrangles` (96), `.aircraft_nodes` (102), `.symmetry_nodes` (130), `.fixed_outer_nodes` (136), `.boundary_nodes` (151), `VolumeQualityReport.as_dict` (307), `LoadStepRecord.as_dict` (325), `LoadSteppedVolumeResult` (337), `write_comparison_summary` (1068) |

Line numbers are baseline navigation aids, not post-edit assertions.

## Documentation contract

Bring the slice to **17/17 module docstrings and 167/167 public-definition
docstrings**. Every public callable must have a genuine NumPy-style docstring:

- imperative/summary first line with no leading blank line;
- `Parameters` entries for every and only every signature parameter other
  than `self`/`cls`, including `*items`, `**additional_inputs`, and keyword-only
  parameters under their source names;
- `Returns`, `Yields`, `Raises`, `Warns`, `Notes`, and `See Also` only where
  truthful and useful;
- exact shapes, units, coordinate ordering, key sets, ownership, mutability,
  side effects, optional dependency behavior, and failure conditions when the
  body establishes them;
- no invented ordering, convergence, cost, monotonicity, differentiability,
  or support guarantees.

Document all **148 locally declared dataclass fields** in NumPy `Attributes`
sections, with zero missing and zero extra field names. Inherited fields need
not be duplicated in subclass `Attributes` sections; explain inheritance in
prose where useful. Properties need `Returns` sections that match the actual
array/boolean/container returned.

Do not merely add the 59 absent strings. Existing one-line and prose-only
docstrings in this slice are incomplete: all 132 callable contracts and all 22
dataclass contracts are in scope.

## Semantic points that must be established from code

### Generic boundary versus aircraft drivers

Describe `cfd_mesh_movement_test.py`, `cfd_mesh_dafoam_analysis.py`,
`e175_derivative_ladder.py`, and `run_dafoam_gmsh.py` as concrete E175 or
OpenFOAM/DAFoam drivers/adapters. Do not imply that they define the generic
geometry contract. Preserve the already documented generic boundary:
externally produced, topology-compatible LFS/BSM3 coefficient arrays enter
through `GeometryModel.add_component`; built-in wing/body helpers are optional
conveniences.

`run_dafoam_gmsh.py` is intentionally a CLI driver and may be documented as
one. Do not confuse it with the no-CLI user example accepted in M1.7a.

### CSDL custom operations and return containers

Read each `evaluate` and `compute` body. The handoff checklist must explicitly
record these container/side-effect contracts:

- `DAFoamAnalysisOperation.evaluate` returns a dictionary keyed by configured
  aerodynamic function name; `compute` mutates `outputs` and returns `None`.
- `DAFoamAnalysisVJP.evaluate` returns a dictionary keyed by primal input name;
  `compute` mutates `outputs` and returns `None`.
- `GeometryVolumeOperation.evaluate` returns one CSDL volume-coordinate
  variable; `compute` mutates `outputs` and returns `None`.
- `GeometryVolumeVJP.evaluate` returns a dictionary keyed by design-variable
  name; `compute` mutates `outputs` and returns `None`.
- backend primal and VJP mappings must document their actual key sets and
  global/local coordinate shapes without inventing tuple ordering.

### MPI ownership and collective safety

`SerialComm` is a one-rank test/fallback communicator implementing only this
module's subset, not a general MPI replacement. Document identity/copy versus
in-place behavior of its object and buffer collectives from their bodies.

For the real helpers, distinguish:

- root-only execution and symmetric exception propagation in `run_on_root`;
- typed `Bcast`/`Reduce`/`Allreduce` array movement versus pickled object
  collectives;
- forward gather `global[local_to_global]` and reverse scatter-add, including
  duplicated processor-boundary points;
- `ownership="root"` versus `ownership="replicated"`, and what non-root ranks
  receive;
- collective participation requirements and synchronous validation failures.

Do not claim that import-only or mocked tests exercise a real MPI launch.

### DAFoam boundary

Document lazy optional imports, local case-directory requirements, global Gmsh
versus local OpenFOAM coordinates, the coordinate matching tolerance, primal
state/cache invalidation, deterministic-baseline behavior, function/input key
contracts, and the discrete-adjoint VJP only where the implementation proves
them. Do not claim live DAFoam/OpenFOAM execution is covered by this turn.

### Forward-only derivative checker and ladder

Document the deliberate forward-first order, centered-FD step/scaling
conventions, output/design-variable mapping keys, relative-error calculation,
degree/radian diagnostic, and each ladder level's actual boundary. Do not turn
diagnostics into guarantees. Environment variables and local files are caller
requirements, not repository assets.

### Volume motion, RBF, and plotting

- Keep surface motion and volume motion distinct. The retained surface method
  is graph Laplacian plus N-gon regularization; this module separately exposes
  graph and linear-elasticity **volume** propagators.
- Document hybrid tetrahedron/pyramid decomposition, assembly versus quality
  cell sets, physical-patch node sets, reference-matrix differentiable paths,
  forward-only load stepping, and quality metric meanings from the body.
- For RBF data/training/evaluation, document coefficient/vertex shapes,
  component ownership, seam behavior, and fit-mode effects only as implemented.
- `plotting.py` lazily requires PyVista/mesh readers. Document returned plotting
  element lists and `show` side effects. `node_colore` is a misspelled legacy
  alias that must be documented, not removed or renamed.
- `bsm3/__init__.py` conditionally exposes optional projection helpers; its
  documentation must not promise those names exist when their imports fail.

## CI change

Add one step named exactly:

```text
Numpydoc checks for drivers, volume motion, and MPI
```

It must run `python -m ruff check --select D` over exactly the 17 Python paths
in the literal allowlist, each named explicitly. Do not collapse directories
or alter the three existing documentation steps.

Ruff is known to be absent from `central_geom`. Attempt the exact local command
once, do not install anything, and record the limitation. CI's pinned
`ruff==0.9.10` remains authoritative. If static reading shows an obvious Ruff-D
violation, correct the docstring rather than assuming CI will forgive it.

## Mechanical gates

Before editing, save:

```bash
git rev-parse HEAD
git status --short
```

After editing, prove all of the following:

1. The changed-path set from `c4f2e69` is a subset of the literal 21 paths.
2. Every non-allowlisted dirty/untracked path remains untouched.
3. Stripping docstrings from both sides gives identical ASTs for all 17 Python
   files, comparing both working-tree files and the committed source-doc blob
   against `c4f2e69`.
4. Module/definition coverage is **17/17 and 167/167**.
5. The signature audit reports **132 public callables, 293 parameters, 0
   missing, 0 extra**.
6. The dataclass audit reports **22 dataclasses, 148 fields, 0 missing, 0
   extra** in `Attributes` sections.
7. The four custom-operation return containers and four `compute -> None`
   callback contracts above match their bodies.
8. Workflow YAML parses and the new step lists exactly the 17 paths once each.
9. `git diff --check` is clean over the 21 paths.

Use an AST docstring stripper, not line comparison, for item 3. The parameter
and dataclass-field audits must be embedded verbatim in the handoff checklist
so Codex can extract and reproduce them from a clean directory. A grep is not
a substitute for semantic review.

## Numerical regression gates

Run exactly:

```bash
conda run -n central_geom python -m pytest -q \
  tests/test_dafoam_csdl.py \
  tests/test_geometry_volume_mpi.py \
  tests/test_volume_mesh_motion.py \
  tests/test_preprocessing_plotting.py \
  tests/test_e175_driver_configuration.py

conda run -n central_geom python -m pytest -q \
  tests/test_derivative_gate.py \
  tests/test_ngon_affine_operator.py \
  tests/test_ngon_affine_load_step.py
```

Pre-edit baselines independently measured by Codex are **89 passed** (30
warnings) and **6 passed** (11 warnings). No live DAFoam, OpenFOAM, real-MPI,
VortexAD, E175 integration, or clean-clone run is required for a doc-only
slice whose executable AST is identical.

## Commit structure

Make exactly two new commits after the Codex planning commit:

1. One implementation commit containing only changed files among the 17
   Python paths and `.github/workflows/actions.yml`.
2. One handoff-doc commit containing only `PLAN.md`, `LOG.md`, and
   `CODEX_NEXT.md`.

Stage every file literally. Do not stage a directory, `bsm3/`, or `docs/`.
Do not use amend/reset/rebase.

## Stop rule

Stop and report without widening scope if:

- truthful documentation requires a behavioral/signature/type/export change;
- a dependency outside the allowlist must change;
- the measured inventories cannot be reproduced under the stated convention;
- a numerical regression appears;
- or the existing dirty tree prevents isolating the change.

The stop rule is mandatory and is not a planning failure on your part. Do not
silently absorb an allowlist or baseline defect.

## Definition of done and handoff

Update `PLAN.md` and append a concise Turn-48 entry to `LOG.md`. Replace this
file with a Codex review checklist containing:

- exact two commit hashes and base;
- exact changed paths;
- before/after coverage, parameter, and dataclass-field counts;
- the reproducible AST/signature/field/workflow audit commands;
- the explicit custom-operation return-container table;
- exact test/lint/diff results;
- semantic findings and every deviation, prominently;
- confirmation that `e175_panel_opt.py` and all other unrelated artifacts
  remain untouched;
- a clear statement that M1.6 slice 3 is ready for Codex review and is **not
  accepted by the implementer**.

Do not mark M1.6 complete. Codex accepts or rejects the slice after review.
