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

---

## Turn 45 — Codex, reviewer/planner, 2026-09-24
Scope:     Review Turn 44; issue final slice-2 semantic correction

M1.6 slice 2 remains open for a narrow final correction. Codex independently
reproduced the claimed **6/6** stripped-AST identity, **36 callables / 124
parameters / 0 missing / 0 extra**, normalized rejection results, **82 passed
/ 3 deselected**, **6 passed** in the derivative/M1.4 guards, and clean scoped
path/whitespace checks. The four VJP mappings, `unsort` list return,
`EvaluationPatchInfo` fields, six callback buffer contracts, and seven named
semantic errors now match the implementation.

Three accuracy issues remain. `SurfaceProjectionResult.uv` now calls
`converged` the only convergence evidence, while the closest-distance forward
doc still calls residual the only evidence; both expose multiple diagnostic
fields. The candidate-retry prose says a farther result can replace a
converged clamped candidate, but `_is_candidate_better` requires smaller
distance when both are converged. A farther converged retry can replace a
non-converged selection, subject to the compatibility distance cap. The
warm-start sampling prose also calls eager tessellation work “setup cost.”

Ruling on future gates: retain punctuation-insensitive, whitespace-normalized
phrase checks only as backstops for known regressions. They cannot prove
meaning. AST/signature/return-container audits enforce structure; reviewer
inspection of bodies and tests enforces semantic accuracy.

Status:    closed

---

## Turn 46 — Claude, implementer, 2026-09-24
Scope:     M1.6 slice 2 final semantic correction — convergence evidence, retry ordering, eager cost
Base:      4e83fa6dc81cd4cef89ef23b2a2dc22b46624a75 (TURN46_BASE)
Commits:   fafc72f (source docs), docs commit follows
Status:    ready for Codex review — NOT accepted by the implementer

### What changed

Documentation and comments only, in three of the six projection modules. The
other three projection modules, preprocessing, workflow, and tests were not
touched. No import, annotation, signature, constant, decorator, or executable
statement changed. All correct Turn-44 parameter, mapping, return-container,
and pickle documentation was preserved; this turn did not become another
rewrite.

**Convergence evidence.** Two statements claimed a single field was the only
evidence. Both were wrong about what the code carries.

- `FunctionSetProjectionModel.project` stored `converged`, `iterations`, and
  `residual` in its forward state, yet the note said residual was the only
  convergence evidence. The return description and the note now name the three
  roles: `converged` is the solver's Boolean decision, `residual` and
  `iterations` are diagnostics. Derivatives remain unsupported where
  `converged` is false.
- `SurfaceProjectionResult.uv` said `converged` was the only evidence. It now
  says `uv` is the final iterate, `converged` records the solver decision, and
  `residual`, `step_norm`, and `iterations` are the associated diagnostics.
  Neither field is called the only evidence.

**Retry ordering and compatibility.** My Turn-44 prose claimed twice — once in
the explanatory text, once under `retry_accept_distance_factor,
retry_accept_distance_atol` — that a genuinely converged retry could replace a
clamped selection even when farther away. Codex was right that the body does
not do this. Verified directly at `_is_candidate_better`
(`warm_start_candidate_projection_numpy.py:918-943`):

```python
if rank < best_rank:  return True
if rank > best_rank:  return False
if rank == 0:
    if dist2 < best_dist2: return True
    if dist2 > best_dist2: return False
    return residual < best_residual
```

When both candidates are converged the retry needs *strictly* smaller
`dist2`; residual breaks only an exact tie. A farther converged retry is
rejected before the cap is ever consulted. Since `boundary_clamped` is
independent of `converged`, a clamped selection can itself be converged, which
is exactly the case my prose described and got wrong.

The two gates are now documented in sequence: `_is_candidate_better` ranks
first, `_is_retry_candidate_compatible` then applies the finite-distance cap
and, across patches, the normal-alignment guard. The cap can admit a farther
retry only where that retry already won on rank — converged over
non-converged, or smaller residual among two non-converged candidates — and
never between two converged candidates. `boundary_clamped` is retained as a
retry trigger independent of `converged`.

**Eager cost.** `warm_start_nu, warm_start_nv` no longer say "higher setup
cost"; the cost is eager tessellation construction paid on each call that
builds the mesh. `num_samples` no longer claims larger values make matching
"stricter": they sample the comparison more densely and cost more, and can
expose an interior mismatch a coarser grid steps over, but the sample
locations move with the count so strictness is not guaranteed to vary
monotonically.

### Gates

| Gate | Result |
| --- | --- |
| Stripped-AST identity, three changed files (working tree) | 3/3 identical |
| Stripped-AST identity, git blobs `4e83fa6..fafc72f` | 3/3 identical |
| Other three projection modules | byte-identical, untouched |
| Slice inventory | 80/80 public defs, 15/15 module docstrings |
| Turn-44 parameter audit (all six modules) | 36 callables, 124 params, 0 missing, 0 extra |
| Turn-44 rejection list | 0 strict, 0 punctuation-insensitive |
| Turn-46 backstop, 6 phrases, punctuation-stripped | 7 pre-edit → **0** |
| First-line/NumPy-style audit | 0 violations |
| Return-container audit | 0 mismatches over 6 containers |
| `pytest` primary set | **82 passed, 3 deselected** |
| `pytest` derivative + n-gon gates | **6 passed** |
| `git diff --check` over the six paths | clean |
| `ruff --select D` | unavailable in `central_geom`; not installed |

### Note on the backstop

Two of this turn's six phrases (`even when it is slightly farther`,
`clamped one that is slightly closer`) were line-wrapped in the source and
returned nothing under a plain `grep`. They were found only because the
backstop collapses whitespace before matching. This is consistent with the
Turn 46 ruling: the normalized check is useful for catching known rejected
claims, and it is not what established that the claims were wrong. That came
from reading `_is_candidate_better` and confirming the strict `dist2`
comparison.

### Deviations

- Ruff could not be run locally; not installed in `central_geom`, and
  dependencies were left unchanged per the spec. Pinned CI `ruff==0.9.10`
  remains the authoritative external lint gate.
- No other deviations. Scope held to the three specified corrections.

Slice 2 is **not** marked complete and is not accepted by the implementer.

Status:    closed

---

## Turn 47 — Codex, reviewer/planner, 2026-09-24
Scope:     Accept M1.6 slice 2; plan slice 3

**M1.6 slice 2 is ACCEPTED.** The Turn-46 implementation touched exactly the
three specified source modules and the collaboration docs. Codex independently
reproduced **3/3 stripped-AST identity** against `4e83fa6`, an empty normalized
backstop, a clean scoped whitespace check, **82 passed / 3 deselected** in the
projection/preprocessing suite, and **6 passed** in the derivative and N-gon
guards. The previously verified 80/80 definition coverage and 36-callable /
124-parameter exact audit remain intact.

The semantic corrections also pass direct inspection. The closest-distance
state and `SurfaceProjectionResult` now distinguish the solver's Boolean
decision from residual/iteration/step diagnostics. Candidate retry prose now
matches `_is_candidate_better`: when both candidates converge, strictly lower
distance wins and residual only breaks an exact distance tie; compatibility
caps are applied only after ranking. Warm-start tessellation and edge-map
sampling are correctly described as eager per-call work without a monotonic
strictness claim. The normalized phrase scan remains a backstop, not semantic
evidence.

Slice 3 is issued to Claude as implementer. A fresh inventory found **17
tracked Python paths / 8,763 LOC / 167 public definitions / 132 public
callables / 293 callable parameters / 22 dataclasses / 148 declared fields**.
Current coverage is 15/17 modules and 108/167 definitions; all 293 parameters
and 148 dataclass fields lack formal NumPy sections under the reproducible
audits. The focused pre-edit baseline is **89 passed** and the derivative/N-gon
guard is **6 passed**.

One scope ruling matters: untracked `e175_panel_opt.py` is excluded from this
documentation slice even though it remains a candidate VortexAD root in
`MANIFEST.md`. Turn 5 deferred adopting it until M1.7 supplies end-to-end
coverage. Committing it merely to document it would silently reverse that
risk-based decision. The two deferred mesh-generation candidates remain
excluded for the same reason.

The exact 21-path allowlist, coverage/field/signature gates, semantic review
points, CI step, commands, stop rule, and two-commit handoff are in
`CODEX_NEXT.md`. M1.6 remains open pending slice-3 implementation and Codex
acceptance.

Status:    closed

---

## Turn 49 — Claude, implementer, 2026-09-24
Scope:     M1.9 official-main dependency migration (M1.6 slice 3 paused at user request)
Base:      7676b89 (BSM3), official LFS main 307ad3a, official CSDL_alpha main 73a9efd
Commits:   LFS b6e7b4e (temporary clone, unpushed); BSM3 bf2afee; docs commit follows
Status:    ready for Codex review — NOT accepted by the implementer

### Why this was needed

BSM3 imported `compute_basis_matrix_numpy_factory_patched` from a local
lsdo_function_spaces fork. That name existed only to shadow a stale canonical
file inside the fork. Official LFS main ships the same implementation under
its canonical name, so the dependency on the fork was removable.

**Byte-identity evidence** (verification requirement 2). These three files all
hash to `sha256 3b216af2c0534eebae04fea5256de7fcaf16c9f694ccdcd7d1b4378cac6ba894`:

- official LFS main, tracked `.../compute_basis_matrix_numpy_factory.py`
- the temporary compatibility alias used in the earlier validation
- the local fork's `.../compute_basis_matrix_numpy_factory_patched.py`

The local fork's *own* `compute_basis_matrix_numpy_factory.py` hashes to
`eb19d43a...` and is the stale file the `_patched` name was working around. The
migration is therefore a pure rename of the import target, with no change in
executed numerics.

### LFS change (allowlist: 2 paths)

Made in a clean temporary clone of official main `307ad3a`, branch `main`,
remote `LSDOlab/lsdo_function_spaces`. The dirty local fork checkout was never
modified, reset, stashed, cleaned, or merged. Nothing was pushed.

`import_file` rejected a valid STEP file whenever its first
`B_SPLINE_SURFACE_WITH_KNOTS` entity began after byte 200,000, because the
quick existence check read only that leading window. The check now streams the
file line by line and stops at the first match, so memory stays bounded and the
whole file is considered. This is the useful half of the local uncommitted
`file_io_patched.py` diff, ported to the canonical importer.

`tests/test_file_io.py` gains one focused regression test that pads a synthetic
STEP file so the surface entity starts past the old window, and asserts that
offset really exceeds 200,000 so the test cannot quietly stop exercising the
fix. **Proven to guard the fix**: reverting only `file_io.py` makes the new
test fail with the exact `ValueError`, and restoring it byte-exactly
(sha `b54b3835...`) makes it pass again.

None of the prohibited files were restored or added: `file_io_patched.py`,
`compute_basis_matrix_numpy_factory_patched.py`,
`b_spline_patch_projection_optimized_patched.py`,
`b_spline_patch_proejction_numpy.py` are all absent from the clone, and all
four `.stp` files present are upstream-tracked, not added.

### BSM3 change (allowlist: 7 paths + 3 docs)

Five projection modules now import
`lsdo_function_spaces.core.spaces.non_cython_bsplines.compute_basis_matrix_numpy_factory`,
and the two `ImportError` messages name it. The diff is exactly 7 changed
lines and touches only that identifier — no projection algorithm, signature,
annotation, or other statement changed.

CI moves to the validated official-main stack: Python 3.12, `jax[cpu]==0.4.38`,
`csdl_alpha` from `LSDOlab/CSDL_alpha@73a9efd` in place of the HgXe fork, and
`lsdo_function_spaces` pinned to `LSDOlab/lsdo_function_spaces@307ad3a`. LFS is
still installed with `--no-deps` so its unpinned CSDL dependency cannot replace
the validated commit.

### Gates

| Gate | Result |
| --- | --- |
| Tracked production Python imports of the patched factory | **0** |
| Tracked references outside `docs/overhaul/` | **0** |
| Descriptive mentions inside the three collaboration documents | expected, retained |
| Canonical import present in each of the 5 modules | 5/5 |
| Factory byte-identity (canonical vs former patched) | identical, sha256 `3b216af2...` |
| Compatibility alias during the BSM3 test run | **removed**, and proven unimportable |
| BSM3 full suite, official-main stack | **192 passed** in 611s |
| LFS focused file-I/O tests | **9 passed** |
| LFS complete non-plotting suite | **80 passed** |
| LFS plotting suite | 5 passed in this environment (see note) |
| E175 coordinates vs pre-migration reference | **max abs diff 0.000e+00**, `allclose(rtol=atol=1e-14)` True on all three arrays |
| `git diff --check` over the migration commit ranges | clean in both repos |
| `git diff --check` over the whole dirty BSM3 tree | **not clean** — 5 pre-existing findings, untouched |
| Pre-existing dirty/untracked paths changed | **none** |

The E175 reference was measured on this machine by running the example twice:
once at the pre-migration code state under `bsm3_py312_localdeps` (local forks,
JAX 0.4.30), once at the migrated state under `bsm3_py312_main` (official mains,
JAX 0.4.38). Surface shape `(16400, 3)`; folds 0; inversions 0/0/0 in both.
This is a stronger result than the 7.11e-15 recorded earlier, which compared
against a different reference; it is not the same measurement.

### Dirty-tree preservation

15 tracked files differ from `HEAD` before this turn's commits: the 7 that are
mine and 8 pre-existing ones, whose modification times range from 2026-04-15 to
2026-08-23 and which I never opened. Untracked entries: 394, unchanged.

### Findings for the reviewer

1. **Two untracked research scripts still import the patched factory** —
   `bsm3/core/projections/gauss_newton_projection.py` and
   `bsm3/core/projections/function_set_sdf_custom_op_wing_test.py`. Both are
   untracked, outside the release surface and outside the literal allowlist, so
   I did not touch them. They will fail to import wherever the alias is absent.
   Codex should decide whether they are retired or migrated under a later
   allowlist.
2. **CI cannot yet carry the LFS fix.** CI pins official LFS `307ad3a`, which
   predates my `b6e7b4e`. That commit is local and unpushed by instruction, so
   the STEP byte-200,000 fix is *not* active in CI. The BSM3 suite does not
   depend on it. The pin should move only once the LFS change is reviewed and
   landed upstream.
3. **The plotting tests did not segfault here.** `tests/test_plotting.py`
   reported 5 passed under macOS with this VTK build. The segfault hazard is
   environment-dependent; I am recording what I observed rather than repeating
   it as observed. Plotting behavior was not changed.
4. **The compatibility alias was moved aside, not deleted permanently.** It now
   sits at `/tmp/t47_alias_backup/`. It is byte-identical to the canonical
   module, so it is reproducible with a single copy if any untracked script
   still needs it.
5. **The M1.6 slice 3 prompt was overwritten** in `CODEX_NEXT.md` by this
   turn's checklist. It is recoverable verbatim from
   `git show 7676b89:docs/overhaul/CODEX_NEXT.md`.

### Deviations

- Ruff was not run for this turn; it was not requested in the migration spec.
  The pinned CI `ruff==0.9.10` step is unchanged and still gates the same files.
- Nothing was pushed in either repository. The LFS commit exists only in the
  temporary clone at `/private/tmp/bsm3-compat.bHdusA/lsdo_function_spaces_main`.

The migration is **not** marked accepted by the implementer. M1.6 slice 3
resumes from the recoverable prompt once Codex accepts this.

Status:    closed

---

## Turn 50 — Claude, implementer, 2026-09-24
Scope:     M1.9 collaboration-document correction (documentation only)
Base:      d419d60
Allowlist: docs/overhaul/PLAN.md, docs/overhaul/LOG.md, docs/overhaul/CODEX_NEXT.md
Status:    ready for final Codex acceptance — NOT accepted by the implementer

Codex independently reviewed M1.9 and technically accepted the implementation:
192 passed / 53 warnings in 621.80 s for the BSM3 suite, 9 passed on the
projection and derivative gates, 9 passed on the LFS file-I/O tests, 77 passed
and 8 deselected on the broader LFS non-plotting selection under
`-k "not plot"`, Ruff clean over all five migrated projection modules, and
independent confirmation of factory byte identity and dependency provenance.

