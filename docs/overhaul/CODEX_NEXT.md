# Codex review checklist — Turn 35 (bounded M1.7a correction)

Claude implemented Turn 34. Codex owns the acceptance ruling. Baseline for
comparison is `597ba41`.

## Commits and changed paths

| Commit | Contents |
|---|---|
| `2bcaf05` | `geometry_model.py`, `mesh_motion_pipeline.py`, `mesh_motion_config.py`, `bsm3/mesh_motion.py` |
| `63109d6` | `examples/e175_surface_deformation.py`, `tests/test_e175_example.py` |
| `8f5907a` | `tests/test_e175_example.py` (STEP-cache containment fix) |
| docs commit | `PLAN.md`, `LOG.md`, `CODEX_NEXT.md` |

- [ ] `git diff --name-only 597ba41..HEAD` stays inside the 10-path allowlist.
      Claude measured 6 source/test paths + 3 docs, **zero violations**.
- [ ] No tracked E175 asset or generated cache was modified.

## 1. External coefficients

```python
GeometryModel.add_component(
    *, name, search_name, deformed_coefficients,
    free_region=None, projection_name=None, projection_mode="all",
)
```

- [ ] Accepts a stacked `(N, 3)` CSDL variable/array in sorted patch-ID order
      **and** a per-patch mapping.
- [ ] Validation runs **after** STEP import, in
      `_resolve_external_coefficients`, and rejects missing/extra patch IDs,
      wrong block shapes, wrong stacked row count, and non-3D trailing
      dimension.
- [ ] CSDL expressions are preserved, never converted to NumPy.
- [ ] At `f=1` the exact target is returned; otherwise
      `baseline + f * (target - baseline)`.
- [ ] `_ComponentRecord`, coefficient callbacks, free-region factories, and
      polygon helpers remain unexposed. Free region is a plain
      `{"x"|"y"|"z": (lower, upper, mode)}` mapping; no new public dataclass.
- [ ] `validate()` no longer requires a model-owned design variable.

**Derivative evidence.** `test_external_coefficients_drive_the_real_pipeline`
imports the STEP itself, builds `baseline + shift * direction` outside BSM3,
runs the full pipeline, and asserts
`|d(sum(final reprojected coords))/d(shift)| > 1e-6`. It passes, with 0 folds
and 0 final inversions.

## 2. Recorder lifecycle

- [ ] `_recorder`, `_owns_recorder`, `recorder`, `owns_recorder`, and all
      automatic creation/start/stop are gone from `GeometryModel`.
- [ ] `design_variable` raises `RuntimeError` when no recorder is active.
- [ ] `mm.run(recorder=...)` is **required** and never starts or stops it.
- [ ] Tests cover: construction does not alter recorder state; missing recorder
      raises clearly; `run` neither starts nor stops; an exception from `run`
      leaves caller ownership unchanged.

## 3. Inversion accounting

- [ ] `baseline_inversion_report` is gone with **no** alias; replaced by
      `initial_inversion_report`, `preprojection_inversion_report`,
      `surface_inversion_report`.
- [ ] `print_summary()` labels all three; fold count computed **once**
      (`cfd_folds`, function scope).

**Claude independently reproduced the input reference:** the untouched tracked
quad asset measures **114 inverted elements, 114 inverted corners, 0
degenerate**. Turn 32's `118 -> 118` was preprojection -> final; four
inversions had been introduced.

| Run | Time | initial | preprojection | final | new IDs vs initial | folds | n-gon modes |
|---|---:|---:|---:|---:|---|---:|---:|
| tri wall | 106.4 s | 0 | 0 | 0 | none | 0 | 0 |
| quad panel | 67.2 s | 114 | 114 | 114 | **none** | 0 | 2,535 |

- [ ] ID sets compared, not only counts. At the Turn-32 values the quad gained
      IDs **8075** and **14923**, a symmetric pair of slivers (area 3.3e-4 vs
      4.2e-3 median). Scaling all five deformations 10x down removes them; all
      five remain strictly nonzero.
- [ ] Confirm the tuned values are acceptable, or specify different ones.

## 4. Regression gates and mechanical checks

```bash
python -m pytest -q tests/test_e175_example.py tests/test_e175_driver_configuration.py
python -m pytest -q tests/test_derivative_gate.py \
  tests/test_ngon_affine_operator.py tests/test_ngon_affine_load_step.py
```

- [ ] Derivative gate + M1.4: **6 passed**, values unchanged. Driver config:
      **10 passed**. Working tree: **185 passed, 1 skipped**.
- [ ] Both required greps return no matches (verified). Scoped
      `git diff --check` clean; the remaining hits are pre-existing excluded
      dirty files Claude did not touch.
- [ ] No membrane, log-barrier, tangential-smoothing, pickle, or mesh-kind
      branch reintroduced; applicable-if-present polygon regularization intact.

## 5. Clean clone

```bash
git clone --no-hardlinks --branch production-ready-overhaul \
  "file:///Users/mariusruh/Documents/Research/nasa_uli/mesh_movement/packages/BSM3" \
  /tmp/bsm3-t34-codex-verify
```

- [ ] **171 passed, 2 skipped**; `git status --porcelain` **empty before and
      after** the example and the suite.
- [ ] The first clone run left `?? stored_files/`: the new end-to-end test
      called `lfs.import_file_patched` directly, bypassing the containment the
      library performs internally. Fixed in `8f5907a` and re-verified on a
      fresh clone. Confirm the fix belongs in the test rather than the library.

## 6. Two deviations requiring a ruling

1. **Blocked dependency outside the allowlist.** `free_region=None` on every
   component leaves no reevaluation vertices, and
   `bsm3/preprocessing/movement.py:305` evaluates
   `np.asarray([]) &= ~assigned` — `float64`, so `TypeError`. **One-line fix:
   `dtype=bool`.** That file is not allowlisted, so per the stop rule it was
   not touched; `test_external_coefficients_with_whole_component_free_regions`
   is skipped with the diagnosis and fix recorded. External coefficients work
   end to end **with** free regions. **Rule on adding
   `bsm3/preprocessing/movement.py`.**
2. **Three named regression-gate paths do not exist:**
   `test_e175_boundary_surface_movement_derivatives.py`,
   `test_polygon_regularization.py`, `test_ngon_affine_regularization.py`. The
   real gates are `test_derivative_gate.py`, `test_ngon_affine_operator.py`,
   `test_ngon_affine_load_step.py`, which were run. Confirm the substitution.

## 7. Remaining M1 scope — unchanged

M1.6 slices 2 and 3, then M1.8 pickle retirement, then full M1.7 acceptance.
M1.7 carry-ins stand: the `GraphDistanceWeighting.summary` `TypedDict` and its
dead `"decay"` key.

M1.7a is **not** marked accepted by Claude.
