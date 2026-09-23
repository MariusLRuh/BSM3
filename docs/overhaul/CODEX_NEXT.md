# Claude implementation prompt — Turn 32 (M1.7a usability correction)

Paste this entire prompt into Claude at the repository root.

---

You are the **implementer** for this turn. Codex is now the planner/reviewer.
Implement the bounded plan below, verify it, commit it, record the result, and
hand it back to Codex for review. Do not redesign the task or write a prompt
for another implementer.

Read `docs/overhaul/PLAN.md` through the Turn-31 planning section and
`docs/overhaul/LOG.md` through Turn 31. The user rejected the first M1.7a
example (`476b10d`, `a9c2830`) on usability grounds while retaining its
numerical behavior as the regression baseline.

Claim `## Turn 32` by appending to `LOG.md` before editing implementation
files. Close it when done.

## Outcome

Replace the current 600-line example-facing object graph with a small,
intuitive mesh-motion API and an uncluttered E175 main script. The script must
show five short executable stages, accept paths and high-level geometry values,
and contain none of the coefficient, connectivity, polygon-normal, cache, or
CLI machinery.

This is a clean API break. Do not preserve deprecated aliases for the rejected
names.

## Public vocabulary — implement these exact names

Rename the high-level types in `mesh_motion_config.py` as follows:

| Old name | New name |
|---|---|
| `ModelFiles` | `InputFiles` |
| `GraphDistanceWeightingConfig` | `DistanceWeighting` |
| `DistortionRegularizationConfig` | `DistortionPenalty` |
| `NgonAffineRegularizationConfig` | `PolygonRegularization` |
| `SurfaceMotionConfig` | `SurfaceMotion` |
| `VolumeMotionConfig` | `VolumeMotion` |
| `MeshQualityOutputConfig` | `QualityChecks` |
| `VisualizationConfig` | `Visualization` |
| `FiniteDifferenceConfig` | `DerivativeCheck` |
| `PipelineConfig` | `MeshMotion` |
| `DeclarativeGeometryParameterization` and its public protocol | one concrete `GeometryModel` |

`MeshMotionResult` keeps its name. Low-level numerical solver types such as
`NgonAffineConfig`, `QuadraticDistortionConfig`, and `FlowConfig` are outside
this high-level rename and keep their names.

No exact proposed name collides with a tracked class today. In particular,
`DistanceWeighting` deliberately avoids the existing runtime
`GraphDistanceWeighting` object.

Rename the corresponding fields for readability, without compatibility
properties:

- `InputFiles.geometry_file`, `surface_mesh_file`, `volume_mesh_file`,
  `volume_wall_map_file`, `cache_directory`;
- `SurfaceMotion.distance_weighting`, `distortion_penalty`, and
  `polygon_regularization`;
- `MeshMotion.surface`, `volume`, `quality`, `visualization`, and
  `derivative_check`.

Make the safe high-level defaults surface-only and headless:

- `VolumeMotion(mode="off", write_meshes=False)`;
- surface quality enabled, volume/Gmsh quality disabled;
- visualization disabled;
- derivative check disabled.

The tracked DAFoam driver must continue to opt into its required volume and CFD
behavior explicitly.

## Compact namespace

Add `bsm3/mesh_motion.py` as the intended user entry point. A user should write
only:

```python
import bsm3.mesh_motion as mm
```

Export the high-level names above, `GeometryModel`, `MeshMotionResult`, and a
single `run(...)` entry point. Do not re-export low-level component specs,
callbacks, polygon helpers, or solver-assembly types from this facade.

The underlying boundary-surface package may expose `run_mesh_motion`; the
facade's `run` is the deliberately designed public spelling, not a deprecated
alias. Delete `build_mesh_motion_model` rather than retaining it as an alias,
and update every tracked caller.

## `GeometryModel`: high-level geometry input