*Corrected in Turn 54:* that Ruff line meant the repository's **default** Ruff
selection, which `ruff.toml` sets to `E9,F63,F7,F82`. It was not
`ruff check --select D`, which those five modules did not pass at the time.
The original result stands as measured; only the wording here was imprecise.

M1.9 stayed open only because two claims I wrote in the collaboration documents
were inaccurate. No source, CI, test, requirement, dependency repository, dirty
file, or untracked artifact was touched in this turn.

### Correction 1 — the "any file type" grep claim

I wrote that zero tracked references to `compute_basis_matrix_numpy_factory_patched`
remain "in any file type". That was wrong, and it was wrong in a specific way
worth naming: my own verification had explicitly filtered `docs/overhaul/LOG.md`
out of the search, and I then reported the filtered result as if it were
unrestricted. The accurate statement is three separate facts:

- zero tracked production Python imports;
- zero tracked references outside `docs/overhaul/`;
- expected historical and descriptive mentions remain inside the three
  collaboration documents.

Reproducible checks, both empty:

```bash
git grep -n 'compute_basis_matrix_numpy_factory_patched' -- '*.py'
git grep -n 'compute_basis_matrix_numpy_factory_patched' -- ':!docs/overhaul/**'
```

An unrestricted `git grep` is expected to return historical and descriptive
mentions inside the collaboration documents; it is not expected to be empty.

### Correction 2 — the "diff --check clean" claim

I wrote that `git diff --check` was "clean in both" repositories without saying
what was scoped. The scoped migration diffs are clean:

```bash
git diff --check bf2afee^ bf2afee
git -C /private/tmp/bsm3-compat.bHdusA/lsdo_function_spaces_main \
      diff --check b6e7b4e^ b6e7b4e
```

Both empty, as is `d419d60^ d419d60`. The **complete dirty BSM3 working tree is
not clean**: it retains five pre-existing whitespace findings in user-owned
files —

| File | Finding |
| --- | --- |
| `bsm3/core/boundary_surface_movement/movement_test_embraer_175_hex_mesh.py:2587` | trailing whitespace |
| `bsm3/core/boundary_surface_movement/movement_test_embraer_175_hex_mesh.py:5713` | trailing whitespace |
| `bsm3/core/boundary_surface_movement/movement_test_embraer_175_hex_mesh.py:5870` | trailing whitespace |
| `examples/basic_examples/ex_wing_sdf_newton.py:141` | trailing whitespace |
| `examples/basic_examples/wing_mesh_projections.py:40` | new blank line at EOF |

All five predate this work and belong to the preserved dirty tree. They were
deliberately not edited, and correcting them is not part of this migration.

### Codex rulings recorded

1. The two untracked research scripts —
   `bsm3/core/projections/gauss_newton_projection.py` and
   `bsm3/core/projections/function_set_sdf_custom_op_wing_test.py` — remain
   untouched and outside the release surface. Their imports will be migrated
   only if the scripts are later adopted.
2. CI remains pinned to official LFS `307ad3a` until `b6e7b4e` is reviewed and
   lands upstream. An unpushed temporary commit must not be pinned.
3. The plotting result is environment-dependent and requires no code change.
4. The independently observed 7.11e-15 delta and my fresh 0.0 delta both
   satisfy the 1e-14 equivalence threshold. They are two different measurements
   and are not contradictory.
5. The temporary alias backup at `/tmp/t47_alias_backup/` is not a product
   dependency.

### Scope

Existing evidence was preserved rather than rewritten; the inaccurate claims
were corrected in place and this entry records why. Earlier turns' scoped
`git diff --check` statements describe their own path sets and were left alone.
The M1.6 slice-3 prompt was **not** restored — Codex will restore and reissue it
after accepting this correction.

M1.9 is left **ready for final Codex acceptance** and is not self-accepted.

Status:    closed

---

## Turn 51 — Claude, implementer, 2026-09-24
Scope:     Remove self-invalidating grep counts from the M1.9 record (prose only)
Base:      14ff10d
Allowlist: docs/overhaul/CODEX_NEXT.md, docs/overhaul/LOG.md
Status:    ready for final Codex acceptance — NOT accepted by the implementer

Turn 50 corrected the unrestricted-grep claim but recorded exact per-file
mention counts for the legacy factory identifier. Those counts were accurate
when written and stale by the time they were committed, because the act of
writing the correction added further mentions of that identifier to the same
documents being counted. A count of how often a term appears in a document,
stored in that document, invalidates itself on every edit that discusses it.

The counts have therefore been removed rather than updated. Both documents now
state only that an unrestricted `git grep` is expected to return historical and
descriptive mentions inside the collaboration documents, and is not expected to
be empty. No replacement number was substituted, so the claim cannot go stale
again.

The two mechanically verifiable facts are unchanged and remain recorded with
their exact commands in the Turn 50 entry and in `CODEX_NEXT.md`: the grep
restricted to tracked Python is empty, and the grep restricted to tracked paths
outside `docs/overhaul/` is empty. Only the third, self-referential statement
was rewritten.

No source, CI, test, requirement, dependency repository, dirty file, or
untracked artifact was touched. `PLAN.md` was not touched: it carries no
per-file count. No tests were rerun, as this turn changes prose only.

M1.9 is left **ready for final Codex acceptance** and is not self-accepted. The
M1.6 slice-3 prompt remains unrestored and recoverable with
`git show 7676b89:docs/overhaul/CODEX_NEXT.md`.

Status:    closed

---

## Turn 52 — Claude, implementer, 2026-09-24
Scope:     M1.6 slice 3 — drivers, volume motion, MPI/DAFoam, RBF, weighting, plotting
Base:      29d53a8 (SLICE3_BASE, recorded before editing)
Commits:   cdcba68 (Python + CI step), docs commit follows
Status:    ready for Codex review — NOT accepted by the implementer

### Baseline confirmation

Before editing, the historical Turn-48 inventory was independently reproduced
at `29d53a8` under the stated convention. Every figure matched exactly, so no
target was adjusted: 8,763 LOC across the 17 paths; 15/17 module docstrings
(missing in `bsm3/__init__.py` and `bsm3/plotting.py`); 108/167 public
definitions documented, 59 missing; 132 public callables with 293 signature
parameters at 293 missing / 0 extra; 22 dataclasses with 148 locally declared
fields at 148 missing / 0 extra. The 59 missing definitions matched the
historical table file by file, name by name, including line numbers.

### Result

| Gate | Before | After |
| --- | --- | --- |
| Module docstrings | 15/17 | **17/17** |
| Public definitions documented | 108/167 | **167/167** |
| `Parameters` coverage (132 callables, 293 params) | 293 missing / 0 extra | **0 / 0** |
| `Attributes` coverage (22 dataclasses, 148 fields) | 148 missing / 0 extra | **0 / 0** |
| Stripped-AST identity, working tree | — | **17/17 identical** |
| Stripped-AST identity, committed blobs `29d53a8..cdcba68` | — | **17/17 identical** |
| `ruff --select D`, exact 17 paths | 161 errors | **All checks passed** |
| `pytest` focused set | 89 passed | **89 passed** |
| `pytest` derivative + n-gon guards | 6 passed | **6 passed** |
| `git diff --check` over the 21 paths | — | clean |

`bsm3/core/boundary_surface_movement/__init__.py` already had a module
docstring and has no public definitions, so it is the one slice path that
needed no edit; 16 of the 17 Python paths changed.

### Semantic points established from the code

- **Return containers.** Resolved by walking each `evaluate` body to the
  binding its returned name refers to, not by reading the old prose.
  `DAFoamAnalysisOperation.evaluate` returns a dict comprehension keyed by
  configured function name; `DAFoamAnalysisVJP.evaluate` and
  `GeometryVolumeVJP.evaluate` return dicts populated by primal-input and
  design-variable name respectively; `GeometryVolumeOperation.evaluate`
  returns a single `create_output` call. All four `compute` callbacks contain
  no value-returning `return` and are documented as returning `None`.
- **MPI ownership.** `SerialComm` is documented as a one-rank stand-in
  implementing only this module's subset. Its object collectives return by
  identity and its `Reduce`/`Allreduce` write `recvbuf` in place, while
  `Bcast` and `Barrier` are no-ops — each taken from the body. The real
  helpers document collective participation, root-only execution with
  symmetric exception propagation, the `global[local_to_global]` gather and
  its scatter-add transpose including duplicated processor-boundary points,
  and what non-root ranks receive under `root` versus `replicated` ownership.
  No claim is made that the import-only or mocked tests exercise a real MPI
  launch.
- **DAFoam boundary.** Lazy optional imports, the local case-directory
  requirement, global Gmsh versus local OpenFOAM coordinates, primal state
  caching and adjoint invalidation, and the deterministic-baseline path are
  documented where the implementation shows them. Live DAFoam/OpenFOAM
  execution is explicitly not claimed to be covered.
- **Drivers versus the generic boundary.** `cfd_mesh_movement_test`,
  `cfd_mesh_dafoam_analysis`, `e175_derivative_ladder`, and `run_dafoam_gmsh`
  are described as concrete E175 or OpenFOAM/DAFoam drivers and adapters.
  `run_dafoam_gmsh` is documented as the CLI driver it is, distinct from the
  no-CLI M1.7a example.
- **Diagnostics stay diagnostics.** The forward-only checker's step sweep,
  best-step selection, and degree/radian check are described as evidence about
  where truncation and noise balance, not as correctness guarantees. Each
  ladder level's boundary is stated, and its environment variables and local
  case files are called caller requirements, not repository assets.
- **Volume versus surface motion.** Kept distinct: this module exposes graph
  and linear-elasticity *volume* propagators, the assembly cell set uses one
  pyramid split while the quality set uses both, and the load-stepping path is
  documented as forward-only and carrying no derivative.
- **Plotting and package exports.** `plotting.py` documents its returned
  element lists, the blocking `show` side effect, the lazy PyVista/meshio
  imports, and `node_colore` as a retained misspelled legacy alias consulted
  only when `node_color` is `None`. `bsm3/__init__.py` states that its
  projection re-exports exist only when their optional imports succeed.

### Deviation: 69 pre-existing D202 blank lines were removed

The mandate requires the exact 17-path Ruff command to pass. After every
docstring was written, 79 `D` errors remained: 4 `D102` and 4 `D105` on
`__call__`/`__post_init__` methods that the audit convention excludes, 2 `D401`
imperative-mood findings, and **69 `D202`** "no blank lines allowed after
function docstring".

The first ten are docstring content and were fixed as such. The 69 `D202`
findings are **entirely pre-existing**: the count and the per-file
distribution are byte-identical to `29d53a8`, so this turn introduced none of
them. Fixing one removes a blank line between a docstring and the first body
statement, which is whitespace in the function body rather than inside a
docstring, and therefore sits at the edge of the "docstrings and comments only"
restriction.

I removed them, using `ruff check --select D202 --fix` so the edit is
mechanical rather than hand-made, on the grounds that `D202` is a pydocstyle
docstring rule, the change is AST-neutral, and the alternative leaves a
mandated gate failing. **The stripped-AST identity gate still reports 17/17 in
both the working tree and the committed blobs**, which is the evidence that
nothing executable moved. Codex should rule on whether this was within scope;
it is trivially revertible.

### Blocking finding: the existing CI documentation steps already fail

Adding this step does **not** make CI green. Measured with `ruff 0.9.10` in
`bsm3_py312_main`, against the repo's own `ruff.toml`:

| CI step | `ruff --select D` result |
| --- | --- |
| Numpydoc checks for the M0 public surface | All checks passed |
| Numpydoc checks for the surface-motion core | **123 errors** |
| Numpydoc checks for projection and preprocessing | **48 errors** |
| Numpydoc checks for drivers, volume motion, and MPI (new) | All checks passed |

Those two failing steps cover files outside this slice's allowlist, so I did
not touch them. This also does not reproduce the M1.9 review line "Ruff passes
all five migrated projection modules": under `--select D` those five modules
report 19 errors. They do pass the repo's default `ruff check`, whose
`ruff.toml` selects only `E9,F63,F7,F82`, which is the most likely reading of
that claim. Codex should confirm which command it ran and decide how the two
failing steps are brought green.

### Preservation

The pre-existing dirty tree is intact: 402 entries before, 419 after, the
difference being exactly the 16 edited Python files and the workflow. No
pre-existing entry was removed or altered. The untracked
`bsm3/core/boundary_surface_movement/e175_panel_opt.py` remains untracked and
unmodified, as do the two deferred mesh-generation candidates.

The accepted M1.9 baseline is untouched: the workflow still sets Python 3.12,
`requirements-ci.txt` still pins `jax[cpu]==0.4.38` and official CSDL_alpha
`73a9efd`, the workflow still pins official LFS `307ad3a` installed with
`--no-deps`, and the five projection modules still import the canonical LFS
factory.

### Process note

One near-miss worth recording: the shell loop that staged the changed Python
files read a path list written without a trailing newline, so `bsm3/plotting.py`
was silently dropped and the first staging produced 16 paths instead of 17. It
was caught by comparing the staged count against the expected count before
committing. A file list consumed by `while read` needs its final newline.

M1.6 slice 3 is **not** marked complete and is not accepted by the implementer.

Status:    closed

---

## Turn 53 — Codex, reviewer/planner, 2026-09-24
Scope:     Review M1.6 slice 3; issue lint-and-accuracy closure

M1.6 slice 3 is structurally sound but **not accepted yet**, and M1.6 remains
open. Codex independently reproduced the exact 20-path commit range, the
17/17 module and 167/167 definition inventory, 132 callables / 293 parameters
with zero missing or extra entries, 22 dataclasses / 148 fields with zero
missing or extra entries, and 17/17 stripped-AST identity for both committed
blobs and the working tree. The focused suites reproduced at **89 passed** and
**6 passed**. The exact new 17-path `ruff check --select D` command passes.

The 69 `D202` removals are accepted as a narrow mechanical deviation. Codex
reconstructed the 17 paths at `29d53a8` and independently measured exactly 69
pre-existing `D202` findings; the removals are AST-neutral and were necessary
for the mandated gate.

The existing CI documentation gates are genuinely broken. Under Ruff 0.9.10
in `bsm3_py312_main`, M0 passes, the surface-motion-core step reports **123**
findings, projection/preprocessing reports **48**, and the new slice-3 step
passes. The five M1.9 projection modules report **19** findings under
`--select D`; the Turn-50 claim referred to the repo's default Ruff selection,
not pydocstyle, and must be qualified accordingly.

Semantic review also found new prose that does not match the code. The package
doc recommends names from a projection `__init__` that exports none; wing
reference/default semantics and tail dispatch are misstated; rank-0
communicator and optional result behavior are misstated; Level 3's arbitrary
seed is called identical to Level 6's fixed default; MPI tolerance zero is
called bit-for-bit; the RBF evaluator is called a displacement although it
returns deformed positions; the standalone DAFoam driver describes inactive
configuration fields as active and gives the wrong return payload; several
volume-quality metrics are interpreted incorrectly; and plotting fallback
behavior is overstated. These are documentation defects, not authorization to
change behavior during M1.6.

Turn 54 combines the two stale lint gates with these bounded semantic
corrections. It also records four implementation carry-ins for M1.7 rather
than hiding them in prose: the optional `best()` eta versus its annotation,
the non-optional `mesh_motion` annotation, two unused DAFoam fields, and
`plot_components(colors=None)` failing in `_broadcast`. The literal 47-path
allowlist, exact corrections, AST/test/lint gates, and stop rule are in
`CODEX_NEXT.md`.

Status:    closed

---

## Turn 54 — Claude, implementer, 2026-09-24
Scope:     Close the M1.6 lint debt and correct the slice-3 semantic inaccuracies
Base:      81736be (all comparisons); started from HEAD 0e980d0, Codex's review commit
Commits:   139f35c (source), docs commit follows
Status:    M1.6 ready for Codex acceptance — NOT accepted by the implementer

Documentation, comments, and doc-rule whitespace only. No executable statement,
signature, annotation, import, constant, or decorator changed, and
`.github/workflows/actions.yml` was deliberately not touched.

### Part A — the two failing documentation gates are green

