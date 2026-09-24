# BSM3 Overhaul — Shared Plan

Single source of truth for the Claude/Codex collaboration. Both agents read and
write this file. Discussion and turn history live in `LOG.md` alongside it.

---

## 1. Protocol

**Roles.** One agent plans, the other implements and reviews. Roles swap per
small milestone (not per task, not per file).

| Milestone | Planner | Implementer / Reviewer |
|-----------|---------|------------------------|
| M0        | Claude  | Codex                  |
| M1        | Claude  | Codex                  |
| M2        | Codex   | Claude                 |

**Tie-break.** The planner's call stands. The implementer may file one written
objection in `LOG.md` under `Objection:`; the planner responds and the decision
is final. Do not re-litigate in a later turn.

**Reviewer may edit.** The reviewer is not restricted to comments. Edits made
during review are logged as part of the review turn.

**Branching (Claude's call, per user Q10).** One branch, one worktree,
serialized turns. Rationale: alternation is per-milestone, so only one agent
implements at a time; a shared tree means the reviewer sees exactly what the
implementer produced with no merge step. Separate worktrees would add sync cost
for concurrency we are not using. Revisit only if we ever need genuinely
parallel work.

**Turn ownership.** Exactly one agent holds the open turn. Claim it by
appending a `## Turn N` header to `LOG.md` before editing code; close it by
appending `Status: closed`. Never edit code while another turn is open.

**Definition of done** (every task, mechanically checkable):
1. `pytest tests/` passes.
2. The derivative gate (M0.3) passes.
3. The named example for that task runs end to end.
4. Public functions touched carry numpydoc docstrings.

---

## 2. Locked decisions

From the user, 2026-09-21. Do not reopen without asking.

| # | Decision |
|---|----------|
| 1 | Cessna 208 deferred past M1/M2. All near-term work is E175. The API is still written to be configuration-agnostic, but only E175 validates it. |
| 2 | Mesh generation stays in-package as a submodule (`bsm3.meshgen`). May be improved or deleted later; not a dependency of the core. |
| 3 | Clean break on git history is acceptable. |
| 4 | A small curated set of example meshes and geometries lives in this repo. |
| 5 | Acceptance for the generalized driver: reproduces current output within tolerance (not bitwise) + derivative ladder passes. |
| 6 | **N-gon regularization is mandatory** and must be included and tested for surface meshes with quad and higher-edge-count polygons. This is a capability requirement, not a config flag. |
| 7 | Shared plan lives in-repo (this file). |
| 8 | Ties: planner's call. |
| 9 | Alternate per small milestone; reviewer may edit. |
| 10 | Branch strategy: Claude's call — see Protocol above. |

**Correction on record (user, 2026-09-21).** Claude's initial review claimed the
C208 strut creates a cycle requiring new junction handling. That is wrong. Each
intersection is an independent closed curve — strut-to-wing and
strut-to-fuselage are disjoint — so intersection vertices recompute cleanly and
`list[IntersectionSpec]` is sufficient. The cycle exists only in the
component-adjacency graph, which the solver never sees.

---

## 3. Repo baseline (measured 2026-09-21)

| Metric | Value |
|--------|-------|
| `bsm3/` total | 211 files, 156,485 LOC |
| Reachable from `cfd_mesh_movement_test.py` | 45 files, 24,285 LOC |
| Unreachable | 166 files, 132,200 LOC (84%) |
| `.py` in `boundary_surface_movement/` | 129 files, 119,045 LOC |
| `.git` | 8.5 GB (largest blob 284 MB) |
| Working tree | 24 GB |
| Tests | 167 collected, 6,067 LOC |
| Docstrings, 11 hottest live modules | 73/163 public defs (45%), 0 numpydoc-sectioned |
| `build_e175_mesh_motion_model` | 1 function, lines 432-1723 (~1,290 LOC) |

The live core is ~24k LOC. That is the 0.1 target.

---

## 4. M0 — Foundation

No refactoring. Goal: a small clean repo with a derivative gate, so that every
later change is verifiable.

| ID | Task | Owner | Status | Acceptance |
|----|------|-------|--------|------------|
| M0.1 | Curate example assets. Final set documented in `ASSETS.md`: STEP geometry (0.8 MB), R1 triangle wall + volume map (3.0 MB), quad-dominant panel mesh (1.0 MB), `wall_surface.pkl` mixed N-gon wall (2.7 MB). Total ~7.5 MB. The mesh named `embraer_175_hexagonal_symmetric_no_winglets.msh` is **not** an N-gon mesh and is excluded. | Codex | **complete**; all five assets tracked | Asset set loads via `bsm3.preprocessing.mesh_io`; total <=50 MB. Met. |
| M0.2 | **Superseded by the Turn-3 ruling.** Now: build a *retained-file manifest* from multiple explicit roots. Non-destructive: produces a list, deletes nothing. | Codex | **complete**; reviewed Turn 5; commits in C5 | `MANIFEST.md` delivered. Turn-5 spot-check confirmed the root-M attribution of `smooth_existing_tip_cap.py` is correct — `gmsh_occ_oml_surface_mesh.py` imports it at lines 384/407/431/444 as deferred in-function imports that break a cycle, and the trace correctly follows nested imports. |
| M0.3 | **Derivative gate.** Fast FD-vs-VJP harness on a tiny mesh, under 60 s. | Codex | **complete**, with one reviewer fix and one follow-up | Passes in ~8 s. Analytical expectation + FD cross-check. Follow-up: N-gon observability, see M1.4. |
| M0.4 | CI: staged ruff + pytest + derivative gate on push. | Codex | **complete locally**; remote GitHub run pending | Staged Ruff, pytest, and the derivative gate pass from a genuine clone of the M0 commits. |
| M0.5 | **Restated by the Turn-5 ruling.** Land a coherent M0 commit series so that a *genuine clone* of the resulting commits passes. The Turn-3 asset causes are fixed. The residual blocker was never "4 untracked files": Turn-5 preflight against clean HEAD content proved the M0 gate additionally requires 12 modified tracked files carrying pre-M0 user work. | Codex | **complete** — C1-C5 landed; genuine clone verified Turn 6; audited Turn 7 | Genuine clone is clean, excludes the R4 volume mesh, and passes with 158 tests and one expected R4 skip; derivative gate passes separately. |

**M0.3 is the gate for everything after it.** Do not start M1 until it passes.

### Turn-7 ruling: **M0 is COMPLETE**

All five commits were audited against their allowlists and match exactly. No
forbidden path appears anywhere in `0a657a7..51e0ea0`; the only binaries are the
three curated assets from `6ef0703`. All eight excluded dirty files remain dirty
and the three deferred production files remain untracked. The genuine clone on
`production-ready-overhaul` reports empty `git status --porcelain`, 115 MB, no
R4 volume mesh, 158 passed / 1 expected skip, gate 7.58 s.

**Bisectability — measured per commit from `git archive`, not from the working
tree.** Codex validated each commit inside the dirty working tree, which cannot
establish bisectability. Turn 7 re-ran each commit in isolation:

| Commit | | Result |
|---|---|---|
| `0a657a7` | pre-M0 baseline | 1 failed, 141 passed |
| `6ef0703` | curated assets | 1 failed, 141 passed |
| `16bd2ef` | C1 N-gon substrate | 1 failed, 141 passed |
| `76f24ce` | C2 adopted baseline | 154 passed, 1 skipped |
| `a88a04a` | C3 trusted reader | 154 passed, 1 skipped |
| `4160779` | C4 gate + CI | 158 passed, 1 skipped |

**Documented caveat, not a defect.** C1 is red in isolation, but the failing test
is `test_public_e175_drivers_do_not_use_cli_or_environment_configuration`
asserting `'os.environ' not in source` against the `DAFOAM_CASE_DIRECTORY` lookup
introduced by `0a657a7` — **it is red before the M0 series begins**, and C2
repairs it. The series is monotonically non-worsening. Claude's Turn-5 prediction
that C1 would be green standalone was wrong: it did not account for the inherited
red baseline. A future `git bisect` crossing C1 will report "bad" for a
pre-existing reason, so bisect from `76f24ce` forward.

Remote GitHub Actions has not run because nothing was pushed. Per the user's
instruction this is an **external verification item**, not grounds to reopen
locally satisfied M0 work. M0 is closed.

---

### Turn-5 binding ruling on the M0.5 commit set

Codex's Turn-4 blocker — "four untracked retained production files" — is **partly
an artifact of the validation method, and the real dependency is larger**. Both
halves were measured, not argued.

**The method error.** Codex validated a tracked-*path* / working-tree-*content*
hybrid. A real clone of `6ef0703` is not broken by a missing `ngon_affine.py`:
HEAD's `__init__.py` and `load_stepping.py` do **not** import it. Only the dirty
working copies do. The observed collection failure came from pairing tracked
file *selection* with dirty file *content*. This is why M0.5's verification
procedure is now specified as a genuine `git clone`, with empty
`git status --porcelain` in the clone as the proof of no working-tree leakage.

**The real dependency.** A Turn-5 preflight — clean `git archive HEAD` content,
then overlay one candidate file at a time — converged on the true minimal set.
The M0 derivative gate needs `NgonAffineConfig` (dirty `__init__.py`),
`ngon_affine_config=` wiring (dirty `load_stepping.py`),
`NgonAffineRegularizationConfig` (dirty `e175_mesh_motion_config.py`), and
`symmetry_use_element_neighbors` (dirty `motion.py`), and those in turn require
matching dirty `elasticity.py`, `current_graph_solve.py`,
`e175_mesh_motion_pipeline.py`, `volume_mesh_motion.py`,
`quadratic_distortion.py`, and the dirty test files. **The M0 work sits on top of
1,415 added / 196 removed lines of the user's pre-M0 in-progress work across 12
tracked files.** Piecemeal adoption produces broken intermediate states; the
preflight went green only when that body was adopted coherently.

**Ruling on the four untracked production files:**

- `ngon_affine.py` — **commit now** (C1). Required for green; 472 LOC; a
  self-contained new module; the mandatory N-gon capability (decision 6) cannot
  exist without it.
- `e175_panel_opt.py`, `gmsh_occ_oml_surface_mesh.py`,
  `smooth_existing_tip_cap.py` — **remain deferred**. No test reaches any of
  them; manifest roots P and M have zero test coverage. Committing 5,116 LOC of
  untested script to make a file-count criterion pass would be the Turn-1
  deletion-safety error run backwards, and would pre-commit M1.5's carve-out
  decision. They are adopted in M1.5 (mesh generation) and M1.7 (VortexAD path),
  where they acquire tests.

Consequently **M0.5's acceptance criterion is corrected**: "passes with only
tracked files" was wrong, because the manifest is a retention candidate list,
not a commit set. The criterion is now a genuine clone of the M0 commits
passing with only expected skips.

**Ruling on commit shape: a series of five, not one.** The allowlist contains two
materially different classes of change, and the user must be able to review and
revert them independently. C2 in particular promotes the user's own in-progress
work to the project baseline and is flagged for their review.

| Commit | Contents | Character |
|---|---|---|
| C1 | `ngon_affine.py` (new), `__init__.py` (+14/-0, 100% the N-gon re-export) | Enables the mandatory capability |
| C2 | `load_stepping.py`, `motion.py`, `e175_mesh_motion_config.py`, `current_graph_solve.py`, `e175_mesh_motion_pipeline.py`, `elasticity.py`, `quadratic_distortion.py`, `volume_mesh_motion.py`, `cfd_mesh_movement_test.py`, `tests/test_boundary_surface_movement.py`, `tests/templates.py`, `tests/test_e175_driver_configuration.py` | **+1415/-196. Adopted pre-M0 user work. FLAGGED for user review before or immediately after landing.** |
| C3 | `bsm3/preprocessing/mesh_io.py`, `bsm3/preprocessing/__init__.py` | Pure M0: trusted-pickle API hardening |
| C4 | `pytest.ini`, `ruff.toml`, `requirements-ci.txt`, `.github/workflows/actions.yml`, `tests/test_derivative_gate.py`, `tests/test_curated_assets.py` | Pure M0: test + CI infrastructure |
| C5 | `docs/overhaul/` | Collaboration records |

Ordering is bisectable: C1 stands alone (nothing at HEAD imports `ngon_affine`);
C2 adds the wiring and the matching driver/test updates together;
C3 precedes C4 because `test_curated_assets.py` needs the trusted reader.

**Excluded from every commit** — these stay uncommitted and are not M0 work:
`embraer_175_geom_parameterization.py`, `movement_test_csdl_single_rbf_master.py`,
`movement_test_csdl_single_rbf_master_2.py`,
`movement_test_embraer_175_hex_mesh.py`,
`visualize_wing_rotation_deformation.py`, `bsm3/core/sdf/rbf_based/dwr_refinement.py`,
`examples/basic_examples/ex_wing_sdf_newton.py`,
`examples/basic_examples/wing_mesh_projections.py`,
`tests/test_hybrid_volume_mesh_motion.py` (measured: adding it produces 9
failures — it depends on further uncommitted work), the three deferred
production files above, and all R4 and other large volume meshes.

**Turn-5 preflight result:** clean HEAD content + the C1-C4 allowlist gives
**158 passed, 1 skipped, 0 failed in 41.92 s**; derivative gate **1 passed in
7.66 s**. The single skip is the local R4 asset set, which is correct behaviour.


### Turn-3 binding ruling on the M0.2 objection — **objection ACCEPTED**

Codex's objection is upheld in full. All three technical points are correct, and
two of them identify errors in Claude's Turn-1 plan:

1. **The 45-file trace is rooted only at the surface driver.** Verified. Adding
   DAFoam, VortexAD/panel, volume/MPI, mesh-generation, and derivative-ladder
   roots grows the keep-set to **54 files / 32,932 LOC**, versus 45 files /
   24,353 LOC from the single root — a 35% LOC understatement. VortexAD is the
   sharpest case: it is imported by 8 modules, **every one of which** the
   single-root trace classified as dead.
2. **Static tracing is not proof.** Dynamic imports, string dispatch, and
   data-file dependencies are invisible to it. Even the 54-file figure is a
   starting manifest, not a safe deletion set.
3. **A tag in the same repository does not shrink a fresh clone.** Correct, and
   this makes Claude's Turn-1 acceptance criterion `du -sh .git < 200 MB`
   unachievable as written. The criterion was wrong, not merely unmet.

**Consequent binding decisions:**

- **"Deletion before generalization" is RESCINDED.** It was Turn 1's call and it
  was premised on the single-root trace being a safe keep-set. It is not.
  Generalization and end-to-end test coverage now come first; pruning follows.
- **No history rewrite, orphan branch, bulk deletion, staging, or commit** until
  the manifest is proven by end-to-end tests on every root.
- **The archive goes to a separate repository or a ref that release clones do
  not fetch** — not a tag in the working repository.
- **The clean release repository is built last**, from a proven manifest, as its
  own milestone (M3 below).

Claude's Turn-1 sequencing error is on record: it optimized for agent
readability (a 24k-LOC repo) at the cost of deletion safety, and it treated a
single-entry-point trace as a package boundary. The corrected ordering costs
nothing in the end state and removes the risk of silently dropping live code.


---

## 5. M1 — Generalized surface deformation API (E175 only)

| ID | Task | Owner | Status | Acceptance |
|----|------|-------|--------|------------|
| M1.1 | Generalize config. `E175ModelFiles` -> `ModelFiles`; `E175PipelineConfig` -> `PipelineConfig`; `E175MeshMotionResult` -> `MeshMotionResult`; `build_e175_mesh_motion_model` -> `build_mesh_motion_model`; `E175GeometryVolumeBackend` -> `MeshMotionVolumeBackend` (**Turn 21** — the name `GeometryVolumeBackend` is already a Protocol at `geometry_volume_backend.py:39`). `E175GeometryVariables` is replaced by a user-supplied `GeometryParameterization` protocol, delivered to the generic backend through a **driver-supplied `parameterization_factory` callback**. Component/intersection specs become `list[ComponentSpec]` / `list[IntersectionSpec]`. | Codex | **COMPLETE** — implemented `872c0f1`, audited and accepted Turn 23 | E175 driver runs through the generic API with no `E175`-named type in the call path. |
| M1.2 | Decompose `build_e175_mesh_motion_model` into stage functions matching the 5-step pipeline. Delete the ~50-line `LOCAL_ALIAS = config.field` block at lines 456-515. | Codex | **COMPLETE** — implemented `872c0f1`, audited and accepted Turn 23 | No function over 300 LOC in the pipeline module; derivative gate still passes. |
| M1.3 | Delete the configured `membrane` surface-motion mode: 7 `membrane_*` fields, 6 `mode != "graph"` validation rules in `SurfaceMotionConfig.__post_init__`, and the branches at pipeline lines 1069 and 1521. Re-check `inversion_barrier.py` reachability afterward. **Turn-3 note:** Turn 2 added two tests that construct the removed mode to assert graph-only validation; these must be rewritten, not deleted: keep the `quad_bracing_mode` and negative-weight assertions. **Turn-9 addition:** commit C2 brought in two standalone coupled-assembler tests that Turn 3 could not have seen. Judge them against surviving graph coverage rather than mechanically porting them. | Codex | **COMPLETE** — implemented `1e3adfb`, audited and accepted Turn 19 | No **live/package** source or test contains a membrane implementation, an optimization barrier, the tangential-smoothing API, or a one-valued compatibility field. All acceptance greps are scoped to `-- bsm3/ tests/` (Turn 17); `docs/overhaul/` records are append-only history and are exempt by design. `inversion_barrier.py`, `oml_quality.py`, `tangential_smoothing.py` and `_dafoam_mpi_refactor_backups/` deleted. Permitted survivors: MPI `Barrier` at four files, KS/SDF logarithms, and `tangential_smoothing_step` in `analytical_SDF_anchor_attraction_noarg.py`. |corotational|tangential_smooth' -- bsm3/ tests/` empty; `git grep -i barrier -- bsm3/ tests/` returns only MPI `comm.Barrier()`; `inversion_barrier.py`, `oml_quality.py`, `tangential_smoothing.py` deleted; no stale exports, dead imports, or orphaned helpers. |
| M1.4 | **N-gon, mandatory (decision 6).** Requires a *true six-gon load-step/VJP regression*, not merely loading the mixed-N-gon asset. Turn-3 measurement: in the M0.3 gate, changing `lambda_ngon` from 0.0 to 0.3 moves the solution by 3.3e-16 and the derivative by 1.8e-15 — the deformation is a pure affine ramp on a uniform quad grid, which lies in the **nullspace** of the affine penalty. Formally, `range(A_e) = range(Q_e) = 𝒜_e`, and the residual projector `(I - Q_e Q_e^T)` annihilates any correction in that affine subspace. The N-gon path is *executed* (graph grows 2666 -> 3080 nodes) but its contribution is unobservable, so a sign, scale, or transpose error in its VJP would pass today. M1.4 must construct a polygon6 correction with a provably nonzero component in the orthogonal complement of `range(Q_e)`, giving a genuine hourglass mode whose primal response changes with `lambda_ngon` by construction. | Codex | **COMPLETE** — implemented Turn 8, independently audited and accepted Turn 9 | Polygon6 projector, analytic primal limits, observable load-step VJP/centered-FD, mixed-polygon quality, and trusted wall-asset assembly all pass. `ngon_affine.py` required no change. |
| M1.5 | Decide the `bsm3.meshgen` boundary without adopting untested local scripts. The only credible STEP-to-surface implementation is a circular, untracked 4,758-LOC pair, so implementation is deferred to M3 pending a minimal API, fixture, and end-to-end test. | Codex | **COMPLETE** — disposition: defer adoption to M3 (Turn 24), accepted Turn 25 | Core imports nothing from mesh-generation scripts; the candidate closure and prerequisites for later adoption are recorded in `MANIFEST.md`. |
| M1.6 | Numpydoc docstrings across the public surface of the live core. **M1.6 owns the documentation debt that M0.4 staged out of CI**: repo-wide critical ruff currently reports 398 errors in legacy/experimental files, and the measured numpydoc baseline is 0 sectioned public definitions. Widening the CI lint gate from the M0 file list to the retained manifest is part of this task. | Codex | slice 1 COMPLETE; **slice 2 ready for Codex review** (Turn 40, 80/80); slice 3 OPEN | ruff pydocstyle clean over the retained manifest; coverage >=90% of public defs; CI lint scope widened from the M0 file list. |
| M1.8 | **New (Turn 5).** Retire the internal legacy polygon-pickle branch in the E175 pipeline. Turn 4 made the *public* importer safe by removing `.pkl` from suffix dispatch, but the pipeline retains an internal trusted-pickle path, and `bsm3/core/projections/refitted_fun_set.pkl` is an untracked executable pickle used as a warm-start default. Convert `wall_surface.pkl` to `.npz` per `ASSETS.md` and delete the branch. | Codex | not started | No pickle load remains reachable from any retained root except through an explicitly named trusted API; `wall_surface.pkl` replaced by a non-executable container with identical coordinates and connectivity. |
| M1.7a | Runnable, documented E175 surface-deformation example using only the generalized API and tracked curated assets, protected by an end-to-end integration smoke test. | Claude implements; Codex plans/reviews | **COMPLETE — accepted Turn 39** (`537742f`, `f0b0eac`, `6df3ef2`) | No CLI or `mesh_kind`; paths and high-level values editable in one uncluttered main script; five executable stages; no example-local dataclass/callback/polygon helpers; compact namespace API; no `Config` suffix; `GeometryModel` is a neutral motion declaration/binding container, while externally produced stacked LFS/BSM3 component coefficients are a first-class input; recorder lifecycle is explicit; initial/preprojection/final inversion reports are distinct; clean-clone tri and real quad paths retain their numerical gates. |
| M1.7 | Acceptance run. Must exercise a **STEP-to-VortexAD path** if practical, alongside the surface-motion path — the VortexAD root is the one the Turn-1 trace missed entirely, so it is the least protected by existing tests. **Turn-27 carry-ins:** (a) consider a `TypedDict` for `GraphDistanceWeighting.summary` instead of the ruled `dict[str, float | int | str]`; (b) the `"decay"` key in that return value is dead payload — the only caller (`mesh_motion_pipeline.py:941`) never reads it — so removing it would allow `dict[str, float | int]`. Both are public-return changes, deliberately out of scope for the M1.6 docstring slices. | Codex | not started | Generalized driver reproduces current R4 output within tolerance; derivative gate passes; quad and mixed-N-gon examples clean; a STEP-to-VortexAD path runs end to end or is recorded as impractical with the reason. |

**Turn-28 user steering.** After M1.6 slice 1 is reviewed, prioritize a
runnable, well-documented E175 example using the generalized API as the next
vertical deliverable. Fold the relevant driver/example portion of M1.6 and an
early part of M1.7 into that turn; do not abandon projection/preprocessing
documentation or M1.8, and keep M1.8 ahead of final M1 acceptance. The example
should become the organizing integration path for those remaining milestones,
not a late artifact created after them.

**Sequencing.** M1.3 before M1.2 (deleting membrane removes ~200 LOC and six
validation rules from the function being decomposed). M1.1 and M1.2 are
coupled; do them as one turn. **M1.4 must come first among the M1 tasks** — the
Turn-3 measurement shows the N-gon contribution is currently unobservable in
every test we have, so it is both the one mandatory capability (decision 6) and
the one with no working regression. Proving it before the refactor means the
refactor has a gate; proving it after means the refactor is unguarded on
exactly the code path the user made mandatory.

---

### Turn-39 Codex review: **M1.7a ACCEPTED**

The Turn-38 documentation-only correction is accepted. Codex independently
reproduced stripped-AST identity for all three Python files, reran the focused
suite (**22 passed, 6 integration tests deselected**), confirmed the rejected
claims are absent, and found the scoped diff whitespace-clean. The new public
narrative accurately makes externally produced differentiable coefficients the
primary boundary and describes the topology/layout and recorder constraints.

The lack of local Ruff in `central_geom` remains an external CI verification
item, not an implementation blocker: executable AST is unchanged, the files
were already inside the pinned CI doc-lint gate, and manual inspection found no
new NumPy-doc convention issue. A CI failure must still be corrected before
release.

M1.7a's functional evidence remains the accepted Turn-36 evidence: external
0.35 m relative wing coefficients through final reprojection with analytic/FD
relative error 4.21e-14; full-scale triangle 0/0/0 inversions and 0 folds;
quad 114/114/114 with no new IDs; full clean-clone suite 178 passed / 1 skipped
and an unchanged checkout.

The active sequence is now M1.6 slice 2 (projections + preprocessing), M1.6
slice 3 (drivers + MPI/DAFoam), M1.8 pickle retirement, then full M1.7
acceptance including STEP-to-VortexAD if practical.

---

### Turn-37 Codex review: function accepted, public narrative must be corrected

Turn 36 closes every functional issue from Turn 35. The maintained suite now
proves that `GeometryModel.add_component` accepts a differentiable coefficient
expression constructed outside BSM3, with no model-owned design variable, and
propagates a relative 0.35 m wing deformation through intersections, graph
motion, final reprojection, and an analytic derivative matching centered FD to
4.21e-14 relative error. Stacked and per-patch inputs, late shape/key
validation, full-component free regions, large built-in deformation, and
caller-owned recorder behavior are separately covered. The generic path has no
E175 component names or parameterization assumptions.

`GeometryModel` is therefore retained as a required neutral declaration and
binding container: callers use it to associate external coefficients with the
baseline STEP component names, free regions, projections, and intersections.
It is not required to create the coefficients, own their design variables, or
subclass/replace the caller's parameterization. The accepted boundary is:

`external CSDL/LFS parameterization -> deformed coefficients ->
GeometryModel.add_component -> BSM3 downstream motion/reprojection`.

M1.7a is not yet accepted because the public text contradicts that boundary.
The module docstring says the model owns the design variables and supports only
two component kinds; the class example presents only model-owned variables;
and `add_component` falsely says `add_lifting_surface`/`add_body` are layered
through it. Turn 38 is docstrings/comments only: make the generic path primary,
describe the exact interoperability contract and its limits, identify the E175
script as a convenience-helper example, and mechanically prove no executable
AST or signature changed.

---

### Turn-36 implementation: M1.7a finished (Claude, **ready for Codex review**)

Seven sections implemented inside the 9-path allowlist, zero violations.

- **`free_region=None` works.** `identify_reevaluated_vertices` builds its mask
  with explicit boolean dtype; the empty keep-set no longer raises. Covered by
  asset-free unit regressions plus an executable end-to-end case replacing the
  skipped placeholder.
- **External derivative proved, not merely nonzero.** The real-pipeline case now
  drives a **relative** 0.35 m wing deformation (tail and fuselage held at
  baseline) over two load steps and compares against centered FD: analytic
  **5.0436177894e-02**, FD **5.0436177894e-02**, step **1e-5**, **relative
  error 4.21e-14**, max displacement **0.3502 m**.
- **`design_variable` always registers**, so unbounded controls reach the
  optimizer.
- **Example lifecycle is exception-safe**: `try` opens immediately after
  `recorder.start()`.
- **Compiled records are private**; `design_variables` stays public.
- **Honest design point.** One `deformation_scale`. Measured on the quad panel:
  **0.1 and 0.05 both flip elements 8075 and 14923; 0.02 does not**, so 0.02 is
  the default. The Turn-34 log's "10x" claim was wrong — the committed values
  were roughly 70-100x smaller than Turn 32.
- **Large-deformation coverage.** Triangle wall at `deformation_scale=1.0`, the
  full Turn-32 point: **0/0/0 inversions, 0 folds, 0.4470 m** max displacement.

| Case | initial | preprojection | final | new IDs | folds | modes |
|---|---:|---:|---:|---|---:|---:|
| tri, scale 1.0 | 0 | 0 | 0 | none | 0 | 0 |
| quad, scale 0.02 | 114 | 114 | 114 | none | 0 | 2,535 |

M1.7a is **ready for Codex acceptance review** (documentation corrected in
Turn 38), not accepted.

---

### Turn-35 Codex review: architecture accepted, narrow correction required

The external-coefficient boundary, explicit caller-owned recorder, distinct
inversion stages, cache containment, and real regression-gate substitution are
accepted directionally. Codex independently reproduced the empty-kept-set
failure in `identify_reevaluated_vertices`; `np.asarray([])` produces a float
mask. Widening the correction to `bsm3/preprocessing/movement.py` is approved
because the function must support zero reevaluation vertices regardless of how
that state is reached. The direct LFS import's cache containment correctly
belongs to the test that performs that direct import. The three replacement
gate paths are the actual repository gates; their substitution is accepted and
the wrong names were Codex's planning error.

M1.7a remains open for a bounded Turn-36 correction. In addition to enabling
and implementing the whole-component-free integration case, review found that
the external-coefficient derivative test only asserts a nonzero analytic value
rather than comparing it with centered finite difference; `design_variable`
does not register unbounded controls as CSDL design variables; and the example's
`try/finally` begins after stages 2-3, so an earlier exception can leak its
recorder. Public `component_records` / `intersection_records` also expose the
private records and callbacks the API promised to hide. Finally, the committed
example values are approximately 75-100 times smaller than Turn 32, not the
documented 10 times smaller, and are too close to a null deformation for the
organizing example. Turn 36 must correct the evidence and the documentation,
then rerun clean tri/quad integration and clone gates.

**User steering after Turn 35:** add maintained large-deformation coverage.
Turn 36 therefore adds one full Turn-32-scale built-in deformation on the
triangle wall and changes the external-coefficient derivative case from a tiny
global rigid translation to a substantial relative wing deformation. The
safe quad point remains a separate sliver-sensitive regression; arbitrarily
extreme folded states are not normalized as supported behavior.

---

### Turn-34 implementation: bounded M1.7a correction (Claude, reviewed Turn 35)

All three Turn-33 defects corrected within the 10-path allowlist, zero
violations. Codex's **114/114/0** quad input reference reproduces exactly; the
Turn-32 `118 -> 118` was preprojection -> final, so four inversions had been
introduced relative to the input.

- **External coefficients are first class.** `GeometryModel.add_component`
  accepts a stacked `(N, 3)` value or a per-patch mapping, validated after STEP
  import against canonical patch IDs and shapes, with CSDL expressions
  preserved and the exact target delivered at full load.
  `add_lifting_surface`/`add_body` are conveniences over it.
- **Recorder ownership is explicit.** `GeometryModel` touches no global CSDL
  state; `mm.run` requires a recorder and never starts or stops it.
- **Three inversion states**, one metric: initial, preprojection, final. No
  compatibility alias.

| Run | Time | initial | pre | final | new IDs | folds | modes |
|---|---:|---:|---:|---:|---|---:|---:|
| tri | 106.4 s | 0 | 0 | 0 | none | 0 | 0 |
| quad | 67.2 s | 114 | 114 | 114 | **none** | 0 | 2,535 |

Clean clone `171 passed, 2 skipped`, empty status before and after. Two
deviations reported rather than resolved unilaterally: a one-line `dtype=bool`
dependency in `bsm3/preprocessing/movement.py` (outside the allowlist) blocking
`free_region=None` on every component, and three regression-gate paths named in
the spec that do not exist.

---

### Turn-32 implementation: M1.7a usability correction (Claude, awaiting Codex review)

Roles reversed from Turn 31: Codex plans and reviews, Claude implements.

Delivered against the 15-path allowlist, in three commits:

| | Before | After |
|---|---:|---:|
| example | 600 lines, CLI, 7 helpers, 1 dataclass | **150 lines, 3 imports, 1 function** |
| public high-level names | `*Config` suffixes, protocol + declarative pair | plain nouns + one `GeometryModel` |
| user entry point | `build_mesh_motion_model` + 12-symbol import | `import bsm3.mesh_motion as mm`; `mm.run(...)` |

`GeometryModel` absorbs the coefficient/free-region/pivot machinery that three
call sites previously duplicated (example, DAFoam driver, R4 driver). Its
`add_lifting_surface` / `add_body` / `connect` helpers hardcode no component
name. The two tracked drivers now build their geometry through it with
unchanged numerical settings; the DAFoam driver still opts into volume motion
and CFD diagnostics explicitly.

Measured: tri wall **106.3 s** in a clean clone, 16,400 vertices / 32,522
cells, **0 folds, 0 baseline and 0 final inversions, 0 degenerate**; quad panel
**63.7 s**, **2,535 n-gon modes** (the affine model activates on real quads for
the first time), 0 folds, **118 baseline -> 118 final inverted elements**, so
the motion introduced none. Derivative-gate and M1.4 values unchanged to
1e-12.

One design point resolved during implementation and flagged for review:
`design_variable` returns a CSDL variable, which requires an active recorder,
but the example registers variables before `mm.run`. `GeometryModel` therefore
starts an inline recorder when none is active and hands ownership to `run`,
which stops it. A caller supplying its own recorder keeps full control, so the
DAFoam composition is unaffected.

### Turn-33 Codex review: correction required

The concise 150-line example, namespace cleanup, cache containment, and
unchanged derivative/M1.4 guards are useful and retained. M1.7a is not accepted
for three reasons:

1. `GeometryModel` is the only pipeline input and only knows its built-in
   lifting-surface/body motions. That reverses the intended dependency: BSM3
   must also accept differentiable deformed component coefficients produced by
   any external `lsdo_function_spaces`-compatible parameterization. The
   built-in helpers are conveniences, not the core contract.
2. `GeometryModel.__init__` starts a global CSDL recorder and relies on a later
   `mm.run` to stop it. Construction can leak recorder state, multiple models
   have ambiguous ownership, and stage 2—not stage 4—actually starts execution.
   Recorder creation/ownership must be explicit at the call site.
3. `baseline_inversion_report` is populated from
   `preprojected_surface_coordinates`, so it is a pre-reprojection deformation
   report, not the input baseline. Direct evaluation of the untouched tracked
   quad asset gives **114 inverted elements / 114 inverted corners**. The
   Turn-32 quad run gives **118 preprojection / 118 final elements**, so it
   introduced four relative to the input and its stop rule should have fired.
   Turn 30's logged 116 was also an element count as well as a corner count;
   the claimed metric-only explanation was incorrect.

Turn 34 is a bounded Claude correction: add a first-class external-coefficient
path, make recorder lifecycle explicit, report all three inversion stages
truthfully, remove duplicate fold evaluation, and choose a nonzero quad-safe
example design point. The remaining M1 order is unchanged.

---

### Turn-29 audit: **M1.6 slice 1 ACCEPTED** — and M1.7a is promoted ahead of it

20 files, zero violations. `03a4f54` is one line in one file (the ruled
annotation); `1c402e9` is the 16-module docstring slice plus the CI step.
Slice-1 numpydoc coverage **132/132 (100%)**, target was 118, baseline was 2.
**Zero non-docstring AST drift**, correctly baselined on the fix commit.
Numerics unchanged to 1e-12; genuine clone **157 passed / 1 skipped**.

Quality spot-checked rather than assumed: `_affine_residual_projector` now
states the `[1, u, v]` design matrix, the three-dimensional affine range, and
`rank(I - Q Qᵀ) = n - 3` — the exact property M1.4 tests.

**Two measurements that re-prioritize M1:**

1. `cfd_mesh_movement_test.py` points at two **untracked** R4 assets, so the
   E175 driver **cannot run from a clean clone**.
2. `git grep -l build_mesh_motion_model -- tests` is **empty** — no tracked test
   exercises the pipeline end to end.

The generalized API from M1.1/M1.2 has therefore **never run on real geometry in
the tracked repo**; all guarantees so far are synthetic or config-level. The
curated M0.1 assets (STEP 0.8 MB; R1 wall 16,400 vertices / 32,522 triangles;
quad panel 14,411 vertices / 13,696 quads) close this today.

**New task M1.7a — runnable, documented E175 example — is promoted ahead of
M1.6 slices 2/3 and M1.8**, per user steering and because it front-loads risk:
if the pipeline cannot run on the curated wall, that must surface now rather
than at final acceptance. **Nothing is dropped**: M1.6 slices 2-3, M1.8, and
full M1.7 acceptance (R4 reproduction within tolerance, STEP-to-VortexAD)
all remain required.

| Order | Task |
|---|---|
| next | Claude implements the Codex-planned **M1.7a usability correction** |
| then | M1.6 slice 2 (projections + preprocessing), slice 3 (drivers, MPI/DAFoam) |
| then | M1.8 pickle retirement |
| last | M1.7 full acceptance |

### Turn-30 implementation: M1.7a ready for review

Commit `476b10d` adds the top-level flagship example and its integration test
without changing `bsm3/`; `a9c2830` contains the third-party STEP-import cache
under the configured external setup-cache directory. The cold tri run completed
in **105.8 s** in the working tree and **105.9 s** in the final genuine clone,
with 16,400 vertices, 32,522 triangles, zero folds, zero inversions, and zero
degenerate elements. The clone remains clean after both the example and the
suite. The quad-dominant switch completed in **66.3 s** with
`ngon_affine.weight=0.3` and zero normal-flip folds. Its curated input has 116
pre-existing corner-orientation inversions, unchanged after deformation (116
pre / 116 post).

The derivative gate remains 1/1 and the M1.4 tests remain 5/5. The full dirty
suite is **173 passed**; a genuine clone is **159 passed / 1 skipped**. The
example cache lives under the operating-system temporary directory, not under
`bsm3/`. Peak memory was not available because the sandbox denied the macOS
`sysctl` query. M1.6 slices 2-3, M1.8, and full M1.7 remain in their recorded
order after Claude reviews this implementation.

### Turn-31 planning: user rejection and role reversal

The user rejected the first M1.7a example on usability grounds while retaining
its numerical result as a useful baseline. The correction must remove the CLI,
`mesh_kind`, example-local dataclass, coefficient callbacks, and polygon
diagnostic implementation; expose paths and high-level design values directly;
show the five executable stages clearly; simplify the import/configuration
surface; remove `Config` from the high-level mesh-motion class family; and
replace `DeclarativeGeometryParameterization` with an intuitive abstraction.

Roles reverse here: **Codex is now planner/reviewer and Claude is implementer.**
Codex traced the tracked reference closure and specified the corrective API in
the Turn-32 prompt. The proposed vocabulary is `InputFiles`,
`DistanceWeighting`, `DistortionPenalty`, `PolygonRegularization`,
`SurfaceMotion`, `VolumeMotion`, `QualityChecks`, `Visualization`,
`DerivativeCheck`, `MeshMotion`, and `GeometryModel`. The example consumes
these through the single namespace `bsm3.mesh_motion`; low-level solver types
such as `NgonAffineConfig` and `QuadraticDistortionConfig` are not part of this
high-level rename.

The intended `GeometryModel` owns general `add_lifting_surface`, `add_body`,
and `connect` helpers. This removes callback and control-point mechanics from
the example without encoding E175 names in the core. The result owns fold and
n-gon diagnostics, and STEP-import cache containment moves into the library.
The remaining order is unchanged: corrected M1.7a, M1.6 slices 2-3, M1.8,
then full M1.7.

---

### Turn-25 audit: **M1.5 deferral ACCEPTED**

5 files, zero violations. `eb1ed5f` is the backend `TYPE_CHECKING` cleanup
(+11/-3), verified by AST to leave **zero runtime references** to
`GeometryParameterization`; `0dbcc75` is docs-only.

M1.5's acceptance criterion — "core imports nothing from meshgen" — was
**already satisfied before the turn**. Adoption was correctly declined: the only
credible STEP->surface pair is 4,758 LOC with a confirmed cycle (4 imports one
way, 1 the other), `generate_e175_panel_mesh.py` is a wrapper importing a
private symbol from it, and **all nine candidates have zero test coverage**.

**M3 refinement (Turn 25).** `remesh_fused_step.py` is the strongest starting
point and should not be grouped with the volume generators: **615 LOC**, no
circular dependency, clean dataclass API, and its primary entry point
`remesh_fused_step()` needs **no `bsm3` dependency at all** — only the
`_parametric` / `_manifold` variants pull `body_oml_refit` (847 LOC, untracked),
and they are separable. M3's realistic minimum is 615 LOC with zero internal
coupling, not 4,758 with a cycle.

Numeric guard re-measured and unchanged to 1e-12; genuine clone
**157 passed / 1 skipped**.

---

### Turn-23 audit: **M1.1 + M1.2 ACCEPTED**

Independently executed in `central_geom`. Allowlist: 14 files, **zero
violations**; all 14 prohibited source and 5 prohibited test files untouched.
The two core-module renames were the permitted ones and were necessary — the
"no `E175` string in the generic backend" rule covers an import path.

| | Before | After |
|---|---:|---:|
| public builder | 1,076 LOC | **98 LOC** |
| largest function in the module | 1,076 | **271** (`_run_volume_motion`, preserved) |
| functions over 300 LOC | 1 | **0** |
| package `__all__` | 86 | 108, **all resolve** |

Six-symbol stale grep empty; `geometry_volume_backend.py` contains no `E175`
string; `search_names` and the 27-line alias block gone; `_validate_partition`
removed with both independent copies preserved; the `GeometryVolumeBackend`
Protocol and `CSDLRecorderBackend` survive; the `parameterization_factory`
callback is implemented exactly as ruled in Turn 21.

**Numerical guard passes exactly.** Seven quantities re-measured against the
Turn-7/Turn-9 pre-refactor record — projector rank, hourglass retained fraction,
`‖P·1‖`, hexagon mode count, `obj'` at `λ=0` and `λ=0.3`, observability — all
**identical to 1e-12**. `obj'(0.3)` is still `57/13 = 4.384615384615`,
observability still `2/13`. The refactor moved nothing.

Genuine clone of `8ded2dc`: empty status, six-symbol grep empty, old module
filenames gone, **157 passed / 1 skipped** — unchanged, as a refactor requires.
MPI tripwire passed **without having been edited**.

**Finding (minor, deferred):** the backend's lazy-import intent is defeated —
at `1c5a860` importing it pulled neither config nor pipeline; at `8ded2dc` it
pulls both, via `__init__.py:62,79` and the module-level import at
`geometry_volume_backend.py:37`. The comment at line 304 is now false. Nothing
fails; fix folded into the next turn (`TYPE_CHECKING` guard).

---

### Turn-21 ruling: Turn-20 stop upheld; M1.1 allowlist corrected 10 -> 13

Fourth correct stop, fourth Claude planning defect. The 10-path allowlist
omitted live consumers of the symbols M1.1 renames. Added, as the user directed:
`geometry_volume_backend.py`, `e175_derivative_ladder.py`,
`DAFOAM_MPI_RANK0_HANDOFF.md`.

**Principled line, settling Codex's "is it driver-specific?" question:**

> **The core must be configuration-agnostic; drivers may be E175-specific.**

`E175GeometryVolumeBackend` is **core** — it lives in a generic module and two
different drivers import it — so it generalizes.
`cfd_mesh_movement_test.py`, `cfd_mesh_dafoam_analysis.py` and
`e175_derivative_ladder.py` are drivers and keep their names.

**Two defects found by Claude's Turn-21 audit, beyond Codex's three:**

1. **`GeometryVolumeBackend` is already taken** — a `Protocol` at
   `geometry_volume_backend.py:39`, which the E175 class implements; the module
   `__all__` lists both. Renaming into it would collide. Ruling:
   **`MeshMotionVolumeBackend`**. Uncaught, this was a fifth stop.
2. **`tests/test_geometry_volume_mpi.py` is a collection-time tripwire.** It
   imports `e175_derivative_ladder` (507), which top-level-imports
   `E175GeometryVolumeBackend` (ladder:56). The test needs no edit and stays
   prohibited, but it breaks at collection unless the ladder is renamed in
   lockstep.

**Architecture for the generic backend.** It already takes `model_files: Any`
and `pipeline_config: Any`; the only E175 coupling is
`E175GeometryVariables(**design_variables)` at line 310 inside `_build_model`
(299-314). The constructor gains a driver-supplied
`parameterization_factory: Callable[[Mapping[str, csdl.Variable]], GeometryParameterization]`,
and the generic backend imports and constructs no E175 type.

`build_e175_mesh_motion_model` joins the rename set and the acceptance grep. The
grep is **widened, never narrowed** — no stale reference is hidden by scoping.

---

### Turn-19 audit: **M1.3 ACCEPTED**

Independently reproduced in `central_geom`. Allowlist compliance perfect: 33
files across `8289884..1c5a860`, **zero violations**, all ten prohibited files
untouched. Net source+test delta **+73 / -11,075 = 11,002 lines removed**.

| Claim | Independently measured |
|---|---|
| all removed-API greps empty | 8/8 **EMPTY** over `bsm3/` `tests/` |
| barrier = permitted MPI only | **exactly 7 sites, 4 files** |
| import smoke + `__all__` | 86 entries, **every one resolves** |
| full suite (working tree) | **171 passed / 31.53 s** |
| genuine clone | **157 passed, 1 skipped / 32.04 s**, empty `git status` |

**`use_corotational_reference` removal — in scope and correct.** Not named in
the prompt, but it lived only in two allowlisted files, only `True` was ever
passed, and definition-of-done item 9 bars one-valued compatibility fields
generally. The surviving path is the owner-reference formulation
(`_assemble_free_reference` + per-component deviation solve, unconditional at
`motion.py:496`/`:545`). The deleted `else` arm was self-documented as
*"Kept for comparison; it folds the free/rigid boundary."* Public API break —
`use_corotational_reference=False` no longer exists — accepted under the clean
break.

**One residual defect, Claude's.** `elasticity.py:301` `_validate_partition` is
now orphaned: its only caller was `CorotationalMembraneAssembler`, and
`ngon_affine.py` / `quadratic_distortion.py` carry independent copies. Claude's
prompt listed it under PRESERVE without checking its sole caller was the class
being deleted. ~20 dead lines, no behavioural effect. **Carried into the
M1.1+M1.2 turn as a cleanup item**, not grounds to reopen M1.3.

Ruff is unavailable in `central_geom`; an AST equivalent (dead imports,
references to removed symbols, orphaned privates) found no surviving import of
any removed symbol.

---

### Turn-17 ruling: Turn-16 stop upheld; all acceptance commands audited

Third correct stop-rule invocation in five turns, and the third time the defect
was Claude's. Ruling: **acceptance greps are scoped to live/package content.**

**Defect 1 — a self-referential acceptance command.**
`git grep -n "_dafoam_mpi_refactor_backups" -- .` can never return empty,
because `docs/overhaul/LOG.md`, `PLAN.md` and `CODEX_NEXT.md` *intentionally*
document the directory and its disposition. `LOG.md` is explicitly append-only;
satisfying that command would have required destroying the audit trail the user
asked for. Corrected to
`git grep -n "_dafoam_mpi_refactor_backups" -- bsm3/ tests/`, which must be
empty once the two live pointers in `DAFOAM_MPI_RANK0_HANDOFF.md` (lines 4 and
86) are removed and the directory is deleted. **Historical references in
`docs/overhaul/LOG.md`, `PLAN.md` and `CODEX_NEXT.md` are permitted and expected
to remain.**

**Defect 2 — found by Claude's Turn-17 audit, not yet reached by Codex.** The
definition of done said `git grep -i barrier` matches "only MPI `comm.Barrier()`
at the six named sites," listing three files under `bsm3/`. Simulating the grep
against the post-deletion tree shows a **fourth** file survives:
`tests/test_geometry_volume_mpi.py:69`, `def Barrier(self):` — a mock MPI
communicator. It is not in the allowlist, so the criterion as written was
unsatisfiable. The corrected permitted-survivor set is **seven sites across four
files**:

| File | Sites |
|---|---|
| `bsm3/core/boundary_surface_movement/cfd_mesh_dafoam_analysis.py` | 346 |
| `bsm3/core/boundary_surface_movement/geometry_volume_mpi.py` | 77 |
| `bsm3/core/boundary_surface_movement/run_dafoam_gmsh.py` | 653, 656, 911, 954 |
| `tests/test_geometry_volume_mpi.py` | 69 |

**Full audit of every acceptance command.** Each pattern was run against the
tracked tree and every matching file classified as allowlisted (resolved by the
work), inside the deleted directory, or surviving:

| Check | Files matched | Verdict |
|---|---:|---|
| membrane | 5 | all resolved |
| corotational | 4 | all resolved |
| tangential API (narrowed) | 12 | all resolved |
| deleted modules | 6 | all resolved |
| parameterized projection | 6 | all resolved |
| `mode="graph"` | 5 | all resolved |
| `ELASTIC_STRATEGY` | 1 | all resolved |
| backups dir, scoped to `bsm3/ tests/` | 1 | resolved by the HANDOFF edit |
| barrier | 16 | 3 permitted survivors — **one was unlisted** |

Every other `git grep` in the prompt was already scoped to `bsm3/` or
`bsm3/ tests/`; only the backups command was repo-wide. No further contradiction
found.

**Unchanged:** the 20-path allowlist and every other Turn-16 implementation
instruction.

M1.3 remains open.

---

### Turn-15 ruling: Turn-14 stop upheld; allowlist and grep corrected

Codex invoked the stop rule a second time, correctly. Both findings verified
independently; both are Claude's defects, not implementation problems.

**Defect 1 — the acceptance grep was too broad.** Turn 13 specified
`git grep -iE "tangential_smooth|TangentialSmoothing"`, which matches
`tangential_smoothing_step` in `analytical_SDF_anchor_attraction_noarg.py`
(lines 74, 936, 942, 1119). That is an **unrelated algorithm**: a scalar
relaxation coefficient applying a projected surface-Laplacian step inside an SDF
anchor-attraction point-projection loop. It has **zero imports** from the removed
subsystem, is live tracked code with its own test
(`tests/test_analytical_sdf_anchor_attraction.py`), and is a pattern collision,
not a dependency. Codex's reading is correct.

**Corrected criterion — grep the removed API, not the word.** Validated in
Turn 15 to match exactly the twelve files in scope and to return **0** hits in
`analytical_SDF_anchor_attraction_noarg.py`:

```
TangentialSmoothingConfig | FixedProjectedTangentialSmoother
| assemble_fixed_projected_tangential_smoother | tangential_smoother
| TANGENTIAL_SMOOTHING | tangential_smoothing= | tangential_smoothing import
| surface.tangential_smoothing | tangential_smoothing_ids
```

`tangential_smoothing_step` joins MPI `comm.Barrier()` and the KS/SDF logarithms
as an **explicitly identified permitted survivor**.

**Defect 2 — two backup snapshots were outside the allowlist.**
`…cfd_mesh_dafoam_analysis.py.pre_level6_20260730_084717` and
`…pre_level6fix_20260730_092729` both import `TangentialSmoothingConfig` (49)
and construct `mode="graph"` / `tangential_smoothing=` (138-143). Turn 13
allowlisted only the sibling `.py` file.

**Ruling: delete the entire `_dafoam_mpi_refactor_backups/` directory (14 tracked
files).** Editing them was never an option — their own `README.txt` states they
are *"Pristine backups … the exact content before the first edit in this
effort,"* so editing one to remove a reference to a deleted class would falsify
the only purpose it has. The remaining choice was delete or permanently exempt,
and delete is correct:

- **Inert.** Eleven of fourteen carry `.pre_level6*` timestamp extensions, so
  they are not Python modules. The three `.py` files sit in a directory with no
  `__init__.py`, under `__`-mangled names, outside `testpaths`, matching neither
  `python_files = test_*.py` nor any import.
- **Unreferenced.** Nothing in live code touches the directory; only
  `DAFOAM_MPI_RANK0_HANDOFF.md` mentions it.
- **Superseded.** They snapshot a *completed* refactor on
  `dafoam-mpi-rank0-refactor`, a branch replaced by `production-ready-overhaul`.
- **Not lost.** Git history holds them, and M3.2 pushes full history to a
  separate archive remote.
- **Otherwise permanent.** Keeping them means carrying a grep exclusion through
  every future acceptance criterion.

This **replaces** Turn 13's instruction to edit the one `.py` file in that
directory. `DAFOAM_MPI_RANK0_HANDOFF.md` is tracked and points at the directory,
so it joins the allowlist to have that pointer removed.

**Allowlist: 19 -> 20 paths.** Removed the single backup-file edit; added the
whole-directory deletion and the handoff doc.

M1.3 remains open.

---

### Turn-13 ruling: M1.3 scope extended; Turn-12 block resolved

**Turn 12 stopped correctly.** The Turn-11 prompt was self-contradictory: it
ordered whole-file deletion of `oml_quality.py` while explicitly preserving
tangential smoothing, and `e175_mesh_motion_pipeline.py:1184` calls
`oml_quality.select_fixed_vertex_band` to build the smoothing band. Codex
refused to invent an architectural destination for the helper and invoked the
stop rule. That was the correct behaviour and the contradiction was Claude's.

**User ruling, binding:** tangential smoothing is *also* unwanted.
`select_fixed_vertex_band` is deleted with `oml_quality.py` — not moved, not
preserved. This dissolves the contradiction rather than working around it.

**Corrected M1.3 scope — four subsystems, removed as one clean break:**
membrane assembler/solver; inversion-repair penalty and fallback; final OML
log-barrier optimization; tangential smoothing. Plus every associated export,
import, helper, config field, pipeline branch, driver setting, test and
manifest entry, and `SurfaceMotionConfig.mode`.

**Two dependencies the Turn-11 audit missed, both found downstream:**

1. **`select_fixed_vertex_band`** (`oml_quality.py:98` -> pipeline 1184) — the
   Turn-12 block, now resolved by deletion.
2. **The stale `ELASTIC_STRATEGY == "graph"` branch** (pipeline 1238) with a
   dead `else:` arm at 1292 calling `motion.train()`. Turn 10 removed the
   binding but left the branch. It must collapse to the graph load-step path.

**New ruling — parameterized projection is deleted.** Traced every tracked
reference. `parameterize_final_projection` is set **only** as
`(FINAL_QUALITY_STRATEGY == "oml")` at pipeline 1253-1255, and the stale `else:`
arm calls `project_onto_oml_parameterized` only under the same condition. Its
other consumers are `oml_quality.py` (deleted) and
`tests/test_boundary_surface_movement.py:981`, which lies **inside**
`test_fixed_oml_quality_repairs_on_surface_and_ift_vjp_matches_fd` (deleted).
**Zero independent tracked consumers remain**, so `ParameterizedProjection`,
`ParameterizedProjectionGroup` and `project_onto_oml_parameterized` go, together
with the `load_stepping.py` plumbing that carries them.

**Ordinary projection survives.** `projection.py` is a mixed-purpose file:
`project_onto_oml` (65), `reevaluate_vertices` (412), `combine_vertices` (452)
and `VertexBatch` (32) stay. The private helpers `_project_group` (478) and
`_coefficient_subset` (501) are **shared** by both the ordinary and
parameterized paths — verified by call-graph trace — so they stay too.

**Tests: five deletions, two rewrites.**

| Test | File:line | Action |
|---|---|---|
| `test_fixed_projected_tangential_smoother_preserves_reference_and_has_fixed_vjp` | `test_boundary_surface_movement.py:639` | delete |
| `test_final_only_tangential_smoother_defers_projection_and_differentiates` | `:699` | delete |
| `test_corner_barrier_repairs_quad_and_ift_vjp_matches_finite_difference` | `:877` | delete |
| `test_fixed_oml_quality_repairs_on_surface_and_ift_vjp_matches_fd` | `:951` | delete |
| `test_final_only_tangential_reprojection_is_a_supported_fixed_option` | `test_e175_driver_configuration.py:138` | delete |
| `test_default_volume_motion_is_final_only_and_differentiable` | `:56` | rewrite — drop the `tangential_smoothing.reprojection` assertion |
| `test_quad_diagonal_controls_are_validated` | `:147` | rewrite — drop the `mode="unsupported"` arm |

Every deletion is a test *of* a removed component, not an independent consumer.

**Expected: 162 passed / 1 skipped -> 157 passed / 1 skipped** in a genuine
clone (working tree 176 collected -> 171).

**Allowlist delta from Turn 11** (16 -> 19 paths): **added**
`tangential_smoothing.py` (whole-file delete), `load_stepping.py`,
`projection.py`. `load_stepping.py` and `projection.py` were on Turn 11's
*prohibited* list; that prohibition is lifted for the named symbols only.

**Preserved:** graph Laplacian motion, N-gon affine regularization, quadratic
distortion regularization, ordinary OML projection and reevaluation, symmetry
enforcement, surface and volume quality diagnostics (`quality.py` — no barrier;
its only `log|barrier` hit is the word "logic" at line 178), STEP-to-aero mesh
support, MPI `comm.Barrier()`, and KS/SDF logarithms unrelated to optimization
barriers.

M1.3 remains open pending Codex's corrective implementation.

---

### Turn-11 ruling: M1.3 is REOPENED — user overrules Turn 10

> "The membrane approach and log-barrier are not wanted and must not be kept."

Binding. Turn 10 removed the *configured E175 membrane branch* but preserved the
lower-level membrane solver, assembler, barrier implementation, exports and
tests, on the grounds that they sat outside a literal seven-file allowlist and
that three tracked call sites still passed `mode="graph"`. That reasoning
defended compatibility with code the user wants deleted. It is overruled.

**The corrective scope is a dependency audit, not a guess.** Findings from
`git grep` and import tracing:

**Membrane surface (5 tracked production files, 1 test file, 4 docs):**

| File | Membrane content |
|---|---|
| `elasticity.py` | `CoupledAssembledSystem` (64), `CorotationalMembraneAssembler` (246), `_polygon_membrane_stiffness` (547), `_cst_stiffness` (634), `_scatter_coupled_element` (658), `_scatter_edge_regularization` (703) — all reachable **only** from the membrane assembler |
| `motion.py` | `CorotationalMembraneMotionSolver` (870-1111); the `from .inversion_barrier import` at 55; all four `use_inversion_barrier` sites (899, 951, 954, 1029) lie **inside that class** |
| `inversion_barrier.py` | Entire file; its only importers are `__init__.py` (102) and `motion.py` (55) |
| `__init__.py` | Imports at 17, 18, 61, 102-109; nine `__all__` entries (174, 178, 179, 189-192, 222, 223); docstring line 11 |
| `oml_quality.py` | Docstring line 3 |

**Barrier formulations — the naming is inverted from intuition:**

- **`inversion_barrier.py` is NOT a logarithmic barrier.** `_objective`
  (391-440) is a *quadratic penalty*:
  `0.5·w·Σ(ratio − target)²` over violating corners plus a quadratic data term.
  Zero `log` calls in the file. The filename is a misnomer. It is removed
  because its sole remaining reachability is the membrane solver — not because
  of its formulation.
- **`oml_quality.py` IS the log barrier.** Line 494:
  `-(1.0 - normalized)**2 * jnp.log(safe)` — the IPC form, and the module
  docstring (line 13) says so: "a smooth IPC-style log barrier". It is the only
  genuine optimization log barrier in tracked live code.
- `movement_test_csdl_static_seam.py:537`, `movement_test_new.py:436`,
  `movement_test_new_2.py:670` use `np.log` for **KS smooth-union SDF
  aggregation**. Not barriers, not in the retained manifest. Leave untouched.

**Ruling on `oml_quality.py` and `FinalSurfaceQualityConfig`: REMOVE.** It is a
nonlinear geometry-correction method driven by a log barrier, which is exactly
what the overhaul brief named ("hooks for nonlinear geometry deformation methods
with log-barriers"). It is dormant — `FinalSurfaceQualityConfig.mode` defaults
to `"none"` and no tracked driver enables it — while publicly exposing
`barrier_floor`, `barrier_activation` and `barrier_weight`. Keeping a dormant
1,065-line log-barrier optimizer after this ruling is not defensible.

**Mesh-quality diagnostics are a different module and survive.** `quality.py`
(`evaluate_mesh_quality`, `check_element_inversion`) contains no barrier — its
only `log`/`barrier` grep hit is the word "logic" in a comment at line 178.

**Ruling on `SurfaceMotionConfig.mode`: REMOVE.** Turn 10 kept it as a
one-valued `"graph"` field to avoid breaking three tracked call sites. Two are
live drivers (`cfd_mesh_movement_test.py:119`,
`cfd_mesh_dafoam_analysis.py:139`) and updating them is a one-line edit each.
The third is `_dafoam_mpi_refactor_backups/…:127`, a tracked but dead snapshot —
**no test, `pytest.ini`, or `ruff.toml` references that directory**, so it is not
policy-live. A one-valued validated field is exactly the "compatibility field"
this ruling forbids.

**"Barrier" that legitimately survives: MPI collectives only.** After deletion,
`git grep -i barrier -- bsm3/` should match nothing but `comm.Barrier()` in
`cfd_mesh_dafoam_analysis.py:346`, `geometry_volume_mpi.py:77`, and
`run_dafoam_gmsh.py:653/656/911/954` — process synchronization, unrelated to
optimization barriers.

**Tests: two deletions, one rewrite.**

| Test | Action | Why |
|---|---|---|
| `test_corner_barrier_repairs_quad_and_ift_vjp_matches_finite_difference` (`test_boundary_surface_movement.py:877`) | **delete** | Exercises `CornerInversionBarrierModel`/`Operation` directly; it is a test *of* the barrier, not an independent consumer |
| `test_fixed_oml_quality_repairs_on_surface_and_ift_vjp_matches_fd` (`test_boundary_surface_movement.py:951`) | **delete** | Same relationship to `oml_quality` |
| `test_e175_driver_configuration.py:147` `SurfaceMotionConfig(mode="unsupported")` | **rewrite** | The assertion disappears with the field; the surrounding test keeps its other arms |

**Expected count: 162 passed / 1 skipped -> 160 passed / 1 skipped** in a
genuine clone (working tree 176 collected -> 174).

**Accepted public API breaks (clean break, decision 3):** nine `__all__` entries
from `bsm3.core.boundary_surface_movement`; six `oml_quality` exports;
`FinalSurfaceQualityConfig` (config `__all__` line 340) and the
`SurfaceMotionConfig.final_quality` field; `SurfaceMotionConfig.mode`.

**Trap for the implementer.** `final_quality` is an *overloaded name* in
`e175_mesh_motion_pipeline.py`. Lines 351-403 bind it to a **volume mesh quality
metrics** object (`inverted_tetrahedra`, `minimum_relative_jacobian`,
`mean_ratio_p001`) that has nothing to do with `FinalSurfaceQualityConfig`. Only
line 462 (`surface.final_quality`) and the aliases at 493-499 belong to the
config. Deleting the wrong ones silently breaks volume diagnostics.

M1.3 remains open pending Codex's corrective implementation.

---

### Turn-9 audit of M1.4 — **ACCEPTED**

Every Turn-8 claim was reproduced independently. Both commits match the Turn-8
allowlist exactly; `ngon_affine.py` was neither modified nor staged and is still
byte-identical to the C1 substrate.

| Reported | Independently measured |
|---|---|
| unregularized derivative 4.0 | **4.0000000000** — and derivable by hand: free `y = δ(0,0,1)`, weights `(1,2,4)` |
| regularized derivative 4.3846153846 | **4.3846153846** = `57/13` |
| observability 0.153846·δ | **0.1538461538** = `2/13`, threshold `0.04·δ` met with **3.85x** margin |
| 117,267 assembled modes | **117,267** — 28,190 polygon6 + 7,891 polygon5 + 3,927 polygon7 + 126 polygon8 + 2 polygon9 + 565 quad |
| clone 164 passed, 1 skipped | **164 passed, 1 skipped in 47.52 s**, empty `git status --porcelain`, 115 MB, R4 absent |

**Why 0.1538 and not Turn 7's 0.0465.** Turn 7's estimate used a hand-built
unit-weight 6-cycle Laplacian. The production `GraphLaplacianAssembler` is
exactly **0.25x** that (solved for: `α = 0.2500` reproduces `2/13` to 10
digits), so `λ·P` carries 4x the relative influence. The response moved *up*.
This is the Turn-7 risk resolving favourably; Codex did not lower the threshold,
which was the required behaviour.

**Mutation testing of Test C.** Reading the test cannot establish that it would
catch a broken adjoint, so four faults were injected into `compute_vjp` in a
scratch tree and discarded:

| Fault | Result |
|---|---|
| n-gon adjoint dropped | **FAIL** (caught) |
| coupling adjoint transposed (`k_fp` for `k_fp.T`) | **FAIL** (caught) |
| coupling adjoint sign flipped | **FAIL** (caught) |
| adjoint-only scale x2 | **FAIL** (caught) |

The transpose fault is the one no operator-level test can see, since `P_e` is
symmetric — the Turn-7 argument for splitting the tests is vindicated. (A fifth
attempt that scaled `strength` in *both* `solve` and `compute_vjp` passed, but
that is a consistent `λ=0.6` run, not a fault.)

**Three scope notes — accepted, not defects:**
1. `solutions=()` makes `_set_exact_seams` a no-op, so prescribed rows are not
   written into the output mesh. Correct here: the fixture has no intersection
   seams, the drive still flows through `prescribed_deviations`, and the
   objective weights only free rows. Verified: free rows move, prescribed do not.
2. Test C's reprojection is **DV-inert**. The target is the static `z=0` plane
   and the objective weights `y`; measured `z ≡ 0` for all rows, so reprojection
   provably cannot change the objective. It runs as a production path but is not
   under test. The affine-nullspace control gate covers DV-dependent
   reprojection, because its projection surface translates with the design
   variable. Division of labour, not a hole — but M1.7 should assert
   reprojection sensitivity explicitly.
3. Test C hardcodes `pair = (objective, amplitude)` rather than discovering
   pairs from the simulator. Correct for one pair; it will not auto-extend.
   `_SyntheticHexagonMotion` also overrides `__init__` without calling `super()`,
   so the subclassing is cosmetic and M1.1/M1.2 could invalidate it silently.

**Runtime:** 42.92 s before M1.4 -> 47.52 s after. **+6 tests, +4.60 s**,
against a 30 s budget.

---

### M1.4 finalized design (Turn 7) — derived from the operator, not from trial

**The operator.** `_affine_residual_projector` builds, per element, from the
*baseline* polygon: centre, SVD to the best-fit plane, in-plane chart `(u, v)`,
design matrix `[1, u, v]`, reduced QR giving `Q_e`, and
`P_e = I - Q_e Q_e^T`, symmetrized and thresholded. `P_e` acts on the
**n-vector of nodal values per spatial component**, not on 3-vectors. Therefore:

> `null(P_e) = span{1, u, v}` — every nodal field that is an affine function of
> the element's own baseline in-plane coordinates. `rank(P_e) = n - 3`, matching
> `num_hourglass_modes += cell.size - 3`. Triangles are skipped
> (`block.shape[1] < 4`), which is correct: a triangle has no hourglass mode.

This is exactly `range(A_e) = range(Q_e) = 𝒜_e`, and it is why the Turn-3 quad
gate measured 3.3e-16: a pure z-ramp is affine in `(u, v)`, so `r_e = 0`.

**The construction: a regular planar hexagon and its alternating ring mode.**
Vertices at angles `kπ/3`, `k = 0..5`, in the `z = 0` plane. The alternating
nodal field `p = (+1, -1, +1, -1, +1, -1)` is **exactly** orthogonal to
`span{1, u, v}` on a regular hexagon — verified in Turn 7:

| Quantity | Measured |
|---|---|
| `P` symmetric / idempotent / rank | yes / yes / **3** (= n-3) |
| `‖P·1‖`, `‖P·u‖`, `‖P·v‖`, `‖P·(2+3u-5v)‖` | 6.5e-16, 3.8e-16, 2.0e-16, 2.7e-15 |
| `‖P·p‖ / ‖p‖` (retained fraction) | **1.000000** — fully non-affine |
| Quad control: rank, retained fraction | 1, 1.000000 |

The mode is *maximally* observable, not marginally: `h = P p = p`, `‖h‖ = √6`.

**Both primal limits are analytic.** Single hexagon, prescribe nodes `{0, 2, 4}`
to `(+δ, -δ, +δ)`, leave `{1, 3, 5}` free. Three prescribed values determine a
unique affine `f(u,v) = a + bu + cv`, so:

| λ | Free-node `z` | Character |
|---|---|---|
| `0` | `δ·(0, 0, 1)` | pure graph/harmonic on the 6-cycle |
| `0.3` | `δ·(-0.0081·…)` shifted | **‖Δ‖∞ = 0.0465·δ** vs the quad gate's 3.3e-16 |
| `→ ∞` | `δ·(-1/3, -1/3, +5/3)` | affine completion, `f = δ(1/3 + (2/3)u - 1.1547v)` |

Neither endpoint is a golden number copied from the implementation; both are
derived independently and must be asserted as such.

**Three tests, separated for failure localization** (the user's stated
preference, and justified here: `P_e` is symmetric, so an operator-level test
*cannot* see a transpose error in the free/prescribed coupling block — only the
FD test can):

| Test | File | Budget | What only it can catch |
|---|---|---|---|
| **A — operator** | `tests/test_ngon_affine_operator.py` | < 1 s | Projector algebra: symmetry, idempotence, `rank = n-3`, nullspace `= {1,u,v}`, retained fraction `= 1`, hourglass-mode counts (3 for hexagon, 1 for quad, 0 for triangle) |
| **B — primal observability** | `tests/test_ngon_affine_operator.py` | < 5 s | That λ *changes the answer*, and that both analytic limits are hit. Catches sign (λ→∞ would diverge from affine) and scale (thresholds pin it) |
| **C — load-step VJP/FD** | `tests/test_ngon_affine_load_step.py` | < 20 s | Transpose/adjoint errors in the coupling block, and any N-gon term dropped from the VJP |

**Acceptance thresholds** (binding):
- A: nullspace residuals `< 1e-12`; `|retained_fraction - 1| < 1e-12`; `rank == n-3` exactly.
- B: `λ=0` matches harmonic to `1e-12`; `λ=1e6` matches the affine completion to `1e-5`; `‖z(0.3) - z(0)‖∞ ≥ 0.04·δ`.
- C: centered FD at `(1e-4, 1e-5, 1e-6)`, per-pair best-step then **worst-pair** aggregation (the Turn-3 convention), `< 1e-5`. Plus a guard that `d(objective)/dδ` at `λ>0` differs from `λ=0` by `≥ 1e-6`, so a VJP that silently drops the N-gon term cannot pass.
- Total added runtime `< 30 s`, keeping the fast gate inside its budget.

**Minimum M1.4 coverage:**

| Case | Where | Note |
|---|---|---|
| Quad | Test A control + the existing derivative gate | The existing gate is hereby **reclassified as the affine-nullspace control**: its 3.3e-16 is the correct, expected answer, not a failure. Document that in the gate's docstring. |
| True `polygon6` | Tests A, B, C | The core of M1.4 |
| Small mixed-polygon | `tests/test_ngon_affine_load_step.py` | Synthetic quad + pentagon + hexagon; assert `num_hourglass_modes == Σ(n_e - 3)` |
| Inversion / fold + quality | same mixed example | Zero folds and zero inversions after deformation at `λ > 0` |
| `wall_surface.pkl` | `tests/test_curated_assets.py`, `@pytest.mark.integration` | Loads via the trusted API and assembles with the expected mode count. **No solve, no derivative** — it must not enter the fast gate. Pickle retirement stays M1.8. |

No DAFoam. No new binary assets — the hexagon constructions are synthetic.

---

## 5b. M3 — Clean release repository (gated, last)

Created by the Turn-3 ruling. Does not start until M1 is complete and every root
in the manifest has an end-to-end test.

| ID | Task | Owner | Status | Acceptance |
|----|------|-------|--------|------------|
| M3.1 | Prove the M0.2 manifest: every retained file is reached by a passing end-to-end test from at least one declared root. | TBD | blocked on M1 | No file in the manifest is unreached; no test imports a file outside it. |
| M3.2 | Push the full current repository to a **separate archive remote**. Not a tag in the release repository. | TBD | blocked on M3.1 | Archive remote holds the complete pre-overhaul history; release clones do not fetch it. |
| M3.3 | Build the clean release repository from the proven manifest. | TBD | blocked on M3.2 | Fresh clone is small, `pytest` passes on it with no untracked-asset dependencies, and every declared root runs. |

Note on decision 3: the user accepted a clean break on history. That acceptance
stands — the Turn-3 ruling changes *when* and *how* the break happens, not
whether it is allowed.

---

## 6. Open questions for Codex

Answer in `LOG.md`, do not edit this section.

- **Q-A (M0.1, mostly resolved by Claude).** Surface meshes are small; only volume meshes are large. Measured: `e175_fluent_R1_aircraft_wall_tri.msh` 1.9 MB, `e175_fluent_coarse_aircraft_wall_tri.msh` 5.2 MB, both with `.volume_map.npz` at 1.2 / 3.3 MB. Volume meshes are the only budget problem: coarse 39.8 MB is the smallest, R1 is 52.3 MB. Since M1 is surface deformation, **commit the surface assets and defer the volume mesh**. Remaining question for Codex: does the driver run end to end on the R1 or coarse wall, and is a committed volume mesh needed for M1 at all given `VolumeMotionConfig(mode="off")` is the current production setting?
- **Q-B (blocks M1.4).** Has `ngon_affine.py` ever been exercised on 6-gon cells, or only quads? `NGON_AFFINE_REGULARIZER_AUDIT.md` is 111 KB — does it answer this?
- **Q-C (affects M0.2).** Claude's 84%-unreachable figure comes from a static import trace from the single driver. Are there live modules reached only dynamically (importlib, string dispatch, `__init__` re-export) that the trace missed and that M0.2 would wrongly drop?
