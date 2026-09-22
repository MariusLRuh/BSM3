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

Decided:
- `ngon_affine.py` remains unchanged unless a new test demonstrates a genuine
  operator defect.

Open:
- none

Status:    open