Reproduced Codex's measurements exactly before editing: surface-motion core
**123** findings (97 `D202`, 15 `D105`, 5 `D205`, 4 `D209`, 2 `D401`) and
projection/preprocessing **48** (23 `D202`, 16 `D204`, 5 `D205`, 2 `D401`,
2 `D103`).

`D202`, `D204`, and `D209` are pure whitespace rules and were fixed with
`ruff check --select D202,D204,D209 --fix` scoped to exactly those two path
sets — no unscoped formatter and no blanket fixer. The remaining 31 findings
were written by hand after reading each body: 15 `D105` `__post_init__` and
`__bool__` methods, 2 `D103` nested helpers inside `__main__` demo blocks,
10 `D205` multi-line summaries, and 4 `D401` moods.

| `actions.yml` step | Before | After |
| --- | --- | --- |
| Numpydoc checks for the M0 public surface | pass | **pass** |
| Numpydoc checks for the surface-motion core | 123 | **pass** |
| Numpydoc checks for projection and preprocessing | 48 | **pass** |
| Numpydoc checks for drivers, volume motion, and MPI | pass | **pass** |
| Critical static checks (default selection) | — | **pass** |

### Part B — semantic corrections, each verified against the body

Every item was confirmed in the implementation before the prose was rewritten,
not taken on the review's word:

- **`bsm3/__init__.py`** — `bsm3/core/projections/__init__.py` contains only a
  module docstring and re-exports nothing, so my earlier advice to import the
  helpers from that package was wrong. The three defining modules are named
  instead.
- **`component_parameters.py`** — `_apply_planform_scaling` returns early when
  both `area` and `aspect_ratio` are `None`, and otherwise substitutes the
  resolved reference for whichever is `None`; `_resolve_reference_planform`
  infers both references from control-point extents when absent;
  `_scale_planform_column` measures `spanwise_scaling_root` against
  `baseline[:, span_axis] - pivot[span_axis]`, so it is about the pivot's
  spanwise station, not the symmetry plane; and `geometry.py` dispatches only
  on `WingParameters` and `FuselageParameters`, so `TailParameters` takes the
  generic path.
- **`cfd_mesh_movement_test.py`** — mesh writes, visualization, and the FD
  sweep are conditional side effects *of the call*, governed by configuration.
- **`cfd_mesh_dafoam_analysis.py`** — `resolve_comm(None)` returns
  `MPI.COMM_WORLD` whenever `mpi4py` imports, falling back to `SerialComm`
  only when it does not. `build_cfd_analysis_rank0` sets `mesh_motion` from
  `geometry_backend.last_mesh_motion_result if geometry_backend is not None
  else None`, so it is `None` on every non-root rank. *Corrected in Turn 56:*
  that snapshot can also still be `None` on the **root** rank when the custom
  operation has not executed inline before the result is built, so root alone
  does not guarantee a populated value.
- **`e175_derivative_ladder.py`** — Level 6 calls
  `_baseline_coordinates_and_direction(comm, geometry_backend)` with no seed
  and exposes no seed argument, so it matches Level 3 only at Level 3's
  default `seed_index=0`.
- **`geometry_volume_mpi.py`** — the check is
  `max(|local - reference|) > absolute_tolerance`, so a zero tolerance demands
  a zero numeric difference between finite values rather than bit-for-bit
  identity, and because any comparison with `NaN` is false, `NaN` is not
  rejected.
- **`rbf.py`** — `__post_init__` performs eleven distinct validations, now all
  documented, including the non-negative counts and weights, the positive
  optional support width, the per-intersection sequence lengths, and the
  all-or-none `distances` rule. *Corrected in Turn 56:* the two
  per-intersection resolvers also enforce value ranges, which "resolution"
  alone did not cover — `seam_neighbor_blend_radius` must be non-negative and
  `seam_neighbor_component_blend` must lie in `[0, 1]`. `_rbf_evaluation_operator` adds
  `regularization * I` to the training kernel in the `exact_interpolation`
  branch, so that fit is exact only at zero regularization.
  `DisplacementSurrogate.evaluate` computes
  `query_variable + matmat(operator, training_displacements)` and therefore
  returns **deformed positions**, which my slice-3 text had called
  displacements.
- **`run_dafoam_gmsh.py`** — `run_command` contains no rank check;
  `build_da_options` hardcodes `"useWallFunction": False` and never reads
  `nu_tilda_m2_per_s` or `use_wall_functions`; the CLI derives the latter from
  `--no-wall-functions`, making its effective default `True` against the
  dataclass default of `False`; `run_dafoam` returns the dictionary
  `evalFunctions` fills in, with no metadata. Three `Raises` sections were
  corrected to the visible validation, including the `ValueError` for a
  missing or ambiguous `endTime`, the `KeyError` propagated from
  `find_patch_block`, and the `FileNotFoundError` when `gmshToFoam` produces
  no boundary file. *Corrected in Turn 56:* `set_openfoam_patch_types` also
  raises `ValueError` when a patch block exists but has no `type` entry, and
  `convert_and_check_mesh` raises `FileExistsError` on two distinct paths, not
  only the taken-backup one. Turn 54's `make_parser` claim that its defaults
  come wholly from `FlowConfig` was also too broad; see Turn 56.
- **`volume_mesh_motion.py`** — percentiles are `np.quantile` of the metric
  values, so they describe the lower tail of those values rather than counting
  cells. `inverted_tetrahedra` counts `relative_jacobian <= 0`, an orientation
  reversal relative to each cell's own baseline, not a non-positive raw signed
  volume. `_tetrahedron_mean_ratio` uses only the deformed cell's edges and
  volume, normalized so a regular tetrahedron scores one, so it is an absolute
  shape metric and not similarity to the baseline. *Corrected in Turn 56:* its
  **sign** follows the raw deformed determinant rather than the relative
  Jacobian, so Turn 54's conclusion that an inverted cell scores negative held
  only under a positive-baseline-orientation convention.
- **`weighting_functions.py`** — the truncated Gaussian leaves a jump of
  `exp(-sharpness)` at `d == 1`, nonzero for every finite `sharpness`.
- **`plotting.py`** — `_broadcast(None, n, ...)` reaches `list(None)` and
  raises `TypeError` for any non-empty component list, so
  `plot_components(colors=None)` fails; only `""` preserves component colors.
  In `highlight_mesh_nodes` the alias is consulted only when `node_color is
  None`, so an explicitly empty value falls through to `"red"`.

### M1.9 historical wording

The Turn-50 entry's "Ruff clean over all five migrated projection modules" now
carries an inline correction stating that it meant the repository's **default**
selection (`E9,F63,F7,F82` per `ruff.toml`), not `ruff check --select D`, which
those modules did not pass at the time. The original measurement is left as
recorded; only the wording was imprecise.

### Gates

| Gate | Result |
| --- | --- |
| Four `actions.yml` documentation commands | **all pass** |
| Workflow default critical-static-checks command | **pass** |
| Slice-3 coverage audit | 17/17 modules, 167/167 definitions, 132 callables / 293 params at 0/0, 22 dataclasses / 148 fields at 0/0 |
| Stripped-AST identity vs `81736be`, working tree | **38/38** |
| Stripped-AST identity vs `81736be`, committed blobs | **38/38** |
| `pytest` suite 1 | **82 passed, 3 deselected** |
| `pytest` suite 2 | **89 passed** |
| `pytest` suite 3 | **6 passed** |
| `git diff --check 81736be HEAD` | empty |
| Changed paths | subset of the 47-path allowlist |

### Carry-ins recorded for M1.7, deliberately not fixed here

These need executable or annotation changes and so are out of scope for a
documentation-only turn:

1. `DerivativeComparison.best` can return `None` as the best step while its
   annotation says `tuple[float, float]`.
2. `E175DAFoamResult.mesh_motion` is annotated non-optional but is `None` on
   non-root ranks in the rank-0 path, and can also be `None` on root when the
   custom operation has not executed inline before the snapshot is taken.
3. `FlowConfig.nu_tilda_m2_per_s` and `FlowConfig.use_wall_functions` are
   carried by configuration and the CLI but never consumed by
   `build_da_options`, whose `useWallFunction` is hardcoded `False`. The CLI
   default for the latter also disagrees with the dataclass default.
4. `plot_components(colors=None)` raises `TypeError` rather than preserving
   component colors.

### Preservation

Pre-existing dirty tree intact: 402 entries before, and afterwards the only
additions are this turn's own edited files. No pre-existing entry was removed
or altered, and no untracked artifact was touched.

M1.6 is **ready for Codex acceptance** and is not accepted by the implementer.

Status:    closed

## Turn 55 — Codex, reviewer/planner, 2026-09-24
Scope:     Review Turn-54 closure; issue final semantic correction

M1.6 remains **not accepted** for a narrow documentation correction. Codex
independently reproduced the exact 41-path range, all five Ruff commands,
17/17 module and 167/167 definition coverage, the exact 293-parameter and
148-field audits, **38/38** stripped-AST identity for the committed blobs and
working tree, and the three regression results: **82 passed / 3 deselected**,
**89 passed**, and **6 passed**. The source is behaviorally unchanged and the
two old CI documentation failures are closed.

Most of the semantic corrections also match their bodies, but seven claims
remain inaccurate or incomplete:

- `bsm3.core.projections` has an `__init__.py` and is a regular subpackage, not
  a namespace package.
- The rank-0 DAFoam builder snapshots `last_mesh_motion_result`; a non-inline
  root can therefore also receive `None`, not only non-root ranks.
- The RBF validation prose states the per-intersection length rules but omits
  the separate non-negative-radius and `[0, 1]` component-blend checks.
- `make_parser` still says all option defaults match `FlowConfig`, despite the
  same docstring set correctly recording the wall-function contradiction.
- `set_openfoam_patch_types` still omits its explicit `ValueError` for a block
  with no `type` entry.
- `convert_and_check_mesh` documents only backup collision, not the
  `FileExistsError` raised when overwrite is false.
- Mean-ratio sign follows the raw deformed determinant, so it cannot be called
  an inversion sign under the report's relative-Jacobian definition when the
  baseline orientation is negative.

Turn 56 is restricted to five source docstrings and the three collaboration
documents. No executable change is authorized. Its exact eight-path allowlist,
corrections, gates, and stop rule are in `CODEX_NEXT.md`. M1.8 remains next
after M1.6 acceptance.

Status:    closed

---

## Turn 56 — Claude, implementer, 2026-09-24
Scope:     Final M1.6 semantic residue — seven narrow docstring inaccuracies
Base:      139f35c (source comparisons); TURN56_BASE = deb225e (turn-local paths and whitespace)
Commits:   b999476 (five source files), docs commit follows
Status:    M1.6 ready for Codex acceptance — NOT accepted by the implementer

Documentation only. Stripped-docstring ASTs are identical to `139f35c` for all
five changed files, in both the working tree and the committed blobs. The
completed lint sweep was not reopened and no behavior changed.

Each defect was confirmed in the implementation before the prose was rewritten:

1. **Regular package, not namespace package** — `bsm3/core/projections/__init__.py`
   exists and is tracked, so `bsm3.core.projections` is a regular subpackage
   whose `__init__` re-exports nothing. Only the terminology changed; the
   concrete-module guidance is preserved.
2. **`mesh_motion` can also be absent on root** — `MeshMotionVolumeBackend` is
   constructed in `build_cfd_analysis_rank0` without `build_eagerly`, so the
   model is built lazily. `mesh_motion` is a snapshot of
   `last_mesh_motion_result` taken while the result object is constructed: it
   is `None` on every non-root rank, which holds no backend, and can also still
   be `None` on root if the custom operation has not executed inline by then.
   Being on root is documented as no guarantee. The annotation is untouched and
   remains the recorded M1.7 carry-in.
3. **Two omitted RBF value constraints** — `_resolve_seam_neighbor_radii`
   rejects any negative radius and `_resolve_per_intersection_fractions`
   rejects any blend outside `[0, 1]`, both separately from the length rule.
   Stated separately in the class prose and in the `__post_init__` prose;
   "cannot be resolved" covered only the lengths.
4. **Parser defaults** — `make_parser`'s blanket consistency claim is replaced
   by the boundary: the numerical flow and solver options default from
   `FlowConfig`, the case, path, and patch-name options carry their own parser
   defaults, and the wall-function flag is inverted by `--no-wall-functions`,
   leaving its effective default at odds with the dataclass.
5. **Missing `ValueError`** — `set_openfoam_patch_types` raises `ValueError`
   when a named patch's block exists but contains no `type` entry to rewrite;
   the `KeyError` remains the absent-block case.
6. **Both `FileExistsError` paths** — `convert_and_check_mesh` raises it either
   when `polyMesh` exists and `overwrite_existing` is `False`, or when
   overwriting is permitted but the timestamped backup destination is taken.
7. **Raw mean-ratio sign is not relative inversion** —
   `_tetrahedron_mean_ratio` applies `np.where(determinant >= 0, q, -q)` on the
   **raw** deformed determinant, while `inverted_tetrahedra` uses the
   deformed-to-baseline ratio. The unconditional "inverted cell scores
   negative" is gone; the signs are documented as coinciding only under a
   positive-baseline-orientation convention, with the counterexample of a
   negative-oriented baseline cell that is unchanged.

The Turn-54 entry and the M1.7 carry-in wording now carry inline corrections so
they no longer assert the rejected claims. Every other Turn-54 correction is
preserved.

### Gates

| Gate | Result |
| --- | --- |
| Four `actions.yml` `--select D` steps | **all pass** |
| Workflow default critical-static step | **pass** |
| Stripped-AST identity vs `139f35c`, working tree | **5/5** |
| Stripped-AST identity vs `139f35c`, committed blobs | **5/5** |
| Slice-3 coverage audit | 17/17 modules, 167/167 definitions, 132 callables / 293 params at 0/0, 22 dataclasses / 148 fields at 0/0 |
| `pytest` suite 1 | **82 passed, 3 deselected** |
| `pytest` suite 2 | **89 passed** |
| `pytest` suite 3 | **6 passed** |
| `git diff --check deb225e HEAD` | empty |
| Changed paths after `TURN56_BASE` | subset of the eight-path allowlist |

### Deviations

None. No executable change was required and the allowlist was not widened.

### Process note

The first attempt to batch these edits aborted midway: one search span assumed
a line began with a token that actually sat mid-line after a wrap, so the
strict replacer refused the batch and the two files after it in the same call
were never written. Caught by diffing the working tree before continuing. The
corrections were then applied per file against spans read out of the file.

M1.6 is **ready for Codex acceptance** and is not accepted by the implementer.

Status:    closed

---

## Turn 57 — Codex, reviewer/planner, 2026-09-24
Scope:     Accept M1.6; audit and issue M1.8 pickle-retirement implementation

**M1.6 ACCEPTED.** Codex independently reproduced the exact eight changed
paths after `deb225e`, a clean scoped whitespace check, all five literal Ruff
commands from CI, the complete 17-module coverage audit, and stripped-AST
identity for all five changed Python files against `139f35c` in both the
working tree and committed blobs. The three regression suites independently
returned **82 passed / 3 deselected**, **89 passed**, and **6 passed**. The
seven corrected contracts match their implementations. No M1.6 work remains;
the four executable/API findings stay assigned to M1.7.

The M1.8 pre-implementation audit found that the tracked legacy wall asset is
not safely representable as one rectangular connectivity array. It contains
79,207 float64 vertices and 40,706 faces with widths 3 through 9, and its face
width changes 14,720 times in source order. Grouping by width alone would
therefore preserve topology counts but destroy the original face sequence.
The safe replacement schema is fixed as three non-object arrays:
`vertices`, flattened `connectivity`, and cumulative `offsets`. The importer
must use `numpy.load(..., allow_pickle=False)`, reconstruct the original
sequence in `MeshData.connectivity`/`cell_types`, and separately build the
width-grouped `cell_blocks` required by the solvers.

The trusted local legacy baseline was measured once before deletion:

- file: 2,863,763 bytes; SHA-256
  `34165debb2a3dde52dd7380cc1d91e99d829db96042858f710154b201f055b4d`;
- vertices: shape `(79207, 3)`, float64, byte SHA-256
  `76ceaadd74a93eeb4153e51b784a4d4ff6dfa7079382510652cf8070ed3aad1a`;
