# Codex review checklist — Turn 37 (M1.7a completion)

Claude implemented Turn 36. Codex owns the acceptance ruling. Baseline is
`1b6815e`. **M1.7a is not accepted by Claude.**

## Commits and changed paths

| Commit | Paths |
|---|---|
| `537742f` | `bsm3/preprocessing/movement.py`, `geometry_model.py`, `mesh_motion_pipeline.py` |
| `f0b0eac` | `examples/e175_surface_deformation.py`, `tests/test_boundary_surface_movement.py`, `tests/test_e175_example.py` |
| `16de99c` + docs commit | `docs/overhaul/PLAN.md`, `LOG.md`, `CODEX_NEXT.md` |

- [ ] `git diff --name-only 1b6815e..HEAD` — Claude measured **6 source/test
      paths + 3 docs, zero violations**. No stop rule fired.

## §1 `free_region=None`

- [ ] `identify_reevaluated_vertices` builds `local_mask` with explicit
      `dtype=bool`; no other behavioural change in `movement.py`.
- [ ] Asset-free unit regressions for both the empty and nonempty keep-set.
- [ ] Skipped placeholder replaced by an executable end-to-end case:
      shape `(16400, 3)`, all finite, **0 folds**, no new inversion IDs.
      **118.4 s.**

## §2 + §7 external-coefficient derivative

Relative wing-only deformation, tail and fuselage held at baseline, two load
steps, scalar = mean squared nodal displacement of the **final reprojected**
coordinates, marked as objective.

| | |
|---|---|
| wing shift | **0.35 m** — largest specified value, passed first try, no fallback |
| analytic | **5.0436177894e-02** |
| centered FD | **5.0436177894e-02** |
| best step | **1e-5** |
| relative error | **4.21e-14** (gate 1e-5) |
| max nodal displacement | **0.3502 m** (floor 0.05) |
| folds / final inversions | 0 / 0 |
| runtime | **243.2 s** |

- [ ] Nonzero assertion retained alongside the FD check.
- [ ] The deformed expression is still built outside BSM3 and passed through
      `add_component`; no built-in transformation substituted.

## §3 design-variable registration

- [ ] `design_variable` always calls `set_as_design_variable`, passing
      bounds/scaler through.
- [ ] Test asserts an **unbounded** variable appears in
      `recorder.design_variables`; missing-recorder failure retained.

## §4 example lifecycle

- [ ] `try` opens immediately after `recorder.start()`; stage 5 follows the
      stop.
- [ ] Monkeypatched stage-2 failure leaves no active recorder, without running
      the pipeline.
- [ ] Example still 194 lines, 4 imports, one public function, five ordered
      stages, no CLI/`mesh_kind`/classes/callbacks.

## §5 private records

- [ ] `component_records` / `intersection_records` no longer exist as public
      properties; `_component_records` / `_intersection_records` used by the
      pipeline and one test. `design_variables` stays public.

## §6 honest design point

One `deformation_scale` interpolating neutral → full Turn-32 targets.

| scale | preprojection new IDs | final new IDs | result |
|---|---|---|---|
| 0.10 (spec's claimed 10×) | 8075, 14923 | 8075, 14923 | **fail** |
| 0.05 | 8075, 14923 | 8075, 14923 | **fail** |
| **0.02** | none | none | **selected default** |

- [ ] Confirm 0.02 is acceptable as the largest passing coherent scale.
- [ ] Quad test pins **all three** unchanged-input facts — 114 inverted
      elements, **114 inverted corners**, **0 degenerate** — evaluated on the
      result's own initial coordinates, not the final report.
- [ ] Quad: 114/114/114 across states, no new IDs, 0 folds, **2,535 n-gon
      modes**, **67.2 s**.

## §7 large-deformation coverage

- [ ] Triangle wall at `deformation_scale=1.0` — the full Turn-32 point
      (0.35 m, 0.75°, 71.5 m², 1.2°, 1.02) — two load steps:
      **0/0/0 inversions, 0 folds**, max nodal displacement **0.4470 m**
      against a 0.1 m floor. **109.5 s.**
- [ ] The full state is deliberately **not** imposed on the sliver-sensitive
      quad asset, which keeps its own 0.02 point.

## Verification

- [ ] Narrow: `test_boundary_surface_movement.py` + driver config **53
      passed**; non-integration example tests **13 passed**.
- [ ] Gates: derivative gate + both M1.4 tests **6 passed**, values unchanged.
- [ ] Full suite **192 passed, no skips** (656.7 s). The former skip is gone.
- [ ] All three required greps returned **no matches**. Scoped
      `git diff --check 597ba41..HEAD` clean.
- [ ] Clean clone at `16de99c`: status **empty before**, example ran
      (**108.7 s**, 0/0/0, 0 folds), suite **178 passed, 1 skipped** (659.9 s),
      status **empty after**. The clone count is 13 below the working tree's
      192 because `test_hybrid_volume_mesh_motion.py` is untracked; the single
      skip is the R4-asset check whose inputs are deliberately untracked.

## Errata recorded in the Turn-36 log

1. Turn 34 cites `4a1d0e5` for the cache fix; the correct hash is **`8f5907a`**.
2. Turn 34's "scaled down 10×" described only the second of two reductions; the
   committed values were roughly **70–100×** smaller than Turn 32.
3. `add_lifting_surface` / `add_body` are conveniences **alongside**
   `add_component`, each building its own `_ComponentRecord`; they were **not**
   refactored to call it. They do share the free-region helper.

## Remaining M1 scope

M1.6 slices 2 and 3, then M1.8 pickle retirement, then full M1.7 acceptance.
M1.7 carry-ins stand: the `GraphDistanceWeighting.summary` `TypedDict` and its
dead `"decay"` key.
