# Review prompt for Claude — Turn 29 (M1.6 slice 1)

Paste into a Claude session at the repository root.

---

Review Codex Turn 28 in `docs/overhaul/LOG.md`, the defect-fix commit
`03a4f54`, and its immediate documentation successor at the current branch
tip. Read the updated M1.6 status and Turn-28 user steering in
`docs/overhaul/PLAN.md`.

## Required ruling

Rule independently on both commits:

1. `03a4f54` must change only
   `GraphDistanceWeighting.summary`'s return annotation from
   `dict[str, float]` to `dict[str, float | int | str]`. Its returned mapping,
   including the dead `"decay"` payload, must be byte-identical.
2. The successor must contain only docstrings in the 16 slice-1 source files,
   the new 16-path CI step, and collaboration documentation. No callable
   signature, executable AST, test, or excluded dirty file may change.

If both pass, mark **M1.6 slice 1 complete**. M1.6 as a whole remains open.

## Literal Turn-28 allowlist

```
.github/workflows/actions.yml
bsm3/core/boundary_surface_movement/mesh_motion_config.py
bsm3/core/boundary_surface_movement/mesh_motion_pipeline.py
bsm3/core/boundary_surface_movement/motion.py
bsm3/core/boundary_surface_movement/elasticity.py
bsm3/core/boundary_surface_movement/load_stepping.py
bsm3/core/boundary_surface_movement/current_graph_solve.py
bsm3/core/boundary_surface_movement/ngon_affine.py
bsm3/core/boundary_surface_movement/quadratic_distortion.py
bsm3/core/boundary_surface_movement/projection.py
bsm3/core/boundary_surface_movement/quality.py
bsm3/core/boundary_surface_movement/graph_distance.py
bsm3/core/boundary_surface_movement/free_region.py
bsm3/core/boundary_surface_movement/constraints.py
bsm3/core/boundary_surface_movement/spd_solve_custom_op.py
bsm3/core/boundary_surface_movement/geometry.py
bsm3/core/boundary_surface_movement/intersections.py
docs/overhaul/PLAN.md
docs/overhaul/LOG.md
docs/overhaul/CODEX_NEXT.md
```

Confirm that all eight pre-existing tracked edits outside this list remain
dirty and uncommitted.

## Independent checks

Run the Turn-28 coverage check. Expected: **132/132 (100%)**, zero
undocumented definitions. Ruff and pydocstyle are absent from `central_geom`;
do not install them into the user's environment.

Verify the defect commit directly:

```bash
git diff --name-status 0dbcc75..03a4f54
git diff 0dbcc75..03a4f54 -- \
  bsm3/core/boundary_surface_movement/graph_distance.py
```

Then compare executable ASTs against the fix commit, not `0dbcc75`:

```bash
python - <<'PY'
import ast
import subprocess
from pathlib import Path

base = Path("bsm3/core/boundary_surface_movement")
files = """mesh_motion_config mesh_motion_pipeline motion elasticity
load_stepping current_graph_solve ngon_affine quadratic_distortion projection
quality graph_distance free_region constraints spd_solve_custom_op geometry
intersections""".split()

class StripDocstrings(ast.NodeTransformer):
    def strip(self, node):
        if (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            node.body = node.body[1:] or [ast.Pass()]
        return self.generic_visit(node)

    visit_Module = strip
    visit_ClassDef = strip
    visit_FunctionDef = strip
    visit_AsyncFunctionDef = strip

drift = []
for name in files:
    path = str(base / f"{name}.py")
    old = subprocess.run(
        ["git", "show", f"03a4f54:{path}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    before = ast.dump(
        StripDocstrings().visit(ast.parse(old)), include_attributes=False
    )
    after = ast.dump(
        StripDocstrings().visit(ast.parse(Path(path).read_text())),
        include_attributes=False,
    )
    if before != after:
        drift.append(path)
print("non-docstring AST drift:", drift or "none")
PY
```

Expected: `none`.

Confirm `.github/workflows/actions.yml` adds exactly one new lint step covering
the 16 paths, without changing either existing lint step. Then run:

```bash
conda run -n central_geom python -m pytest -q tests/test_derivative_gate.py
conda run -n central_geom python -m pytest -q \
  tests/test_ngon_affine_operator.py tests/test_ngon_affine_load_step.py
conda run -n central_geom python -m pytest -q tests
```

Expected counts: **1**, **5**, and **171 passed**. Re-measure the seven M1.4
values rather than treating passing assertions as proof of numerical identity.

## Genuine-clone verification

Use a fresh temporary directory rather than deleting an uncertain path:

```bash
VERIFY_DIR=$(mktemp -d /tmp/bsm3-m16-s1-claude.XXXXXX)
git clone --no-hardlinks --branch production-ready-overhaul \
  "file:///Users/mariusruh/Documents/Research/nasa_uli/mesh_movement/packages/BSM3" \
  "$VERIFY_DIR/repo"
cd "$VERIFY_DIR/repo"
git status --porcelain
git grep -n "float | int | str" -- \
  bsm3/core/boundary_surface_movement/graph_distance.py
conda run -n central_geom python -m pytest -q tests
```

Expected: empty status and **157 passed / 1 skipped**.

## Next-task steering from the user

After the review, do **not** automatically issue M1.6 slice 2 as another broad
documentation batch. The user wants the work steered toward a runnable,
well-documented E175 example using the generalized API without discarding the
remaining milestones.

Audit the existing tracked E175 entry points and prepare the next concrete
Codex prompt around the smallest useful vertical deliverable:

- a clearly named E175 example using `ModelFiles`, `PipelineConfig`,
  `DeclarativeGeometryParameterization` or a driver-supplied parameterization
  factory, and `build_mesh_motion_model`;
- local user-provided paths, with the existing E175 files as the initial case;
- a documented command/configuration path that a new user can actually run;
- analytical derivatives of the final deformed and reprojected mesh with
  respect to design variables, retaining the existing scalar FD gate;
- VortexAD integration if practical; no DAFoam test requirement;
- graph Laplacian plus n-gon regularization only;
- no revival of removed membrane, barrier, or tangential-smoothing paths.

Use that example as the organizing integration path for the remaining driver
documentation and early M1.7 acceptance work. Keep preprocessing/projection
documentation and M1.8 explicitly scheduled, with M1.8 still completed before
final M1 acceptance.

Append Claude Turn 29 to `docs/overhaul/LOG.md`, update `PLAN.md` with the
accepted status and concrete revised sequencing, then replace this file with a
literal allowlisted Codex prompt. Preserve the stop rule: Codex must report
rather than widen scope silently.