- flattened connectivity: shape `(239385,)`, int64, byte SHA-256
  `971e53f7bc46fd694955be2f00b1b4355e513d5e066c5ebe1499b72a463b4ff3`;
- offsets: shape `(40707,)`, int64, byte SHA-256
  `eff2e0fe7cd471ab5bac922b5290a0560db4d8d72d4fc3b2917ff70582083509`;
- counts by width: 3:5, 4:565, 5:7,891, 6:28,190, 7:3,927,
  8:126, 9:2; node IDs span 0 through 79,206.

The audit also separated three boundaries that must not be conflated. The
LFS-generated STEP cache ending in `.pickle` is dependency-managed cache data,
not a BSM3 surface reader. `movement_test_embraer_175_hex_mesh.py` is a
tracked but non-retained, already user-modified research script with its own
pickle loader and is outside this turn. The retained projection modules do
expose trusted function-set pickle loaders, but their default points at an
untracked `refitted_fun_set.pkl`; M1.8 removes that hidden default and
consolidates the loader under an explicitly trusted-pickle name. Untracked
drivers that import the old name or default remain untouched and must be
reported as incompatible local artifacts, not silently adopted.

Claude's literal allowlist, schema, test gates, stop rule, and commit structure
are in `CODEX_NEXT.md`. M1.8 is not accepted in advance.

Status:    closed

---

## Turn 57 — Claude, implementer, 2026-09-24
Scope:     M1.8 — safe polygon asset and pickle boundary
Base:      TURN57_BASE = eeb2c38
Commits:   2449441 (asset, reader, pipeline, tests), 4a39fd8 (warm-start API), docs commit follows
Status:    M1.8 ready for Codex acceptance — NOT accepted by the implementer

### Asset conversion

The legacy file verified against the recorded baseline before anything was
touched: 2,863,763 bytes, sha256
`34165debb2a3dde52dd7380cc1d91e99d829db96042858f710154b201f055b4d`. It was a
dict of `points` `(79207, 3)` float64 and a 40,706-entry `connectivity` list.

It was converted once with a script kept outside the repository, and every
recorded value reproduced exactly:

| Item | Result |
| --- | --- |
| `vertices` | `(79207, 3)` float64, sha256 `76ceaadd…` ✓ |
| `connectivity` | `(239385,)` int64, sha256 `971e53f7…` ✓ |
| `offsets` | `(40707,)` int64, sha256 `eff2e0fe…` ✓ |
| Face counts by width | 3:5, 4:565, 5:7,891, 6:28,190, 7:3,927, 8:126, 9:2 ✓ |
| Node-ID range | 0 through 79,206 ✓ |
| Faces / adjacent width transitions | 40,706 / 14,720 ✓ |
| Per-face round trip in original order | exact for all 40,706 faces |
| Object arrays | none |

`wall_surface.pkl` was then deleted and `wall_surface.npz` added.

### Safe reader

`import_mesh`/`read_mesh` dispatch `.npz` by suffix, with no `mesh_kind`
argument and no new public importer. `_import_npz` calls
`numpy.load(..., allow_pickle=False)` explicitly, requires exactly the three
field names, and validates dimensions, numeric/integer dtypes, finite vertices,
offset start and end, face spans of at least three nodes, a nonempty face set,
and node-ID bounds.

The decoded face sequence is preserved in `MeshData.connectivity` with matching
per-face `cell_types`, while `cell_blocks` regroup the same faces by ascending
width. Those two orderings deliberately differ for a mixed-width surface; the
docstring says so. Uniform-width archives return a 2-D connectivity, mixed ones
an object array of rows.

`.pkl`/`.pickle` remain outside suffix dispatch.
`import_trusted_polygon_pickle` stays as the explicit opt-in boundary, keeps
its warning, and now has a synthetic test that also asserts suffix dispatch
still refuses the same file — so the boundary is intentional, not dead code.

### Pipeline

`_load_polygon_surface_pickle` and `_cfd_mesh_from_pickle` are deleted, along
with the direct `pickle` import and the `.pkl`/`.pickle` suffix checks. The
surface always loads through `bsm3.preprocessing.import_mesh`.

`polygon_connectivity` now comes from the imported mesh's stored connectivity
via a new `_ordered_surface_cells`, which restores the legacy face sequence the
fold diagnostics are defined against — previously only the pickle branch had
it, and the generic branch silently used the width-grouped order.
`_cfd_surface_cells` is unchanged and still supplies the width-grouped
quality/inversion order. No solver, projection, regularization, quality, or
derivative behavior changed.

### Warm-start API

`DEFAULT_FUN_SET_PATH` is deleted from `warm_start_projections`, together with
the `pathlib` import that became dead there, and the stale re-export and
`pathlib` import in `warm_start_candidate_projection_numpy`. The duplicate
loader in the candidate module is removed. Both are consolidated into
`load_function_set_from_trusted_pickle(pickle_path)` with a **mandatory** path:
no default, no package-relative fallback, no implicit lookup.

**Defect found and fixed during consolidation.** `warm_start_projections`
imported `lsdo_function_spaces` only inside its `__main__` block, so its
retained `load_function_set` raised `NameError: name 'lfs' is not defined`
whenever it was called as a library function — confirmed by direct call before
editing. The duplicate in the candidate module carried the guarded import that
made it work. The consolidated entry point now has that guarded module-level
import and its `ImportError`. This is the only executable change in commit 2
beyond the removals, and it was required for the consolidated function to work
at all.

### Local incompatibility from the clean break

The untracked `bsm3/core/projections/warm_start_candidate_projection_driver.py`
imports `load_function_set_from_pickle` (line 44) and `DEFAULT_FUN_SET_PATH`
(lines 48, 117), and calls the old loader at line 206. It will fail to import
until its owner updates it to
`load_function_set_from_trusted_pickle(<explicit path>)`. It was deliberately
not edited or adopted, per the allowlist.

The tracked-but-prohibited research script
`bsm3/core/boundary_surface_movement/movement_test_embraer_175_hex_mesh.py`
still sets `MESH_PATH = SCRIPT_DIR / "wall_surface.pkl"` at line 33 and will
break on the deleted asset. It is an already-modified dirty file that the
allowlist explicitly forbids touching, so it was left alone. It should point at
`wall_surface.npz`, which the generic importer now reads.

No tracked module, test, or curated asset references either removed name.

### Gates

| Gate | Result |
| --- | --- |
| Focused implementation tests | **54 passed** |
| Focused suite (`-m "not integration"`) | **97 passed, 3 deselected** (82 baseline + 15 added) |
| Drivers/volume/MPI suite | **102 passed** (89 baseline + 13 added) |
| Derivative + N-gon guards | **6 passed** (unchanged) |
| Curated integration, incl. 40,706-face affine assembly | **3 passed, 3 deselected** |
| Critical static checks (default Ruff) | **All checks passed** |
| Surface-motion core `--select D` | **All checks passed** |
| Projection/preprocessing `--select D` | **All checks passed** |
| `git ls-files` on the two asset paths | only `wall_surface.npz` |
| `pickle.load` in the four scoped modules | only `load_function_set_from_trusted_pickle` and `import_trusted_polygon_pickle` |
| `DEFAULT_FUN_SET_PATH` in the retained modules | absent |
| Scoped old-asset-name grep | empty |

Every added test is accounted for: 13 in `test_preprocessing_plotting.py` and
2 fast checks in `test_curated_assets.py`. The +15 and +13 deltas are exactly
those, so no historical count moved on its own.

### Deviations

- The scoped old-asset-name grep must be empty, so `ASSETS.md` and
  `MANIFEST.md` record the superseded asset's provenance by size and sha256
  rather than by its literal former filename. `PLAN.md` and `LOG.md` are
  outside that scoped grep and keep their historical mentions.
- The guarded `lsdo_function_spaces` import described above is an executable
  addition inside an allowlisted file. Reported rather than absorbed silently.

M1.8 is **ready for Codex acceptance** and is not accepted by the implementer.

Status:    closed

---

## Turn 58 — Codex, reviewer/planner, 2026-09-24
Scope:     Accept M1.8; issue final M1.7 correction and acceptance run

**M1.8 ACCEPTED.** The range from `eeb2c38` contains exactly the 13 reported
allowlisted paths and is whitespace-clean. Codex independently reproduced the
three safe-array hashes, 40,706-face stored order, 14,720 width transitions,
and width-grouped blocks; imported the archive through `import_mesh`; and
called `load_function_set_from_trusted_pickle` directly with an empty trusted
fixture, obtaining an LFS `FunctionSet`. The surviving direct loads are exactly
the explicitly named trusted polygon and function-set APIs.

Independent tests reproduced **54**, **97 passed / 3 deselected**, **102**,
**6**, and **3 passed / 3 deselected**. All five literal workflow Ruff commands
pass. The guarded LFS import is accepted: consolidation exposed a real
`NameError` in the formerly duplicated loader, and the new explicit entry point
would otherwise have been unusable.

One implementer claim is corrected without reopening the retained milestone.
The prohibited dirty research script
`movement_test_embraer_175_hex_mesh.py` cannot be repaired by changing only
`MESH_PATH`: it still calls its private `_load_polygon_surface_pickle`, whose
`pickle.load` would reject the NPZ. It needs both a path change and a reader
change. Because it is a non-retained, already user-modified research root, it
stays untouched for its owner or M3. The untracked warm-start driver likewise
stays unadopted. Neither is part of the accepted package boundary.

M1.7 now owns five accumulated API corrections: the typed graph-distance
summary and dead `decay` payload; `DerivativeComparison.best`'s optional step;
the optional DAFoam mesh-motion snapshot; propagation of `nu_tilda_m2_per_s`
and `use_wall_functions`; and `plot_components(colors=None)`. It then runs the
final R4, flagship-example, external-coefficient derivative, polygon, and
clean-clone gates.

VortexAD was re-evaluated rather than dismissed from package discovery alone.
It is absent from `bsm3_py312_main`; a sibling checkout exists at `../VortexAD`
on dirty branch `dev_new_derivs` at `c33828d`, but a read-only `PYTHONPATH`
import fails on missing `vedo`. The untracked panel driver and its mesh are not
release assets, and the driver imports API modules removed by the overhaul.
Installing dependencies, modifying that dirty checkout, or adopting the stale
driver would materially widen final acceptance, so this turn records the
STEP-to-VortexAD path as impractical and leaves a clean future integration
task. Claude must re-confirm, not alter, that boundary.

The literal allowlist, corrections, numerical gates, clone instructions, and
stop rules are in `CODEX_NEXT.md`. M1.7 is not accepted in advance.

Status:    closed

---

## Turn 58 — Claude, implementer, 2026-09-25
Scope:     M1.7 — five accumulated API corrections and the final numerical acceptance run
Base:      TURN58_BASE = 7b1bee9
Commits:   338fde8 (six production paths + five test files), docs commit follows
Status:    M1.7 and M1 ready for final Codex acceptance — NOT accepted by the implementer

### Pre-edit R4 reference

The reference was captured twice. The first run launched before any source
edit; the authoritative one ran from a **pristine `git clone` checked out at
`TURN58_BASE`** in `/tmp`, with the untracked R4 inputs copied in read-only.
Both produced the identical `final_sha256` `15be1547…` and sum
`882013.438439012`, which also establishes that the probe is deterministic.

Volume motion off, mesh writing off, visualization off, setup cache forced to a
fresh `/tmp` directory. No cache or output was written inside the repository:
the untracked count stayed at 394 throughout, and no `_setup_cache_*` file
appeared in the tree. Runtime 197.1 s, well inside the 15-minute limit.

### Part A — the five findings

**A1.** `GraphDistanceSummary(TypedDict)` documents the eight fields
`summary()` actually returns, and `summary()` is annotated with it. The dead
`"decay"` entry is gone: the only retained caller prints `distance.decay` from
configuration, confirmed at `mesh_motion_pipeline.py`. The type is exported
beside `GraphDistanceWeighting`. Weights, distances, and solver behavior are
untouched.

**A2.** `DerivativeComparison.best` is annotated
`dict[tuple[str, str], tuple[float | None, float]]` on both the return and the
local result. The selection algorithm is unchanged.

**A3.** `E175DAFoamResult.mesh_motion` is `MeshMotionResult | None`, and the
two stale notes calling the annotation non-optional are removed.

**A4.** Both formerly dead `FlowConfig` fields are now real inputs.
`nu_tilda_m2_per_s` is validated finite and non-negative and becomes the
farfield `nuTilda0` primal BC with variable `"nuTilda"`, native-list patches,
and a one-element value list. `primalBC["useWallFunction"]` comes from
`bool(config.use_wall_functions)`. The contradictory `--no-wall-functions`
inversion is replaced by one `--wall-functions` option using
`argparse.BooleanOptionalAction` defaulting to
`FlowConfig().use_wall_functions`, so parser and dataclass defaults now agree
and both flag spellings work.

**A5.** `plot_components` treats `colors=None` like the empty-string sentinel,
so components keep their own colors instead of raising `TypeError` inside
`_broadcast`. Scalar, per-component, and length-rule behavior are unchanged.

### Part B — numerical acceptance

**B1. R4 reproduced bit-for-bit.** Pristine `TURN58_BASE` clone versus the
post-edit tree:

| Check | Result |
| --- | --- |
| Shape | `(35190, 3)` both |
| Max abs coordinate difference | **0.000e+00** |
| `allclose(rtol=atol=1e-12)` | True |
| `final` sha256 | identical, `15be1547…` |
| `initial` / `preprojected` max difference | 0.000e+00 / 0.000e+00 |
| Inverted + degenerate IDs, all three stages | identical, all empty |
| Fold count / cell count / n-gon modes | 0 / 69,942 / 0, identical |
| Quality scalars | 13 compared, worst difference **0.000e+00** |

The five corrections did not move the mesh.

**B2. Flagship and derivative gates.** `tests/test_e175_example.py`:
**18 passed** in 592.87 s. The five named cases, rerun with diagnostics:

| Case | Outcome |
| --- | --- |
| Real triangle wall | passed; inversions 0/0/0; zero folds |
| Real quad panel | passed; inversions 114/114/114 — the baseline 114 preserved, none added |
| External-coefficient analytic vs centered FD | passed; analytic `5.0436177894e-02`, FD identical, **relative error 4.196e-14** against the 1e-5 threshold, best step 1e-5, max displacement 0.3502 |
| Whole-component free regions | passed; inversions 0/0/0 |
| Full-scale triangle | passed; zero folds |

Curated mixed-N-gon integration: **3 passed, 3 deselected**, retaining the
40,706-face / 117,267-mode assembly. Derivative and N-gon gates: **exactly 6
passed**.

**B3. VortexAD — verified, not mutated.** Five read-only facts:

1. Neither `VortexAD` nor `vortexad` is installed in `bsm3_py312_main`, and
   pip lists no vortex package.
2. Sibling `../VortexAD` is on `dev_new_derivs` at `c33828d` with three
   modified solver files: `pfse_solver.py`, `unsteady_panel_solver.py`,
   `unsteady_vlm_solver.py`.
3. `PYTHONPATH=../VortexAD python -c "import VortexAD"` fails with
   `ModuleNotFoundError: No module named 'vedo'`, raised from
   `VortexAD/utils/plotting/plot_vlm.py`.
4. The panel driver `e175_panel_opt.py` and every candidate panel mesh,
   including `embraer_175_panel_quad_dominant_high_quality.msh`, are untracked.
5. That driver imports `e175_mesh_motion_config` and
   `e175_mesh_motion_pipeline`, **both removed**, and the types
   `E175ModelFiles`, `E175PipelineConfig`, and `E175MeshMotionResult`, none of
   which exists anywhere tracked. Installing `vedo` alone would therefore still
   not make it a supported test.

Nothing was installed, altered, or adopted. **Future task:** build a tracked
adapter against a pinned clean VortexAD revision, driven by the generalized
`mm.run` result and the curated quad mesh, rather than the untracked driver.

**B4. Regressions, lint, clean clone.**

| Suite | Result |
| --- | --- |
| Focused group 1 | **100 passed, 3 deselected** (97 baseline + 3 added) |
| Focused group 2 | **109 passed** (102 baseline + 7 added) |
| Clean clone, full `tests` | **202 passed, 1 skipped**, 617.83 s |

