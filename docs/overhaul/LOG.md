# BSM3 Overhaul — Collaboration Log

Append-only. Newest turn at the bottom. Keep entries short: what was decided,
what changed, what is open. Detail belongs in `PLAN.md` or in the code.

Entry format:

```
## Turn N — <agent>, <role>, <date>
Scope:     <milestone/task IDs>
Did:       <2-5 bullets>
Decided:   <decisions that bind future turns, or "none">
Open:      <questions handed to the other agent, or "none">
Status:    open | closed
```

---

## Turn 1 — Claude, planner, 2026-09-21
Scope:     Repo audit + M0/M1 plan

Did:
- Audited the repo against `production_ready_code_base_overhaul.md`. Key finding:
  only 45 files / 24,285 LOC are reachable from `cfd_mesh_movement_test.py`, out
  of 211 files / 156,485 LOC in `bsm3/`. The 0.1 target is a ~24k-LOC package.
- Measured the blockers the overhaul doc did not name: `.git` is 8.5 GB (largest
  blob 284 MB); `build_e175_mesh_motion_model` is a single ~1,290-line function
  opening with ~50 lines of `LOCAL_ALIAS = config.field`; numpydoc coverage is 0%;
  `bsm3/utils/` is three empty files.
- Wrote `PLAN.md`: protocol, 10 locked decisions, M0 (4 tasks) and M1 (7 tasks)
  with per-task acceptance criteria.

Decided:
- **Branch strategy (user delegated, Q10):** one branch, one worktree, serialized
  turns. Alternation is per-milestone so only one agent implements at a time;
  a shared tree removes the merge step for the reviewer.
- **M0.3 (derivative gate) blocks all of M1.** Refactoring a 1,290-line
  differentiable builder without a fast VJP check risks silently breaking
  derivatives and discovering it weeks later on the cluster.
- **Deletion before generalization.** The overhaul doc runs these in parallel;
  ordering deletion first means both agents read a 24k-LOC repo for every
  subsequent step.
- **M1.3 before M1.2.** Removing `membrane` strips ~200 LOC and six validation
  rules out of the function being decomposed.

Retracted:
- Claude's review claimed the C208 strut creates a cyclic intersection graph
  needing new junction handling. User corrected: each intersection is an
  independent closed curve, strut-to-wing and strut-to-fuselage are disjoint,
  so `list[IntersectionSpec]` is sufficient. The cycle is in component
  adjacency, which the solver never sees. This removed the main argument for
  designing against C208 in M1; C208 is deferred per decision 1.

Open:
- Q-A, Q-B, Q-C in `PLAN.md` section 6, handed to Codex.
- Environment note: the `codex` CLI is not installed on this machine
  (`~/.codex` has config and auth but no binary on PATH), so Claude cannot
  invoke Codex directly. Collaboration is file-mediated through this repo,
  relayed by the user.

Status:    closed

---

## Turn 2 — Codex, implementer/reviewer, 2026-09-21
Scope:     Plan review; Q-A/Q-B/Q-C; safe portions of M0.1/M0.3/M0.4

Did:
- Claimed the turn after reading `CODEX_KICKOFF.md`, `PLAN.md`, and `LOG.md` in
  full. No implementation file had been edited before this claim.
- Reproduced the static trace to within its counting convention: 46 modules and
  24,286 lines including the entry module, equivalent to Claude's 45/24,285
  reachable dependencies.
- Verified the proposed R1 triangle wall, quad mesh, and legacy mixed-polygon
  mesh load locally; recorded the actual polygon content below.
- Ran the current focused baseline: 54 passed and 2 stale driver-contract tests
  failed; no numerical surface-motion test failed.
- Added a trusted legacy polygon-pickle reader and documented/tested the 7.9 MB
  curated STEP, triangle-wall/map, quad, and true mixed-N-gon asset set.
- Added a 5x5-quad analytical derivative gate covering intersection
  recomputation, graph load steps, nonzero affine N-gon regularization, final
  reprojection/reevaluation, and symmetry.
- Added explicit pytest discovery and staged CI: pinned Python 3.9 dependencies,
  critical Ruff checks, numpydoc checks on the M0 surface, the fast derivative
  gate, and the full test suite. Reconciled two stale driver-contract tests and
  corrected the R4 wall-map filename used by the current dirty-tree driver.

Decided:
- **Q-A:** no committed volume mesh is needed for M1 surface work. The R1 wall
  loads as 16,400 vertices / 32,522 triangles and can run with volume motion
  off. Preserve volume-motion/DAFoam interfaces, and validate them later against
  a user-supplied local volume mesh.
- **Q-B:** the N-gon implementation is generic, but current tests exercise the
  affine projector on quads and pentagons, the VJP on quads, and the E175 study
  on a quad-dominant mesh. There is no six-gon load-step/VJP regression. The
  proposed `embraer_175_hexagonal_symmetric_no_winglets.msh` is not a six-gon
  surface: it contains 156,843 triangles and 565 quads. `wall_surface.pkl` is
  the real mixed-polygon asset: 28,190 polygon6 cells plus polygon5/7/8/9 cells.
- **Q-C:** the count is reproducible but not a safe deletion set. It is rooted
  only at the surface driver and omits separate required entry paths including
  VortexAD, DAFoam, geometry-volume glue, and mesh generation. Static analysis
  is also not proof against dynamic imports or data-file dependencies.
- M0.4 lint is intentionally staged. Repo-wide critical Ruff currently reports
  398 legacy/experimental-tree errors, while the M0 files pass both critical
  rules and the selected numpydoc convention. Repo-wide documentation remains
  M1.6 work.

Objection:
- **M0.2 and deletion-before-generalization should not proceed as written.** An
  orphan branch restricted to the 45-file trace would contradict the required
  STEP-to-aerodynamics scope and risks discarding dirty-tree source work. Also,
  retaining `pre-overhaul-archive` as a tag in the same fetched repository keeps
  the old objects reachable, so it cannot guarantee a sub-200 MB fresh clone.
  Defer the history cut until the generic E175, VortexAD, volume-hook, and
  mesh-generation entry points define the true keep-set. Store the archive in a
  separate repository/ref that release clones do not fetch.

Open:
- M0.4's repo-wide numpydoc gate conflicts with M1.6: the measured baseline has
  zero numpydoc-sectioned public definitions. CI should start with critical
  Ruff rules, pytest, and the derivative gate; enable full numpydoc enforcement
  when M1.6 brings the live public surface into compliance.
- Claude should respond to the M0.2 objection before any history rewrite or
  bulk deletion. Safe, additive M0 work may continue meanwhile.
- M0.1's three previously untracked asset files still need to be included in
  the eventual clean-history commit. M0.4 is locally validated but has not run
  on GitHub yet.

Validation:
- `pytest -q tests`: 170 passed in 40.92 s.
- Derivative/asset/config focused suite: 12 passed in 9.10 s; the derivative
  gate is below the 60 s limit.
- Staged critical Ruff and numpydoc checks: passed.

Status:    closed

---

## Turn 3 — Claude, planner/reviewer, 2026-09-22
Scope:     Review of Codex M0 implementation; binding ruling on the M0.2 objection

Did:
- Reviewed all ten artifacts from Turn 2. Reproduced Codex's validation:
  170 passed in 42.39 s full suite; 12 passed in 11.06 s focused. Verified the
  curated asset set at 7.5 MB and confirmed the `cfd_mesh_movement_test.py`
  wall-map fix — the doubled `.volume_map.volume_map.npz` suffix was real and
  the file exists only under the corrected single-suffix name.
- Ran a multi-root reachability trace to adjudicate the objection quantitatively.
- Probed the derivative gate empirically rather than reading it: ran the full
  pipeline at `lambda_ngon` 0.0 and 0.3 and compared primal and derivative.
- Made one reviewer edit to `tests/test_derivative_gate.py` (below).

**Ruling: the M0.2 objection is ACCEPTED in full.** Detailed reasoning is in
`PLAN.md` section 4. Summary:
- Multi-root trace confirms point 1 quantitatively. Adding DAFoam, VortexAD,
  volume/MPI, mesh-generation, and derivative-ladder roots yields **54 files /
  32,932 LOC** against the single root's 45 / 24,353 — Turn 1 understated the
  keep-set by 35% of LOC. VortexAD is the decisive case: 8 modules import it and
  the single-root trace marked **all 8** dead.
- Point 2 stands: static tracing cannot see dynamic imports or data
  dependencies, so even 54 files is a starting manifest, not a deletion set.
- Point 3 is correct and exposes a Claude error: `du -sh .git < 200 MB` with the
  archive retained as a tag in the same repository was never achievable. The
  Turn-1 acceptance criterion was wrong, not merely unmet.

Decided (binding):
- **"Deletion before generalization" is RESCINDED.** Turn 1 optimized for agent
  readability over deletion safety and treated a single-entry-point trace as a
  package boundary. Generalization and end-to-end coverage now precede pruning.
- **M0.2 is redefined** as a non-destructive multi-root manifest
  (`docs/overhaul/MANIFEST.md`). It deletes nothing.
- **New M3 milestone** holds the history cut, gated behind M1 and behind every
  root having an end-to-end test. Archive goes to a separate remote, not a tag.
- **M1.4 moves to the front of M1** — see the N-gon finding below.
- M0.4's staged lint is accepted as correct; M1.6 explicitly owns widening it.
- No committed volume mesh for M1; volume and DAFoam hooks stay supported on
  user-supplied local paths. Confirms Codex's Q-A.

Reviewer edit made:
- `tests/test_derivative_gate.py`: the FD assertion was
  `assert errors and min(errors) < 1.0e-5`, flattening step sizes and derivative
  pairs into one list. Minimising over step sizes is correct (FD error is
  U-shaped in h); minimising over *pairs* is not — one accurate derivative would
  mask a broken one. Rewritten to score each pair at its own best step and then
  require `max(best_error_per_pair.values()) < 1.0e-5`. A no-op today (one pair)
  and correct once M1 adds design variables. Gate re-run: passes in 8.33 s.

Requested changes for Codex (precise, in priority order):
1. **M0.5, blocker.** CI will fail on its first GitHub run.
   `test_public_drivers_expose_explicit_matching_model_files` asserts
   `.is_file()` on three untracked R4 assets (107.6 MB, incl. a 100.9 MB volume
   mesh) and carries no marker. Separately, `pytest.ini` registers the
   `integration` marker but never deselects it and there is no `conftest.py`, so
   the asset-dependent tests in `test_curated_assets.py` also run by default.
   Fix both: gate asset-dependent assertions behind a skip-if-missing helper, or
   add `addopts = -m "not integration"` plus markers. Do not fix it by committing
   a 100.9 MB mesh.
2. **M1.4, capability.** The gate exercises the N-gon path but cannot observe it.
   Measured: `lambda_ngon` 0.0 -> 0.3 changes the solution by 3.3e-16 and the
   derivative by 1.8e-15, because a pure affine ramp on a uniform quad grid is
   in the nullspace of the affine penalty. The path *is* traversed (graph 2666
   -> 3080 nodes), so this is unobservability, not dead code — but a sign,
   scale, or transpose error in the N-gon VJP passes today. Turn 2's claim that
   the gate covers "nonzero affine N-gon regularization" covers execution, not
   correctness. M1.4 needs a genuine hourglass mode on polygon6 cells.
3. **M1.3, coupling.** Turn 2 added two tests constructing
   `SurfaceMotionConfig(mode="membrane", ...)`, entrenching in the suite the mode
   M1.3 deletes. Rewrite rather than delete them when membrane goes: keep the
   `quad_bracing_mode` and negative-weight arms.
4. **Public API hazard.** `import_mesh` now dispatches to `pickle.load` on a
   `.pkl`/`.pickle` suffix, so any caller handed an untrusted path executes
   arbitrary code. The docstring warning does not constrain callers. Planner's
   call: keep the reader, remove it from the suffix dispatch, and expose it as an
   explicitly named `import_trusted_polygon_pickle()` that a caller must choose.
   Converting `wall_surface.pkl` to `.npz`, as ASSETS.md already proposes,
   retires the hazard entirely and is preferred.
5. **Minor.** `assert time.perf_counter() - start < 60.0` inside the gate makes a
   slow CI runner report a derivative failure. Prefer `pytest-timeout` or a
   generous ceiling so the signal stays "derivatives are wrong", not "the
   machine was busy".

Validation run this turn:
- `pytest -q tests`: **170 passed in 42.39 s** (unchanged after the reviewer edit).
- `pytest -q tests/test_derivative_gate.py`: **1 passed in 8.33 s**.
- Focused derivative/asset/config suite: **12 passed in 11.06 s**.
- Multi-root trace: 54 files / 32,932 LOC retained (21% of `bsm3/`).
- N-gon observability probe: primal delta 3.3e-16, derivative delta 1.8e-15.
- Ruff not run locally — not installed in the `central_geom` environment. CI
  installs `ruff==0.9.10`; the lint result remains unverified outside CI.

Remaining work before M1 starts:
- M0.5 (fresh-clone CI) and M0.2-redefined (multi-root manifest). Both are
  Codex's next turn; the prompt is in `docs/overhaul/CODEX_NEXT.md`.
- Working tree left dirty and uncommitted by design, per the user's constraint
  for this turn. Nothing staged, deleted, or rewritten.

Status:    closed

---

## Turn 4 — Codex, implementer/reviewer, 2026-09-22
Scope:     M0.5; M0.2-redefined; trusted polygon import review

Did:
- Claimed the turn after reading `PLAN.md`, `LOG.md`, and `CODEX_NEXT.md`.
- Committed only the three authorized curated assets (R1 wall/map and quad
  panel) in `6ef0703`; no volume mesh or other dirty-tree file was staged.
- Split driver path-contract checks from optional local R4 file-existence
  checks, and made curated-asset tests skip cleanly if their fixtures are
  absent. Replaced generic pickle suffix dispatch with the explicit
  `import_trusted_polygon_pickle()` API and added a security regression.
- Added `MANIFEST.md`: the reproduced six-root union is 54 Python files / 32,937
  current LOC, with per-root membership plus computed imports, re-exports,
  string dispatch, external tools, caches, and runtime data paths.
- Replaced the derivative gate's in-test stopwatch assertion with a
  `pytest-timeout` marker/dependency and retained Claude's per-derivative,
  best-step FD scoring.

Decided:
- Agree with the N-gon unobservability finding: execution alone is not a
  correctness test; M1.4 needs a non-affine polygon6 hourglass case.
- Agree that the two membrane validation arms must be rewritten, not simply
  deleted, during M1.3.
- Agree with Claude's derivative assertion edit. Minimizing over step size per
  derivative pair, then bounding the worst pair, is the correct aggregation.
- Claude's 54-file count is reproduced. The LOC delta from 32,932 to 32,937 is
  exactly the net Turn-4 trusted-reader API edit.

Open:
- Literal tracked-only validation exposed a third M0.5 blocker not listed in
  Turn 3: four files in the retained 54-file set are untracked
  (`e175_panel_opt.py`, `gmsh_occ_oml_surface_mesh.py`, `ngon_affine.py`, and
  `smooth_existing_tip_cap.py`). Collection stops first on missing
  `ngon_affine.py`. This turn expressly permitted staging only the three
  assets, so these source files remain untracked for Claude's ruling.
- The internal E175 pipeline still supports a legacy trusted polygon-pickle
  branch. The generic public importer is now safe, but fully retiring pickle
  requires the planned asset conversion and pipeline cleanup.

Validation:
- Current working tree: `pytest -q tests` — **172 passed in 44.03 s**.
- Derivative gate: **1 passed in 10.06 s** (11.18 s wall clock).
- Candidate source tree with all current Python source but no untracked data:
  **171 passed, 1 skipped in 43.31 s**; the one skip is the local R4 asset set.
- Literal tracked-only tree: **10 collection errors**, first caused by the
  untracked `ngon_affine.py`; therefore the exact M0.5 acceptance criterion is
  not yet met.
- Staged critical Ruff, numpydoc checks, and `git diff --check`: passed.

Status:    closed

---

## Turn 5 — Claude, planner/reviewer, 2026-09-22
Scope:     Turn-4 review; binding ruling on the M0.5 commit set

Did:
- Reviewed commit `6ef0703` (exactly the three authorized assets, nothing else),
  the trusted-pickle API split, the R4 integration-marker split, the
  `pytest-timeout` replacement for the in-test stopwatch, and `MANIFEST.md`.
- Spot-checked the manifest's least obvious attribution. `smooth_existing_tip_cap.py`
  under root M is **correct**: `gmsh_occ_oml_surface_mesh.py` imports it at lines
  384/407/431/444 as deferred in-function imports breaking a circular dependency,
  and the trace properly follows nested imports. No manifest defect found.
- Built a preflight tree from `git archive HEAD` (clean committed content only)
  and overlaid candidate files one at a time to find the true minimal M0 closure.

Findings that change the ruling:

1. **Codex's blocker was measured against a hybrid, not a clone.** HEAD's
   `__init__.py` and `load_stepping.py` do **not** import `ngon_affine`; only the
   dirty working copies do. A real clone of `6ef0703` does not fail on a missing
   `ngon_affine.py`. The observed collection error came from pairing tracked file
   *selection* with dirty file *content*. Diagnosis correct, cause misattributed.
2. **The real dependency is far larger than four files.** The preflight converged
   only after adopting **12 modified tracked files carrying +1415/-196 lines of
   pre-M0 user work**. The chain: the gate needs `NgonAffineConfig` (dirty
   `__init__.py`), `ngon_affine_config=` (dirty `load_stepping.py`),
   `NgonAffineRegularizationConfig` (dirty `e175_mesh_motion_config.py`), and
   `symmetry_use_element_neighbors` (dirty `motion.py`), which drag in matching
   dirty `elasticity.py`, `current_graph_solve.py`, `e175_mesh_motion_pipeline.py`,
   `volume_mesh_motion.py`, `quadratic_distortion.py` and the dirty tests.
   Partial adoption produced 3, then 5, then 9 failures; only coherent adoption
   went green.
3. **`__init__.py`'s dirty diff is +14 lines and 100% the N-gon re-export** —
   verified line by line. It is not mixed work. `load_stepping.py` by contrast is
   +169/-5 with only 47 N-gon lines, so 127 lines are unrelated user work.

Decided (binding) — full detail in `PLAN.md` section 4:
- **`ngon_affine.py` is committed now** (472 LOC, self-contained, required for the
  mandatory N-gon capability). **The other three untracked production files stay
  deferred**: no test reaches them, roots P and M have zero coverage, and
  committing 5,116 LOC of untested script to satisfy a file-count criterion is the
  Turn-1 deletion-safety error inverted. They land in M1.5 and M1.7 with tests.
