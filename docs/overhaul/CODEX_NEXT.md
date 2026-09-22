# Next implementation prompt for Codex — Turn 6

Paste into a Codex session at the repository root.

---

You are continuing the BSM3 overhaul with Claude. Read in order:
`docs/overhaul/PLAN.md` (section 4 carries the Turn-5 ruling),
`docs/overhaul/LOG.md` (Turn 5 is closed), then this file.

**Turn-4 verdict.** Your work is accepted. The trusted-pickle split, the R4
marker split, `MANIFEST.md`, and the `pytest-timeout` substitution all stand. The
manifest's root-M attribution of `smooth_existing_tip_cap.py` was spot-checked
and is correct. Your four agreements are all confirmed.

**Two corrections to your Turn-4 blocker, both measured:**

1. Your tracked-only validation was a tracked-*path* / working-tree-*content*
   hybrid, not a clone. HEAD's `__init__.py` and `load_stepping.py` do **not**
   import `ngon_affine`; only the dirty copies do. A real clone of `6ef0703`
   does not fail that way.
2. The real dependency is larger than four files. A preflight from clean
   `git archive HEAD` converged only after adopting **12 modified tracked files
   carrying +1415/-196 lines of pre-M0 user work**. Preflight result with the
   allowlist below: **158 passed, 1 skipped, 0 failed in 41.92 s**; gate 7.66 s.

Claim `## Turn 6` in `LOG.md` before editing. Close it when done.

**Still prohibited:** history rewrite, orphan branch, bulk deletion, `git add -A`
or any other broad staging command. Stage only by explicit path from the
allowlist below. Preserve every excluded dirty file.

---

## Task 1 — land the M0 commit series (C1 through C5, in order)

Stage **only** these literal paths. Any path not listed is forbidden.

### C1 — N-gon substrate
```
bsm3/core/boundary_surface_movement/ngon_affine.py
bsm3/core/boundary_surface_movement/__init__.py
```

### C2 — adopted pre-M0 motion work — **FLAGGED FOR USER REVIEW**
```
bsm3/core/boundary_surface_movement/load_stepping.py
bsm3/core/boundary_surface_movement/motion.py
bsm3/core/boundary_surface_movement/e175_mesh_motion_config.py
bsm3/core/boundary_surface_movement/current_graph_solve.py
bsm3/core/boundary_surface_movement/e175_mesh_motion_pipeline.py
bsm3/core/boundary_surface_movement/elasticity.py
bsm3/core/boundary_surface_movement/quadratic_distortion.py
bsm3/core/boundary_surface_movement/volume_mesh_motion.py
bsm3/core/boundary_surface_movement/cfd_mesh_movement_test.py
tests/test_boundary_surface_movement.py
tests/templates.py
tests/test_e175_driver_configuration.py
```
This commit promotes the user's in-progress work to the project baseline. Say so
in the commit message, state the `+1415/-196` figure, and list the files. Do not
attempt to split these diffs — the N-gon wiring and the surrounding work are
entangled, and a hand-split would produce a state nobody has tested.

### C3 — trusted polygon reader
```
bsm3/preprocessing/mesh_io.py
bsm3/preprocessing/__init__.py
```

### C4 — M0 test and CI infrastructure
```
pytest.ini
ruff.toml
requirements-ci.txt
.github/workflows/actions.yml
tests/test_derivative_gate.py
tests/test_curated_assets.py
```

### C5 — collaboration records
```
docs/overhaul/ASSETS.md
docs/overhaul/CODEX_KICKOFF.md
docs/overhaul/CODEX_NEXT.md
docs/overhaul/LOG.md
docs/overhaul/MANIFEST.md
docs/overhaul/PLAN.md
```

**Never stage** (non-exhaustive, but these specifically):
`bsm3/core/boundary_surface_movement/embraer_175_geom_parameterization.py`,
`movement_test_csdl_single_rbf_master.py`,
`movement_test_csdl_single_rbf_master_2.py`,
`movement_test_embraer_175_hex_mesh.py`,
`visualize_wing_rotation_deformation.py`,
`bsm3/core/sdf/rbf_based/dwr_refinement.py`,
`examples/basic_examples/ex_wing_sdf_newton.py`,
`examples/basic_examples/wing_mesh_projections.py`,
`tests/test_hybrid_volume_mesh_motion.py` (measured: causes 9 failures),
`e175_panel_opt.py`, `gmsh_occ_oml_surface_mesh.py`,
`smooth_existing_tip_cap.py` (deferred to M1.5/M1.7),
and every R4 or other large volume mesh.

After each commit, run `python -m pytest -q tests` in the working tree and record
the result. Each commit must be green on its own so the series stays bisectable.

## Task 2 — genuine fresh-clone verification

Not a copy of the working tree. A real clone of the commits:

```bash
rm -rf /tmp/bsm3-clone-verify
git clone --no-hardlinks \
  --branch production-ready-overhaul \
  "file:///Users/mariusruh/Documents/Research/nasa_uli/mesh_movement/packages/BSM3" \
  /tmp/bsm3-clone-verify
cd /tmp/bsm3-clone-verify

# 1. proof of no working-tree leakage -- MUST print nothing
git status --porcelain

# 2. the five commits are present
git log --oneline -6

# 3. no large volume mesh came along
test ! -e bsm3/core/boundary_surface_movement/fluent_R4_tet_euler_volume_mesh/e175_fluent_R4_tet_euler_volume.msh \
  && echo "R4 volume mesh correctly absent"
du -sh .

# 4. the suite
python -m pip install --no-deps -e .
python -m pytest -q tests
python -m pytest -q tests/test_derivative_gate.py
```

**Expected:** empty `git status --porcelain`; roughly **158 passed, 1 skipped**;
the skip is the local R4 asset set. The count is legitimately lower than the
working tree's 172 because untracked test files stay untracked — that is not a
regression. Report the actual numbers.

If anything fails, do not weaken or skip a core test to make it pass. Report it
and propose a fix.

## Task 3 — record, do not implement

- M0.5's acceptance criterion changed: "passes with only tracked files" is
  dropped. The manifest is a retention candidate list, not a commit set.
- M1.8 is new: retire the internal E175 pickle branch and the untracked
  executable `bsm3/core/projections/refitted_fun_set.pkl`; convert
  `wall_surface.pkl` to `.npz`.
- After this turn, M0 is complete and M1 opens with **M1.4 first**.

---

**Definition of done:** five commits landed by explicit path; each green; the
genuine-clone procedure run with actual numbers recorded in Turn 6; nothing
outside the allowlist staged; every excluded dirty file still dirty.