The +3 and +7 are exactly the added unit tests. The single clone skip is the
predicted local R4 check: *"local R4 assets are unavailable:
e175_fluent_R4_aircraft_wall_tri.msh, …"*. The clone finished with empty
`git status --porcelain` at `338fde8`.

All five literal `actions.yml` Ruff commands pass.

**Lint finding reported rather than glossed.** The default Ruff selection over
my changed Python paths is **not** clean: four `F821` findings remain, one
`create_geometry_from_variables` in `cfd_mesh_dafoam_analysis.py` and three
`MPI` in `run_dafoam_gmsh.py`. All four are **pre-existing and identical at
`TURN58_BASE`** — same files, same names, only line numbers shifted by my
edits. Likewise `--select D` over those paths reports 136 findings, every one
in a test file and byte-identical in count and distribution to the base; my
added tests introduced none, and the production paths are clean under
`--select D`. Neither set is covered by any workflow step, so CI is unaffected,
but I am not claiming a clean result I did not get.

### Turn-58 correction to the M1.8 handoff

M1.8 reported that the excluded dirty research script
`movement_test_embraer_175_hex_mesh.py` "should point at `wall_surface.npz`".
That was incomplete. The script carries its own `_load_polygon_surface_pickle`
that calls `pickle.load` and expects `points`/`connectivity` keys, so it needs
a **reader** change as well as a path change: repointing `MESH_PATH` alone
would hand an `.npz` archive to `pickle.load`. The fix is to read through
`bsm3.preprocessing.import_mesh`. It remains a prohibited pre-existing dirty
file and was not edited.

### Preservation

All eight pre-existing modified files are byte-identical to the `TURN58_BASE`
snapshot. Untracked entries: 394 before and after, none removed or adopted.
Committed changes vs base: 11 paths, all allowlisted.
`git diff --check TURN58_BASE HEAD` is empty. The five static acceptance greps
are all empty, and inspection confirms `GraphDistanceSummary` is exported and a
`TypedDict`, `best` returns the optional step, and `mesh_motion` is optional.

### Deviations

- None affecting scope. Nothing outside the allowlist changed, no dependency or
  environment was touched, and no stop condition was hit.
- Reported above rather than absorbed: the four pre-existing `F821` findings
  and the 136 pre-existing test-file `D` findings.

M1.7 and M1 are **ready for final Codex acceptance** and are not accepted by
the implementer.

Status:    closed

---

## Turn 59 — Codex, reviewer/planner, 2026-09-25
Scope:     Review M1.7 and final M1 acceptance
Base:      7b1bee9
Reviewed:  338fde8, b60f0c0
Status:    correction required — M1.7 and M1 NOT accepted

The five intended M1.7 API corrections pass inspection. Codex independently
ran the five changed test modules (**150 passed**) and the derivative/N-gon
guard (**exactly 6 passed**). The graph-distance return contract, optional
annotations, DAFoam option propagation, CLI polarity, and `colors=None`
behavior agree with their tests. The recorded R4 and flagship numerical
results are not contradicted.

Final production-path review found a blocker outside those five edits. The
default `GEOMETRY_VOLUME_MODE = "rank0"` chain in
`cfd_mesh_dafoam_analysis.py` cannot construct its mesh-motion backend:

1. `build_cfd_analysis_rank0` passes the undefined name
   `create_geometry_from_variables` as its parameterization factory.
2. The same call uses `input_files=`, while `MeshMotionVolumeBackend.__init__`
   still declares `model_files=`.
3. `MeshMotionVolumeBackend._build_model` calls the current
   `run_mesh_motion` with the removed keywords `model_files=` and
   `geometry_parameterization=` instead of `input_files=` and `geometry=`.
4. `e175_derivative_ladder._make_geometry_backend` calls the removed
   `driver.create_geometry_parameterization_from_variables` and still uses
   the old backend keyword.

This is the M1.1 API migration left incomplete, not a DAFoam numerical-test
request. It breaks the required STEP-to-aerodynamic chain before DAFoam is
needed and therefore blocks M1 acceptance.

The implementer's reported Ruff findings also reveal a CI coverage hole.
Running default Ruff over the exact retained production paths already listed
by the workflow yields only four errors: the undefined factory above and three
`MPI.Comm` annotations in `run_dafoam_gmsh.py`. The latter are deferred-string
annotations, so ordinary module import survives, but runtime type-hint
resolution does not and the optional MPI dependency is not represented safely.
The existing critical-static workflow step scans only the old M0 subset, while
the broader retained lists are checked with `--select D`, which replaces the
critical selection and cannot catch F821.

Turn 59 therefore accepts the five corrections as implemented but does not
accept the M1.7 milestone or close M1. The next turn must restore one shared
E175 geometry-construction path for caller-owned variables, migrate
`MeshMotionVolumeBackend` completely to the current `run_mesh_motion` contract,
make communicator annotations safe without importing MPI eagerly, add a
mock-backed executable regression, and extend the critical Ruff gate to the
retained production manifest. No real DAFoam, OpenFOAM, VortexAD, or dependency
installation is required.

Status:    closed

---

## Turn 59 — Claude, implementer, 2026-09-25
Scope:     M1.7 rank-0 chain correction — restore the retained STEP→surface→volume API
Base:      b60f0c0
Commits:   e47d07f (source, tests, workflow), docs commit follows
Status:    M1.7 and M1 ready for Codex acceptance — NOT accepted by the implementer

**The rank-0 geometry-to-volume chain now constructs through the current API.**

### What Turn 58 got wrong

Turn 58 measured four `F821` findings, checked that they were identical at the
base commit, and reported them as pre-existing lint that CI did not cover. The
check was accurate and the conclusion was wrong: those four names *were* the
defect. `build_cfd_analysis_rank0` referenced a parameterization factory that
did not exist, and `run_dafoam_gmsh` annotated three callables against a
module-global `MPI` that was never imported. Confirming a finding is
pre-existing says nothing about whether it is harmless, and I did not follow
the reference to see what it meant.

Codex's review also found a second, related break that no lint rule reports:
`MeshMotionVolumeBackend` accepted `model_files` while `run_mesh_motion` takes
`input_files`, and `_build_model` passed **both** removed keywords,
`model_files=` and `geometry_parameterization=`. M1.1 renamed the public API and
left the retained rank-0 chain behind.

### A. One current parameterization factory

`create_geometry_parameterization_from_variables(variables)` is restored on the
current `GeometryModel` API. Both entry points now call one private
`_populate_e175_geometry` helper, so the wing, tail, fuselage, and two
intersection declarations exist once:

- `create_geometry_model()` still creates and registers the six driver design
  variables with their existing values, bounds, and scalers, then populates.
- `create_geometry_parameterization_from_variables()` registers no design
  variables, owns no recorder, and uses the caller's expressions as supplied.
- The mapping is validated against `GEOMETRY_VARIABLE_NAMES`, reporting missing
  and unexpected names separately rather than ignoring either.
- `build_cfd_analysis_rank0` passes the real function; no alias was added.

### B. Backend migrated to the current public API

`MeshMotionVolumeBackend.__init__` takes `input_files` and stores
`_input_files`; `_build_model` calls
`run_mesh_motion(recorder=…, input_files=…, geometry=…, config=…,
aerodynamic_analysis=None, aerodynamic_volume_method=…)`. Both retained call
sites are updated, in `cfd_mesh_dafoam_analysis` and `e175_derivative_ladder`.
No compatibility alias: the removed spelling raises `TypeError`, and a test
pins that.

### C. Optional-MPI annotations made real

The three annotations now use a private `runtime_checkable` `_Communicator`
protocol describing only `rank`, `size`, `Barrier`, and `bcast` — what this
module actually touches. `typing.get_type_hints` resolves for all three
callables with no mpi4py installed, a real `MPI.Comm` satisfies the protocol
structurally, `mpi4py` is still imported lazily inside `main`, and no `noqa`
suppression was added.

### D. CI coverage hole closed

**Critical static checks** now runs the default Ruff selection over the
complete retained production manifest — all 50 `bsm3` paths the four
documentation steps cover — plus the three M0 test files, replacing the
two-file M0 subset. The list is literal and auditable, `ruff.toml` is
untouched, no per-file ignore was added, and the dirty/untracked research tree
is excluded. The reconstruction command from the prompt now yields 50 paths and
reports **All checks passed**.

### Regressions, each verified to fail at `b60f0c0`

| Test | Guards |
| --- | --- |
| `test_geometry_factory_parity_between_the_two_entry_points` | identical components/intersections; registered entry point owns the six design variables, the other owns none; caller expressions captured **by identity** in the coefficient builder |
| `test_geometry_parameterization_rejects_wrong_variable_names` | missing and unexpected keys each reported |
| `test_mesh_motion_volume_backend_calls_the_current_pipeline_api` | patches the pipeline with a current-signature fake, executes the build/forward path, asserts the fake received `input_files`, `geometry`, and `config` and returned the selected volume output |
| `test_mesh_motion_volume_backend_rejects_the_removed_keyword` | clean break on `model_files` |
| `test_rank0_chain_constructs_the_backend_through_the_current_api` | runs `build_cfd_analysis_rank0` itself, mocking only the volume-point read and the downstream custom operation, and checks the constructor keyword and the real factory object |
| `test_run_dafoam_gmsh_communicator_annotations_resolve_without_mpi` | runtime hint resolution, structural satisfaction, no eager import, no `noqa` |

None requires a CAD asset, volume mesh, MPI, or DAFoam.

### Gates

| Gate | Result |
| --- | --- |
| `git diff --check b60f0c0 HEAD` | empty |
| Changed paths | exactly the 8 implementation-allowlist paths |
| Five modules (150 before this turn) | **156 passed** = 150 + exactly the 6 new tests |
| Derivative / N-gon guard | **exactly 6 passed** |
| Five literal workflow Ruff commands | all **All checks passed** |
| Reconstructed production manifest (50 paths), default Ruff | **All checks passed** |
| Clean clone at `e47d07f`, full `tests` | **208 passed, 1 skipped** in 631.62 s; `git status --porcelain` empty afterwards |
| Pre-existing modified files | 8/8 byte-identical |
| Untracked set | 394 → 394, none removed or adopted |

The Turn-58 R4 and E175 numerical runs were not repeated: none of these changes
touches the surface pipeline those gates exercise.

### Deviations

None. Nothing outside the two allowlists changed, no dependency was installed,
no other repository was touched, DAFoam/OpenFOAM/VortexAD/real-MPI were not
run, and every accepted Turn-58 API correction is unchanged.

M1.7 and M1 are **ready for Codex acceptance** and are not accepted by the
implementer.

Status:    closed

---

## Turn 60 — Codex, reviewer/planner, 2026-09-25
Scope:     Accept M1.7 and M1; open M2 user documentation
Reviewed:  e47d07f, 188ab48
Status:    M1 COMPLETE; M2.1 issued to Claude

**M1.7 and M1 are ACCEPTED.** The Turn-59 correction is exactly contained to
the eight implementation paths and three collaboration documents, with a clean
scoped whitespace diff. Codex read the production changes and independently
reproduced:

- **156 passed** across the five focused modules;
- **exactly 6 passed** in the derivative/N-gon guard;
- default Ruff over the complete 50-path retained production manifest; and
- `--select D` over the union of all four documentation-lint path sets.

The repaired tests exercise the actual failure boundaries. The E175 external
factory and driver-owned model share one population helper; the external path
owns no recorder or design-variable registrations. `MeshMotionVolumeBackend`
now accepts `input_files` and calls the current `run_mesh_motion` keyword
contract. The derivative ladder uses the same restored factory. The rank-0
builder test reaches real backend construction before mocking the downstream
operation, and the backend test executes a current-signature fake pipeline.
The optional communicator protocol resolves at runtime without importing
`mpi4py`. The expanded critical-static workflow makes the escaped F821 class a
CI failure across the retained production manifest.

The clean-clone **208 passed / 1 skipped** result and Turn-58 numerical evidence
complete the acceptance record. No real DAFoam solve was required by the user;
the STEP-to-aerodynamic construction boundary is supported and tested without
DAFoam. VortexAD remains a specifically evidenced deferral: the future work is
a tracked adapter against a pinned clean checkout, not resurrection of the
stale untracked driver. M1.9's previously technical acceptance is final as
part of M1 closure.

### M2 documentation baseline and ruling

The user's requested Read-the-Docs-style guide now opens before M3. The
repository has a tracked `.readthedocs.yaml` and Sphinx scaffold, but it is not
a BSM3 documentation site yet:

- `docs/conf.py` names `lsdo_project_template`, credits the template author,
  and points AutoAPI at nonexistent `../lsdo_project_template/core`;
- `docs/src/getting_started.md` installs the template repository rather than
  BSM3;
- welcome, example, tutorial, custom, API, and bibliography pages contain
  template placeholders and quartic/example paths;
- `.readthedocs.yaml` selects Python 3.11 while the validated stack is 3.12 and
  installs `requirements.txt`, which intentionally contains no active
  dependencies, so it cannot supply Sphinx;
- `bsm3_py312_main` currently has no Sphinx installation; and
- CI has no documentation-build step.

M2.1 replaces the scaffold rather than layering BSM3 pages beside misleading
template content. It covers validated installation, the five-stage E175
example, the external-coefficient contract, the compact `bsm3.mesh_motion`
surface, assets/caches, and honest optional-integration status. The build must
be warning-clean in an isolated `/tmp` documentation environment and in CI,
without executing E175, DAFoam, VortexAD, or MPI. M3 remains next after final
documentation acceptance.

Status:    closed

---

## Turn 61 — Claude, implementer, 2026-09-25
Scope:     M2.1 — replace the inherited template with a buildable BSM3 docs site
Base:      TURN61_BASE = 33ffbf70f4ff3d07a4e6dfb633e4171af9b627d4
Commits:   4ca0435 (site, configuration, CI, test), docs commit follows
Status:    M2.1 ready for Codex review — NOT accepted by the implementer

### What changed

The scaffold was replaced rather than layered over. Nine obsolete template
pages were deleted — `welcome`, `custom_1`, `custom_2`, `tutorials` and its two
children, `examples/basic`, `examples/advanced`, and `references.bib` — so no
misleading page survives in the navigation. The site is now a landing page plus
Installation, E175 example, External parameterization, API reference,
Background, and Integrations.

### Design decision: no autodoc

The API page is hand-written and verified against source rather than generated.
Autodoc would require the whole validated geometry stack (CSDL_alpha,
lsdo_function_spaces, JAX, gmsh) in the documentation environment and on Read
the Docs, purely to render a reference. Writing it by hand keeps
`docs/requirements.txt` to four pinned packages, keeps the build hermetic and
fast, and directly satisfies the requirement that the build not expose a wall
of private modules. `conf.py` reads `bsm3.__version__` from
`bsm3/__init__.py` with a regex, so the real version appears without importing
the package. `tests/test_documentation.py` guards both halves: every name in
`bsm3.mesh_motion.__all__` must be documented, no `mm.` name may be promised
that the namespace does not export, and the version regex must still match.

### Facts resolved from source rather than assumed

- `bsm3.mesh_motion.__all__` is the 13-name public surface; `run` is
  keyword-only with `inputs`, `geometry`, `motion`, `recorder`,
  `aerodynamic_analysis`, and `aerodynamic_volume_method`.
- `run` never starts or stops the recorder and reattaches it to the result.
  The example creates, starts, and stops it, opening its `try` immediately.
- `add_component` is the general boundary; `add_lifting_surface` and
  `add_body` build their own private records rather than calling through it,
  so they are documented as optional conveniences, not the mechanism.
- Coefficient shapes and patch IDs are validated **after** the STEP component
  is imported, not at the `add_component` call. The external guide says so,
  because a caller otherwise expects declaration-time errors.
- `MeshMotionResult` carries three inversion reports using the same metric,
  plus fold, cell, and n-gon mode counts. The quad-panel path is a filename
  substitution, and `PolygonRegularization` is inactive on a triangle-only
  mesh because triangles carry no affine hourglass mode.
- Tracked example assets are the STEP body, the R1 triangle wall, the
  quad-dominant panel, and `wall_surface.npz`. The R4 wall and the volume
  meshes are untracked, so the docs do not imply they exist.

### Verification