Implement `GeometryModel` in a new
`bsm3/core/boundary_surface_movement/geometry_model.py`. It owns design
variables and internally compiles the private component/intersection records
the pipeline already needs. `ComponentSpec`, `IntersectionSpec`, and the
callback-bearing protocol cease to be public; rename them to private internal
types if they remain.

Required public methods and semantics:

```python
geometry = mm.GeometryModel()

variable = geometry.design_variable(
    name,
    value,
    lower=...,
    upper=...,
    scaler=...,
)

geometry.add_lifting_surface(
    name=...,
    search_name=...,
    pivot_intersection=...,
    translation_x=...,
    rotation_y_degrees=...,
    area=...,
    aspect_ratio=...,
    reference_area=...,
    reference_aspect_ratio=...,
    root_half_width=...,
    projection_name=...,
    pivot_chord_fraction=0.25,
)

geometry.add_body(
    name=...,
    search_name=...,
    diameter_scale=...,
    free_axial_fraction=(0.05, 0.97),
    projection_name=...,
)

geometry.connect(
    name=...,
    driving_component=...,
    query_component=...,
    search_direction="u",
    solver_name=...,
)
```

Optional motion arguments may default to their identity values so the tail
does not have to specify planform scaling. Return the CSDL variable from
`design_variable`. Validate names, references, fractions, and paired reference
planform inputs at construction time.

These helpers must be general, not E175-aware:

- a lifting surface derives its pivot from the named intersection at the
  configurable chord fraction, uses the intersection's median absolute span as
  its scaling root, interpolates rigid/planform targets over the load fraction,
  and uses a root free-region defined by `root_half_width`;
- a body derives its pivot from its control-point bounding box, interpolates
  diameter scale from 1.0, and uses `free_axial_fraction` for its free region;
- no aircraft/component name is hardcoded in the library.

The current nested `_wing_coefficients`, `_tail_coefficients`, and
`_fuselage_coefficients` behavior is the numerical reference. Move the general
mechanism into `GeometryModel`; do not copy those functions into another
example helper file.

## `run` and result diagnostics

The facade entry point is:

```python
result = mm.run(
    inputs=inputs,
    geometry=geometry,
    motion=motion,
    recorder=None,
)
```

When `recorder` is `None`, create/start/stop an inline CSDL recorder and retain
it on the returned `MeshMotionResult`. When a recorder is supplied, use it
without taking ownership of its lifecycle so the DAFoam integration remains
composable.

Move the `lsdo_function_spaces` working-directory cache containment from the
example into the library, scoped narrowly around STEP import and restored in a
`finally` block.

Expose diagnostics already computed by the pipeline on `MeshMotionResult`:

- `recorder`;
- `elapsed_seconds`;
- `surface_fold_count`;
- `surface_cell_count`;
- `surface_ngon_mode_count`;
- baseline and final inversion reports;
- a concise `print_summary()` method containing the current vertex/cell, load
  step, fold/inversion, elapsed-time, and surface-quality information.

The example must not recompute connectivity or normals. Keep the existing
vectorized fold implementation private in the pipeline and return its count.

## Rewrite the flagship example

Rewrite `examples/e175_surface_deformation.py`; do not incrementally preserve
its present structure.

Mechanical requirements:

- no `argparse`, CLI parsing, `argv`, `mesh_kind`, `ExampleRun`, dataclass,
  `_wing_coefficients`, `_tail_coefficients`, `_fuselage_coefficients`,
  `_surface_cells`, `_polygon_normals`, or `_count_polygon_folds`;
- no class definitions and no private function definitions;
- exactly one public function: `main`, returning `MeshMotionResult`;
- at most **5 import statements**, with no long symbol import list; use
  `import bsm3.mesh_motion as mm`;
- at most **220 physical lines**;
- no source-tree `sys.path` mutation;
- no topology label or branch. `SURFACE_MESH_FILE` is a directly editable
  `Path`; changing it to the documented quad file is the only mesh-selection
  change. Use `PolygonRegularization(weight=0.3)` for both paths—triangles have
  no affected modes, while quads activate the penalty;
