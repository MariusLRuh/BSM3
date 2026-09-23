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