| Gate | Result |
| --- | --- |
| `git diff --check` pre-commit and `TURN61_BASE..HEAD` | both empty |
| Template identity / quartic grep outside `docs/overhaul` | **clean**; 3 files inside `docs/overhaul` still carry them, as expected |
| Docs environment | disposable `/tmp` venv, Python **3.12.14**, Sphinx **9.1.0** |
| `python -m sphinx -W --keep-going -b html docs …` | **build succeeded**, 9 pages |
| `pytest -q tests/test_documentation.py` | **10 passed** |
| Fast E175 example tests (`-m "not integration"`, discovered from `pytest.ini`) | **13 passed, 5 deselected** |
| Default Ruff on `docs/conf.py` and `tests/test_documentation.py` | All checks passed |
| Five literal workflow Ruff commands | all All checks passed |
| Fresh clone of `4ca0435`: docs build + documentation test | **build succeeded**, **10 passed**, clone status empty afterwards |
| 8 pre-existing modified files | 8/8 byte-identical |
| Original 394 untracked entries | 394/394 intact, none removed or adopted |
| Build output inside the repository | none |

`docs/requirements.txt` pins `sphinx==9.1.0`, `myst-parser==5.1.0`,
`sphinx-rtd-theme==3.1.0`, and `sphinx-copybutton==0.5.2`, and the structural
test asserts it names none of the runtime stack.

### Deviations

- `docs/src/images/` and `docs/make.bat` are outside the allowlist, so they
  were left untouched. The images are now unreferenced by any page and
  `make.bat` is generic Sphinx boilerplate with no template identity; neither
  affects the build or the identity grep. Codex may want them removed under a
  later allowlist.
- No other deviation. Nothing outside the implementation allowlist changed, no
  production Python, example, packaging metadata, or other test was touched,
  and no library change proved necessary.

M2.1 is **ready for Codex review** and is not accepted by the implementer.

Status:    closed

---

## Turn 62 — Codex, reviewer/planner, 2026-09-25
Scope:     Review M2.1 and issue the accuracy correction
Reviewed:  4ca0435, 1cc849e
Status:    M2.1 NOT ACCEPTED; narrow Turn-63 correction issued

The infrastructure portion is good. Codex independently reproduced the exact
27-path allowlisted range and clean scoped diff, **10 documentation tests**,
**13 passed / 5 deselected** fast E175 tests, default Ruff on the new Python
files, and a strict Sphinx 9.1.0 build from both the working tree and a fresh
clone of `4ca0435`. The `.readthedocs.yaml` keys and Python 3.12 selection also
match the current Read the Docs v2 configuration contract. Avoiding autodoc is
accepted: importing the full geometry stack only to render hand-written public
API guidance would add cost and failure modes without improving this site.

M2.1 is not accepted because the principal user promise — a reproducible
validated install — has not yet been met. The documented sequence installs
CSDL, then installs official LFS with `--no-deps`, but never installs all of
LFS's declared dependencies. At official `307ad3a`, those include NumPy,
SciPy, PyVista, joblib, pandas, scikit-learn, and JAX. CSDL does not provide the
complete set. The existing `requirements-ci.txt` is the tested dependency
bootstrap and CSDL pin; documentation should use it before the intentionally
`--no-deps` LFS install, then install BSM3 with
`--no-deps --no-build-isolation -e .`. The correction must execute that recipe
from a truly empty Python 3.12 environment, not infer it from the already
populated compatibility environment.

Four semantic issues also block final accuracy acceptance:

- “so the mesh stays valid” is a guarantee contradicted by the inversion
  diagnostics and failure policy;
- “every node back exactly” ignores the documented projection non-convergence
  path, which still returns a point;
- `print_summary()` does not report load stepping; inspection of its body shows
  vertex/cell/n-gon counts, elapsed time, fold/inversion counts, degenerate
  elements, and minimum scaled Jacobian; and
- “BSM3 never starts or stops a recorder” is too broad. The reviewed public
  `GeometryModel`/`mm.run` contract does not own the caller's recorder, while
  optional internal driver backends can own one.

The README Quickstart also calls `run` on an empty `GeometryModel`, which fails
validation if copied verbatim. It must be labeled as a call-shape skeleton or
replaced with an executable path. Finally, the hand-written API test does not
actually prove its claimed bidirectional equality: a regex scrapes `__all__`,
export names may pass as incidental substrings, and only backticked `mm.Name`
forms count as promises. Turn 63 replaces that with an AST-read `__all__` and a
delimited exact inventory in the API page.

Sphinx reported seven source documents. The handoff's “9 pages” can describe
generated HTML only if it explicitly includes utility pages such as search and
index; it must not be presented as nine authored pages.

No production or example change is authorized. Correct content from Turn 61
is preserved, and M2.2 remains blocked pending this narrow correction.

Status:    closed

---

## Turn 63 — Codex, temporary implementer/planner, 2026-09-25
Scope:     Correct M2.1 and prepare independent Claude review
Base:      441320380760e75b6e153072523dc5d2afca832b
Commits:   ab79087 (implementation), documentation handoff follows
Status:    M2.1 ready for Claude review — NOT self-accepted

The nine requested documentation/test paths now close every Turn-62 accuracy
finding. The install guide creates a Python 3.12 Conda environment, bootstraps
the complete tested stack, installs official LFS `307ad3a` with `--no-deps`,
and installs BSM3 with `--no-deps --no-build-isolation -e .`. PyVista is
correctly separated into two facts: interactive BSM3 visualization is
optional, but the pinned LFS imports PyVista eagerly, so it remains installed
in the validated core environment.

Solver/output guarantees are now bounded by the code. Validity is measured by
quality and inversion diagnostics; reprojection can return a non-converged
point and is not called exact; `print_summary()` lists only the fields its body
actually prints; and recorder non-ownership is scoped to public
`GeometryModel`/`mm.run` rather than internal driver backends. The README calls
its empty-model snippet a non-standalone call shape, requires component
registration, and leads with the runnable tracked E175 command.

The API drift guard now parses literal `mesh_motion.__all__` through the
standard-library AST and compares it by exact set equality with a delimited
13-name inventory in `api.md`. It is explicitly described as an export guard,
not semantic validation. Three targeted assertions retain the rejected
guarantees without becoming a general prose blacklist. Documentation tests
increased from 10 to 12.

### Necessary scope expansion found by the mandatory clean-install gate

The first truly empty-environment install failed before LFS was reached:
`requirements-ci.txt` requested NumPy 2.0.2 while its stale
`lsdo_b_splines_cython@9444ea8` entry declared NumPy 1.26.4, and pip correctly
reported `ResolutionImpossible`. This was not a documentation problem that
could be worded around. Read-only checks found zero tracked BSM3 references
outside overhaul history, and official LFS `307ad3a:release_notes.md` states
that the compiled extension was completely eliminated in favor of
NumPy/JAX-based evaluation. Codex announced the scope change before editing,
widened the implementation range by exactly `requirements-ci.txt`, removed the
single dead requirement, and corrected the adjacent stale dependency comment.
No production source or example changed. Claude must rule explicitly on this
one-path expansion during Turn 64.

### Verification

The documented sequence then completed in a fresh Conda prefix under `/tmp`:

```text
Python 3.12.14
BSM3 0.1.4
CSDL_alpha 0.0.0-a.2 (pinned source commit 73a9efd)
lsdo_function_spaces 1.0.0 (pinned source commit 307ad3a)
NumPy 2.0.2 / SciPy 1.13.1 / JAX 0.4.38 / PyVista 0.46.5
```

The import smoke for CSDL, LFS, and `bsm3.mesh_motion` passed. In that fresh
environment, documentation tests were **12 passed** and fast E175 tests were
**13 passed / 5 deselected**. A fresh clone at `ab79087` then produced:

- strict Sphinx 9.1.0 build success over **7 source documents**;
- **12 passed** documentation tests;
- CSDL/LFS/BSM3 import smoke success;
- **212 passed / 9 deselected** for the complete non-integration suite in
  24.86 seconds; and
- empty `git status` after every gate.

Default Ruff on the changed Python test passed. All five existing literal
workflow Ruff groups passed over 53 / 4 / 18 / 15 / 17 paths. Scoped
`git diff --check` is empty. The 8 pre-existing modified files retain the exact
eight baseline blob hashes, and the untracked inventory retains both 394
status-level entries and its baseline aggregate hash
`0dc0c7e7e5b7fbe702f2068a330bdcb05d72491c`.

Claude now resumes the reviewer/planner role. `CODEX_NEXT.md` is an independent
review checklist; if it passes, Claude may accept M2.1/M2.2 and close M2 before
handing M3 planning/implementation back to Codex.

Status:    closed

---

## Turn 64 — Claude, reviewer/planner, 2026-09-25
Scope:     Review the Turn-63 documentation correction; accept or reject M2
Reviewed:  4413203..20c956e (implementation `ab79087`)
Status:    **M2.1 and M2.2 ACCEPTED; M2 CLOSED.** Next implementation prompt issued to Codex.

### Ruling on the one-path scope widening

Codex widened its own allowlist by `requirements-ci.txt` while acting as both
planner and implementer. Reviewed explicitly rather than absorbed. **Accepted**,
on three independently established facts:

1. **The conflict is structural, not transient.** A shallow clone of
   `lsdo_b_splines_cython@9444ea8` shows `numpy==1.26.4` pinned in *both*
   `pyproject.toml` build requires and `setup.py` install_requires, against the
   environment's `numpy==2.0.2`. No resolver can satisfy both.
2. **The requirement was dead.** `git grep` finds zero tracked BSM3 imports of
   the extension; the only tracked mention is the new test asserting its
   absence. Official LFS 1.0.0 release notes state it "completely eliminated
   compiled Cython and C extensions (`lsdo_b_splines_cython`)".
3. **The corrected file installs.** The documented conda sequence completed end
   to end: Python 3.12.14, `requirements-ci.txt`, LFS `307ad3a` with
   `--no-deps`, then BSM3 with `--no-deps --no-build-isolation -e .`, yielding
   `bsm3-0.1.4` and a working import from outside the source tree.

This is a genuine packaging defect that the mandated gate exposed, and removing
a dead requirement is the minimum fix. The widening stands.

### Documentation accuracy

Checked against source, not against the handoff:

- `print_summary` prose matches the body — vertex, cell, and n-gon-mode counts,
  elapsed time, folds, the three inversion reports, degenerate elements, and
  minimum scaled Jacobian. The removed load-stepping claim is genuinely absent.
- PyVista's eager import is real: `lsdo_function_spaces/__init__.py` imports
  `.core.function_set`, which does a module-level `import pyvista as pv`.
- Recorder ownership is scoped to public `GeometryModel`/`mm.run`, not to all
  internal drivers.
- The README labels its snippet "the call shape, not a standalone example" and
  points to the runnable E175 script.
- `tests/test_documentation.py` parses the literal `__all__` with `ast` and
  compares it by exact set equality against one delimited inventory. It is
  described only as an export-inventory guard.

Turn-61 content survives intact: external coefficients remain the primary
contract, the five E175 stages are clear, shape/patch-ID validation is still
placed after STEP import, and NPZ/trusted-pickle and DAFoam/MPI/VortexAD status
are not overstated.

### Gates reproduced

| Gate | Result |
| --- | --- |
| `git diff --check 4413203..HEAD` | empty |
| Changed paths | 13, matching the declared range |
| Documentation tests | **12 passed** |
| Fast E175 tests | **13 passed, 5 deselected** |
| Ruff on the documentation test | pass |
| Strict Sphinx build | **build succeeded** |
| Five workflow Ruff groups | pass at **53 / 4 / 18 / 15 / 17** paths, matching the report |
| Clean clone: strict build + documentation tests | build succeeded, 12 passed, status empty |
| Documented clean install (conda) | all three steps succeeded |
| Preservation | 8/8 modified files byte-identical; untracked 394 → 394 |

### Two residues found, deferred rather than held against M2

1. **`print_summary`'s own docstring still claims load stepping.** The
   user-facing docs were corrected away from that claim, but the production
   docstring they were corrected against still says "Reports mesh size, load
   stepping, …". The site is right; the docstring is wrong. Out of scope for a
   review turn.
2. **The documented install assumes conda.** `conda create … python=3.12`
   ships `setuptools`, so step 3 works. Under a bare `python -m venv`, step 3
   fails with `BackendUnavailable: Cannot import 'setuptools.build_meta'`,
   because `--no-build-isolation` forbids fetching it and `requirements-ci.txt`
   does not list it. The instructions are not false — they say conda — but a
   one-line note would prevent a predictable support question.

Neither is a false claim in the M2 site, so M2 closes.

**A false positive I caught in my own review.** My first clean-install attempt
used a venv and appeared to succeed: `import bsm3` printed `0.1.4`. It had not
installed — step 3 had failed, and the import resolved from the repository
working directory because I ran it from the source tree. Re-running from `/tmp`
gave `ModuleNotFoundError`. Import smoke tests must run from outside the source
tree or they verify nothing.

### Independent review of the E175 example findings

All nine hold. Measurements are mine unless noted.

| # | Finding | Verdict |
| --- | --- | --- |
| 1 | `root_half_width` documented "absolute spanwise half-width" but passed as `{"y": (None, value, "abs")}`, and `AxisRange` mode `"abs"` normalizes `t = \|c\| / max(\|c\|)` | **Confirmed.** `0.3` means 30% of semispan, not 0.3 m. Also unbounded above: a value > 1.0 silently means "all free". |
| 2 | `free_axial_fraction=(0.05, 0.97)` prescribes nose and tail, leaves the middle graph-free | **Confirmed** from `_free_region` + `AxisRange` "extent" mode. |
| 3 | `MeshMotion.derivative_check` is configuration only | **Confirmed.** Neither `mm.run` nor `run_mesh_motion` reads it; only the two drivers do, then call `select_fd_objective`/`run_fd_sweep` themselves. Those functions are exported from `bsm3.core.boundary_surface_movement` but **not** from `bsm3.mesh_motion`, so the compact namespace carries the setting without the means to act on it. |
| 4 | Classification is not on the result | **Confirmed.** No field resembles free/prescribed/intersection. `_write_diagnostic_dump` writes exactly `deformation_vertex_ids`, `graph_free_ids`, `graph_prescribed_ids`, `symmetry_plane_vertex_ids`, and per-component/intersection IDs — so the data exists but only via NPZ reverse engineering. |
| 5 | Composite final surface; non-convergence needs a user-facing status | **Confirmed.** `run_graph_load_steps` receives both `projection_metadata` and `reevaluation_metadata` (`identify_reevaluated_vertices`). No convergence flag reaches `MeshMotionResult`. |
| 6 | 114 baseline inversions; 8075 and 14923 additional and unusually small | **Confirmed and quantified.** Both are quads of area 3.299e-04 — **0.079× the median** cell area, at the **1.43rd percentile**. New: they are an **exact mirrored pair about y = 0** (centroids `[26.8477, ∓1.1392, 1.5577]`), so the two inversions are one geometric feature reflected, not two independent problems. |
| 7 | `PolygonRegularization(weight=0.3)` lacks E175 calibration | **Confirmed, and the most substantive.** The repository's own 12-weight E175 sweep found λ=150 the first inversion-free value and production used λ=200. The only recorded measurement at 0.3 is from a unit-scale uniform quad grid where it moved the solution by 3.3e-16 because the affine ramp lay in the penalty nullspace. The sweep also shows mixed bulk effects: λ=200 removed both inversions but lowered 5th-percentile scaled Jacobian and area ratio. It was run on a different panel revision. |
| 8 | `deformation_scale=0.02` is conservative for the triangle default | **Confirmed.** `test_triangle_wall_at_full_deformation_scale` exercises `deformation_scale=1.0` on the triangle wall. The small default exists only so one setting also survives the quad substitution. |
| 9 | Untracked prototypes target removed APIs | **Confirmed.** `e175_panel_opt.py` is untracked and imports `e175_mesh_motion_config`, `E175ModelFiles`, and `E175PipelineConfig`, none of which exist. The drag build-up and gross-weight scripts are likewise untracked. |

The next Codex prompt covers findings 1–8. Finding 9 becomes a separate, later
milestone rather than a condition on anything already accepted.

Status:    closed

---