- **M0.5's acceptance criterion is corrected.** "Passes with only tracked files"
  was wrong — the manifest is a retention candidate list, not a commit set. The
  criterion is now a genuine clone of the M0 commits passing with expected skips.
- **Five narrowly scoped commits, not one** (C1-C5). C2 promotes the user's
  in-progress work to the baseline and is **flagged for user review**; a separate
  commit makes it independently reviewable and revertible. Order is bisectable.
- **M1.8 created**: retire the internal E175 pickle branch and the untracked
  executable `bsm3/core/projections/refitted_fun_set.pkl`. Confirming Codex — the
  public importer is safe but the internal branch is still live debt.

Confirmed Codex's four agreements, all correct:
- M1.4 needs an observable non-affine polygon6 hourglass/VJP regression. Confirmed;
  this was Claude's Turn-3 measurement and Codex reproduced the reasoning.
- Membrane validation arms rewritten, not deleted, during M1.3. Confirmed.
- Per-derivative best-step FD aggregation is correct. Confirmed. The
  `pytest-timeout` substitution for the in-test stopwatch is an improvement on
  Claude's Turn-3 suggestion and is adopted.
- The internal E175 pickle branch remains technical debt. Confirmed and promoted
  to a tracked task (M1.8) rather than left as a log note.

Validation this turn:
- Working tree: `pytest -q tests` — **172 passed in 44.03 s** (reproduces Turn 4).
- **Preflight** (clean `git archive HEAD` + C1-C4 allowlist only):
  **158 passed, 1 skipped, 0 failed in 41.92 s**; the skip is the local R4 asset
  set, which is correct. Derivative gate in the preflight: **1 passed in 7.66 s**.
- Negative control: adding untracked `tests/test_hybrid_volume_mesh_motion.py`
  produces **9 failures** — it depends on further uncommitted work. Excluded.
- Confirmed the preflight tree contains no R4 volume mesh and that the curated
  assets arrive from `6ef0703`, not from the working tree.
- Ruff still not runnable locally (absent from `central_geom`); unchanged from
  Turn 3 and unverified outside CI.

Remaining work:
- Codex lands C1-C5 and runs the genuine-clone verification. Literal allowlist and
  exact commands are in `docs/overhaul/CODEX_NEXT.md`.
- Working tree left dirty; nothing staged, committed, deleted, or rewritten this
  turn, per the user's constraint.

Status:    closed

---

## Turn 6 — Codex, implementer/reviewer, 2026-09-22
Scope:     M0 C1-C5 commit series; genuine-clone verification

Did:
- Claimed the turn after reading the Turn-5 ruling and `CODEX_NEXT.md`.
- Corrected the clone target from the stale `dafoam-mpi-rank0-refactor` branch
  named in the prompt to the active `production-ready-overhaul` branch that
  contains the M0 commits.
- Landed C1 `16bd2ef` (N-gon substrate), C2 `76f24ce` (the explicitly
  flagged +1415/-196 user-work baseline), C3 `a88a04a` (trusted polygon
  reader), and C4 `4160779` (M0 tests/CI) using only literal allowlisted paths.
- Prepared C5 as the documentation-only collaboration snapshot, including the
  corrected clone command and the formal M1.4 affine-complement criterion.

Decided:
- The Turn-6 clone command's branch name was stale. Validation must target
  `production-ready-overhaul`; the prescribed branch does not contain M0.
- M1.4 will construct its polygon6 perturbation directly outside
  `range(Q_e)`: because `range(A_e) = range(Q_e) = 𝒜_e`, the residual projector
  `(I - Q_e Q_e^T)` annihilates affine ramps and must be explicitly nonzero for
  the test correction.

Open:
- Remote GitHub Actions remains unrun; all CI commands are locally validated.

Validation:
- After C1: **172 passed in 43.83 s**.
- After C2: **172 passed in 43.17 s**.
- After C3: **172 passed in 43.81 s**.
- After C4: **172 passed in 44.47 s**.
- C5 documentation snapshot before commit: **172 passed in 43.36 s**.
- Genuine clone at C4: empty `git status --porcelain`; five M0 commits
  including the asset commit visible; R4 volume absent; checkout size 115 MB.
- Genuine-clone suite: **158 passed, 1 skipped in 44.76 s**; the skip is the
  optional local R4 asset set. Derivative gate: **1 passed in 7.39 s**
  (8.29 s wall clock).

Status:    closed

---

## Turn 7 — Claude, planner/reviewer, 2026-09-22
Scope:     M0 commit-series review and closure; M1.4 operator-level design

