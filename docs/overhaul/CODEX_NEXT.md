# Codex review checklist — Turn 41 (M1.6 slice 2)

Claude implemented Turn 40, documentation and comments only. Codex owns the
ruling. Base commit `cc560f6`. **Slice 2 is not marked complete by Claude.**

## Commits and changed paths

| Commit | Paths |
|---|---|
| `b99b4a4` | `.github/workflows/actions.yml`, 6 projection modules, `bsm3/preprocessing/mesh_io.py` |
| docs commit | `docs/overhaul/PLAN.md`, `LOG.md`, `CODEX_NEXT.md` |

- [ ] **8 source/CI files + 3 docs; zero allowlist violations.** Seven
      preprocessing modules were already complete and correctly received no
      edit, so they do not appear in the diff.

## Coverage: 33/80 → 80/80

| Module | Before | After |
|---|---:|---:|
| `function_set_closest_distance_custom_op.py` | 0/17 | **17/17** |
| `function_set_evaluation_custom_op.py` | 0/10 | **10/10** |
| `function_set_projection_custom_op.py` | 0/6 | **6/6** |
| `orthogonality_projection_numpy.py` | 0/5 | **5/5** |
| `warm_start_candidate_projection_numpy.py` | 0/5 | **5/5** |
| `warm_start_projections.py` | 7/10 | **10/10** |
| `mesh_io.py` | 6/7 | **7/7** |
| `components/gmsh/intersections/movement/quad_conversion/stl/symmetry/__init__` | complete | unchanged |

- [ ] Re-run the inventory: aggregate **80/80**, zero missing names, module
      docstrings on all 15.
- [ ] The last four filled were `WarmStartResult`, `sample_bounding_box_faces`,
      `load_function_set`, and the `MeshData.nodes` **setter** (the getter was
      already documented; the property pair counts as two definitions).

## Stripped-AST proof

- [ ] **15/15 identical** under `ast.dump(..., include_attributes=False)` after
      recursively stripping leading string-literal docstrings from every
      module, class, function, and async-function scope.
- [ ] Hunk inspection: 519 changed Python lines. A regex classifier flagged 8,
      all false positives — docstring prose containing a colon, e.g.
      `output_measure : numpy.ndarray`. The stripped-AST equality is the
      authoritative evidence.

## Documented contracts to spot-check

- [ ] Stacked coefficient convention and per-patch `start`/`stop` row spans.
- [ ] Setup-time NumPy vs differentiable CSDL custom operation, and each
      operation's `evaluate`/`compute` boundary.
- [ ] Warm-start candidate selection, degenerate-edge exclusion, and the
      boundary-clamped retry path.
- [ ] Newton convergence/failure semantics; non-converged points are returned,
      not raised.
- [ ] First- and second-order VJP inputs/outputs, stated as built from the
      converged forward state via the implicit-function theorem, with **no**
      guarantee where the solve did not converge.
- [ ] `MeshData.nodes` alias, component discovery/search names, file-format
      behaviour, quad-conversion gates.
- [ ] **Both** `load_function_set_from_pickle` and `load_function_set` warn
      that pickle executes arbitrary code and only trusted local input is
      acceptable. Neither was renamed, deleted, or redesigned; M1.8 owns that.

## CI

- [ ] One new step, *Numpydoc checks for projection and preprocessing*, over
      exactly the 15 literal paths, pinned `ruff==0.9.10`, existing
      indentation. The three prior lint steps are byte-unchanged; the workflow
      parses with 9 steps.

## Verification

- [ ] Focused projection/preprocessing suite **82 passed, 3 deselected** —
      matches the pre-edit baseline.
- [ ] Derivative gate + both M1.4 tests **6 passed** — matches the baseline;
      numerical guard values unchanged.
- [ ] `git diff --check` clean over all allowlisted paths.
- [ ] **Ruff unavailable in `central_geom`** (recorded since Turn 18). The
      local run was attempted and recorded; no dependency installed or changed.
      The new pinned CI step is the authoritative gate and is **unverified
      locally** — worth confirming on the next CI run before release.
- [ ] No E175 integration or clean-clone rerun, per the spec.

## Deviation to rule on

An initial commit used `git add bsm3/core/projections/` and swept in **12
untracked research artifacts**, including `.stp`, `.pkl`, and `.pickle`
binaries. The allowlist check caught it immediately; it was reset with
`git reset --soft HEAD~1 && git reset` and replaced by explicit per-file
staging. The final commit contains 8 files, all 12 artifacts are verified
still untracked, and the dirty tree is unchanged. No force-push or history
rewrite was involved — the bad commit never left the working repository.

## Remaining M1 scope

M1.6 slice 3 (drivers, MPI/DAFoam), then M1.8 pickle retirement, then full
M1.7 acceptance. M1.7 carry-ins stand: the
`GraphDistanceWeighting.summary` `TypedDict` and its dead `"decay"` key.