- no setup/caching implementation beyond supplying `CACHE_DIRECTORY` through
  `InputFiles`.

The body of `main` must have these five visible, numbered section comments in
this order:

```python
# 1. Choose geometry and mesh files
# 2. Define design variables and component motion
# 3. Choose mesh-motion and quality settings
# 4. Run the differentiable mesh-motion model
# 5. Inspect the result
```

Use a path-based signature so tests and users can select another tracked mesh
without editing control flow:

```python
def main(
    *,
    geometry_file: Path = STEP_FILE,
    surface_mesh_file: Path = SURFACE_MESH_FILE,
    cache_directory: Path = CACHE_DIRECTORY,
) -> mm.MeshMotionResult:
```

All user-adjustable paths, design values, component names/intersections, and
motion settings must appear under those sections. The module docstring should
explain the same five stages, but comments in executable code are mandatory.
No CLI is permitted. `if __name__ == "__main__": main()` remains the direct
execution path.

The example should need only `pathlib`, `tempfile`, and the `mm` namespace
unless one additional standard-library import is demonstrably necessary.

Because the same settings are used for both files, treat positive polygon
regularization as an applicable-if-present setting: when the loaded surface
contains no four-or-more-sided cells, the pipeline must record zero n-gon modes
and skip constructing the affine model rather than raising on its zero matrix.
Do this selection inside `mesh_motion_pipeline.py`; the example must not inspect
topology. On the quad file the same weight must activate the existing affine
model and report a nonzero mode count.

## Tests and tracked drivers

Update both tracked drivers and their configuration tests to the new clean-break
API. Do not change their numerical settings or optional-solver behavior.

Rewrite `tests/test_e175_example.py` so it:

- calls `main` using the explicit triangle surface path, never a `mesh_kind`;
- retains the 600-second integration timeout and asset skip;
- asserts stable vertex count, expected result fields, zero folds, zero
  baseline/final inversions, and zero degenerate elements;
- statically enforces the example clutter constraints above;
- verifies the explicit quad path selects `PolygonRegularization(weight=0.3)`
  without a topology string.

Run the quad path once on the real tracked panel and record the time, fold
count, n-gon mode count, and baseline/final inversion counts in `LOG.md`. It
does not have to become a second expensive CI solve. The current baseline is
66.3 s, zero normal-flip folds, nonzero n-gon modes, and 116 baseline / 116
final corner-orientation inversions. Any newly introduced inversion is a stop;
final M1.7 still owns making the broader quad acceptance clean.

## Literal allowlist — 15 paths

```
bsm3/mesh_motion.py                                      (new)
bsm3/core/boundary_surface_movement/geometry_model.py    (new)
bsm3/core/boundary_surface_movement/mesh_motion_config.py
bsm3/core/boundary_surface_movement/mesh_motion_pipeline.py
bsm3/core/boundary_surface_movement/geometry_volume_backend.py
bsm3/core/boundary_surface_movement/__init__.py
bsm3/core/boundary_surface_movement/cfd_mesh_movement_test.py
bsm3/core/boundary_surface_movement/cfd_mesh_dafoam_analysis.py
examples/e175_surface_deformation.py
tests/test_e175_example.py
tests/test_e175_driver_configuration.py
.github/workflows/actions.yml                            (only to lint new public modules)
docs/overhaul/PLAN.md
docs/overhaul/LOG.md
docs/overhaul/CODEX_NEXT.md
```

If actual tracked-reference tracing proves one additional clean tracked file is
required, stop and report it rather than silently widening this list. All
pre-existing dirty files and all untracked research artifacts remain
prohibited.

## Required guards

Before implementation, save the current derivative-gate and M1.4 numerical
outputs. After implementation they must be unchanged to `1e-12`:

```bash
python -m pytest -q tests/test_derivative_gate.py
python -m pytest -q tests/test_ngon_affine_operator.py tests/test_ngon_affine_load_step.py
```

Required static acceptance:

```bash
# Rejected names are gone from tracked live Python code.
git grep -n -e ModelFiles -e PipelineConfig -e SurfaceMotionConfig \
  -e VolumeMotionConfig -e GraphDistanceWeightingConfig \
  -e NgonAffineRegularizationConfig -e DistortionRegularizationConfig \
  -e MeshQualityOutputConfig -e VisualizationConfig \
  -e FiniteDifferenceConfig -e DeclarativeGeometryParameterization \
  -e GeometryParameterization -e ComponentSpec -e IntersectionSpec \
  -e build_mesh_motion_model -- '*.py'                 # MUST be empty

# The example is visibly small and has the requested shape.
python - <<'PY'
import ast
from pathlib import Path
p = Path('examples/e175_surface_deformation.py')
s = p.read_text()
t = ast.parse(s)
imports = [n for n in t.body if isinstance(n, (ast.Import, ast.ImportFrom))]
classes = [n for n in ast.walk(t) if isinstance(n, ast.ClassDef)]
functions = [n for n in ast.walk(t) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
assert len(s.splitlines()) <= 220
assert len(imports) <= 5
assert not classes
assert [n.name for n in functions] == ['main']
for forbidden in ('argparse', 'mesh_kind', 'ExampleRun', '_wing_coefficients',
                  '_surface_cells', '_polygon_normals', '_count_polygon_folds'):
    assert forbidden not in s, forbidden
labels = [f'# {i}.' for i in range(1, 6)]
positions = [s.index(label) for label in labels]
assert positions == sorted(positions)
print(f'{len(s.splitlines())} lines; {len(imports)} imports; five ordered stages')
PY

python -m pytest -q tests/test_e175_driver_configuration.py
python -m pytest -q tests/test_e175_example.py
python -m pytest -q tests
```

Use the validated `central_geom` environment. Run the default example and the
manual quad example. A single deformation over roughly ten minutes is a stop.

## Clean-clone acceptance

Commit implementation before cloning. Use a fresh explicit target and verify
status both before and after execution:

```bash
git clone --no-hardlinks --branch production-ready-overhaul \
  "file:///Users/mariusruh/Documents/Research/nasa_uli/mesh_movement/packages/BSM3" \
  /tmp/bsm3-m17a-claude-verify
cd /tmp/bsm3-m17a-claude-verify
git status --porcelain
PYTHONPATH=/tmp/bsm3-m17a-claude-verify python examples/e175_surface_deformation.py
PYTHONPATH=/tmp/bsm3-m17a-claude-verify python -m pytest -q tests
git status --porcelain            # MUST still be empty
```

Record the new suite count; do not assume it remains 159/1.

## Stop rules

Stop, append the exact finding to Turn 32, and do not improvise if:

- a proposed public name has an unresolved collision;
- the high-level geometry helper would require an E175/component-name
  assumption in library code;
- a required tracked dependency lies outside the literal allowlist;
- derivative or M1.4 values drift at all;
- the tri result gains any fold/inversion or the quad motion introduces an
  inversion relative to its baseline;
- a deformation exceeds roughly ten minutes;
- a clean-clone run writes into the checkout.

## Commits and hand-back

Use explicit `git add` paths only. Prefer three reviewable commits:

1. high-level API, renames, pipeline diagnostics/cache ownership, and tracked
   driver updates;
2. simplified example and tests;
3. `PLAN.md`, appended Turn 32 `LOG.md`, CI lint scope if used, and hand-back.

Do not rewrite history. In `CODEX_NEXT.md`, leave a concise **Codex review
checklist**, not instructions for Claude to plan or review its own work. Codex
will independently inspect the implementation, rerun proportionate tests, and
issue the acceptance ruling.
