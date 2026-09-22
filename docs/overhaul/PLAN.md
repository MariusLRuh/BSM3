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
| M0.5 | **Restated by the Turn-5 ruling.** Land a coherent M0 commit series so that a *genuine clone* of the resulting commits passes. The Turn-3 asset causes are fixed. The residual blocker was never "4 untracked files": Turn-5 preflight against clean HEAD content proved the M0 gate additionally requires 12 modified tracked files carrying pre-M0 user work. | Codex | **complete** | Genuine clone is clean, excludes the R4 volume mesh, and passes with 158 tests and one expected R4 skip; derivative gate passes separately. |

**M0.3 is the gate for everything after it.** Do not start M1 until it passes.

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
| M1.1 | Generalize config. `E175ModelFiles` -> `ModelFiles`; component/intersection specs become `list[ComponentSpec]` / `list[IntersectionSpec]`; geometry parameterization becomes a user-supplied protocol rather than the frozen `E175GeometryVariables`. | Codex | not started | E175 driver runs through the generic API with no `E175`-named type in the call path. |
| M1.2 | Decompose `build_e175_mesh_motion_model` into stage functions matching the 5-step pipeline. Delete the ~50-line `LOCAL_ALIAS = config.field` block at lines 456-515. | Codex | not started | No function over 300 LOC in the pipeline module; derivative gate still passes. |
| M1.3 | Delete `membrane` mode: 7 `membrane_*` fields, 6 `mode != "graph"` validation rules in `SurfaceMotionConfig.__post_init__`, and the branches at pipeline lines 1069 and 1521. Re-check `inversion_barrier.py` reachability afterward. **Turn-3 note:** Turn 2 added two tests that construct `SurfaceMotionConfig(mode="membrane", ...)` to assert graph-only validation — `test_quad_diagonal_weight_is_validated_as_graph_only` and `test_ngon_affine_weight_is_validated_as_graph_only`. These must be rewritten, not deleted: keep the `quad_bracing_mode` and negative-weight assertions, drop the membrane arm. | Codex | not started | `grep -ri membrane bsm3/` returns nothing in the live core; tests pass; the two validation tests survive in membrane-free form. |
| M1.4 | **N-gon, mandatory (decision 6).** Requires a *true six-gon load-step/VJP regression*, not merely loading the mixed-N-gon asset. Turn-3 measurement: in the M0.3 gate, changing `lambda_ngon` from 0.0 to 0.3 moves the solution by 3.3e-16 and the derivative by 1.8e-15 — the deformation is a pure affine ramp on a uniform quad grid, which lies in the **nullspace** of the affine penalty. Formally, `range(A_e) = range(Q_e) = 𝒜_e`, and the residual projector `(I - Q_e Q_e^T)` annihilates any correction in that affine subspace. The N-gon path is *executed* (graph grows 2666 -> 3080 nodes) but its contribution is unobservable, so a sign, scale, or transpose error in its VJP would pass today. M1.4 must construct a polygon6 correction with a provably nonzero component in the orthogonal complement of `range(Q_e)`, giving a genuine hourglass mode whose primal response changes with `lambda_ngon` by construction. | Codex | not started | A test on polygon6 cells where the projected non-affine residual is explicitly nonzero and `lambda_ngon` measurably changes the primal solution, with FD-verified derivatives through load stepping; plus quad and mixed-N-gon examples deforming with zero inversions. |
| M1.5 | Carve `bsm3.meshgen` out of the ~40k LOC of gmsh/OCC scripting. Keep one rudimentary path per the high-level plan; delete the rest. | Codex | not started | Core imports nothing from `meshgen`; one example regenerates a surface mesh from STEP. |
| M1.6 | Numpydoc docstrings across the public surface of the live core. **M1.6 owns the documentation debt that M0.4 staged out of CI**: repo-wide critical ruff currently reports 398 errors in legacy/experimental files, and the measured numpydoc baseline is 0 sectioned public definitions. Widening the CI lint gate from the M0 file list to the retained manifest is part of this task. | Codex | not started | ruff pydocstyle clean over the retained manifest; coverage >=90% of public defs; CI lint scope widened from the M0 file list. |
| M1.8 | **New (Turn 5).** Retire the internal legacy polygon-pickle branch in the E175 pipeline. Turn 4 made the *public* importer safe by removing `.pkl` from suffix dispatch, but the pipeline retains an internal trusted-pickle path, and `bsm3/core/projections/refitted_fun_set.pkl` is an untracked executable pickle used as a warm-start default. Convert `wall_surface.pkl` to `.npz` per `ASSETS.md` and delete the branch. | Codex | not started | No pickle load remains reachable from any retained root except through an explicitly named trusted API; `wall_surface.pkl` replaced by a non-executable container with identical coordinates and connectivity. |
| M1.7 | Acceptance run. Must exercise a **STEP-to-VortexAD path** if practical, alongside the surface-motion path — the VortexAD root is the one the Turn-1 trace missed entirely, so it is the least protected by existing tests. | Codex | not started | Generalized driver reproduces current R4 output within tolerance; derivative gate passes; quad and mixed-N-gon examples clean; a STEP-to-VortexAD path runs end to end or is recorded as impractical with the reason. |

**Sequencing.** M1.3 before M1.2 (deleting membrane removes ~200 LOC and six
validation rules from the function being decomposed). M1.1 and M1.2 are
coupled; do them as one turn. **M1.4 must come first among the M1 tasks** — the
Turn-3 measurement shows the N-gon contribution is currently unobservable in
every test we have, so it is both the one mandatory capability (decision 6) and
the one with no working regression. Proving it before the refactor means the
refactor has a gate; proving it after means the refactor is unguarded on
exactly the code path the user made mandatory.

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
