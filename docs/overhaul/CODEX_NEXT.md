# Codex review checklist — Turn 33 (M1.7a usability correction)

Claude implemented the Turn-32 plan. Codex owns the acceptance ruling.
Implementation commits: `987b8cf`, `37e3028`, plus the documentation commit.
Baseline for comparison is `d3ae980`.

## 1. Allowlist and commit hygiene

- [ ] Only the 15 allowed paths appear in `d3ae980..HEAD`; no pre-existing
      dirty file and no untracked research artifact was staged.
- [ ] Three reviewable commits, explicit `git add` paths, no history rewrite.
- [ ] `bsm3/mesh_motion.py` and
      `bsm3/core/boundary_surface_movement/geometry_model.py` are the only new
      source files.

## 2. Public vocabulary

- [ ] Every rejected name is absent from tracked live Python:

```bash
git grep -n -e ModelFiles -e PipelineConfig -e SurfaceMotionConfig \
  -e VolumeMotionConfig -e GraphDistanceWeightingConfig \
  -e NgonAffineRegularizationConfig -e DistortionRegularizationConfig \
  -e MeshQualityOutputConfig -e VisualizationConfig \
  -e FiniteDifferenceConfig -e DeclarativeGeometryParameterization \
  -e GeometryParameterization -e ComponentSpec -e IntersectionSpec \
  -e build_mesh_motion_model -- '*.py'        # expect empty
```

- [ ] No deprecated aliases survive; `run_mesh_motion` replaced
      `build_mesh_motion_model` outright.
- [ ] Low-level names (`NgonAffineConfig`, `QuadraticDistortionConfig`,
      `FlowConfig`) and the `ngon_affine` module are untouched.
- [ ] Field renames applied: `InputFiles.geometry_file` / `cache_directory`;
      `SurfaceMotion.distance_weighting` / `distortion_penalty` /
      `polygon_regularization`; `MeshMotion.surface` / `volume` / `quality` /
      `visualization` / `derivative_check`.

## 3. Facade

- [ ] `import bsm3.mesh_motion as mm` exposes only high-level names,
      `GeometryModel`, `MeshMotionResult`, and `run`.
- [ ] No component records, callbacks, polygon helpers, or solver-assembly
      types leak through it.
- [ ] `run(recorder=...)` does not take ownership of a supplied recorder.

## 4. `GeometryModel`

- [ ] No aircraft or component name is hardcoded in library code.
- [ ] `add_lifting_surface` derives its pivot from the named intersection at
      `pivot_chord_fraction`, uses the intersection's median absolute span as
      the scaling root, interpolates over the load fraction, and uses
      `root_half_width` for the root free region.
- [ ] `add_body` uses the control-point bounding-box pivot, interpolates
      diameter scale from 1.0, and honours `free_axial_fraction`.
- [ ] Validation covers names, unknown references, fractions, dangling
      `pivot_intersection`, and paired reference planform inputs.
- [ ] **Design point to rule on:** `design_variable` returns a CSDL variable,
      which needs an active recorder, but the example registers variables
      before `mm.run`. `GeometryModel` starts an inline recorder when none is
      active and hands ownership to `run`, which stops it. Confirm this is the
      intended resolution, or specify another.

## 5. Example

```bash
python - <<'PY'
import ast
from pathlib import Path
s = Path('examples/e175_surface_deformation.py').read_text(); t = ast.parse(s)
imports = [n for n in t.body if isinstance(n, (ast.Import, ast.ImportFrom))]
functions = [n for n in ast.walk(t) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
assert len(s.splitlines()) <= 220
assert len(imports) <= 5
assert not [n for n in ast.walk(t) if isinstance(n, ast.ClassDef)]
assert [n.name for n in functions] == ['main']
for f in ('argparse','mesh_kind','ExampleRun','_wing_coefficients','_surface_cells','_polygon_normals','_count_polygon_folds'):
    assert f not in s, f
p = [s.index(f'# {i}.') for i in range(1, 6)]
assert p == sorted(p)
print(f'{len(s.splitlines())} lines; {len(imports)} imports; five ordered stages')
PY
```

- [ ] Reported: **150 lines, 3 imports, five ordered stages**, one public
      function, no class, no private function.
- [ ] Path-based `main` signature; quad selection is a `SURFACE_MESH_FILE`
      edit with no topology label or branch.
- [ ] A single `PolygonRegularization(weight=0.3)` serves both meshes.

## 6. Numerical guards — must be unchanged to 1e-12

```bash
python -m pytest -q tests/test_derivative_gate.py
python -m pytest -q tests/test_ngon_affine_operator.py tests/test_ngon_affine_load_step.py
```

Claude measured, against the pre-implementation baseline: projector rank **3**,
retained fraction **1.0**, `‖P·1‖` **0**, hexagon modes **3**, `obj'(λ=0)`
**4.0**, `obj'(λ=0.3)` **57/13**, observability **2/13** — all unchanged.

## 7. Measured behaviour to re-verify proportionately

| Run | Time | Result |
|---|---:|---|
| tri wall, clean clone | **106.3 s** | 16,400 vertices / 32,522 cells; **0 folds, 0 baseline and 0 final inversions, 0 degenerate**; 0 n-gon modes |
| quad panel | **63.7 s** | 14,411 vertices / 15,122 cells; **2,535 n-gon modes**; 0 folds; **118 baseline → 118 final inverted elements** |

- [ ] The quad motion introduced **no** new inversion (118 → 118). Note this is
      `inversion_report.num_inverted` (inverted *elements*); Turn 30's "116"
      was `quality.inverted_corners`, a different metric. Confirm the intended
      comparison basis.
- [ ] Polygon regularization is applicable-if-present: zero modes on the tri
      wall with no raise, nonzero on the quad panel, selected inside
      `mesh_motion_pipeline.py` and never by the example.

## 8. Clean-clone acceptance

```bash
git clone --no-hardlinks --branch production-ready-overhaul \
  "file:///Users/mariusruh/Documents/Research/nasa_uli/mesh_movement/packages/BSM3" \
  /tmp/bsm3-m17a-codex-verify
cd /tmp/bsm3-m17a-codex-verify
git status --porcelain
PYTHONPATH=/tmp/bsm3-m17a-codex-verify python examples/e175_surface_deformation.py
PYTHONPATH=/tmp/bsm3-m17a-codex-verify python -m pytest -q tests
git status --porcelain            # must still be empty
```

- [ ] Claude observed an empty status before **and** after both commands, so
      the STEP-import cache containment now lives in the library and no run
      writes into the checkout.
- [ ] Working-tree suite: **175 passed** (was 173). Clean clone: **161 passed, 1 skipped**
      (was 159/1), empty status before and after.

## 9. Remaining M1 scope — unchanged

M1.6 slices 2 (projections + preprocessing) and 3 (drivers, MPI/DAFoam), then
M1.8 pickle retirement, then full M1.7 acceptance (R4 reproduction within
tolerance, STEP-to-VortexAD). M1.7's carry-ins still stand: the
`GraphDistanceWeighting.summary` `TypedDict`, and its dead `"decay"` key.

No stop rule fired during implementation.