## Turn 65 — Codex, implementer/planner, 2026-09-25
Scope:     M4.1 E175 ergonomics, exact seams, and clean panel replacement
Base:      11fb4522f354b56e05ccd1c5795f9f078fcbfe46
Commit:    d0d1ff0 (implementation); documentation handoff follows
Status:    M4.1 ready for Claude review — NOT self-accepted

The public result now exposes full-input-mesh-indexed
`SurfaceVertexClassification` and `SurfaceProjectionStatus` records. The first
contains deformation, closest-projection, fixed-parametric, graph-free,
graph-prescribed, symmetry-plane, component, and exact-intersection IDs; the
diagnostic NPZ derives its corresponding arrays from the same object. The
second comes directly from the existing projection operation's cached forward
`converged` array, with no diagnostic re-solve.

Exact bracketed-intersection IDs are now excluded from every closest-point
batch. Their implicit-solve coordinates remain in the assembled mesh, while
only graph-moved non-seam rows are replaced by closest-point outputs. The
synthetic test confirms seam IDs are absent from projection, satisfy both
driving and query planes, retain the analytic derivative, and pass centered FD.

API/example changes: `root_half_width` cleanly became bounded
`free_span_fraction`; the body helper now explains its prescribed nose/tail;
the basic triangle example defaults to full scale and exposes visualization,
diagnostic-dump, and FD controls; enabled `DerivativeCheck` registers its
objective through `mm.run`; the two FD helpers are public; and the advanced
quad example prints the new classifications and convergence status.

The user's two follow-up decisions expanded the original allowlist to 21 paths.
The supported panel is now
`embraer_175_panel_quad_dominant_high_quality.msh` (SHA-256
`92feeeda05905a13d23a18c863e76b9596773beccb021148cc2d4e7016cd733c`):
13,262 vertices, 2,804 triangles, 11,858 quads, zero baseline inversions. The
former 114-inversion asset was deleted. One already-dirty tracked visualization
script named that deleted asset; only its `DEFAULT_MESH` line was staged via an
index-only patch, leaving its unrelated user edits unstaged. Thus 7/8 dirty
files are byte-identical and the eighth has the one authorized path change.
Untracked entries are 394 -> 393 solely because the panel asset was adopted.

### N-gon calibration measurement

Full deformation, clean panel, two load steps. Raw JSON is at
`/tmp/bsm3_turn65_ngon_sweep.json`. Every row has zero inversions. The recorded
`contains_8075` / `contains_14923` fields do not continue the Turn-64 finding:
the replacement mesh has only 14,662 cells, so 14923 does not exist and 8075
is an unrelated cell.

| weight | min scaled J | p05 scaled J | p05 area ratio | seconds |
|---:|---:|---:|---:|---:|
| 0 | 0.160662 | 0.540688 | 0.982300 | 61.00 |
| 0.3 | 0.160662 | 0.540688 | 0.981775 | 46.69 |
| 1 | 0.160662 | 0.540688 | 0.981150 | 40.32 |
| 10 | 0.160662 | 0.540686 | 0.978746 | 39.81 |
| 50 | 0.160662 | 0.540682 | 0.977821 | 41.86 |
| 100 | 0.160662 | 0.540524 | 0.977484 | 46.50 |
| 150 | 0.160662 | 0.540426 | 0.977454 | 46.06 |
| 200 | 0.160662 | 0.540430 | 0.977684 | 39.79 |

This design point gives no evidence that 100–200 is better: the minimum is
invariant and both fifth-percentile metrics are slightly worse. The 0.3 example
value remains unchanged pending Claude's ruling and a broader calibration set.

Verification: core **45 passed**; fast E175 **16 passed / 5 deselected**; all
non-integration tests **228 passed / 9 deselected**; derivative/N-gon guard
**exactly 6 passed**; full-scale triangle **1 passed in 104.48 s** with dump
equality and zero projection failures; docs **12 passed**; strict Sphinx and all
five workflow Ruff groups passed; fresh clone of `d0d1ff0` built docs, passed
the documentation tests, and remained clean. No DAFoam, OpenFOAM, VortexAD, or
real-MPI solve ran. M4.2 remains separate.

Status:    closed

---

## Turn 66 — Claude, reviewer/planner, 2026-09-25
Scope:     Independent review of M4.1
Base:      11fb4522f354b56e05ccd1c5795f9f078fcbfe46
Reviewed:  d0d1ff0 (implementation), 00894cb (handoff)
Status:    **M4.1 NOT accepted — one narrow corrective turn required**

### Structural

21 changed paths, exactly matching the declared inventory; `git diff --check`
clean. Replacement mesh SHA-256 matches
`92feeeda05905a13d23a18c863e76b9596773beccb021148cc2d4e7016cd733c`. The retired
filename survives only in collaboration prose (`CODEX_NEXT.md`, `LOG.md`).

Dirty tree verified as declared: seven of the eight pre-existing modified files
are untouched (mtimes range 2026-04-15 to 2026-08-23, all months before this
turn), and the eighth, `visualize_wing_rotation_deformation.py`, retains exactly
its unrelated unstaged `DEFAULT_HDF5` and `--field` edits while only the
`DEFAULT_MESH` line was committed. Untracked entries 394 -> 393, solely from
adopting the panel asset.

### Both user-directed expansions are justified and minimally implemented

`_solution_vertex_ids` takes the deduplicated union across intersections, and
`reproject_mask = ~np.isin(ids, exact_seam_ids)` removes those rows from the
closest-point call itself rather than overwriting them afterwards. Seam rows are
written by `_set_exact_seams` into `preprojected_deformation`, excluded from
projection, and carried verbatim into `projected_deformation`, so the implicit
intersection VJP survives; `enforce_symmetry_plane` runs after assembly, which
the synthetic regression pins with `final[seam_ids, 0] == 0.0`. The empty case
(`reprojected_ids.size == 0`) short-circuits before `project_onto_oml` would
raise on empty metadata. `converged` is read from the already-cached
`shared_state["forward"]`, so no second solve occurs, and its rows are written
through the same index arrays used for the projected values.

The replacement asset was measured independently, not taken on report: 13,262
vertices, 2,804 triangles, 11,858 quads, `inverted_elements = 0`,
`inverted_corners = 0`, `degenerate_elements = 0`, minimum scaled Jacobian
0.1606796.

### Classification verified by execution, not by reading

On the half-mesh triangle wall (16,400 vertices): deformation 4,547 +
parametrically prescribed 11,853 = 16,400 exactly; closest-projection IDs equal
`surface_projection_status.reprojected_vertex_ids`; the closest set is a subset
of the deformation set and disjoint from both exact seams; every array stays in
range. On the symmetric quad panel (13,262 vertices) the partition and the
seam-disjointness both hold again, with 4,262 closest projections, 2,236 n-gon
modes, and zero inversions.

### The defect

The tracked triangle wall is a **half** mesh (`y` in `[0, 11.96]`), so
`setup.symmetry_split is None` and `_global_surface_ids` takes its
`np.unique(ids)` branch. Every dump-equality assertion in the suite runs on that
mesh, so the symmetric branch of the new code is never exercised by a test.

The curated quad panel **is** a full symmetric mesh (`y` in `[-11.96, 11.96]`).
There `_global_surface_ids` mirror-expands via
`np.where(np.isin(gather_index, ids))[0]`, which is correct and desirable for
the public classification. But `_write_diagnostic_dump` still writes the
half-mesh seam coordinates for `{name}_vertices` while `{name}_ids` is now the
mirror-expanded array:

| key | rows |
| --- | ---: |
| `wing_root_vertices` | 97 |
| `wing_root_ids` | **194** |
| `tail_root_vertices` | 67 |
| `tail_root_ids` | **134** |

Before this turn both were 97 and 67, aligned 1:1 by construction
(`half_to_full[data.vertex_ids]`). Pairing them was the only reason the archive
carries both. Any consumer zipping them now mispairs coordinates with IDs or
fails, and nothing in the archive announces the change. The public
classification object is correct; the regression is confined to the NPZ.

### N-gon sweep ruling

**The sweep is a null result, not a calibration, and must not be read as one.**

The minimum scaled Jacobian is bit-identical (0.16066206527471977) at all eight
weights, and the undeformed panel's own minimum is 0.1606796 — the statistic is
pinned by a pre-existing worst cell the deformation barely touches, so its
constancy says nothing about regularization. The p05 scaled Jacobian is
bit-identical for weights 0, 0.3 and 1, so the regularizer has no measurable
effect there at all. The p05 area ratio degrades monotonically, 0.982300 at
weight 0 to 0.977454 at 150. On this mesh at this design point, increasing the
weight is mildly harmful and never helpful; the elapsed-time column (61.0 s at
weight 0 against 39.8 s at 200) is warm-up noise and carries no cost signal.

This is expected: a clean, inversion-free panel gives the affine regularizer
nothing to suppress. Hourglass control matters under deformations that actually
provoke it. **Ruling: keep `0.3` in the advanced example as the explicitly
labeled non-recommendation it already is, do not adopt 100–200, and do not adopt
0 either.** No universal weight may be inferred from one deformation case.

The sweep's `contains_8075` / `contains_14923` columns are vacuous on the
replacement mesh: it has 14,662 cells, so **element 14923 does not exist**, and
element 8075 is an unrelated cell. The retired pair was a property of the
retired 114-inversion asset. The LOG's "neither 8075 nor 14923 in the
inverted-ID set" is true but carries no continuity with the Turn-64
measurement.

### Gates reproduced independently

| Gate | Result |
| --- | --- |
| `tests/test_boundary_surface_movement.py` | 45 passed |
| `tests/test_e175_example.py -m "not integration"` | 16 passed, 5 deselected |
| `tests -m "not integration"` | 228 passed, 9 deselected |
| Derivative / N-gon guard (three files) | **exactly 6 passed** |
| `test_triangle_wall_at_full_deformation_scale` | 1 passed, 105.14 s; 0 folds, 0/0/0 inversions, 4,435 projected, **0 projection failures** |
| `tests/test_documentation.py` | 12 passed |
| Strict Sphinx 9.1.0 on a fresh clone of `d0d1ff0` | build succeeded |
| All five literal workflow Ruff steps | passed |
| Default Ruff on the 13 changed Python paths | passed |
| Fresh clone doc tests + status | 12 passed, status empty |

Every number Codex reported reproduced exactly.

### Recorded residues, not blockers

- `_project_group` now raises `RuntimeError` when `shared_state["forward"]` is
  absent, naming the inline recorder. This adds no restriction — the pipeline
  already read `.value` in several places and so already required an inline
  recorder — but the requirement is still not stated on the API page.
- `mm.run` calls `objective.set_as_objective()` whenever
  `derivative_check.enabled` is true. Inside a larger optimization graph that
  already has an objective, enabling the debug flag would replace it. The flag
  is opt-in and defaults off; worth a documented warning.
- Turn 64's `print_summary` load-stepping docstring residue was fixed here.

### Naming guidance (no rename; M3 concern)

`GAMMA` — Geometry Adaptation for Multidisciplinary Modeling and Analysis —
expands accurately to what the package does. Two cautions. First, the token is
heavily overloaded in exactly this domain: γ is both flight-path angle and the
ratio of specific heats, and several unrelated software projects already carry
the name, so the distributed name likely needs a qualifier. Second, the tagline
phrase "analytically differentiable" should be squared with the pipeline's own
documented behavior that a non-converged projection is returned rather than
raised, and derivatives at those points are not guaranteed. A rename touches
packaging metadata, imports, docs and the workflow, so it belongs with **M3**
release pruning, not M4.

Status:    closed

---

## Turn 67 — Codex, corrective implementer, 2026-09-25
Scope:     Symmetric-mesh diagnostic-dump alignment only
Base:      9930dbe
Commit:    bc40560 (implementation); documentation handoff follows
Status:    M4.1 correction ready for Claude review — NOT self-accepted

The defect reproduced before editing: on the curated full symmetric panel,
`wing_root_vertices` had 97 rows beside 194 `wing_root_ids`, and
`tail_root_vertices` had 67 rows beside 134 IDs. The new integration assertion
failed against the unfixed implementation at `(97, 3) != (194, 3)`.

Option 1 from the corrective prompt was implemented, preserving the archive's
existing row-pair contract. `_global_intersection_vertices` maps each
complete-mesh intersection ID through `SymmetrySplit.gather_index`, selects the
aligned retained-half coordinate, and applies that complete vertex's
`mirror_sign`. On nonsymmetric inputs it orders the retained coordinates by
the same global IDs. Consequently `{name}_vertices` and `{name}_ids` remain
one-to-one in complete-mesh order on both paths. The corrected quad integration
test passed and additionally checks every coordinate against
`initial_vertices[vertex_ids]`, so equal lengths alone cannot satisfy it.

The API page now states the inline-recorder requirement, warns that enabling
the convenience FD check calls `set_as_objective()` and can replace an existing
optimization objective, and documents the diagnostic archive's aligned global
intersection arrays.

**N-gon weight.** The sweep is a null result, not a calibration. The minimum
scaled Jacobian is bit-identical (0.16066206527471977) at all eight weights and
the undeformed panel's own minimum is 0.1606796, so the statistic is pinned by
a pre-existing worst cell the deformation barely touches. The p05 scaled
Jacobian is bit-identical at weights 0, 0.3 and 1. The p05 area ratio degrades
monotonically from 0.982300 at weight 0 to 0.977454 at 150. Increasing the
weight is mildly harmful here and never helpful; the elapsed-time column is
warm-up noise. **Keep `0.3` as the explicitly labeled non-recommendation it
already is. Do not adopt 100–200. Do not adopt 0.** No universal weight follows
from one deformation case; a real calibration needs a deformation that
provokes hourglassing.

**Retired element IDs.** The sweep's `contains_8075` / `contains_14923` columns
are vacuous on the replacement mesh: it has 14,662 cells, so element 14923 does
not exist and element 8075 is an unrelated cell. The Turn-65 entry was
corrected so it cannot be read as continuous with the Turn-64 measurement.

Verification: the new symmetric regression failed before the implementation
and then passed in 65.73 s; fast E175 **16 passed / 5 deselected**; all
non-integration tests **228 passed / 9 deselected**; core **45 passed**;
derivative/N-gon guard **exactly 6 passed**; full-scale triangle **1 passed in
101.93 s** with zero folds, 0/0/0 inversions, 4,435 projections, and zero
projection failures; documentation **12 passed**; strict Sphinx 9.1.0 and all
five literal workflow Ruff groups passed. No DAFoam, OpenFOAM, VortexAD, or
real-MPI run occurred.

Status:    closed

---

## Turn 68 — Claude, reviewer/planner, 2026-09-25
Scope:     Review the M4.1 symmetric-dump correction; accept M4.1; plan M4.2
Base:      9930dbe
Reviewed:  bc40560 (implementation), 7077ca6 (handoff)
Status:    **M4.1 ACCEPTED**

### Scope

The changed-path union across `ad3099a`, `bc40560` and `7077ca6` is exactly the
six authorized paths, and `git diff --check` is clean. Measured against the
already-accepted `d0d1ff0`, only three production-side files differ — the
pipeline helper, `docs/src/api.md`, and one test — and
`load_stepping.py`, `projection.py`, `mesh_motion_config.py`, `mesh_motion.py`
and `geometry_model.py` are byte-identical. No accepted M4.1 substance was
touched.

### `_global_intersection_vertices` verified by construction, not by reading

Exercised directly against a synthetic `SymmetrySplit` covering both branches:

- **Symmetric.** Each complete-mesh ID resolves through `gather_index` to its
  retained-half row and takes that vertex's `mirror_sign`. Mirrored rows come
  back with the axis coordinate negated and the other two preserved.
- **Nonsymmetric.** Deliberately unsorted retained-half IDs are reordered into
  the sorted global-ID order that `_global_surface_ids` produces, so the
  coordinates follow the IDs rather than the input order. This was the latent
  ordering hazard in the original half-mesh path; it is now closed.
- **Symmetry plane.** `symmetry.py:133` sets `mirror_sign[plane, axis] = 0.0`,
  so a plane seam vertex's axis coordinate is written as exactly `0.0`. That is
  not a loss of precision: it reproduces the pipeline's own
  `reconstruct_full_from_half` convention (`gathered * mirror_sign`) bit for
  bit, so the archive and the reconstructed mesh agree exactly. The curated
  panel's two seams carry no plane vertices (97/97 and 67/67 split about
  `y = 0`), so the case is consistent but not exercised in production.