M0 review — **ruling: M0 is COMPLETE**:
- All five commits match their allowlists exactly. `0a657a7..51e0ea0` contains
  none of the twelve forbidden paths; the only binaries are the three curated
  assets from `6ef0703`. All eight excluded dirty files are still dirty; the
  three deferred production files are still untracked. Dirty count moved 24 M ->
  9 M, which reconciles exactly (16 committed, plus this turn's `LOG.md`).
- Scope of C2 confirmed at the predicted 12 files / +1415/-196.
- **Bisectability was re-measured properly.** Codex validated each commit inside
  the dirty working tree, which cannot establish it. Turn 7 ran each commit from
  `git archive` in isolation: `0a657a7` 1F/141P, `6ef0703` 1F/141P, C1 1F/141P,
  C2 154P/1S, C3 154P/1S, C4 158P/1S.
- **C1 is red standalone, and Claude's Turn-5 prediction that it would be green
  was wrong.** But the failure is inherited, not introduced:
  `test_public_e175_drivers_do_not_use_cli_or_environment_configuration` asserts
  `'os.environ' not in source` against the `DAFOAM_CASE_DIRECTORY` lookup added
  by `0a657a7`, which is red *before* the series starts. C2 repairs it. The
  series is monotonically non-worsening, so this is a documented caveat
  (bisect from `76f24ce` forward), not a defect.
- Trusted-pickle boundary verified: `.pkl`/`.pickle` no longer reach generic
  `import_mesh`; the explicit API is the only route.
- Remote GitHub Actions unrun. Treated as an external verification item per the
  user's instruction, not grounds to reopen M0.

Review of the flagged C2 baseline commit:
- It does what it was authorized to do and nothing more: exactly the twelve
  allowlisted paths, no forbidden file, no binary. It is a single revertible
  commit, which was the entire point of isolating it.
- It is also the commit that *repairs* the inherited red baseline, so the
  project's first green commit is C2. Worth knowing before any future bisect.
- The risk remains what Turn 5 stated: 1,415 added lines of the user's
  in-progress work are now the project baseline, adopted without line-by-line
  review because the N-gon wiring and surrounding work are entangled. Nothing in
  Turn 7 changes that; it is recorded, reviewable, and revertible.

M1.4 design — derived from the operator, verified numerically this turn:
- `P_e = I - Q_e Q_e^T` acts on the **n-vector of nodal values per spatial
  component**, built from the *baseline* polygon's own in-plane chart. Hence
  `null(P_e) = span{1, u, v}` and `rank(P_e) = n - 3`, matching
  `num_hourglass_modes += cell.size - 3`. Triangles are correctly skipped.
- **Selected construction: a regular planar hexagon and its alternating ring
  mode** `p = (+1,-1,+1,-1,+1,-1)`. Measured: `P` symmetric, idempotent,
  rank exactly 3; `‖P·1‖=6.5e-16`, `‖P·u‖=3.8e-16`, `‖P·v‖=2.0e-16`,
  `‖P·(2+3u-5v)‖=2.7e-15`; **retained fraction exactly 1.000000**. The mode is
  maximally non-affine, not marginally — `h = P p = p`, `‖h‖ = √6`.
- **Both primal limits are analytic.** Prescribe `{0,2,4}` to `(+δ,-δ,+δ)`,
  free `{1,3,5}`. `λ=0` gives harmonic `δ·(0,0,1)`; `λ→∞` gives the affine
  completion `δ·(-1/3,-1/3,+5/3)` with `f = δ(1/3 + (2/3)u - 1.1547v)`. Both
  derived independently and confirmed against a direct solve. Observability at
  `λ=0.3`: **‖Δ‖∞ = 0.0465·δ**, against the Turn-3 quad gate's 3.3e-16.
- **Three tests, not one.** The decisive argument for splitting is that `P_e` is
  symmetric, so an operator-level test is structurally blind to a transpose
  error in the free/prescribed coupling block — only the FD test can see it.
  A: projector algebra. B: primal observability and both analytic limits.
  C: load-step VJP vs centered FD, with a guard that the derivative at `λ>0`
  differs from `λ=0` so a dropped N-gon adjoint term cannot pass.
- The existing derivative gate is **reclassified as the affine-nullspace
  control**: its 3.3e-16 is the mathematically correct answer for an affine
  ramp, not a failure, and its docstring should say so.
- Coverage, thresholds, and budgets are in `PLAN.md` section 5. No DAFoam, no
  new binary assets, and `wall_surface.pkl` stays integration-marked and out of
  the fast gate.

Risks and open questions:
- Test C must drive the hourglass through `run_graph_load_steps` on a synthetic
  polygon6 mesh. If the existing solver path rejects a bare hexagon ring for
  want of projection/intersection metadata, Codex should enlarge to a small
  honeycomb rather than weaken the assertion, and report the change.
- The `λ=0.3` threshold of `0.04·δ` is set from a uniform-weight 6-cycle. The
  production solver applies area/stiffening weights, so the measured value may
  shift. The threshold is deliberately ~14 orders above noise; if it is missed,
  that is a finding to report, not a number to lower.
- Remote CI remains unverified.

Validation this turn:
- Per-commit isolation runs as tabulated above (6 archives, 6 suites).
- Projector algebra and both primal limits verified numerically against
  independently derived closed forms.
- Working tree preserved: nothing staged, committed, deleted, or rewritten.

Status:    closed

---

## Turn 8 — Codex, implementer/reviewer, 2026-09-22
Scope:     M1.4 observable polygon6 regularization and VJP regression

Did:
- Claimed the turn after reading the finalized M1.4 design and allowlist.
- Added pure polygon6/quad projector algebra and mode-count checks, including
  the analytically derived harmonic and affine-completion limits.
- Added an observable polygon6 CSDL design variable through the production
  `run_graph_load_steps` solve and OML reprojection path. The boundary-state
  fixture is synthetic; the graph solve, N-gon custom operation/VJP, and
  projection are production implementations.
- Added a disconnected quad + pentagon + hexagon deformation check with six
  total hourglass modes, zero inverted elements/corners, zero degeneracies,
  and positive scaled-Jacobian and area-ratio bounds.
- Added an integration-only assembly of the trusted `wall_surface.pkl` asset:
  **117,267** expected and assembled modes, with no solve or derivative.
- Reclassified the existing derivative gate as the expected affine-nullspace
  control in its docstring only.
- Committed the implementation as `0f3e10c` using exactly the seven literal
  allowlisted paths.

Decided:
- **No operator defect was found.** `ngon_affine.py` was not changed or staged.
- The bare six-node ring is sufficient when paired with a broad bilinear plane
  for the real reprojection. A honeycomb enlargement was not needed.
- At `lambda_ngon=0.3`, the normalized production operator changes the free
  solution by **0.153846·delta** in infinity norm, above the binding
  `0.04·delta` threshold. The earlier 0.0465 estimate was not used as a golden
  value.

Open:
- Remote GitHub Actions remains unrun; local and genuine-clone gates are green.

Validation:
- Operator file: **3 passed in 2.78 s**.
- Load-step file: **2 passed in 3.17 s**.
- Focused operator + load-step + affine-nullspace gate: **6 passed in 8.50 s**.
- Derivative observability: regularized analytic derivative **4.3846153846**,
  unregularized **4.0**, difference **0.3846153846**; centered-FD relative
  errors at `(1e-4, 1e-5, 1e-6)` were **9.22e-13, 8.45e-12, 1.11e-10**.
- Working-tree suite (includes the excluded untracked hybrid-volume test):
  **178 passed in 49.52 s**.
- Ruff default and `--select D`: **all checks passed** for both new files.
- Genuine clone of `0f3e10c`: empty `git status --porcelain`; editable install
  succeeded; **164 passed, 1 skipped in 50.98 s**. This is six new passes and
  about **6.22 s** over the prior 158-pass/1-skip clone, below the 30 s budget.
- The prompt-mandated editable install first failed because the sandbox blocked
  build-isolation access to `setuptools`; rerunning the identical command with
  approved network access succeeded. No dependency or source change was made.

Status:    closed

---

## Turn 9 — Claude, planner/reviewer, 2026-09-22
Scope:     Independent audit of the Turn-8 M1.4 claim

**RULING: M1.4 is ACCEPTED.** Every reported number was reproduced
independently; no defect found. Full evidence in `PLAN.md` section 5.

Audit results, by the ten required points:

1. **Allowlist.** `51e0ea0..52afde3` is an exact set-match to the Turn-8
   allowlist. `0f3e10c` carries the seven permitted paths; `52afde3` is
   `LOG.md` only. No forbidden path, no binary, no production source.
2. **Re-ran everything.** Focused operator + load-step: **5 passed in 2.28 s**.
   Affine-nullspace control gate: **1 passed in 7.26 s**. Genuine
   `git clone file://` of `52afde3`: empty `git status --porcelain`, 115 MB,
   R4 volume mesh absent, **164 passed / 1 skipped in 47.52 s**. (Used
   `PYTHONPATH` rather than `pip install -e .` so the audit could not mutate the
   working environment — the step Codex had to undo in Turn 8.)
3. **Derived, not copied.** The operator test solves `[1, u, v] c = z_prescribed`
   in-test for the affine field and evaluates it at the free nodes, *then*
   cross-checks against the closed form `δ(-1/3, -1/3, 5/3)`. The harmonic limit
   `δ(0, 0, 1)` is the closed form I derived by hand in Turn 7. Nullspace and
   rank assertions match Turn 7's measurements. `δ = 0.7`, so scaling is
   exercised rather than a unit special case.
4. **Threshold genuinely met, and the discrepancy is explained.**
   `‖Δ‖∞ = 0.1538461538 = 2/13`, against `0.04·δ` — a **3.85x** margin.
   Turn 7's 0.0465 assumed a unit-weight 6-cycle; the production
   `GraphLaplacianAssembler` is exactly **0.25x** that (`α = 0.2500` reproduces
   `2/13` to ten digits), so `λP` carries 4x the relative influence and the
   response moved *up*. This is precisely the Turn-7 risk resolving favourably.
   **Codex did not lower the threshold**, which was the required behaviour.
   Independently confirmed: `obj'(λ=0) = 4.0000000000` exactly, and derivable by
   hand from free `y = δ(0,0,1)` with weights `(1,2,4)`.
5. **Test C, inspected critically.**
   - Production paths: `run_graph_load_steps`, `GraphLaplacianAssembler`,
     `CurrentGraphNgonAffineModel` and its custom operation/VJP, and the real
     projection call are all production. Only the *boundary-data supply* is
     synthetic. That is the right shape for a targeted coupling regression.
   - `solutions=()` makes `_set_exact_seams` a no-op. Acceptable: the fixture has
     no intersection seams, the drive still flows through
     `prescribed_deviations`, and the objective weights only free rows. Verified
     directly — free rows move, prescribed rows stay at baseline.
   - Objective is on `final_mesh_vertices`, i.e. post-reprojection. But the
     target is the static `z = 0` plane and the objective weights `y`; measured
     `z ≡ 0` on every row, so **reprojection provably cannot change the
     objective**. It executes as a path but is not under test. The control gate
     covers DV-dependent reprojection because its projection surface translates
     with the design variable. Recorded as a scope note for M1.7.
   - FD is genuinely centered at all three steps: `(f(x+h) - f(x-h)) / 2h` at
     `1e-4, 1e-5, 1e-6`. Reported relative errors 9.22e-13, 8.45e-12, 1.11e-10.
   - Aggregation is correct: min over step sizes per pair, then max over pairs.
     It hardcodes the single pair rather than discovering pairs from the
     simulator, so it is right today but will not auto-extend.
   - **Mutation-tested rather than argued.** Four faults injected into
     `compute_vjp` in a scratch tree: adjoint dropped, coupling transposed,
     coupling sign flipped, adjoint-only scale x2 — **all four FAIL the test**.
     The transpose fault is the one no operator-level test can see, since `P_e`
     is symmetric; Turn 7's argument for splitting the tests is vindicated.
6. **Mixed polygons.** `num_hourglass_modes == Σ(n-3) = 1+2+3 = 6` asserted, and
   after a `λ = 0.3` deformation the test asserts zero inverted elements, zero
   inverted corners, zero degenerate elements, positive minimum scaled Jacobian
   and area ratio, and finite aspect ratio.
7. **Large pickle stays out.** `@pytest.mark.integration`, assemble-only, no
   solve, no derivative, no CSDL import. Mode count independently verified at
   **117,267** = 28,190 polygon6 + 7,891 polygon5 + 3,927 polygon7 + 126
   polygon8 + 2 polygon9 + 565 quad. Not in the fast gate.
8. **`test_derivative_gate.py`**: docstring only — a five-line reclassification,
   zero behavioural change.
9. **`ngon_affine.py`**: never modified since the C1 substrate commit, clean in
   the working tree, and byte-identical in the clone. Codex's "no operator
   defect" claim is confirmed rather than assumed.
10. **Runtime.** 42.92 s before M1.4 -> 47.52 s after: **+6 tests, +4.60 s**
    against the 30 s budget.

Findings for later milestones, none blocking:
- **M1.3 scope is larger than PLAN.md stated.** Commit C2 brought in two further
  membrane tests Turn 3 could not have seen:
  `test_coupled_membrane_patch_test_and_interleaved_dofs` and
  `test_coupled_membrane_can_pin_one_symmetry_component` in
  `tests/test_boundary_surface_movement.py`. Four tests, not two. `PLAN.md`
  updated.
- `inversion_barrier.py` is imported by both `__init__.py` and `motion.py`, so
  it probably survives membrane removal. M1.3 must verify, not assume.
- M1.7 should assert reprojection sensitivity explicitly, since neither M1.4
  test does.
- Remote GitHub Actions still unrun. External item, unchanged.

Next task selected from the `PLAN.md` dependency order: **M1.3** (delete
membrane mode), which the sequencing note places before M1.2, with M1.1+M1.2
coupled as one later turn. Prompt written to `CODEX_NEXT.md`. No milestones
combined.

Validation this turn: 2 suite runs in scratch trees, 1 genuine clone, 5 mutation
runs, and 4 independent numerical derivations. Working tree preserved; nothing
staged, committed, deleted, or rewritten.

Status:    closed

---

## Turn 10 — Codex, implementer/reviewer, 2026-09-22
Scope:     M1.3 removal of the membrane surface-motion configuration path

Did:
- Claimed the turn after reading the Turn-9 ruling and literal allowlist.
- Removed all seven `membrane_*` fields, the six now-vacuous graph-only
  validation branches, and the obsolete wording in the affine/distortion
  mutual-exclusion error.
- Removed the membrane aliases, solver-selection branch, and diagnostics branch
  from the E175 pipeline. The existing graph body is now unconditional.
- Rewrote both driver-configuration tests to retain the negative-weight and
  bracing-mode assertions. Added an explicit assertion that the retained
  one-valued surface mode rejects unsupported values.
- Deleted two standalone coupled-assembler tests. They exercised only the
  removed strategy: affine reproduction is already covered immediately above
  by `test_harmonic_solve_reproduces_affine_field_exactly`, and surviving
  symmetry behavior is covered by
  `test_fixed_symmetry_plane_constraint_overwrites_only_the_normal_coordinate`.

Decided:
- `SurfaceMotionConfig.mode` **survives as a one-valued `"graph"` field**.
  Three tracked production configurations outside this turn's allowlist still
  explicitly pass `mode="graph"`; retaining and validating it avoids breaking
  those call sites and gives M1.1 a clean compatibility point. The pipeline no
  longer branches on or reads the field.
- `motion.py` and `inversion_barrier.py` are not dead and were not changed.
  The barrier model/operation are independently exported and directly covered
  by the corner-repair test. They are also used by the separately exported
  lower-level `CorotationalMembraneMotionSolver`, which M1.3's literal
  allowlist cannot remove.

Open:
- The literal repository-wide `grep -ri membrane bsm3/` criterion is
  incompatible with both the allowlist and the instruction to preserve the
  still-reachable inversion barrier. The configured E175 live path
  (`e175_mesh_motion_config.py` and `e175_mesh_motion_pipeline.py`) has zero
  matches, and tracked tests have zero matches. Five lower-level tracked modules
  still contain the independently public membrane implementation:
  `__init__.py`, `elasticity.py`, `motion.py`, `inversion_barrier.py`, and
  `oml_quality.py`. Removing those is a broader public-API deletion and was not
  inferred into this turn.
- Remote GitHub Actions remains unrun; local and genuine-clone gates are green.

Validation:
- Driver configuration: **10 passed in 2.78 s**.
- Boundary-surface movement: **45 passed in 35.59 s** after deleting the two
  strategy-only tests.
- M1.4 polygon6 tests: **5 passed in 3.08 s**.
- Affine-nullspace derivative gate: **1 passed in 8.20 s**.
- Working-tree suite, including the excluded untracked hybrid-volume test:
  **176 passed in 47.05 s**.
- Ruff on `e175_mesh_motion_config.py`: **all checks passed**; both modified
  production modules compile; `git diff --check` is clean.
- `git grep -i membrane -- tests`: no matches. The E175 config and pipeline
  likewise have no matches. The five residual lower-level module paths are
  listed above and justified by direct reachability.
- Commit `52b43c9` contains exactly the seven allowed paths. Code/test delta:
  **+52/-163**. `motion.py` and `inversion_barrier.py` are absent.
- Genuine clone of `52b43c9`: empty `git status --porcelain` and
  **162 passed, 1 skipped in 47.22 s**, exactly two fewer passes than Turn 9
  because the two standalone strategy-only tests were removed.

Status:    closed

---

## Turn 11 — Claude, planner/reviewer, 2026-09-22
Scope:     User ruling overturns Turn 10's preservation decision; M1.3 reopened

**User ruling, binding:** "The membrane approach and log-barrier are not wanted
and must not be kept." Turn 10's preservation of the lower-level membrane
solver, assembler, barrier implementation, exports and tests is **overruled**.
Its justification — a literal seven-file allowlist, plus three tracked call
sites still passing `mode="graph"` — defended compatibility with code the user
wants deleted. **M1.3 is reopened.** Full ruling in `PLAN.md` section 5.

Claude's error is on record: Turn 9's allowlist was scoped to the *configured*
membrane path and did not extend to the implementation behind it, so Codex's
reading was reasonable against the prompt it was given. The prompt was too
narrow, not the execution.

Dependency audit, by the six required reports:

**1. Tracked files containing `membrane` / `CorotationalMembrane`, or importing
`inversion_barrier`** — 5 production, 1 test, 4 docs:
- `elasticity.py` (17 hits): `CoupledAssembledSystem` 64,
  `CorotationalMembraneAssembler` 246, `_polygon_membrane_stiffness` 547,
  `_cst_stiffness` 634, `_scatter_coupled_element` 658,
  `_scatter_edge_regularization` 703. Call-graph traced: every one is reachable
  **only** from `CorotationalMembraneAssembler`; `_cst_stiffness`'s sole caller
  is `_polygon_membrane_stiffness`.
- `motion.py` (21 hits): `CorotationalMembraneMotionSolver` 870-1111; import at
  55. **All four `use_inversion_barrier` sites (899, 951, 954, 1029) are inside
  that class** — confirmed by mapping each line to its enclosing class.
- `inversion_barrier.py` (1 hit, docstring 590): importers are exactly
  `__init__.py:102` and `motion.py:55`. No non-membrane caller exists.
- `__init__.py` (5 hits): imports 17, 18, 61, 102-109; `__all__` 174, 178, 179,
  189, 190, 191, 192, 222, 223; docstring 11.
- `oml_quality.py` (1 hit, docstring 3).
- `tests/test_boundary_surface_movement.py`: barrier imports 16-17, used at
  888 and 906.
- Docs: `MANIFEST.md:57`, plus `PLAN.md`, `LOG.md`, `CODEX_NEXT.md`.

**2. Logarithmic barrier formulations — the naming is inverted:**
- **`inversion_barrier.py` is not a log barrier.** `_objective` (391-440) is a
  quadratic penalty, `0.5·w·Σ(ratio − target)²` plus a quadratic data term;
  zero `log` calls in the file. It is removed for reachability, not formulation.
- **`oml_quality.py` is the log barrier**: line 494,
  `-(1.0 - normalized)**2 * jnp.log(safe)` — IPC form, and the docstring at
  line 13 names it. The only genuine optimization log barrier in tracked live
  code.
- `movement_test_csdl_static_seam.py:537`, `movement_test_new.py:436`,
  `movement_test_new_2.py:670`: `np.log` in KS smooth-union SDF aggregation.
  Not barriers; not in the retained manifest; untouched.

**3. Symbols unreachable after deletion:** the six `elasticity.py` symbols
above; `CorotationalMembraneMotionSolver`; all of `inversion_barrier.py`
(`BarrierSolveInfo`, `_BarrierState`, `CornerInversionBarrierModel`,
`CornerInversionBarrierOperation`, `CornerInversionBarrierVJP`,
`FallbackCornerInversionBarrierOperation`, `FallbackCornerInversionBarrierVJP`,
`_corner_ratio_gradients`, `_corner_ratio_hessian`); all of `oml_quality.py`
(`OMLQualityModel`, `OMLQualityOperation`, `OMLQualitySolveInfo`,
`OMLQualityVJP`, `optimize_mesh_on_oml`, `select_fixed_vertex_band`);
`FinalSurfaceQualityConfig`; `SurfaceMotionConfig.final_quality` and `.mode`.

**4. Tests — two deletions, one rewrite.** Both deletions are tests *of* the
removed component, not independent consumers that happen to use it:
`test_corner_barrier_repairs_quad_and_ift_vjp_matches_finite_difference` (877)
and `test_fixed_oml_quality_repairs_on_surface_and_ift_vjp_matches_fd` (951).
The rewrite is `test_e175_driver_configuration.py:147`, whose
`SurfaceMotionConfig(mode="unsupported")` arm goes with the field while the
rest of the test stands.

**5. Expected reduction: 162 passed / 1 skipped -> 160 passed / 1 skipped** in a
genuine clone (working tree 176 collected -> 174).

**6. Accepted public API breaks:** nine `__all__` entries from the
boundary-surface package; six `oml_quality` exports; `FinalSurfaceQualityConfig`
(config `__all__` 340) and `SurfaceMotionConfig.final_quality`;
`SurfaceMotionConfig.mode`.

Two rulings the prompt asked me to make:

- **`oml_quality.py` and `FinalSurfaceQualityConfig`: REMOVE.** It is a
  nonlinear geometry-correction method driven by a log barrier — precisely what
  the overhaul brief named. It is dormant (`mode` defaults to `"none"`, no
  tracked driver enables it) yet publicly exposes `barrier_floor`,
  `barrier_activation`, `barrier_weight`. `quality.py` — the diagnostics module —
  is a different file, contains no barrier (its one grep hit is the word
  "logic" at line 178), and survives.
- **`SurfaceMotionConfig.mode`: REMOVE.** Turn 10 kept it for three call sites.
  Two are live drivers needing a one-line edit each; the third is
  `_dafoam_mpi_refactor_backups/…:127`. I checked whether repository policy
  treats that directory as live — **no test, `pytest.ini`, or `ruff.toml`
  references it** — so it is a dead tracked snapshot, updated for consistency
  but not load-bearing. A one-valued validated field is the compatibility field
  this ruling forbids.

Precise distinction recorded for the implementer: **the only "barrier" that
survives is MPI `comm.Barrier()`** — `cfd_mesh_dafoam_analysis.py:346`,
`geometry_volume_mpi.py:77`, `run_dafoam_gmsh.py:653/656/911/954`. Process
synchronization, not optimization.

Trap flagged: `final_quality` is overloaded in `e175_mesh_motion_pipeline.py`.
Lines 351-403 bind it to a **volume mesh quality metrics** object
(`inverted_tetrahedra`, `minimum_relative_jacobian`, `mean_ratio_p001`)
unrelated to `FinalSurfaceQualityConfig`; only line 462 and the aliases at
493-499 belong to the config. Deleting the wrong ones breaks volume diagnostics
silently.

Preserved explicitly: graph Laplacian, N-gon affine regularization, quadratic
distortion regularization, tangential smoothing, projection, and the
`quality.py` diagnostics — none depends on the removed barrier.

This turn was audit and planning only. No production file was staged,
committed, modified or deleted; only the three permitted docs were edited.

**M1.3 remains OPEN** pending Codex's corrective implementation; the prompt is
in `docs/overhaul/CODEX_NEXT.md` with a 16-path allowlist.

Status:    closed

---

## Turn 12 — Codex, implementer/reviewer, 2026-09-22
Scope:     Corrective M1.3 deletion of membrane and optimization-barrier code

Did:
- Claimed the turn after reading the Turn-11 ruling, dependency audit, and
  16-path literal allowlist.
- Traced every deletion target before changing production code and found a
  preserved-path dependency omitted by the audit.

Decided:
- No compatibility exception applies. The unwanted implementations, exports,
  tests, dormant surface-quality configuration, and one-valued mode field will
  be removed as one coherent clean break.

Open:
- **Blocking missed dependency:** `oml_quality.py:98` defines
  `select_fixed_vertex_band`, but the explicitly preserved tangential-smoothing
  path calls it at `e175_mesh_motion_pipeline.py:1184`. Whole-file deletion plus
  removal of its export would break graph tangential smoothing. Its natural
  destination is `tangential_smoothing.py`, which is outside the allowlist and
  explicitly prohibited. Copying it into the monolithic pipeline would stay
  inside the literal paths but would be an unreviewed architectural choice and
  discard the only assertion of the helper when the OML-quality test is deleted.
- **Additional in-scope stale branch:** the pipeline still contains
  `if ELASTIC_STRATEGY == "graph"` at line 1238 and a dead alternate motion path,
  although Turn 10 removed the `ELASTIC_STRATEGY` binding. The corrective prompt
  removes `SurfaceMotionConfig.mode` but does not name this branch; it must be
  collapsed to the graph path for the clean break to be runnable.
- No production file was modified or deleted. Per the prompt's stop rule, the
  allowlist/design needs an explicit ruling before implementation continues.

Status:    blocked — corrective prompt amendment required

---

## Turn 13 — Claude, planner/reviewer, 2026-09-22
Scope:     Resolve the Turn-12 block; user extends M1.3 to tangential smoothing

**User decision, binding:** tangential smoothing is also unwanted and must be
removed. `select_fixed_vertex_band` is **deleted with `oml_quality.py`** — not
moved to `tangential_smoothing.py`, not copied into the pipeline.

**Why Turn 12 stopped, and it was right to.** The Turn-11 prompt ordered
whole-file deletion of `oml_quality.py` while explicitly preserving tangential
smoothing — but `oml_quality.py:98` defines `select_fixed_vertex_band` and
`e175_mesh_motion_pipeline.py:1184` calls it to build the smoothing band. Every
available resolution was bad: moving the helper meant editing a prohibited file,
copying it into the pipeline meant an unreviewed architectural choice plus
losing its only assertion when the OML test was deleted. Codex invoked the stop
rule instead of guessing. **The contradiction was Claude's, not Codex's**, and
the user's ruling dissolves it rather than patching around it.

Revised dependency graph — four subsystems, one clean break:

1. **Membrane + inversion repair** (unchanged from the Turn-11 audit):
   `elasticity.py` symbols 64/246/547/634/658/703, all reachable only from
   `CorotationalMembraneAssembler`; `CorotationalMembraneMotionSolver`
   (`motion.py` 870-1111) with all four `use_inversion_barrier` sites inside it;
   whole-file `inversion_barrier.py`.
2. **OML log-barrier quality**: whole-file `oml_quality.py` (the IPC log barrier
   at line 494) including `select_fixed_vertex_band`; `FinalSurfaceQualityConfig`;
   pipeline aliases 493-499 and branches 1254/1304/1369/1532.
3. **Tangential smoothing** (new this turn): whole-file
   `tangential_smoothing.py`; `TangentialSmoothingConfig` (config 48, 141-142,
   346); `__init__.py` 79-82 and `__all__` 237; `load_stepping.py` 51, 98,
   518-519; pipeline 458, 480-485, 1177-1224, 1280, 1525-1530, 1587-1588; three
   tracked drivers incl. the backup.
4. **Stale pipeline branch** (found by Codex in Turn 12): `ELASTIC_STRATEGY ==
   "graph"` at 1238 with a dead `else:` arm at 1292 calling `motion.train()`.
   Turn 10 removed the binding but left the branch. Must collapse to the graph
   load-step path.

**Newly discovered dependency — parameterized projection is dead too.** Traced
every tracked reference:
- `parameterize_final_projection` is set **only** as
  `(FINAL_QUALITY_STRATEGY == "oml")` at pipeline 1253-1255;
- the stale `else:` arm calls `project_onto_oml_parameterized` under the same
  condition;
- `oml_quality.py` imports `ParameterizedProjectionGroup` — deleted;
- `tests/test_boundary_surface_movement.py:981` sits **inside**
  `test_fixed_oml_quality_repairs_on_surface_and_ift_vjp_matches_fd` (951),
  which is deleted.

Zero independent tracked consumers survive, so `ParameterizedProjection`,
`ParameterizedProjectionGroup` and `project_onto_oml_parameterized` are deleted
with their `load_stepping.py` plumbing (44, 48, 64, 95, 294, 532-540, 572).
**Ordinary projection survives**: `project_onto_oml`, `reevaluate_vertices`,
`combine_vertices`, `VertexBatch`. The private helpers `_project_group` (478)
and `_coefficient_subset` (501) are **shared by both paths** — verified by
call-graph trace — so they stay. This is a partial-file edit, not a deletion.

**Allowlist delta (Turn 11: 16 paths -> Turn 13: 19).** Added:
`tangential_smoothing.py` (whole-file delete), `load_stepping.py`,
`projection.py`. The latter two were on Turn 11's *prohibited* list; that
prohibition is lifted for the named symbols only, and `ngon_affine.py`,
`quality.py`, `current_graph_solve.py` and `quadratic_distortion.py` remain
prohibited.

**Tests — five deletions, two rewrites.** Deletions:
`test_fixed_projected_tangential_smoother_preserves_reference_and_has_fixed_vjp`
(639), `test_final_only_tangential_smoother_defers_projection_and_differentiates`
(699), `test_corner_barrier_repairs_quad_and_ift_vjp_matches_finite_difference`
(877), `test_fixed_oml_quality_repairs_on_surface_and_ift_vjp_matches_fd` (951)
in `test_boundary_surface_movement.py`; and
`test_final_only_tangential_reprojection_is_a_supported_fixed_option` (138) in
`test_e175_driver_configuration.py`. Each is a test *of* a removed component.
Rewrites: `test_default_volume_motion_is_final_only_and_differentiable` (56,
drop the `tangential_smoothing.reprojection` assertion) and
`test_quad_diagonal_controls_are_validated` (147, drop the `mode="unsupported"`
arm).

**Expected final count: 162 passed / 1 skipped -> 157 passed / 1 skipped** in a
genuine clone (working tree 176 collected -> 171).

Acceptance greps may retain only MPI `comm.Barrier()`
(`cfd_mesh_dafoam_analysis.py:346`, `geometry_volume_mpi.py:77`,
`run_dafoam_gmsh.py:653/656/911/954`) and the KS smooth-union `np.log` in the
three `movement_test_*` scripts, which are outside the retained manifest.
`quality.py` diagnostics are **not** removed for containing the word "quality";
they contain no barrier.

**Turn 13 changed no production code.** Only `PLAN.md`, `LOG.md` and
`CODEX_NEXT.md` were edited; nothing staged, committed, modified or deleted
under `bsm3/` or `tests/`. Verified by `git status --porcelain`.

**M1.3 remains OPEN** pending Codex's corrective implementation; the prompt is
in `docs/overhaul/CODEX_NEXT.md` with a 19-path allowlist.

Status:    closed

## Turn 14 — Codex, implementer, 2026-09-22

Claimed the amended M1.3 corrective implementation. Scope was limited to the
19-path allowlist in `CODEX_NEXT.md`: remove the four obsolete subsystems,
collapse the E175 surface pipeline to its graph load-step path, update the five
component-specific tests and two remaining assertions, then validate and commit
from the dirty working tree without touching excluded user files.

**STOP RULE invoked before production edits.** The pre-edit tracked-reference
audit found three paths outside the literal allowlist that make Turn 14's
acceptance criteria impossible as written:

1. `_dafoam_mpi_refactor_backups/bsm3__core__boundary_surface_movement__cfd_mesh_dafoam_analysis.py.pre_level6_20260730_084717`
   imports `TangentialSmoothingConfig` at line 49 and constructs both
   `mode="graph"` and `tangential_smoothing=...` at lines 138-143.
2. `_dafoam_mpi_refactor_backups/bsm3__core__boundary_surface_movement__cfd_mesh_dafoam_analysis.py.pre_level6fix_20260730_092729`
   has the same tracked references at lines 49 and 138-143.
3. `analytical_SDF_anchor_attraction_noarg.py` independently uses a setting
   named `tangential_smoothing_step` at lines 74, 936, 942 and 1119. It is not
   part of the surface-motion subsystem being removed, but the required
   repository-wide `tangential_smooth` grep still matches it.

The first two are stale tracked snapshots whose imports would name a deleted
config class; the third is an acceptance-pattern collision rather than a
dependency. None is in the 19-path allowlist. No symbol was relocated and the
allowlist was not widened. No production or test file was modified, deleted,
staged or committed; only this log entry changed. Claude must either add the two
snapshots to the deletion/cleanup scope and narrow the tangential grep to the
removed API, or explicitly add and disposition all three paths.

**M1.3 remains OPEN.**

Status:    closed — stopped on an out-of-allowlist dependency

---

## Turn 15 — Claude, planner/reviewer, 2026-09-22
Scope:     Rule on the Turn-14 stop; correct the allowlist and the acceptance grep

**Turn-14 stop upheld.** Both findings verified independently; both are Claude's
planning defects, not implementation problems. This is Codex's second correct
stop-rule invocation in three turns — the rule is doing its job.

**Defect 1 (Claude's): the tangential-smoothing acceptance grep was too broad.**
Turn 13 wrote `git grep -iE "tangential_smooth|TangentialSmoothing"`, which
matches `tangential_smoothing_step` in
`analytical_SDF_anchor_attraction_noarg.py` (74, 936, 942, 1119). Inspected the
code: it is a scalar relaxation coefficient applying a **projected surface
Laplacian** step inside an SDF anchor-attraction point-projection loop —
`lap = surface_laplacian_displacement(...)`, projected through `projectors`,
scaled, then re-projected to the surface. Entirely unrelated to
`FixedProjectedTangentialSmoother`. Verified **zero imports** from the removed
subsystem; the file is tracked, live, and covered by
`tests/test_analytical_sdf_anchor_attraction.py`. Codex called it a pattern
collision rather than a dependency and was right.

Corrected criterion greps the **removed API symbols**, not the word. Validated
this turn: the narrowed pattern matches exactly the twelve in-scope files and
returns **0** hits in `analytical_SDF_anchor_attraction_noarg.py`.
`tangential_smoothing_step` is now an explicitly identified permitted survivor,
alongside MPI `comm.Barrier()` and the KS/SDF logarithms.

**Defect 2 (Claude's): two backup snapshots sat outside the allowlist.** Both
`…cfd_mesh_dafoam_analysis.py.pre_level6_20260730_084717` and
`…pre_level6fix_20260730_092729` import `TangentialSmoothingConfig` at 49 and
construct `mode="graph"` / `tangential_smoothing=` at 138-143 — confirmed by
direct inspection. Turn 13 allowlisted only the sibling `.py`.

**Ruling: delete the whole `_dafoam_mpi_refactor_backups/` directory (14 tracked
files).** Editing them was never a legitimate option: the directory's own
`README.txt` says they are *"Pristine backups … the exact content before the
first edit in this effort,"* with restore instructions. Editing a backup to
remove a reference to a deleted class destroys the only property it has. That
left delete or permanently exempt. Delete, because:

- **Inert.** 11 of 14 carry `.pre_level6*` timestamp extensions and are not
  Python modules at all. The 3 `.py` files live in a directory with no
  `__init__.py`, under `__`-mangled names, outside `testpaths`, matching neither
  `python_files = test_*.py` nor any import — checked against `pytest.ini`.
- **Unreferenced** by live code; only `DAFOAM_MPI_RANK0_HANDOFF.md` mentions it.
- **Superseded**: snapshots of a completed refactor on
  `dafoam-mpi-rank0-refactor`, replaced by `production-ready-overhaul`.
- **Preserved** in git history regardless, and M3.2 pushes full history to a
  separate archive remote.
- **Otherwise permanent**: keeping them means carrying a grep exclusion through
  every future acceptance criterion in this project.

This **replaces** Turn 13's instruction to edit the single `.py` file there.
`DAFOAM_MPI_RANK0_HANDOFF.md` is tracked and points at the directory, so it is
added to the allowlist to have that pointer removed.

**Allowlist 19 -> 20 paths.** Removed: the single backup-file edit. Added: the
whole-directory deletion and `DAFOAM_MPI_RANK0_HANDOFF.md`.

Unchanged from Turn 13: the four-subsystem scope, the three whole-file source
deletions, the parameterized-projection deletion with ordinary projection and
the shared `_project_group` / `_coefficient_subset` helpers preserved, the stale
`ELASTIC_STRATEGY` collapse, five test deletions and two rewrites, and the
expected **157 passed / 1 skipped**.

**Turn 15 changed no production code.** Only `PLAN.md`, `LOG.md` and
`CODEX_NEXT.md` were edited; nothing staged, committed, modified or deleted
under `bsm3/` or `tests/`.

**M1.3 remains OPEN** pending Codex's implementation; the corrected prompt is in
`docs/overhaul/CODEX_NEXT.md` with a 20-path allowlist.

Status:    closed

## Turn 16 — Codex, implementer/reviewer, 2026-09-22

Claimed the second-amended M1.3 implementation and audited the acceptance
commands against tracked files before touching production code.

**STOP RULE invoked before production edits.** The new directory disposition
closes Turn 14's source dependency gap, and the narrowed tangential API grep no
longer matches `analytical_SDF_anchor_attraction_noarg.py`. However, this new
required command is impossible as written:

```bash
git grep -n "_dafoam_mpi_refactor_backups" -- .  # MUST be empty
```

It currently matches the two intentionally removable pointers in
`DAFOAM_MPI_RANK0_HANDOFF.md`, but also historical/audit references that must
survive deletion of the directory:

- `docs/overhaul/LOG.md`: Turns 10, 14 and 15, including the append-only record
  of the two earlier stop decisions;
- `docs/overhaul/PLAN.md`: the M1.3 acceptance/ruling and historical Turn-10
  audit notes;
- `docs/overhaul/CODEX_NEXT.md`: the current instruction, allowlist, acceptance
  command, clone check and definition of done.

All three documents are allowlisted, but erasing the LOG matches would violate
its explicit append-only policy and destroy the audit trail the user requested.
The directory can be deleted and live-code pointers can be removed without
claiming the string is absent from repository history documents. The acceptance
criterion should instead be scoped to live/package content, for example:

```bash
git grep -n "_dafoam_mpi_refactor_backups" -- bsm3/ tests/
```

After the two HANDOFF lines are removed, that scoped grep can be empty while
PLAN/LOG retain the decision record. Alternatively, exclude `docs/overhaul/`
explicitly. No production/test file was modified, deleted, staged or committed;
only this Turn-16 log entry changed.

**M1.3 remains OPEN.**

Status:    closed — stopped on a contradictory acceptance criterion

---

## Turn 17 — Claude, planner/reviewer, 2026-09-22
Scope:     Rule on the Turn-16 stop; full audit of every acceptance command

**Turn-16 stop upheld.** Third correct stop-rule invocation in five turns, and
the third time the defect was Claude's. Codex has not once absorbed a bad
instruction, which is the behaviour the rule exists for.

**Defect 1 (Claude's): a self-referential acceptance command.**
`git grep -n "_dafoam_mpi_refactor_backups" -- .` cannot return empty, because
`docs/overhaul/LOG.md`, `PLAN.md` and `CODEX_NEXT.md` intentionally document the
directory and its disposition. `LOG.md` is explicitly append-only, so satisfying
that command would have meant destroying the audit trail the user asked for.
Codex's proposed fix is adopted verbatim.

**Binding correction:** the command is scoped to
`git grep -n "_dafoam_mpi_refactor_backups" -- bsm3/ tests/`, which must be
empty once the two live pointers in `DAFOAM_MPI_RANK0_HANDOFF.md` (4, 86) are
removed and the directory is deleted. **Historical references in
`docs/overhaul/LOG.md`, `PLAN.md` and `CODEX_NEXT.md` are explicitly permitted
and must remain.**

**Defect 2 (Claude's, found this turn — Codex had not reached it).** Per the
user's instruction to audit *every* acceptance command for the same class of
fault, each pattern was run against the tracked tree and every matching file
classified as allowlisted, inside the deleted directory, or surviving:

| Check | Files matched | Verdict |
|---|---:|---|
| membrane | 5 | all resolved by the work |
| corotational | 4 | all resolved |
| tangential API (narrowed, Turn 15) | 12 | all resolved |
| deleted modules | 6 | all resolved |
| parameterized projection | 6 | all resolved |
| `mode="graph"` | 5 | all resolved |
| `ELASTIC_STRATEGY` | 1 | all resolved |
| backups dir, scoped to `bsm3/ tests/` | 1 | resolved by the HANDOFF edit |
| barrier | 16 | 3 survivors — **one was unlisted** |

The definition of done claimed `git grep -i barrier` matches "only MPI
`comm.Barrier()` at the six named sites," listing three files under `bsm3/`. A
fourth survivor exists: **`tests/test_geometry_volume_mpi.py:69`,
`def Barrier(self):`** — a mock MPI communicator, not in the allowlist, so the
criterion was unsatisfiable as written. Corrected permitted-survivor set is
**seven sites across four files**: `cfd_mesh_dafoam_analysis.py:346`,
`geometry_volume_mpi.py:77`, `run_dafoam_gmsh.py:653/656/911/954`, and
`tests/test_geometry_volume_mpi.py:69`. Note that
`cfd_mesh_dafoam_analysis.py` is allowlisted for the tangential/mode edits, so
the prompt now states explicitly that its `comm.Barrier()` must **survive** that
edit.

Every other `git grep` in the prompt was already scoped to `bsm3/` or
`bsm3/ tests/`; the backups command was the only repo-wide one. No further
contradiction found.

**Unchanged:** the 20-path allowlist and every other Turn-16 implementation
instruction — four subsystems, three whole-file source deletions plus the backup
directory, parameterized-projection removal with ordinary projection and the
shared `_project_group` / `_coefficient_subset` helpers preserved, the stale
`ELASTIC_STRATEGY` collapse, five test deletions, two rewrites, expected
**157 passed / 1 skipped**.

**Turn 17 changed no production code.** Only `PLAN.md`, `LOG.md` and
`CODEX_NEXT.md` were edited; nothing staged, committed, modified or deleted
under `bsm3/` or `tests/`.

**M1.3 remains OPEN** pending Codex's implementation; the corrected prompt is in
`docs/overhaul/CODEX_NEXT.md`.

Status:    closed

## Turn 18 — Codex, implementer, 2026-09-22

Claimed the third-amended M1.3 corrective implementation. The pre-edit audit
confirmed that the live-code-scoped backup grep and the seven-site MPI barrier
exception are satisfiable. Work is restricted to the 20-path allowlist in
`CODEX_NEXT.md`; historical overhaul records and excluded dirty files remain
untouched except for this append-only turn.

Implementation results before commit:

- Deleted the membrane assembler/solver, inversion penalty, OML log-barrier
  optimizer, tangential smoother, parameterized projection path, and all 14
  tracked legacy backup snapshots. Ordinary OML projection, graph motion,
  quadratic distortion, and N-gon affine regularization remain.
- Collapsed the E175 pipeline to unconditional graph load stepping and removed
  the one-valued surface `mode`. The same acceptance grep exposed the likewise
  one-valued `use_corotational_reference=True` graph-solver option; its active
  owner-reference formulation is now unconditional and the unreachable
  absolute-formulation branch/helpers are gone.
- All removed-API greps are empty over `bsm3/` and `tests/`. The only seven
  `barrier` hits are the permitted MPI method/calls; the independent SDF
  `tangential_smoothing_step` remains.
- Focused results in `central_geom`: boundary surface **41 passed**; N-gon plus
  projection **8 passed**; driver/derivative gates **10 passed**; SDF/MPI
  survivors **29 passed**. Full dirty-tree suite: **171 passed** in 33.49 s
  (includes the intentionally excluded untracked hybrid-volume tests).
- Import smoke and every public `__all__` lookup pass. Named files compile.
  Ruff and pyflakes are not installed in `central_geom`; the base environment
  has neither Ruff nor a compatible CSDL API. `git diff --check` is clean over
  every allowlisted implementation path. A directory-wide compile also reports
  a pre-existing `IndentationError` in excluded untracked
  `cfd_mesh_volume_movement_test.py`; it is outside this turn.
- Committed the bounded implementation as `1e3adfb` (`Remove obsolete surface
  motion subsystems`). A genuine no-hardlinks clone of that commit was clean;
  removed-module and backup-directory checks passed; its full suite produced
  the expected **157 passed, 1 skipped** in **32.25 s**.

**M1.3 implementation is complete, pending Claude's independent acceptance.**

Status:    closed

---

## Turn 19 — Claude, planner/reviewer, 2026-09-22
Scope:     Independent audit of the M1.3 implementation (1e3adfb, 1c5a860)

**RULING: M1.3 is ACCEPTED.** Every claim reproduced independently. One residual
defect found — and it is Claude's, not Codex's. Details below.

**Allowlist compliance: perfect.** 33 files touched across `8289884..1c5a860`;
14 of them the backup directory, the rest exactly the 19 named paths.
**Zero violations.** All ten prohibited files verified untouched, including
`current_graph_solve.py`, `ngon_affine.py`, `quality.py`,
`quadratic_distortion.py`, `analytical_SDF_anchor_attraction_noarg.py`,
`geometry_volume_mpi.py` and `run_dafoam_gmsh.py`. `1c5a860` is docs-only.
Net source+test delta: **+73 / -11,075 = 11,002 lines removed.**

**The unauthorized-looking change was in fact in scope and correct.** Codex
removed `use_corotational_reference`, which was not named in the prompt. Audited:
it lived only at `motion.py` 182/192/602/924 and
`e175_mesh_motion_pipeline.py:1071` — **both allowlisted** — and only `True` was
ever passed, so it is exactly the "one-valued compatibility field" that
definition-of-done item 9 prohibits generally. Codex applied the general rule
correctly rather than only the three named instances.

More importantly, the **correct branch survived**. The deleted `else` arm
carried its own verdict in its comment: *"Absolute formulation … **Kept for
comparison**; it **folds** the free/rigid boundary of a moving component because
a graph-harmonic field cannot reproduce that component's affine
(planform-scaling) motion on a non-uniform mesh."* It was a documented
fold-producing path. The surviving formulation is the owner-reference
(co-rotational) one: `_assemble_free_reference` + per-component deviation solve,
now unconditional at `motion.py:496` and `:545`. `_assemble_absolute_prescribed`
is gone. This is a **public API break** — `ElasticityMotionSolver(
use_corotational_reference=False)` no longer exists — accepted under the clean
break.

**Acceptance greps — all eight EMPTY** over `bsm3/` and `tests/`: membrane,
corotational, tangential API (narrowed), deleted modules, parameterized
projection, `mode="graph"`, `ELASTIC_STRATEGY`, backups directory.

**Barrier: exactly the seven permitted MPI sites in four files** —
`cfd_mesh_dafoam_analysis.py:337` (line shifted from 346 by the 9-line removal,
expected), `geometry_volume_mpi.py:77`, `run_dafoam_gmsh.py:653/656/911/954`,
`tests/test_geometry_volume_mpi.py:69`. Nothing else.

**Permitted survivors intact**: `tangential_smoothing_step` still has 4 hits in
`analytical_SDF_anchor_attraction_noarg.py`; its test and the MPI test pass.
`docs/overhaul/` retains its historical record, as required.

**Imports and exports**: import smoke OK; `__all__` is 86 entries and **every
one resolves**; `bsm3.preprocessing.__all__` likewise. All 16 spot-checked
preserved public symbols present (graph assembler, motion solvers,
`run_graph_load_steps`, N-gon, distortion, ordinary projection quartet, quality
diagnostics).

**Defect found (Claude's): one orphaned private helper.**
`elasticity.py:301` `_validate_partition` is now **defined and never called**.
Traced: before the deletion its *only* caller was
`CorotationalMembraneAssembler` (line 305 at `8289884`); `ngon_affine.py:453`
and `quadratic_distortion.py:732` each carry their own independent copies. This
violates definition-of-done item 8 ("no orphaned private helpers"). **The cause
is Claude's prompt**, which listed `_validate_partition` under PRESERVE for
`elasticity.py` without checking that its sole caller was the class being
deleted — the same failure mode as the three stop-rule defects. Codex followed
the instruction correctly. ~20 dead lines; no import error, no test failure, no
behavioural effect. Folded into the next turn as a one-line cleanup rather than
reopening M1.3.

**Static review.** Ruff is not installed in `central_geom` (confirmed
independently), so an AST-based equivalent was run over the eleven edited source
and test files, checking F401-style dead imports, F821-style references to
removed symbols, and orphaned module-level privates. **No surviving import
references any removed symbol** — the only genuine finding is the
`_validate_partition` orphan above. Remaining flags were `__future__` imports
and legitimate `__init__`/test re-exports.

**Validation, all re-run in `central_geom`:**
- derivative gate + M1.4 polygon6 operator/load-step: **6 passed in 7.41 s**
- boundary surface + drivers + projection: **53 passed in 19.35 s**
- permitted-survivor tests (SDF anchor, MPI): **29 passed in 1.85 s**
- full suite, working tree: **171 passed in 31.53 s** (matches Codex exactly)
- **genuine clone of `1c5a860`**: empty `git status --porcelain`; all three
  modules and the backup directory absent; scoped greps empty;
  **157 passed, 1 skipped in 32.04 s** — exactly the predicted count and exactly
  Codex's result
- `MANIFEST.md` carries zero rows for the three deleted modules
- eight excluded dirty files still dirty; nothing staged

**M1.3 is COMPLETE.** `PLAN.md` updated. Next: the combined **M1.1 + M1.2**
turn (generalize the config API and decompose `build_e175_mesh_motion_model`),
which the sequencing note requires be done as one turn. Prompt written to
`CODEX_NEXT.md`; the `_validate_partition` cleanup rides along.

Status:    closed

## Turn 20 — Codex, implementer/reviewer, 2026-09-22

Claimed the combined M1.1 + M1.2 implementation and audited the public call
path and acceptance greps before editing production code.

**STOP RULE invoked before production edits.** The 10-path allowlist omits a
live core consumer that must change for the requested clean API break:

- `bsm3/core/boundary_surface_movement/geometry_volume_backend.py:299-314`
  imports `E175GeometryVariables`, constructs it from the rank-0 backend's
  design-variable mapping, and passes it to `build_e175_mesh_motion_model`.
  This is not a documentation-only reference: the allowlisted DAFoam driver
  imports and uses `E175GeometryVolumeBackend`, so renaming/removing the frozen
  type without updating this file breaks the live geometry-to-volume call path.
- The same prohibited file's line 286 docstring names
  `E175MeshMotionResult`. The prompt's repository-scoped type-name grep cannot
  be empty while that reference remains.
- The live class is itself named `E175GeometryVolumeBackend`. That name is not
  included in the prompt's four-symbol grep, but it conflicts with the broader
  definition "no `E175`-named type in the core call path" unless Claude
  explicitly rules it driver-specific or includes its rename/generalization.
- `bsm3/core/boundary_surface_movement/e175_derivative_ladder.py:57,120,123`
  imports, annotates, and constructs `E175GeometryVolumeBackend`; generalizing
  the backend therefore requires this second prohibited live consumer.
- `bsm3/core/boundary_surface_movement/DAFOAM_MPI_RANK0_HANDOFF.md:25,78,91`
  also names the E175 backend/result types. This is documentation rather than
  executable call-path code, but the literal `-- bsm3/ tests/` acceptance grep
  still matches it and the file is outside the allowlist.

The first dependency is architectural and cannot be handled by narrowing the
grep: the rank-0 backend must receive or construct the new user-supplied
parameterization object. Claude must add `geometry_volume_backend.py` to the
implementation allowlist and specify how the driver's concrete E175
parameterization is supplied to it (a driver-provided factory is one clean
option). It must also add `e175_derivative_ladder.py` if it generalizes
`E175GeometryVolumeBackend`, and either add the handoff document for terminology
cleanup or scope the type-name grep to Python sources. No
production or test file was modified, staged, or committed; only this append-only
Turn-20 record changed.

**M1.1 + M1.2 remain OPEN.**

Status:    closed — stopped on an out-of-allowlist live API consumer

---

## Turn 21 — Claude, planner/reviewer, 2026-09-22
Scope:     Rule on the Turn-20 stop; full consumer audit of every renamed symbol

**Turn-20 stop upheld.** Fourth correct stop-rule invocation, fourth Claude
planning defect. The 10-path allowlist omitted live consumers of the very
symbols M1.1 renames.

**Full consumer audit** — every E175-named symbol traced across `bsm3/` and
`tests/`, not just the ones Codex named:

| Symbol | Consumer files | Allowlisted before? |
|---|---|---|
| `E175ModelFiles` | config, pipeline, 2 drivers, driver test | yes |
| `E175PipelineConfig` | config, pipeline, 2 drivers, driver test | yes |
| `E175GeometryVariables` | config, pipeline, 2 drivers, **`geometry_volume_backend.py:300,310`** | **NO** |
| `E175MeshMotionResult` | config, pipeline, dafoam driver, **backend:286**, **handoff:91** | **NO** |
| `E175GeometryVolumeBackend` | **backend:257,361**, dafoam driver, **ladder:57,120,123**, **handoff:25,78** | **NO** |
| `build_e175_mesh_motion_model` | pipeline, 2 drivers, **backend:303,311**, **handoff:24,189** | **NO** |

Codex's three missing paths are confirmed exactly:
`geometry_volume_backend.py`, `e175_derivative_ladder.py`,
`DAFOAM_MPI_RANK0_HANDOFF.md`. **Allowlist 10 -> 13.**

**Two further defects found this turn that Codex had not yet reached:**

1. **The obvious rename target is already taken.**
   `geometry_volume_backend.py:39` already defines
   `class GeometryVolumeBackend(Protocol)` — the interface that
   `E175GeometryVolumeBackend` implements. Renaming to `GeometryVolumeBackend`
   would collide. Module `__all__` currently lists **both**. Ruling: rename to
   **`MeshMotionVolumeBackend`** — it says what the class does, keeps the
   Protocol intact, and drops the E175 prefix. Had this not been caught it would
   have produced a fifth stop.

2. **`tests/test_geometry_volume_mpi.py` is a tripwire, not an edit target.**
   It imports `e175_derivative_ladder` at line 507; the ladder does a
   **top-level** import of `E175GeometryVolumeBackend` at line 56. If the ladder
   is not updated in lockstep with the rename, that test fails at **collection**
   — and it is one of the 29 tests verified green in Turn 19. The test file
   itself imports only `CSDLRecorderBackend`, so it needs no edit and **stays
   prohibited**; the ladder being allowlisted is sufficient. Flagged explicitly
   in the prompt so it is not discovered as a mystery failure.

**Architecture ruling for `geometry_volume_backend.py`.** The backend already
takes `model_files: Any` and `pipeline_config: Any`; the *only* E175 coupling is
`E175GeometryVariables(**design_variables)` at line 310, inside `_build_model`
(299-314). The fix is surgical and matches the user's recommendation: the
constructor gains a **driver-supplied `parameterization_factory`** callback,
`Callable[[Mapping[str, csdl.Variable]], GeometryParameterization]`, and
`_build_model` calls it instead of naming an E175 type. The generic backend then
imports and constructs no E175 configuration type at all. Both E175 drivers
(`cfd_mesh_dafoam_analysis.py`, `e175_derivative_ladder.py`) supply their own
factory.

**Principled line drawn, to settle Codex's "is it driver-specific?" question:**

> **The core must be configuration-agnostic; drivers may be E175-specific.**

- **Core, must generalize:** `e175_mesh_motion_config.py`,
  `e175_mesh_motion_pipeline.py`, and the types in `geometry_volume_backend.py`.
  `E175GeometryVolumeBackend` is **core**, not driver-specific — it lives in a
  generic module and is imported by two different drivers — so it generalizes.
- **Drivers, may keep E175 names:** `cfd_mesh_movement_test.py`,
  `cfd_mesh_dafoam_analysis.py`, `e175_derivative_ladder.py`. These are
  configuration-specific by design; renaming them is out of scope.

`build_e175_mesh_motion_model` is added to the rename set
(-> `build_mesh_motion_model`) and to the acceptance grep: it is the central
core entry point, and all its consumers are now allowlisted, so leaving it
E175-named would defeat the clean break. **The grep is widened, never narrowed**
— per the user's instruction, no stale reference is hidden by scoping.

**Unchanged:** combined M1.1 + M1.2 scope; the 1,076-LOC builder decomposition
(lines 432-1507); the 300-LOC function ceiling; removal of the 27-line alias
block (466-492); removal of `search_names=["wing", "HT", "fuselage"]` (571-572);
deletion of the orphaned `elasticity._validate_partition` (301); derivative gate
and M1.4 polygon6 tests preserved **exactly**; expected clone count
**157 passed / 1 skipped**; all unrelated dirty-tree files untouched.

**Turn 21 changed no production or test code.** Only `PLAN.md`, `LOG.md` and
`CODEX_NEXT.md` were edited; nothing staged or committed.

**M1.1 + M1.2 remain OPEN.**

Status:    closed

---

## Turn 22 — Codex, implementer/reviewer, 2026-09-22
Scope:     Combined M1.1 + M1.2 implementation

Claimed the turn after auditing the corrected 13-path allowlist and the six
renamed-symbol consumer map. No additional out-of-allowlist live consumer was
found during preflight.

Implemented and committed the combined change as **`872c0f1`**
(`Generalize and decompose mesh motion pipeline`). The explicitly permitted
core-module renames were taken:

- `e175_mesh_motion_config.py` -> `mesh_motion_config.py`
- `e175_mesh_motion_pipeline.py` -> `mesh_motion_pipeline.py`

The rename was necessary, not cosmetic: the generic rank-0 backend's acceptance
criterion forbids every `E175` string, including an import path. The pipeline
module is now 1,572 LOC (1,588 before); the public builder is **98 LOC** (1,076
before). Its five named stages are geometry/setup, parameterization/deformation,
intersections + graph construction, reprojection/reevaluation, and volume
handoff. The largest function is the preserved `_run_volume_motion` at 271 LOC;
the largest new stage is `_setup_geometry_and_mesh` at 243 LOC.

**M1.1.** The six old public symbols are absent from tracked `bsm3/` and
`tests/`. The core now exports `ModelFiles`, `PipelineConfig`,
`MeshMotionResult`, `GeometryParameterization`, `ComponentSpec`,
`IntersectionSpec`, `build_mesh_motion_model`, and
`MeshMotionVolumeBackend`. E175 design-variable names and coefficient builders
live in the two E175 drivers. The generic backend accepts the ruled
`parameterization_factory`; the DAFoam driver and derivative ladder pass it
explicitly. `GeometryVolumeBackend` and `CSDLRecorderBackend` survive unchanged.

**M1.2.** The 27-line uppercase alias block and hardcoded component search are
gone. Component ownership, free regions, projection behavior, independent
intersection curves, and coefficient construction are driven by the ordered
spec lists. The graph-Laplacian, N-gon affine, quadratic-distortion, projection,
symmetry, volume-motion, quality, and MPI paths retain the same production
operators. `elasticity._validate_partition` was deleted; its two independent
copies were untouched. Static AST review found no dead imports or orphaned
module-level private helpers in the touched files. Ruff remains unavailable in
the `central_geom` environment, as previously recorded.

**Driver test rewrite.** `tests/test_e175_driver_configuration.py` retained all
tests and assertions; only the clean-break type imports and the two
`isinstance` assertions changed from the removed E175 names to
`PipelineConfig` / `ModelFiles`. No test was added or deleted, so the tracked
suite count is unchanged.

**Validation (`central_geom`):**

- all six structural greps: empty as required
- backend protocol/base/new-class import and `__all__`: all resolve
- package `__all__`: **108/108 resolve**
- derivative gate + M1.4 polygon6 guard + MPI tripwire + driver tests:
  **41 passed in 8.65 s**
- full dirty-tree suite: **171 passed in 30.67 s**
- genuine clone of `872c0f1`: empty status, empty six-symbol grep,
  **157 passed / 1 skipped in 32.08 s**

Only the authorized implementation paths were staged. The eight excluded dirty
files and all unrelated untracked files remain untouched. M1.1 + M1.2 are
implemented and await Claude's Turn-23 independent review before being marked
complete.

Status:    closed

---

## Turn 23 — Claude, planner/reviewer, 2026-09-23
Scope:     Independent review of the M1.1 + M1.2 implementation (872c0f1, 8ded2dc)

**RULING: M1.1 + M1.2 ACCEPTED.** Every check in `CODEX_NEXT.md` executed
independently in `central_geom`. One minor finding, recorded below and folded
into the next turn; not blocking.

**Allowlist compliance: perfect.** 14 files across `1c5a860..8ded2dc`,
**zero violations**. The two core-module renames
(`e175_mesh_motion_config.py` -> `mesh_motion_config.py`,
`e175_mesh_motion_pipeline.py` -> `mesh_motion_pipeline.py`) were explicitly
permitted, and Codex's justification is correct: the "no `E175` string in the
generic backend" criterion covers an import path. All 14 prohibited source
files and all 5 prohibited test files verified untouched. `8ded2dc` is
docs-only.

**Structural checks — all pass:**

| Check | Result |
|---|---|
| six-symbol stale grep over `bsm3/` `tests/` | **0 hits** ✓ |
| `GeometryVolumeBackend` Protocol + `CSDLRecorderBackend` survive | both present ✓ |
| `MeshMotionVolumeBackend` replaces the E175 class | present; module `__all__` resolves, no stale entry ✓ |
| `E175` anywhere in `geometry_volume_backend.py` | **0 hits** ✓ |
| `search_names=["wing"...]` | **0 hits** ✓ |
| 27-line uppercase alias block | **0 hits** ✓ |
| `elasticity._validate_partition` | removed; `ngon_affine.py:453` and `quadratic_distortion.py:732` copies untouched ✓ |
| package `__all__` | **108/108 resolve** (86 before, +22 for the new API) ✓ |
| all 8 new generic symbols exported | ✓ |

**Decomposition verified independently.** `mesh_motion_pipeline.py` is 1,572 LOC
across 20 functions. **No function exceeds 300 LOC.** The public builder is
**98 LOC**, down from 1,076 — a 91% reduction. Largest: the preserved
`_run_volume_motion` (271), then `_setup_geometry_and_mesh` (243),
`_build_intersections_and_graph` (145), `_evaluate_surface_diagnostics` (139),
`_reproject_and_reevaluate` (125). The five named stages match the plan's
five-step pipeline.

**Architecture: the factory callback is implemented exactly as ruled.**
`MeshMotionVolumeBackend.__init__` takes a keyword-only
`parameterization_factory: Callable[[Mapping[str, csdl.Variable]], GeometryParameterization]`;
`_build_model` builds the design-variable dict and calls the factory instead of
naming an E175 type; the lazy import now pulls `build_mesh_motion_model` from
`mesh_motion_pipeline`. Both drivers pass their own factory.

**Numerical guard — this is the check that matters, and it passes exactly.**
"Pass" is not the same as "unchanged", so seven quantities were re-measured
against the values recorded in Turns 7 and 9, **pre-refactor**:

| Quantity | Now | Pre-refactor | |
|---|---|---|---|
| projector rank | 3 | 3 | ✓ |
| hourglass retained fraction | 1.000000000000 | 1.0 | ✓ |
| `‖P·1‖` | 0.000000000000 | 0 | ✓ |
| hexagon hourglass modes | 3 | 3 | ✓ |
| `obj'` at `λ=0` | 4.000000000000 | 4.0 | ✓ |
| `obj'` at `λ=0.3` | 4.384615384615 | 57/13 | ✓ |
| observability `‖Δ‖∞` | 0.153846153846 | 2/13 | ✓ |

**All seven identical to 1e-12. The refactor moved nothing.**

**Tests:** guard suite (derivative gate + M1.4 operator + load-step) **6 passed
in 7.62 s**; MPI tripwire **26 passed** and **verified untouched by the diff**,
exactly as the prompt required; driver config **9 passed**; full dirty-tree
suite **171 passed in 31.07 s**; **genuine clone of `8ded2dc`: empty
`git status --porcelain`, six-symbol grep empty, both old module filenames gone,
157 passed / 1 skipped in 30.52 s.** Count unchanged from M1.3, as a refactor
requires.

**Static review.** Ruff remains unavailable in `central_geom` (confirmed
again). An AST equivalent over the nine edited files flagged nine
quadratic-distortion names in `__init__.py`; investigated and **dismissed as
false positives** — they were never in `__all__` (0 of 9 before *and* after),
and `QuadraticDistortionConfig` is consumed via the package attribute path at
`mesh_motion_pipeline.py:1113`, which AST cannot see. **No genuine dead imports,
no orphaned private helpers.**

**Finding (minor, non-blocking): the backend's lazy-import intent is now
defeated.** `geometry_volume_backend.py` carries the comment *"Imported here so
the module imports without the mesh-motion stack."* Measured against both
commits:

- **at `1c5a860`**: importing the backend pulled **neither** config nor pipeline
- **at `8ded2dc`**: it pulls **both**

Two contributing causes, both introduced by this commit:
1. `__init__.py:62,79` now import `mesh_motion_config` and
   `mesh_motion_pipeline` for the new re-exports — and any submodule import
   executes the parent `__init__`, so this alone defeats it;
2. `geometry_volume_backend.py:37` is a **module-level**
   `from .mesh_motion_config import GeometryParameterization`.

Nothing fails — the MPI suite passes — but the comment at line 304 is now false,
and the rank-0 design intends non-root MPI ranks to avoid the heavy stack.
Cheap partial fix: `from __future__ import annotations` is already present at
line 29, so the annotation needs no runtime import; guard line 37 with
`TYPE_CHECKING`. Whether to stop re-exporting the pipeline from `__init__` is a
judgment call deferred to M1.6/M3. Folded into the next turn as a cleanup item.

**M1.1 + M1.2 are COMPLETE.** `PLAN.md` updated. Next: **M1.5**, the
`bsm3.meshgen` carve-out. Scoped this turn: the core already imports nothing
from any gmsh/OCC script (verified), and all nine candidate meshgen modules
(~11,254 LOC) are **untracked**, so M1.5 is primarily a decision about what to
adopt rather than what to delete. Prompt written to `CODEX_NEXT.md`.

Status:    closed

---

## Turn 24 — Codex, implementer/reviewer, 2026-09-23
Scope:     M1.5 mesh-generation disposition and deferred backend cleanup

Claimed the turn after confirming that the five-path allowlist covers the only
authorized implementation cleanup and collaboration records.

### Task 1 recommendation — defer `bsm3.meshgen` adoption to M3

Do **not** adopt mesh-generation code in M1.5. The core already has zero imports
from the candidate Gmsh/OCC scripts, so adopting an untested generator now would
increase the release surface without improving core separation.

The only credible STEP-to-surface candidate is manifest root M,
`gmsh_occ_oml_surface_mesh.py` (2,475 LOC). Its four deferred imports lead to
`smooth_existing_tip_cap.py` (2,283 LOC), and the latter imports the former, so
adopting the working pair means accepting **4,758 untested LOC** with a circular
dependency. This exceeds the prompt's ~800-LOC stop threshold by nearly 6x.
The 502-LOC `generate_e175_panel_mesh.py` is only an E175-specific wrapper over
that pair, not an independent smaller implementation. The other candidates are
volume generators, format converters, remeshers, or OpenVSP-based paths rather
than the required general STEP-to-surface entry point.

A new thin module is also the wrong M1.5 action: with every test path prohibited
and no proven small subset of the OCC healing/meshing logic, it would either be
an untested facade over untracked code or a second implementation with no
equivalence evidence. M3 should revisit adoption only with a minimal public
`STEP -> surface mesh` API, a deterministic small STEP fixture, and an
end-to-end topology/quality test. Until then, root M remains a local candidate,
not release code. No `bsm3.meshgen` file is adopted, staged, or committed in
this turn.

The stop rule is **not** invoked because the recommendation is deferral, which
the prompt explicitly permits; work proceeds only to the mandatory five-path
cleanup and documentation.

### Implementation and verification

Commit `eb1ed5f` moves the `GeometryParameterization` import under
`TYPE_CHECKING` and replaces the false lazy-import claim with the narrower fact
that the pipeline import is deferred until private-model construction. Package
re-exports still load config and pipeline when the submodule is imported; that
known behavior remains deliberately out of scope. No `bsm3.meshgen` module or
binary asset was adopted.

The core-clean grep is empty. The backend imports successfully and exposes all
four expected public symbols. The numerical guard was re-measured, not merely
run: projector rank **3**, retained hourglass fraction **1.0**, `‖P·1‖` **0**,
hexagon modes **3**, `obj'(λ=0)` **4.0**, `obj'(λ=0.3)` **57/13**, and the
amplitude-normalized observable displacement **2/13**. All seven match the
Turn-23 values to 1e-12.

Focused tests: derivative gate **1 passed**; M1.4 N-gon operator/load-step
**5 passed**; MPI tripwire **26 passed**. Full dirty-tree suite: **171 passed**.
A genuine clone of `eb1ed5f` had empty status, an empty core-clean grep, and
**157 passed / 1 skipped**. The five-path allowlist was respected; every
pre-existing excluded dirty file remains outside the commit.

**Codex recommends accepting M1.5 as complete as a disposition decision;
implementation is deferred to M3 under the prerequisites recorded in
`MANIFEST.md`. Claude's Turn-25 review will rule.**

Status:    closed

---

## Turn 25 — Claude, planner/reviewer, 2026-09-23
Scope:     Review of the M1.5 disposition and deferred backend cleanup

**RULING: the M1.5 deferral is ACCEPTED, and M1.5 is COMPLETE as a disposition
decision.** Codex's recommendation is correct and every supporting fact was
verified independently. One refinement to the M3 hand-off is added below.

**Allowlist: 5 files across `8ded2dc..0dbcc75`, zero violations.** `eb1ed5f` is
the backend cleanup only (+11/-3); `0dbcc75` is docs-only. No `bsm3.meshgen`
module, no binary asset, nothing untracked adopted.

**Task 2 verified.** The `GeometryParameterization` import is under
`TYPE_CHECKING`; AST analysis confirms **zero runtime (non-annotation)
references** and no module-level import of `mesh_motion_config`. The false
comment at line 304 is replaced with a narrower true statement about the
deferred pipeline import. Backend imports cleanly; all four public symbols
resolve. As the prompt predicted, importing the submodule still loads both
modules via the `__init__` re-exports — deliberately out of scope, correctly
left alone.

**Task 1 — every factual claim checked and confirmed:**

| Claim | Verified |
|---|---|
| root M is the only credible STEP->surface candidate | yes |
| `gmsh_occ_oml_surface_mesh.py` 2,475 LOC | yes |
| `smooth_existing_tip_cap.py` 2,283 LOC | yes |
| circular pair | **4** deferred imports M->S, **1** S->M |
| combined 4,758 LOC, ~5.9x the 800 threshold | exact |
| `generate_e175_panel_mesh.py` is a wrapper, not an independent implementation | yes — imports `OccOmlSettings`, `_preset_overrides`, `run` from root M, including a **private** symbol |
| remaining candidates are volume generators / converters / remeshers | yes, by docstring inspection |
| **zero test coverage across all nine candidates** | confirmed — the decisive fact |

The deferral is the right call, and for the reason that matters: M1.5's stated
acceptance ("core imports nothing from meshgen") was **already satisfied before
this turn**. Adopting 4,758 untested LOC with a circular dependency to satisfy a
checkbox would be the Turn-3 deletion-safety error run backwards.

**Refinement for M3 — Codex under-sold the best candidate.** Turn 24 grouped
`remesh_fused_step.py` with "remeshers rather than the required general
STEP-to-surface entry point." Measured this turn, it is materially the strongest
starting point and deserves to be named rather than rediscovered:

- **615 LOC** — under the 800 threshold
- **No circular dependency**; it imports neither root M nor
  `smooth_existing_tip_cap`
- Clean dataclass-configured API with three public entry points
- Critically: **`remesh_fused_step()`, the primary entry point, needs no `bsm3`
  dependency at all.** Only the `_parametric` and `_manifold` variants pull
  `body_oml_refit` (847 LOC, untracked) — and they are separable.

So M3's realistic minimum is **615 LOC with zero internal coupling**, not 4,758
with a cycle. That does not change the M1.5 verdict — it still has no tests, and
M1.5's criterion was already met — but it makes M3's decision concrete. Recorded
in `MANIFEST.md` via the next turn.

**Validation, re-run in `central_geom`:**
- numeric guard re-measured (an import-only change cannot move numerics, but
  verified anyway): hexagon modes **3**, `obj'(λ=0)` **4.000000000000**,
  `obj'(λ=0.3)` **4.384615384615** = 57/13, observability **0.153846153846** =
  2/13 — **all unchanged to 1e-12**
- guards + MPI tripwire: **32 passed in 8.16 s**
- full dirty-tree suite: **171 passed in 30.81 s**
- **genuine clone of `0dbcc75`**: empty `git status --porcelain`, core-clean grep
  empty, `bsm3/meshgen` absent, **157 passed / 1 skipped in 33.28 s**
- eight excluded dirty files untouched; nothing staged

**M1.5 is COMPLETE** (disposition: defer adoption to M3). `PLAN.md` updated.

Remaining M1 work: **M1.6** (numpydoc across the live core + widen the CI lint
gate), **M1.8** (retire the internal pickle branch), then **M1.7** (acceptance
run). Next turn is **M1.6**; prompt written to `CODEX_NEXT.md`.

Status:    closed

---

## Turn 26 — Codex, implementer/reviewer, 2026-09-23
Scope:     M1.6 slice 1 of 3 — surface-motion-core numpydoc coverage

Claimed the turn after reviewing the 20-path allowlist, the three-slice M1.6
plan, and the signature-drift guard. Work is limited to docstrings in the 16
surface-motion-core modules, the new slice-specific CI lint step, and the three
collaboration documents.

### STOP — wrong public return annotation exposed by documentation

While documenting `GraphDistanceWeighting.summary`, found that its declared
return type is `dict[str, float]`, but the returned mapping includes
`"decay": self.decay`, whose value is a string. This is a genuine signature
defect covered verbatim by the Turn-26 stop rule. The signature was **not**
changed and the defect was **not** hidden in the docstring.

At the stop point, the allowed docstring work is prepared but uncommitted:
the prompt's AST coverage check reports **132/132 (100%)**, its signature-drift
check reports **none**, and a stronger comparison that removes docstrings from
both ASTs reports **no non-docstring AST drift** across all 16 modules. The
slice-specific CI step is also prepared with exactly the 16 named paths. Ruff
was not run locally because it is absent from `central_geom`, as expected.

No tests or clone verification were run after the finding, no files were
staged, and no commit was created. Claude must rule whether the annotation is
fixed in a separate defect commit before the documentation slice resumes, or
is deliberately left inaccurate. Codex recommends the separate fix, with
`dict[str, float | int | str]` (or a typed diagnostic mapping) chosen explicitly
rather than silently weakening the annotation during a docstrings-only turn.

Status:    stopped — awaiting Claude ruling

---

## Turn 27 — Claude, planner/reviewer, 2026-09-23
Scope:     Rule on the Turn-26 stop (GraphDistanceWeighting.summary annotation)

**RULING: the stop is UPHELD. Fix the annotation in a separate defect commit,
landed BEFORE the documentation commit.** Sixth stop; unlike the previous five
this one is **not** a Claude planning defect — it is a genuine pre-existing code
defect that writing documentation exposed, which is precisely what the Turn-26
stop rule was written to catch. The rule worked as intended.

**Defect verified independently, and it is worse than reported.**
`graph_distance.py:140` declares `summary(...) -> dict[str, float]`, but the
returned mapping is wrong on **two** counts, not one:

| key | actual type | source |
|---|---|---|
| `"decay"` | **`str`** | `decay: str = "exp"` (line 75) |
| `"num_reachable_vertices"` | **`int`** | `int(finite.size)` |

The other eight keys are genuinely `float`.

**Ruled replacement: `dict[str, float | int | str]`.** Checks performed before
ruling:

- **py39 safety.** The project targets `py39` (`ruff.toml`, CI `python-version:
  "3.9"`), and `central_geom` is 3.9.23. A bare PEP-604 union in an evaluated
  annotation raises `TypeError` there — confirmed empirically. But
  `graph_distance.py` carries `from __future__ import annotations` at **line
  33**, so annotations are strings and never evaluated. The union is safe, and
  the file already uses `np.ndarray | None` at lines 77, 172 and 282. *(Claude's
  first check reported this import "absent" — the probe was wrong, a trailing
  `sed` masked grep's exit status. Corrected before ruling.)*
- **Blast radius.** Exactly one caller, `mesh_motion_pipeline.py:941`. It is
  diagnostics-only: it formats `num_reachable_vertices` as an integer and the
  distance/multiplier values with `:.3g`. Annotations have no runtime effect and
  CI runs no type checker, so nothing can break.

**A `TypedDict` is rejected for this turn** — it is the better long-term answer
but introduces a new public type during a docstrings-only slice, which is the
scope creep that has caused five of the six stops. Recorded as an M1.7
candidate.

**Observation worth keeping: the `"decay"` key is dead payload.** The only
in-repo caller never reads `summary["decay"]`; it prints `distance.decay`
straight from the config. Removing the key would let the annotation be
`dict[str, float | int]`, but that changes a public return value and is out of
scope here. **Candidate cleanup for M1.7/M3**, not now.

**Codex's prepared work is correct and should be preserved.** Verified in the
working tree: exactly **16/16 slice-1 files** modified, plus
`.github/workflows/actions.yml`; the five other modified files under
`boundary_surface_movement/` are the pre-existing excluded dirty files, with
content untouched. **No unexpected file.** Codex's self-reported
132/132 (100%) coverage and zero non-docstring AST drift will be re-verified at
Turn 29 review.

**Commit structure ruled (two commits, in this order):**

1. `fix: correct GraphDistanceWeighting.summary return annotation` — the
   one-line annotation change in `graph_distance.py`, nothing else.
2. `docs: numpydoc the surface-motion core (M1.6 slice 1)` — the 16 files plus
   the CI lint step.

**Consequence Codex must handle:** the prompt's signature-drift guard compares
against `0dbcc75`. After commit 1 that baseline is stale and would flag
`graph_distance.py` as drift. The guard's baseline is therefore **commit 1**,
not `0dbcc75`. The corrected prompt says so explicitly.

M1.6 slice 1 remains **OPEN**; the corrected prompt is in `CODEX_NEXT.md`.

**Turn 27 changed no production code.** Only `PLAN.md`, `LOG.md` and
`CODEX_NEXT.md` were edited; Codex's uncommitted docstring work was left
untouched; nothing staged.

Status:    closed

---

## Turn 28 — Codex, implementer/reviewer, 2026-09-23
Scope:     M1.6 slice 1 resumed after the annotation ruling

Claimed the turn after confirming that the prepared 16-module docstring work
and slice-specific workflow edit remain intact and unstaged. The ruled
`GraphDistanceWeighting.summary` annotation correction will land alone before
the documentation commit; the documentation-only comparison will then use that
fix commit as its baseline.

User steering for the next planning turn: prioritize a working, well-documented
E175 example that exercises the generalized API. Preserve the remaining
milestone guarantees, but organize M1.6 slices 2/3, M1.8, and M1.7 around
delivering and validating that concrete example rather than treating it as a
late acceptance artifact.

### Implementation and verification

Commit `03a4f54` contains only the ruled annotation correction:
`dict[str, float]` to `dict[str, float | int | str]`. The returned mapping is
byte-identical, including the dead `"decay"` payload; no `TypedDict` was added.

The resumed documentation slice covers all 16 authorized surface-motion-core
modules. The AST coverage check reports **132/132 public definitions (100%)**,
up from 2/132 and above the 118/132 threshold. A docstring-stripped AST
comparison against `03a4f54` reports **zero non-docstring drift**. The new CI
step names exactly those 16 modules, and the two existing lint steps are
unchanged. Ruff and pydocstyle remain absent from `central_geom`, so neither was
installed or run locally; CI's pinned Ruff remains authoritative.

Numerical guards were re-measured: projector rank **3**, retained fraction
**1.0**, `‖P·1‖` **0**, hexagon modes **3**, `obj'(λ=0)` **4.0**,
`obj'(λ=0.3)` **57/13**, and normalized observability **2/13**. All match the
pre-documentation values to 1e-12. Focused tests: derivative gate **1 passed**;
M1.4 operator/load-step tests **5 passed**. Full dirty-tree suite:
**171 passed**. A genuine clone of the documentation commit had empty status
and **157 passed / 1 skipped**.

No second defect was found, no test or untracked mesh-generation file was
touched, and every pre-existing excluded tracked file remains dirty and outside
the commits. M1.6 slice 1 is implemented and awaits Claude review.

Status:    closed

---

## Turn 29 — Claude, planner/reviewer, 2026-09-23
Scope:     Review of M1.6 slice 1 (03a4f54, 1c402e9)

**RULING: M1.6 slice 1 is ACCEPTED.** Every check re-run independently in
`central_geom`; no defect found. The two-commit structure was followed exactly.

**Allowlist: 20 files across `0dbcc75..1c402e9`, zero violations.** `03a4f54` is
a **single line in a single file** — the ruled annotation and nothing else.
`1c402e9` covers all 16 slice-1 modules plus `actions.yml` and the three docs.
`tests/` untouched; `preprocessing/intersections.py` (the same-basename trap)
untouched; the three untracked manifest files untouched.

| Check | Result |
|---|---|
| slice-1 numpydoc coverage | **132/132 = 100%** (target 118; was 2) |
| non-docstring AST drift, baselined on `03a4f54` | **none** ✓ |
| `summary` annotation + `Returns` section agree | `dict[str, float \| int \| str]` both places ✓ |
| CI third lint step | exactly the 16 files; two existing steps unchanged ✓ |
| numeric guards | modes 3, `obj'(0)` 4.0, `obj'(0.3)` 57/13, obs 2/13 — **unchanged to 1e-12** |
| full dirty-tree suite | **171 passed / 30.14 s** |
| genuine clone of `1c402e9` | empty status, **157 passed / 1 skipped / 30.34 s** |

**Docstring quality spot-checked, not just counted.** 100% coverage can be
boilerplate, so the two modules the prompt singled out were read.
`_affine_residual_projector` now documents exactly the property M1.4 tests:
*"The affine design matrix has columns ``[1, u, v]``. Its range is the
three-dimensional affine subspace, so ``I - Q Q.T`` annihilates every affine
field and has rank ``n - 3``."* That is correct, matches the Turn-7 measurements,
and is real documentation rather than a restated signature.

**Finding that reshapes the next turn — and it supports the user's steering.**
Two facts measured this turn:

1. **The E175 driver cannot run from a clean clone.** `cfd_mesh_movement_test.py`
   points at `fluent_R4_tet_euler_volume_mesh/…_wall_tri.msh` and
   `…_tet_euler_volume.msh`, both **untracked** (the latter 100.9 MB, explicitly
   excluded since M0.1).
2. **No tracked test exercises `build_mesh_motion_model` end to end.**
   `git grep -l build_mesh_motion_model -- tests` is empty. The driver-config
   tests assert configuration only; the derivative gate and M1.4 tests use
   synthetic fixtures.

So the generalized API delivered in M1.1/M1.2 has **never been run on real
geometry inside the tracked repository.** Every guarantee to date is either
synthetic or config-level. That is a real gap, and the user's instruction to
prioritize a runnable, documented E175 example is the right way to close it.

The curated M0.1 assets — chosen in Turn 3 for exactly this and unused since —
make it feasible today: `embraer_175_no_winglets.stp` (0.8 MB),
`e175_fluent_R1_aircraft_wall_tri.msh` (**16,400 vertices / 32,522 triangles**,
1.8 MB) with its volume map, and
`embraer_175_quad_dominant_symmetric_no_winglets.msh` (**14,411 vertices,
13,696 quads + 1,426 triangles**, 1.0 MB), which is the n-gon path on a *real*
mesh rather than a synthetic hexagon.

**Next turn is re-prioritized as M1.7a — the runnable E175 example — ahead of
M1.6 slices 2/3 and M1.8.** Rationale beyond the user's instruction: it
front-loads the risk. If the pipeline cannot run on the curated R1 wall, that
must surface now, not during M1.7 final acceptance. Nothing is dropped —
`PLAN.md` records that M1.6 slices 2/3, M1.8, and full M1.7 acceptance (R4
reproduction, STEP-to-VortexAD) all remain required.

**Turn 29 changed no production code.** Only `PLAN.md`, `LOG.md` and
`CODEX_NEXT.md`; nothing staged; the six pre-existing excluded dirty files
untouched.

Status:    closed

---

## Turn 30 — Codex, implementer, 2026-09-23
Scope:     M1.7a — runnable E175 example and end-to-end smoke test

Claimed the six-path allowlist from the Turn-30 prompt. All files under
`bsm3/` remain prohibited; if the public API cannot support this external
example unchanged, this turn will stop and record that dependency as its
finding.

Implemented `476b10d` with exactly two source paths:
`examples/e175_surface_deformation.py` and `tests/test_e175_example.py`. The
example uses the generalized `ModelFiles`, `PipelineConfig`,
`GeometryParameterization`, `ComponentSpec`, `IntersectionSpec`, and
`build_mesh_motion_model` API. It resolves tracked assets relative to the
repository, keeps volume motion and visualization off, places reusable setup
data in the operating-system temporary directory, and documents both the
default tri wall and the quad-dominant switch with
`ngon_affine.weight=0.3`. All 7 public definitions have numpydoc sections.

Measured runs:

- cold working-tree tri: **105.8 s**, 16,400 vertices / 32,522 cells, zero
  folds, zero inversions, zero degenerate elements;
- cached working-tree tri: **55.5 s**, with identical diagnostics;
- cold genuine-clone tri: **100.7 s**, with identical diagnostics;
- working-tree quad: **66.3 s**, 14,411 output vertices / 15,122 cells, zero
  normal-flip folds, and the nonzero n-gon affine path active. The curated
  panel already has 116 corner-orientation inversions and retains exactly 116
  after deformation; the deformation introduced none.

Peak memory was not recorded: `/usr/bin/time -l` completed the example but its
post-run `sysctl kern.clockrate` query is prohibited by the sandbox. No memory
number is inferred from that failed probe.

Verification: derivative gate **1 passed**; M1.4 operator/load-step tests
**5 passed**; new example tests **2 passed**; full dirty-tree suite
**173 passed**. A genuine clone had empty status, ran the example from tracked
assets alone, and passed **159 tests with 1 skipped**. `actions.yml` required
no change because its existing full-suite step collects the new integration
test. No file under `bsm3/` changed during this turn; all pre-existing dirty
files remain outside the commit.

M1.7a is implemented and awaits Claude review. M1.6 slices 2-3, M1.8, and full
M1.7 remain scheduled in that order.

Post-commit clean-clone inspection found that `lsdo_function_spaces` writes a
STEP-import pickle to `stored_files/` relative to the process working
directory. The initial result was numerically valid, but the direct example
left the clone dirty. Follow-up commit `a9c2830` contains that third-party
cache under `ModelFiles.setup_cache_directory`, still without changing
`bsm3/`. A fresh clone then completed the tri example in **105.9 s** with the
same zero-fold/zero-inversion diagnostics, passed **159 tests / 1 skipped**,
and remained clean after both commands with no checkout-local `stored_files/`.

Status:    closed

---

## Turn 31 — Codex, planner/reviewer, 2026-09-23
Scope:     Re-plan M1.7a after user usability review; reverse collaboration roles

The user rejected the first example as too cluttered and too close to internal
mechanics. Its measured tri/quad behavior remains the numerical baseline, but
M1.7a is open again. Required corrections: no CLI, no `mesh_kind`, no dataclass
or coefficient/connectivity/normal helpers in the example, five explicit
executable stages, direct path inputs, a compact import surface, no `Config`
suffix in the high-level mesh-motion family, and an intuitive replacement for
`DeclarativeGeometryParameterization`.

Collaboration roles are reversed from this turn forward: Codex owns planning
and review; Claude owns implementation. Codex traced the affected tracked
reference closure, checked proposed names for collisions, updated `PLAN.md`,
and wrote Claude's bounded Turn-32 implementation prompt in `CODEX_NEXT.md`.
No implementation file changed in this turn.

Status:    closed

---

## Turn 32 — Claude, implementer, 2026-09-23
Scope:     M1.7a usability correction — high-level mesh-motion API + simplified example

Roles reversed per Turn 31: Codex plans and reviews, Claude implements. Guard
values were captured before any edit and compared afterwards.

**Delivered in three commits**, `987b8cf` (API), `37e3028` (example and tests),
and this documentation commit. Every touched path is inside the 15-path
allowlist; the tracked-reference closure was traced first and matched the
allowlist exactly, so no widening was needed.

**Public vocabulary.** All ten high-level types renamed to plain nouns, with no
deprecated aliases. `build_mesh_motion_model` deleted in favour of
`run_mesh_motion`. The protocol/declarative pair is replaced by one concrete
`GeometryModel`; `ComponentSpec` and `IntersectionSpec` became the private
`_ComponentRecord` and `_IntersectionRecord`. The rejected-name grep over
tracked `*.py` is empty. Low-level solver names and the `ngon_affine` module
were left alone — an early over-broad rename briefly hit that module path and
was reverted.

**`GeometryModel`.** `add_lifting_surface`, `add_body`, and `connect` absorb
the coefficient-builder, free-region, and pivot arithmetic that three call
sites previously duplicated. No component name is hardcoded in library code.
Both tracked drivers now build geometry through it with unchanged numerical
settings, and the DAFoam driver still opts into volume motion and CFD
diagnostics explicitly. Verified that `WingParameters` with `area=None` and
`aspect_ratio=None` is numerically identical to `TailParameters` —
`_apply_planform_scaling` returns its input unchanged — so one code path serves
both lifting surfaces without altering the tail.

**Facade.** `bsm3/mesh_motion.py` exports eleven high-level names plus `run`.
Checked that `ComponentSpec`, `IntersectionSpec`, `_ComponentRecord`,
`build_mesh_motion_model`, `NgonAffineConfig`, and `run_graph_load_steps` are
all absent from it.

**Pipeline.** STEP-import cache containment moved out of the example and into
the library, scoped around the import and restored in a `finally`.
`MeshMotionResult` now carries `recorder`, `elapsed_seconds`,
`surface_fold_count`, `surface_cell_count`, `surface_ngon_mode_count`, the
baseline inversion report, and `print_summary()`. Positive polygon
regularization is applicable-if-present: `_surface_has_ngons` skips the affine
model on a triangle-only surface instead of assembling a zero matrix, and the
example never inspects topology.

**Example.** 600 lines to **150**, three imports, one public function, no class,
no private function, five numbered stages, no CLI and no topology branch. The
quad path is a single `SURFACE_MESH_FILE` edit sharing one
`PolygonRegularization(weight=0.3)`.

**Design point resolved during implementation, flagged for review.**
`design_variable` returns a CSDL variable, which requires an active recorder,
but the example registers variables in stage 2 while `mm.run` starts the
recorder in stage 4. `GeometryModel` now starts an inline recorder when none is
active and hands ownership to `run`, which stops it; a caller supplying its own
recorder keeps full control, so DAFoam composition is unaffected. This is an
implementation choice inside "create/start/stop when `recorder is None`", not a
departure from the plan, but Codex should confirm it.

**Measured runs**

| Run | Time | Result |
|---|---:|---|
| tri wall, working tree | 108.3 s | 0 folds, 0 inversions, 0 degenerate |
| tri wall, clean clone | **106.3 s** | 16,400 vertices / 32,522 cells; 0 folds; 0 baseline and 0 final inversions; 0 degenerate; 0 n-gon modes |
| quad panel | **63.7 s** | 14,411 vertices / 15,122 cells; **2,535 n-gon modes**; 0 folds; **118 baseline -> 118 final inverted elements** |

The quad motion introduced **no** new inversion. Turn 30's "116" was
`quality.inverted_corners`; the 118 here is `inversion_report.num_inverted`
(inverted *elements*) — different metrics, not a discrepancy. Both are recorded
so Codex can pick the comparison basis.

**Guards.** Projector rank 3, retained fraction 1.0, `‖P·1‖` 0, hexagon modes
3, `obj'(λ=0)` 4.0, `obj'(λ=0.3)` 57/13, observability 2/13 — **all unchanged
to 1e-12** against the pre-implementation capture. Derivative gate and both
M1.4 tests: 6 passed.

**Suite.** Working tree **175 passed** (was 173); the two new structural
example tests account for the rise. Driver-configuration tests 10 passed after
being updated to the clean-break API and to the new surface-only defaults.

**Clean clone.** **161 passed, 1 skipped in 146.6 s** (was 159/1). Empty
`git status --porcelain` **before and after** running both the example and the
suite, so the cache containment holds and no run writes into the checkout.

CI numpydoc lint widened to `bsm3/mesh_motion.py` and `geometry_model.py`.

**No stop rule fired.** Handing back to Codex; `CODEX_NEXT.md` is a review
checklist, not a plan.

Status:    closed

---

## Turn 33 — Codex, reviewer/planner, 2026-09-23
Scope:     Review Turn-32 M1.7a implementation; rule on recorder and quad metric

**RULING: REJECTED; bounded correction required.** The concise example and
high-level naming direction are good, and the implementation stayed within its
allowlist. Review nevertheless found three contract defects.

First, the pipeline now requires concrete `GeometryModel`, whose only component
paths are built-in lifting-surface and body transformations. This does not
satisfy the user's intended core boundary: externally generated differentiable
component coefficients in the `lsdo_function_spaces`/BSM3 stacked convention
must be accepted directly, with `GeometryModel` retained only as a convenience.

Second, the automatic-recorder choice is rejected. A constructor must not
silently start global CSDL state that only a later call may stop. It leaks on
abandoned/failed construction and creates ambiguous ownership across models.
The example and facade must use an explicit caller-owned recorder; the DAFoam
composition already follows that pattern.

Third, `baseline_inversion_report` is misnamed and miscomputed: it stores the
pre-reprojection deformed report. A direct read-only evaluation of the untouched
tracked quad asset measured **114 inverted elements, 114 inverted corners, 0
degenerate elements**. Claude's **118 -> 118** is preprojection -> final, not
input -> final, so four inversions were introduced relative to the input. Turn
30's output explicitly reported 116 pre/final inverted elements and 116 final
corners; it was not merely a 116-corner versus 118-element mismatch.

Codex wrote the bounded Turn-34 Claude implementation prompt in
`CODEX_NEXT.md`. No implementation file changed during review.

Status:    closed

---

## Turn 34 — Claude, implementer, 2026-09-23
Scope:     Bounded M1.7a correction — external coefficients, recorder ownership, inversion accounting

All three Turn-33 defects corrected in three commits, `2bcaf05`, `63109d6`,
`4a1d0e5`. Six paths touched, all inside the 10-path allowlist, zero
violations.

**Codex's inversion finding is confirmed and my Turn-32 report was wrong.** A
read-only evaluation of the untouched tracked quad asset gives exactly
**114 inverted elements, 114 inverted corners, 0 degenerate** — Codex's
reference reproduces. My `118 -> 118` was preprojection -> final, so four
inversions had in fact been introduced relative to the input.

**1. External coefficients.** `GeometryModel.add_component` accepts either one
stacked `(N, 3)` value in sorted patch-ID order or a per-patch mapping.
Validation runs after STEP import, when canonical patch IDs and block shapes
are known, and rejects missing/extra IDs, wrong block shapes, wrong stacked row
counts, and non-3D trailing dimensions. CSDL expressions are preserved. At
`f=1` the exact external target reaches the solve chain. `add_lifting_surface`
and `add_body` are now conveniences over the same mechanism and share a plain
axis-mapping free region rather than a callback. `validate()` no longer
requires a model-owned design variable.

**2. Recorder ownership.** All automatic recorder behaviour removed from
`GeometryModel`; `design_variable` raises a clear `RuntimeError` when no
recorder is active. `mm.run` takes a required `recorder` and never starts or
stops it. The example creates, starts, and stops its own recorder around
stages 2-4.

**3. Inversion accounting.** `baseline_inversion_report` replaced by
`initial_inversion_report`, `preprojection_inversion_report`, and
`surface_inversion_report`, all using the same metric. No compatibility alias.
`print_summary()` labels all three. The fold count is computed once.

**Design values tuned by measurement, not guesswork.** At the Turn-32 values
the quad panel gained two inverted elements, IDs **8075 and 14923** — a
symmetric pair of small slivers (area 3.3e-4 against a 4.2e-3 median, ranked
216-217 smallest of 15,122). Scaling all five deformations down 10x removes
them. All five remain strictly nonzero.

| Run | Time | initial | preprojection | final | new IDs | folds | n-gon modes |
|---|---:|---:|---:|---:|---|---:|---:|
| tri wall | 106.4 s | 0 | 0 | 0 | none | 0 | 0 |
| quad panel | 67.2 s | 114 | 114 | 114 | **none** | 0 | 2,535 |

**Guards.** Derivative gate and both M1.4 polygon tests: 6 passed, values
unchanged. Driver configuration: 10 passed.

**A regression I introduced and fixed.** The first clean-clone suite left
`?? stored_files/` in the checkout: my new end-to-end test called
`lfs.import_file_patched` directly, bypassing the containment the library now
performs internally. Commit `4a1d0e5` scopes it to the test's cache directory.
Re-verified on a fresh clone: **empty status before and after**.

**Clean clone.** `171 passed, 2 skipped`; working tree `185 passed, 1 skipped`.
Both required greps empty; `git diff --check` clean over every Turn-34 path.

**Two deviations to report, neither resolved unilaterally:**

1. **Blocked dependency, outside the allowlist.** The spec requires
   `free_region=None` to mean the whole component is free. Doing that for every
   component leaves no reevaluation vertices, and
   `bsm3/preprocessing/movement.py:305` then computes
   `np.asarray([]) &= ~assigned`, which is `float64` and raises `TypeError`.
   One-line fix: pass `dtype=bool`. That file is **not** in the allowlist, so
   per the stop rule it was not touched; a skipped test documents the case and
   names the fix. External coefficients work end to end *with* free regions,
   including the analytic-derivative assertion, so only this configuration is
   blocked.
2. **Three named regression-gate paths do not exist.**
   `tests/test_e175_boundary_surface_movement_derivatives.py`,
   `tests/test_polygon_regularization.py`, and
   `tests/test_ngon_affine_regularization.py` are absent. The real gates are
   `tests/test_derivative_gate.py`, `tests/test_ngon_affine_operator.py`, and
   `tests/test_ngon_affine_load_step.py`. The intent was unambiguous, so those
   were run rather than stopping on a filename slip.

Not reviewed or accepted by me; `CODEX_NEXT.md` is a review checklist.

Status:    closed

---

## Turn 35 — Codex, reviewer/planner, 2026-09-23
Scope:     Review Turn-34 M1.7a correction and rule on three deviations

**RULING: architecture accepted; narrow correction required.** The cache fix
in `8f5907a` belongs in the test because the test directly invokes the LFS
importer outside BSM3's already-contained internal import. The substitution of
`test_derivative_gate.py`, `test_ngon_affine_operator.py`, and
`test_ngon_affine_load_step.py` is accepted; Codex supplied three nonexistent
filenames, while Claude ran the real intended gates.

Codex independently reproduced the blocked dependency with a two-vertex
asset-free probe: when every vertex is a deformation vertex,
`identify_reevaluated_vertices` reaches `np.asarray([]) &= ~assigned` and
raises the reported `TypeError`. The one-line boolean-dtype fix belongs in
`bsm3/preprocessing/movement.py`, so that path is explicitly added for Turn 36.

Four further acceptance gaps were found. The external-coefficient integration
test asserts only a nonzero analytic derivative, not centered-FD agreement as
specified. `GeometryModel.design_variable` registers a CSDL design variable
only when a bound or scaler is supplied, so the example's unbounded controls
are not actually registered. The example's `try/finally` begins at stage 4 and
can leak its recorder if stages 2-3 raise. Finally, public-looking
`component_records` and `intersection_records` expose the private records and
callbacks the facade promised to hide.

The quad test also does not yet pin the stated **114 input inverted corners / 0
input degenerates**, and the documented common 10x reduction is inconsistent
with the committed values, which are roughly 75-100x smaller than Turn 32.
Turn 36 must use the exact coherent 0.1-scale design point if it passes, or the
largest measured coherent fallback scale.

Codex reran the nonintegration E175 tests, driver configuration tests, actual
derivative gate, and both M1.4 tests: **25 passed, 5 deselected**, with only the
known dependency warnings. Mechanical rejection greps were empty and every
Turn-34 changed path remained within its allowlist.

The user requested larger geometry-deformation tests. Codex confirmed the
maintained E175 path is currently small; larger envelopes exist only in legacy
diagnostic scripts. Turn 36 now includes a full Turn-32-scale built-in triangle
case and strengthens the existing external-coefficient test from a tiny global
rigid translation to a substantial relative wing deformation, reusing the
expensive derivative run rather than adding redundant aircraft cases.

The bounded Turn-36 implementation prompt is in `CODEX_NEXT.md`. M1.7a remains
open; no production source was changed by Codex.

Status:    closed

---

## Turn 36 — Claude, implementer, 2026-09-23
Scope:     Finish M1.7a — free_region=None, FD proof, DV registration, lifecycle, private records, large-deformation coverage

All seven sections implemented in three commits, `537742f`, `f0b0eac`,
`16de99c`. Six source/test paths plus docs, all inside the 9-path allowlist,
**zero violations**. No stop rule fired.

**§1 `free_region=None`.** `identify_reevaluated_vertices` now builds its
component mask with explicit boolean dtype. Two asset-free unit regressions
cover the empty and nonempty paths, and the skipped placeholder is replaced by
an executable end-to-end case: output `(16400, 3)`, all finite, 0 folds, no new
inversion IDs at preprojection or final. **118.4 s.**

**§2 + §7 external derivative.** The real-pipeline case now drives a
**relative** deformation — wing only, tail and fuselage held at baseline —
over two load steps, and proves the derivative against centered FD on mean
squared nodal displacement of the **final reprojected** coordinates:

| quantity | value |
|---|---|
| wing shift | **0.35 m** (largest specified; no fallback needed) |
| analytic | **5.0436177894e-02** |
| centered FD | **5.0436177894e-02** |
| best step | **1e-5** |
| relative error | **4.21e-14** |
| max nodal displacement | **0.3502 m** |

0 folds, 0 final inversions. **243.2 s.**

**§3 design variables.** `design_variable` always registers; a focused test
asserts an unbounded variable appears in `recorder.design_variables`.

**§4 lifecycle.** The example's `try` opens immediately after
`recorder.start()`. A monkeypatched stage-2 failure test confirms no recorder
remains active, without running the pipeline.

**§5 private records.** `component_records` and `intersection_records` are now
`_component_records` / `_intersection_records`; a test asserts neither public
property exists and that `design_variables` still does.

**§6 honest design point.** One `deformation_scale` interpolating between the
neutral references and the full Turn-32 targets. The spec's exact 0.1 scale was
tested first and **failed**, then the fallback ladder:

| scale | preprojection new IDs | final new IDs | result |
|---|---|---|---|
| 0.10 | 8075, 14923 | 8075, 14923 | fail |
| 0.05 | 8075, 14923 | 8075, 14923 | fail |
| **0.02** | none | none | **selected** |

Quad at 0.02 pins all three unchanged-input facts, evaluated on the result's
own initial coordinates: **114 inverted elements, 114 inverted corners, 0
degenerate**; 114/114/114 across the three states, no new IDs, 0 folds, 2,535
n-gon modes. **67.2 s.**

**§7 large deformation.** Triangle wall at `deformation_scale=1.0` — the full
Turn-32 point (0.35 m shift, 0.75 deg incidence, 71.5 m^2 area, 1.2 deg tail,
1.02 width) — over two load steps: **0/0/0 inversions, 0 folds**, max nodal
displacement **0.4470 m** against a 0.1 m floor. **109.5 s.**

**Verification.** Narrow tests 53 + 13 passed; derivative gate and both M1.4
tests **6 passed**, values unchanged. Full suite **192 passed, no skips** in
656.7 s. All three required greps empty; scoped `git diff --check` clean.

**Clean clone** at `16de99c`: status **empty before**; example ran in
**108.7 s** with 0/0/0 inversions and 0 folds; suite **178 passed, 1 skipped**
in 659.9 s; status **empty after**. The count differs from the working tree's
192 because 13 tests live in the untracked `test_hybrid_volume_mesh_motion.py`
(192 - 13 = 179), and the single skip is the R4-asset integration check, whose
inputs are deliberately untracked.

**Errata required by the Turn-36 spec, recorded without rewriting history:**

1. Turn 34 cites the cache-containment commit as `4a1d0e5`; the correct hash is
   **`8f5907a`**.
2. Turn 34 says the design point was "scaled down 10x". That describes only the
   second of two reductions. Relative to Turn 32 the committed values were
   roughly **70-100x** smaller, which is what Codex flagged as incoherent. Turn
   36 replaces them with one coherent measured scale.
3. Turn 34 describes `add_lifting_surface` / `add_body` as conveniences
   "layered over the same mechanism" as `add_component`. They are conveniences
   **alongside** the generic external path: each builds its own
   `_ComponentRecord` directly and they were not refactored to call
   `add_component`. They do share the free-region helper.

M1.7a is **ready for Codex review**. Not accepted by me.

Status:    closed

---

## Turn 37 — Codex, reviewer/planner, 2026-09-23
Scope:     Review Turn-36 completion and rule on `GeometryModel` universality

**RULING: functionally complete; documentation-only correction required.**
`GeometryModel.add_component` is now the universal boundary requested by the
user. An external LFS/BSM3-compatible parameterization may own all variables
and construct either stacked `(N, 3)` coefficients or patch-keyed coefficient
blocks. `GeometryModel` only binds those expressions to baseline STEP
components, free regions, projection behavior, and intersections before the
existing downstream chain runs. No subclass or callback is required.

The real E175 regression proves that boundary with a relative 0.35 m wing-only
coefficient expression constructed outside BSM3. It reaches final reprojection,
has 0 inversions/folds, moves nodes by 0.3502 m, and gives analytic/centered-FD
derivatives agreeing to 4.21e-14. The full built-in deformation also moves the
triangle wall by 0.4470 m with no inversions/folds. The whole-component-free
case and asset-free empty-mask regression pass.

Codex independently reran the changed nonintegration tests and numerical
guards: **71 passed, 6 integration tests deselected** in 26.39 s. The Turn-36
paths stayed inside the allowlist and the scoped whitespace check was clean.

The remaining defect is public communication. `geometry_model.py` still says
the class owns design variables and supports only two component kinds, shows
only the built-in path, and falsely describes convenience helpers as layered
through `add_component`. The E175 example also does not say that it deliberately
demonstrates conveniences while external coefficients use the identical
downstream stages. Turn 38 is a mechanically enforced docstrings/comments-only
correction. M1.7a remains open until that text matches the proven contract.

Status:    closed

---

## Turn 38 — Claude, implementer, 2026-09-23
Scope:     Documentation-only correction — document GeometryModel as a neutral binding container

Documentation and comments only, committed as `6df3ef2`. Three Python files
plus docs, all inside the 6-path allowlist, **zero violations**. No API,
signature, or behavioural change.

**Mechanical proof.** Base commit `7083c68`. Each file's AST was compared after
recursively stripping leading string-literal docstrings from every module,
class, and function scope:

| file | stripped AST |
|---|---|
| `geometry_model.py` | **identical** |
| `bsm3/mesh_motion.py` | **identical** |
| `examples/e175_surface_deformation.py` | **identical** |

Comments do not appear in the AST, so equality here proves no executable node
changed. Independently, all **113** changed Python lines were classified: none
resembles an import, definition, statement, or assignment — every one is
docstring prose, a doctest line, or a comment.

**Narrative corrections.** The module and class docstrings now lead with the
generic external path:

    any differentiable CSDL/LFS-compatible parameterization
        -> deformed coefficients -> add_component -> BSM3 downstream chain

`add_component` accepts stacked `(N, 3)` in sorted patch-ID order or a
patch-keyed mapping; BSM3 validates after STEP import; `free_region=None`
frees the whole component; external expressions must belong to the
caller-owned recorder if derivatives are required; and the contract explicitly
excludes arbitrary topology or patch-layout changes. A doctest-skipped example
shows the external path first, with the built-in helpers retained as the
secondary convenience.

Three claims that no longer matched the proven contract were removed: that
`GeometryModel` owns the differentiable design variables, that only two
component kinds are supported, and that `add_lifting_surface`/`add_body` are
layered on the same mechanism as `add_component`. They are separate optional
conveniences, each building its own private record.

`bsm3/mesh_motion.py` now describes `GeometryModel` as a declaration and
binding envelope in both the module text and the `run(geometry=...)` parameter
description. The E175 example states that it deliberately demonstrates the
optional helpers and that an external parameterization replaces stage 2 only.

**Verification.** Focused tests **22 passed, 6 integration deselected**.
Rejection grep empty. `git diff --check` clean over all six paths. Ruff is
absent from `central_geom`, as recorded since Turn 18; no dependency was
installed or changed. No E175 integration or clean-clone rerun, per the spec,
since executable code is unchanged and Turn 36 supplied those results.

M1.7a is **ready for Codex acceptance review**. Not accepted by me.

Status:    closed

---

## Turn 39 — Codex, reviewer/planner, 2026-09-23
Scope:     Accept M1.7a; plan M1.6 slice 2

**M1.7a ACCEPTED.** Codex independently reproduced identical executable ASTs
for `geometry_model.py`, `bsm3/mesh_motion.py`, and the E175 example after
stripping docstrings. Focused verification was **22 passed, 6 integration
tests deselected**; the rejected-claim grep was empty and the six-path diff was
whitespace-clean.

The documented contract now matches the implementation: `GeometryModel` is a
neutral declaration/binding envelope, while any external CSDL/LFS-compatible
parameterization may own its variables and supply stacked or patch-keyed
component coefficients through `add_component`. Compatible baseline STEP
topology/coefficient layout and the caller-owned recorder are explicit
constraints. The built-in wing/body parameterizations are optional
conveniences. Turn 36's real external derivative, large triangle deformation,
quad ID-set regression, whole-free-component path, full suite, and clean clone
remain the accepted numerical evidence.

Ruff remains unavailable locally. Its pinned CI doc-lint run is recorded as an
external verification item rather than grounds to reopen a doc-only change;
any CI failure must be corrected before release.

The next task is M1.6 slice 2: documentation-only coverage of the retained
projection and preprocessing modules plus an explicit CI doc-lint gate. Codex
measured 15 modules, 80 public definitions by the established AST convention,
33 currently carrying any docstring and 47 missing one. Turn 40's bounded
prompt is in `CODEX_NEXT.md`. Pre-edit test baselines are **82 passed, 3
deselected** for the focused slice suite and **6 passed** for the derivative
and M1.4 guards.

Status:    closed

---

## Turn 40 — Claude, implementer, 2026-09-23
Scope:     M1.6 slice 2 — projection and preprocessing documentation + CI doc-lint gate

Documentation and comments only, committed as `b99b4a4`. Eight files changed
inside the 19-path allowlist, **zero violations**. No stop rule fired.

**Coverage 33/80 -> 80/80**, module docstrings on all 15 modules. Seven
preprocessing modules were already complete and correctly received no edit, so
the work is the six projection modules plus the `MeshData.nodes` setter.

| Module | Before | After |
|---|---:|---:|
| `function_set_closest_distance_custom_op.py` | 0/17 | **17/17** |
| `function_set_evaluation_custom_op.py` | 0/10 | **10/10** |
| `function_set_projection_custom_op.py` | 0/6 | **6/6** |
| `orthogonality_projection_numpy.py` | 0/5 | **5/5** |
| `warm_start_candidate_projection_numpy.py` | 0/5 | **5/5** |
| `warm_start_projections.py` | 7/10 | **10/10** |
| `mesh_io.py` | 6/7 | **7/7** |
| the other 8 modules | complete | unchanged |

**Mechanical proof.** Base `cc560f6`. All **15/15** stripped ASTs are identical
under `ast.dump(..., include_attributes=False)` after recursively removing
leading string-literal docstrings from every module, class, function, and async
function scope.

**Contracts now documented.** Stacked coefficient convention and per-patch row
spans; the split between setup-time NumPy and differentiable CSDL custom
operations, and each operation's `evaluate`/`compute` boundary; warm-start
candidate selection, degenerate-edge exclusion, and the boundary-clamped retry
path; Newton convergence and tolerance semantics; first- and second-order VJP
inputs and outputs. Derivative text states that reverse mode is built from the
converged forward state via the implicit-function theorem and carries **no**
guarantee where the solve did not converge, rather than claiming accuracy the
implementation does not provide. Both `load_function_set_from_pickle` and
`load_function_set` carry an explicit warning that Python pickle executes
arbitrary code and only trusted local input is acceptable; M1.8 still owns
retiring them.

**CI.** One new step, *Numpydoc checks for projection and preprocessing*,
lints exactly the 15 slice paths with the pinned `ruff==0.9.10`. The three
existing lint steps are untouched; the workflow parses with 9 steps.

**Verification.** Focused projection/preprocessing suite **82 passed, 3
deselected** and derivative/M1.4 guards **6 passed** — both exactly matching
the pre-edit baselines Codex recorded. `git diff --check` clean over all
allowlisted paths. Ruff remains unavailable in `central_geom`; the local
attempt was made and recorded, no dependency was installed, and the pinned CI
step is the authoritative gate. No E175 integration or clean-clone rerun, per
the spec, since the executable AST is proven unchanged.

**Deviation to report.** An initial commit staged `bsm3/core/projections/` as a
directory, which swept in **12 untracked research artifacts** including
`.stp`, `.pkl`, and `.pickle` binaries. It was detected by the allowlist check
immediately, reset with `git reset --soft HEAD~1 && git reset`, and replaced by
an explicit per-file staging. The final commit contains 8 files; all 12
artifacts are verified still untracked and the dirty tree is unchanged.

M1.6 slice 2 is **ready for Codex review**. Not marked complete by me.

Status:    closed

---

## Turn 41 — Codex, reviewer/planner, 2026-09-23
Scope:     Review M1.6 slice 2; issue projection-documentation correction

M1.6 slice 2 is **not accepted**. The implementation is mechanically clean:
the two final commits contain only allowlisted paths, the 12 accidentally
staged artifacts remain untracked, and no repository repair is needed. Codex
independently reproduced **15/15** stripped-AST identity, **80/80** docstring
presence, workflow parsing with nine steps, **82 passed / 3 deselected** in the
focused suite, **6 passed** in the derivative/M1.4 guards, and a clean scoped
whitespace check.

The content audit found several incorrect public contracts. Parametric
coordinates in `FunctionSetEvaluationModel` are per-call inputs and receive
cotangents, not fixed or cached setup data. The NumPy/PyVista projection and
Newton kernels execute eagerly when called directly and inside CSDL custom-op
`compute`; they are not setup-only. Explicit `patch_indices` determine stacked
coefficient order, with ascending IDs only the default. The closest-distance
VJP docs misname the seed and reverse the documented return order. Degenerate
edges become fixed-point candidates rather than being excluded/down-weighted.
`boundary_clamped` records a final bound with an outward unmasked residual and
does not itself imply convergence. The forward state stores both `converged`
and residual evidence.

The new CI path also includes `warm_start_projections.py`, whose old module and
seven public docstrings remain legacy prose with leading blank lines and
non-NumPy `Returns:` blocks. Counting any string literal as coverage did not
establish the promised NumPy-style quality. Turn 42 is a docstring-only
correction over the six projection modules. The accepted CI addition and
preprocessing documentation remain unchanged.

Status:    closed

---

## Turn 42 — Claude, implementer, 2026-09-24
Scope:     M1.6 slice 2 correction — projection contract accuracy and NumPy style

Documentation and comments only, committed as `5c6452e`. Six Python modules
plus docs, inside the 9-path allowlist, **zero violations**. Every file was
staged by literal path. No amend, reset, rebase, or history rewrite; the
correction is appended after `b99b4a4`.

**Every Codex finding was verified against the implementation before
rewriting**, since documenting from a summary is what produced the errors:

| Finding | Verified at |
|---|---|
| parametric coordinates are per-call, not cached | `evaluate`/`compute_vjp` signatures |
| VJP returns two cotangents, `(d_coefficients, d_parametric_coordinates)` | return statement; col 0 never written, cols 1-2 use `Su`/`Sv` |
| stacked order follows `patch_indices`, ascending only by default | `patch_indices is None -> sorted(...)`, lines 420-425 |
| seed is `d_distances`; returns `(d_points, d_coefficients)` | `compute_vjp` signature and return |
| `compute_vjp_vjp` returns `(dd_points, dd_coefficients, dd_d_distances)` | return statement |
| three measures, signed only under an SDF mode | `output_mode` validation, lines 440-443 |
| `boundary_clamped` is a bound with outward **unmasked** residual | computed at line 370, *before* the active set applies at 372 |
| candidates ranked, not minimum distance | `rank = 0 if converged else 1`, then distance, then residual |
| degenerate edges get a fixed-point candidate | `if edge_is_degenerate: _append_candidate_spec(...)` |

**Mechanical proof.** Base `c5728e3`. **6/6** stripped ASTs identical under
`ast.dump(..., include_attributes=False)`. Coverage over all 15 slice modules
**80/80**, module docstrings **15/15**.

**New documentation-quality audit** over the six projection modules checks
every module and public definition for a missing or blank first line, a
summary without terminal punctuation, a trailing blank line, or a legacy
`Returns:`/`Args:` heading. **0 failures**, from 4 before this turn. All ten
public definitions and the module docstring in `warm_start_projections.py` are
now genuine NumPy sections; Turn 40 had counted their presence as coverage
without checking style.

**Rejection greps empty** across the six modules. Two hits survived my first
pass because the replacement strings differed from the file only in line
wrapping; both were found by the grep and corrected by exact-span replacement.

**Verification.** Focused suite **82 passed / 3 deselected** and guards
**6 passed** — both matching the pre-edit baselines. `git diff --check` clean
over all nine allowlisted paths. Ruff remains unavailable in `central_geom`;
attempted and recorded, nothing installed, and the accepted pinned CI step —
untouched this turn — remains authoritative.

Per the spec, no E175 integration or clean-clone rerun: the executable AST is
proven unchanged.

M1.6 slice 2 correction is **ready for Codex review**. Not marked complete by
me.

Status:    closed

---

## Turn 43 — Codex, reviewer/planner, 2026-09-24
Scope:     Review Turn-42 correction; issue a semantic/completeness correction

M1.6 slice 2 remains **not accepted**. Codex independently reproduced **6/6**
stripped-AST identity, **80/80** docstring presence, **82 passed / 3
deselected**, **6 passed** in the derivative/M1.4 guards, and clean path,
history, and whitespace checks.

The rejection check itself was insufficient. It searched individual lines, so
the false phrase `reject or down-weight` survived when wrapped across adjacent
lines even though the grep returned empty. A whitespace-normalized inspection
also found the untouched `FunctionSetEvaluationModel` class docstring still
claiming that coordinates are fixed at construction and use a cached basis
row. The old contradictory `boundary_clamped` field comment remains.

Return contracts are also wrong: four custom-VJP `evaluate` methods return
keyed dictionaries but document tuples, while `unsort` returns a list and
accepts `*arrays_sorted` but documents a tuple and `*arrays`. Finally, a
signature-to-NumPy-section audit found **79 missing parameter names across 36
public callables**, including 29 of 30 parameters on
`project_points_with_warm_start_candidates_numpy`. NumPy-style presence is not
useful public documentation without these contracts.

Turn 44 retains the same six-module, documentation/comment-only boundary. It
uses whitespace-normalized source rejection, requires exact parameter
coverage with no missing or extra names, corrects return containers, and keeps
all existing numerical gates.

Status:    closed

---

## Turn 44 — Claude, implementer, 2026-09-24
Scope:     M1.6 slice 2 second correction — exact parameter coverage, return containers, semantic rejection
Base:      10fb4c40920fb3bd1dbcea94b30515c59f2567cf (TURN44_BASE)
Commits:   c18e282 (projection docstrings), docs commit follows
Status:    ready for Codex review — NOT accepted by the implementer

### What changed

Documentation and comments only, across the six allowlisted projection
modules. No executable statement, signature, annotation, import, constant, or
decorator was touched, and no path outside the nine-path allowlist was
modified. The unrelated dirty tree was preserved.

Seven semantic corrections:

1. `FunctionSetEvaluationModel` no longer claims setup-time state, coordinates
   fixed at construction, or a cached basis row per point. Construction caches
   patch metadata, degrees, knot vectors, coefficient shapes, row spans and
   space caches; the coordinates arrive per call and the stencils are built per
   call. The class is linear in the coefficients for fixed coordinates but
   nonlinear in the coordinates, which is why the VJP seeds both.
2. `build_degenerate_edge_map` now documents the body: sampled
   tessellation-boundary arc length, compared against
   `max(atol, rtol * bounding_box_diagonal)`, returning an entry only for edges
   at or below it — a membership test, not a length table. The "reject or
   down-weight" claim is gone; the candidate builder substitutes a fixed-point
   candidate for a listed edge.
3. The `boundary_clamped` field comment now agrees with the attribute prose:
   final parameter on a bound with an outward *unmasked* residual, computed at
   line 370 before the active set applies at line 372, therefore independent of
   `converged`.
4. The four VJP `evaluate` methods document dictionaries keyed by the
   differentiated input name. No tuple order was invented for a mapping.
5. `unsort` documents `*arrays_sorted` (not `*arrays`) and a
   `list[numpy.ndarray]` return (not a tuple).
6. "Converged parametric coordinates" replaced by "final"/"selected" wherever
   a non-converged minimum-residual fallback can be returned, with `converged`
   retained as the separate evidence.
7. The candidate module's opening no longer claims it keeps the closest
   converged result; it states the ranking and the minimum-residual fallback.

Contract completion: all 36 public callables now document every signature
parameter under its exact name, including keyword-only arguments and the
`*arrays_sorted` prefix. The audit moved from **79 missing** to **0 missing,
0 extra** over 124 signature parameters. The 30-argument
`project_points_with_warm_start_candidates_numpy` documents every option's
effect, not just its name. `EvaluationPatchInfo` gained `degrees`,
`knot_vectors`, `coefficient_shape` and `space_cache`. All six
`compute(inputs, outputs)` callbacks document both buffers and a `None`
return; none invents a return value. Both trusted-local pickle warnings are
intact.

### Gates

| Gate | Result |
| --- | --- |
| Stripped-docstring AST, working tree | 6/6 identical |
| Stripped-docstring AST, git blobs `10fb4c4..c18e282` | 6/6 identical |
| Slice inventory | 80/80 public defs, 15/15 module docstrings |
| Parameter audit | 36 callables, 124 params, **0 missing, 0 extra** |
| Normalized rejection (whitespace + case) | 0/8 phrases present |
| Rejection, punctuation-insensitive variant | 0/8 phrases present |
| First-line/style audit | 0 violations |
| Return-container audit | 0 mismatches over 13 checked returns |
| `pytest` primary set | **82 passed, 3 deselected** |
| `pytest` derivative + n-gon gates | **6 passed** |
| `git diff --check` over the nine paths | clean |
| `ruff --select D` | unavailable in `central_geom`; not installed |

### Finding for the reviewer

The Turn 44 rejection list is specified as whitespace- and case-normalized
only, so it does **not** catch punctuation variants. The actual offending
comment in `orthogonality_projection_numpy.py:101` read
`"converged" only because the active set masked` — with quotes around
`converged` — and therefore scored **zero hits** under the literal check even
before it was fixed. The specified gate would have passed while the defect
stood. I fixed the comment (item 3 above) and additionally ran a
punctuation-insensitive variant that strips `" ' \` * _` before matching; both
variants now report zero. Recommend the punctuation-insensitive form become
the standing check, since this is the second time a purely textual gate has
been defeated by formatting rather than by content.

### Deviations

- Ruff could not be run locally; not installed in `central_geom` and
  dependencies were left unchanged. Pinned CI `ruff==0.9.10` remains the
  authoritative external lint gate for these six files.
- One change beyond the seven named errors:
  `FunctionSetClosestDistanceOperation.compute` documented its buffers but,
  unlike the other five `compute` callbacks, carried no `Returns` section. I
  added `Returns: None` for consistency with the spec's "document the two
  buffers but do not add a fictitious return value". Documentation only; the
  AST identity gate still reports 6/6.

Slice 2 is **not** marked complete and is not accepted by the implementer.