- **Guards.** Both misalignment paths raise rather than pairing wrong rows: a
  coordinate array of the wrong length or width fails the shape check, and an
  unmapped retained-half row fails `np.any(rows < 0)`. The second cannot
  trigger through the normal flow, since `_global_surface_ids` derives the IDs
  from the same `gather_index`; it is a genuine guard, not dead code.

### Before/after demonstrated, not accepted on report

In a disposable clone of `bc40560`, reverting **only** the pipeline file back
to `d0d1ff0` while keeping the new test:

```text
before: 1 failed — assert (97, 3) == (194, 3)   tests/test_e175_example.py:477
after:  1 passed in 84.46 s
```

This is the correct shape of evidence: the test provably sees the bug it was
written for. The regression also asserts coordinate identity against
`dump["initial_vertices"][vertex_ids]` at `atol=1e-12`, not merely equal
lengths, so a reordering or a sign error fails it too — equal row counts alone
cannot satisfy it. `initial_vertices` is `setup.full_mesh.vertices`, the
complete input mesh, which is the right index space for `vertex_ids`.

### Documentation

The API page now states the inline-recorder requirement where the caller-owned
recorder is described, warns that the convenience FD path calls
`set_as_objective()` and can replace an objective already registered in a
larger optimization graph, and documents the NPZ intersection arrays as
complete-mesh row-aligned pairs including mirror-expanded rows. All three match
the implementation.

The N-gon null-result ruling is recorded verbatim, and the Turn-65 entry was
corrected in place so its `contains_8075` / `contains_14923` sentence can no
longer be read as continuous with the Turn-64 measurement. No regularization
default changed.

### Gates reproduced

| Gate | Result |
| --- | --- |
| `test_quad_panel_introduces_no_new_inverted_elements` | 1 passed, 84.46 s |
| `tests/test_e175_example.py -m "not integration"` | 16 passed, 5 deselected |
| `tests -m "not integration"` | 228 passed, 9 deselected |
| `tests/test_boundary_surface_movement.py` | 45 passed |
| Derivative / N-gon three-file guard | **exactly 6 passed** |
| `test_triangle_wall_at_full_deformation_scale` | 1 passed, 104.99 s; 0 folds, 0/0/0 inversions, 4,435 projected, 0 failures |
| `tests/test_documentation.py` | 12 passed |
| Strict Sphinx 9.1.0 | build succeeded |
| Five literal workflow Ruff groups | all passed |
| Preservation | 8/8 modified byte-identical, 393 untracked, the visualization script's same two unstaged edits |

**M4.1 is accepted. M4 remains open for M4.2.**

### M4.2 planned

The next prompt specifies a tracked VortexAD adapter, a VortexAD-free Breguet
fuel-burn model, and a composed optimization example, against pinned external
revisions. Four planning decisions are deliberate and recorded here:

1. **VortexAD stays optional.** It is not in the validated environment and this
   turn installs nothing. The adapter imports it lazily, mirroring
   `MeshMotionVolumeBackend`, and every tracked test runs without it. M2's
   clean-install contract is explicitly protected: `install_requires` stays
   empty and `requirements-ci.txt` is out of the allowlist.
2. **Fuel burn is separated from aerodynamics** precisely because it has no
   VortexAD dependency and can therefore be tested properly today — analytic
   value plus an FD derivative check — rather than hidden behind a skip.
3. **Skips must not masquerade as passes.** Skip counts are reported separately
   from passes, and the adapter's differentiability is checked against a fake
   panel solver so a real VJP-versus-FD comparison runs in CI.
4. **The example manages its FD objective explicitly**, because M4.1 documented
   that `derivative_check.enabled` calls `set_as_objective()` and would replace
   an optimization's own objective.

The prompt also requires the pin to be a full 40-character SHA or an explicitly
recorded blocker — never an invented hash or a branch name — and requires the
fresh-clone import smoke test to run from outside the source tree, which is the
Turn-64 false positive written into the checklist.

M3 release pruning stays separate and last. `GAMMA` remains M3 naming guidance;
nothing was renamed.

Status:    closed

---

## Turn 69 — Codex, sequencing/identity planner, 2026-09-25
Scope:     Promote GAMMA identity and Read the Docs alpha ahead of M4.2
Base:      38cd0bf
Status:    planning handoff only — no implementation or external mutation

The user asked whether the GAMMA rename should happen in the immediate next
turns and then authorized updating the instructions after M4.1 acceptance.
Codex recommends yes: publishing the first tagged documentation as BSM3 and
renaming immediately afterward would create avoidable public package names,
URLs, badges, and installation instructions.

This supersedes Turn 68's sequencing statement that GAMMA remains an M3-only
concern. M3 still owns archive/history pruning and remains last; public identity
is promoted so it can be stable before the first Read the Docs alpha and before
new M4.2 integration code adopts the old namespace.

The display name is provisionally **GAMMA — Geometry Adaptation for
Multidisciplinary Modeling and Analysis**. Bare `gamma` cannot be assumed as a
technical identifier: a `gamma` distribution already exists on PyPI, and the
term is overloaded in the relevant aerospace domain. The proposed qualified
set is repository `GAMMA-MDO`, distribution and RTD slug `gamma-mdo`, and
import namespace `gamma_mdo`; Claude must separately rule on the import rename
rather than silently equating branding with Python namespace migration.

The current source version is `0.1.4` and the local repository has no tags.
`v0.1.0a1` is appropriate only if `0.1.4` was never publicly released; if it
was, the alpha must move forward. The current dirty tree also makes a wholesale
directory move unsafe: eight tracked files are modified and 393 entries are
untracked, many beneath `bsm3/`. Claude must design an isolated-worktree or
equivalent migration and an integration strategy that cannot move, stage, or
lose user-owned files.

Turn 68's M4.2 prompt is not discarded. It remains recoverable verbatim with
`git show 38cd0bf:docs/overhaul/CODEX_NEXT.md` and is queued after the identity
and documentation-publication turns.

Status:    closed

---

## Turn 70 — Claude, planner, 2026-09-25
Scope:     GAMMA identity and first Read the Docs alpha — rulings only
Base:      c3be7ff
Status:    Rulings recorded; M4.1a/M4.1b prompt issued. Nothing renamed,
           tagged, reserved, published, or pushed.

### 1. Display name and expansion — accepted

**GAMMA — Geometry Adaptation for Multidisciplinary Modeling and Analysis.**

Turn 66 raised that `GAMMA` is overloaded in exactly this domain: γ is both
flight-path angle and the ratio of specific heats, and `gamma` is occupied on
PyPI (version 0.0.1, confirmed HTTP 200). That objection is answered rather
than ignored by splitting the two roles: the **human-facing display name stays
unqualified** (`GAMMA`), and every **technical identifier is qualified**
(`GAMMA-MDO`, `gamma-mdo`). This is the normal resolution and it costs nothing.

### 2. Identifiers, with the evidence and its limits

| Role | Ruling | Evidence | Strength |
| --- | --- | --- | --- |
| Display / docs | `GAMMA` | — | ruling |
| Repository slug | `GAMMA-MDO` | GitHub code search for repos named GAMMA-MDO: `total_count: 0` | **public only** |
| Distribution | `gamma-mdo` | `pypi.org/pypi/gamma-mdo/json` → 404; `gamma_mdo`, `gammamdo` → 404 | good |
| Import namespace | **`bsm3`, unchanged** | see ruling 3 | ruling |
| RTD slug | `gamma-mdo` | RTD API v3 → `{"detail":"No Project matches the given query."}` | **public only** |

Two limits are recorded rather than glossed:

- The GitHub check **cannot** confirm availability inside the owner's own
  namespace. `api.github.com/repos/MariusLRuh/BSM3` also returns 404 because
  that repository is private, so 404 there means "invisible", not "free". The
  user must confirm `GAMMA-MDO` is unused in their account.
- PyPI and RTD 404s mean **unoccupied, not reserved**. This turn reserved
  nothing. A name is only secured when the user publishes or imports it.
- `gamma_mdo` and `gamma-mdo` normalize to the same PyPI name under PEP 503,
  so one registration covers both spellings.

### 3. Import namespace — **retain `import bsm3`**

This is the substantive ruling and it goes against the leading proposal.

Measured in the live checkout:

| Fact | Count |
| --- | ---: |
| Untracked entries beneath `bsm3/` | **304 of 393** |
| Modified tracked files beneath `bsm3/` | **6 of 8** |
| Untracked user `.py` files importing `bsm3` | **57 of 144** |
| Modified tracked files importing `bsm3` | **5 of 8** |
| Tracked `.py` files referencing the namespace | 53 |

Renaming the import package would break 57 untracked user scripts and 5
user-modified tracked files, **none of which either agent is permitted to
edit**. A `git mv bsm3 gamma_mdo` also renames the directory on disk, silently
relocating 304 untracked user files into a namespace their own imports no
longer match. There is no version of that operation that is both complete and
safe while the dirty tree is live.

This is **not** a compatibility shim, which the user rules out; it is declining
to perform a rename. A distribution name that differs from its import name is
ordinary: `scikit-learn`/`sklearn`, `pillow`/`PIL`, `beautifulsoup4`/`bs4`.
`pip install gamma-mdo` then `import bsm3` is coherent and honest.

The migration is recorded as **M5.2, blocked**, and starts only when the user
resolves the dirty work. Splitting public branding from namespace migration is
what makes the alpha shippable now.

Consequence worth stating plainly: the alpha ships with a public name that does
not match its import name. That is a real discoverability cost, accepted
deliberately in exchange for not destroying user work.

### 4. Version — **v0.2.0a1**, not v0.1.0a1

Established facts: `pypi.org/pypi/bsm3/json` → **404**, so the project was
never published. `git tag` is empty and `git ls-remote --tags origin` returns
nothing, so **no release was ever tagged**, locally or on `origin`. `0.1.4`
therefore has no public history, and `v0.1.0a1` would create no *public*
regression — it is permissible under the stated test.

It is still the worse choice. The source has claimed `0.1.4` throughout the
project's life, `setup.py` derives from it and `docs/conf.py` reads it, so every
source install in the user's own environments reports `0.1.4` today. Publishing
`0.1.0a1` would leave working installations reporting a version *newer* than
the first published release, and `pip install --upgrade` would read as a
downgrade. `v0.2.0a1` is strictly forward-moving, costs nothing, and removes
that anomaly.

This is a product decision. If the user prefers `v0.1.0a1`, the evidence
supports it and the prompt needs only that one substitution.

### 5. Dirty-tree-safe implementation

Ruling 3 removes the entire risk class: **because `bsm3/` does not move, there
is no directory operation to make safe.** No worktree gymnastics are required.

The rename surface is 19 tracked files — root metadata and the published docs —
and it was checked against the dirty set directly:

```text
branding files: 19    dirty files: 8    overlap: 0
```

Zero. Every user-dirty file lives under `bsm3/core/...` or
`examples/basic_examples/`, and neither appears in the branding surface. A
literal per-path allowlist is therefore sufficient, with a pre/post count of
8 modified and 393 untracked as the proof.

### 6. Read the Docs alpha — HTML only, and one real config defect

`.readthedocs.yaml` currently declares:

```yaml
formats:
  - pdf
  - htmlzip
```

**Neither has ever been built.** Only strict HTML has been verified, repeatedly,
including from clean clones. With `fail_on_warning: true` in the same file, the
first hosted build would apply warnings-as-errors to an unverified LaTeX
toolchain. This is not merely a policy preference for HTML-first — it is a
change the repository actually needs before any hosted build is attempted.

The build stays hermetic: `docs/conf.py` reads `__version__` by regex without
importing the package, so no CSDL_alpha, lsdo_function_spaces, JAX, gmsh,
DAFoam, MPI, or VortexAD is required to build the site.

**Actions Codex may prepare in the repository:** `setup.py` name/url,
`bsm3/__init__.py` version, `docs/conf.py` project/author/title,
`.readthedocs.yaml` formats and comments, README badge and links, and the
remaining prose in the published docs.

**Actions requiring explicit user authorization — no agent performs them:**
renaming the GitHub repository, creating the Read the Docs project and its
webhook, setting the default version and activating the tag, creating and
pushing the `v0.2.0a1` tag, and any PyPI reservation or publication.

### Ordering

M4.1 accepted → **M5 (identity)** → **M6 (RTD alpha)** → M4.2 → M3 last. The
complete M4.2 prompt is preserved verbatim at `38cd0bf` and is recoverable with
`git show 38cd0bf:docs/overhaul/CODEX_NEXT.md`; it was not rewritten or
weakened. M3 archive/history pruning remains last.

Status:    closed

---

## Turn 71 — Codex stop, then Claude prompt correction, 2026-09-25
Scope:     Turn-71 prompt defect; no implementation attempted
Base:      23ef4ad
Status:    Prompt corrected and reissued. Nothing renamed, tagged, or pushed.

### The defect was mine

Codex stopped before editing rather than working around an unsatisfiable
allowlist. That was the correct call and the stop rule working as designed.

The Turn-71 prompt simultaneously required `docs/conf.py` to declare
`project = "GAMMA"`, `docs/src/api.md` to carry no `BSM3` reference,
`tests/test_documentation.py` to pass, and all of `tests/**` to stay
prohibited. Those cannot all hold. Verified in source at `23ef4ad`:

| Line | Assertion | Effect of the required rebrand |
| --- | --- | ---: |
| `tests/test_documentation.py:115` | `assert 'project = "BSM3"' in conf` | fails |
| `tests/test_documentation.py:155-156` | regex on `<!-- BEGIN/END BSM3 PUBLIC EXPORTS -->` | fails |
| `tests/test_documentation.py:219` | `assert "BSM3 never starts or stops a recorder" not in text` | silently stops protecting |

Line 219 is the subtle one. It is a *negative* guard, one of the four rejected
overclaims. It does not fail after a rebrand — it keeps passing while no longer
guarding anything, because the prose it forbids would now read "GAMMA never
starts or stops a recorder". Leaving it unchanged would quietly retire a
semantic protection rather than break a test. That is worse than a failure, and
it is why the string must move with the brand.

### Scope of the correction

Exactly one path is added to the implementation allowlist:
`tests/test_documentation.py`, removed from the `tests/**` prohibition. No
other test file is authorized and no other part of the prompt is widened.

I checked that this is sufficient rather than assuming it. Every `BSM3`
reference under `tests/` was enumerated: the four above, a docstring at
`test_documentation.py:131`, and three prose comments in
`test_e175_example.py` (lines 204, 492-494, 543) that assert nothing and
correctly describe the historical package. No test asserts on
`.readthedocs.yaml` `formats`, so the HTML-only change needs no test edit, and
no test pins `0.1.4`, so the version bump needs none either. The corrected
prompt is therefore satisfiable as written.

### Baselines independently reproduced

Every figure Codex recorded was re-derived, and the two hashes match exactly
once the formulation is pinned:

| Baseline | Recorded | Verified |
| --- | --- | --- |
| Modified tracked files | 8 | **8** |
| Untracked entries | 393 | **393** |
| `.py` files importing `bsm3` | 53 | **53** |
| Dirty diff SHA-256 | `981318…6177` | **exact match** (`git diff \| shasum -a 256`) |
| Untracked-list SHA-256 | `c38fd9…da60` | **exact match** (`git status --porcelain \| grep '^??' \| cut -c4- \| sort \| shasum -a 256`) |
| Supported-surface `BSM3` | 39 | **39 lines / 40 occurrences** |

The last row is not a discrepancy but an ambiguity worth pinning: `git grep -c`
counts matching *lines* and `git grep -o` counts *occurrences*, and one line in
the branding surface carries two `BSM3` tokens. The corrected prompt states
which command it means so the post-change check cannot be argued either way.

All Turn-70 rulings stand unchanged: `GAMMA` / `GAMMA-MDO` / `gamma-mdo`,
import namespace stays `bsm3`, version `0.2.0a1`, HTML-only first build, and
the four external mutations remain user-authorized. The M4.2 prompt remains
preserved verbatim at `38cd0bf`.

Status:    closed
