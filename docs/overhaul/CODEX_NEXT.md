# Claude Turn 40 — implement M1.6 slice 2 documentation

You are the **implementer**. Codex is the **planner/reviewer**. M1.7a is
accepted. Implement M1.6 slice 2 as a documentation-only change over the
retained projection and preprocessing modules, add their pinned CI doc-lint
gate, verify mechanically, commit coherently, and hand back for Codex review.
Do not mark M1.6 slice 2 complete yourself.

## Measured baseline and target

The slice contains 15 retained modules and 80 public definitions under the
same convention used for slice 1: public module-level functions/classes plus
public methods of public classes. Today, 33/80 carry any docstring and 47 are
missing one.

| Module | Current |
|---|---:|
| `function_set_closest_distance_custom_op.py` | 0/17 |
| `function_set_evaluation_custom_op.py` | 0/10 |
| `function_set_projection_custom_op.py` | 0/6 |
| `orthogonality_projection_numpy.py` | 0/5 |
| `warm_start_candidate_projection_numpy.py` | 0/5 |
| `warm_start_projections.py` | 7/10 |
| `preprocessing/__init__.py` | 0 definitions; module API text exists |
| `components.py` | 3/3 |
| `gmsh.py` | 0 definitions; private parser module |
| `intersections.py` | 1/1 |
| `mesh_io.py` | 6/7 |
| `movement.py` | 9/9 |
| `quad_conversion.py` | 2/2 |
| `stl.py` | 0 definitions; private parser module |
| `symmetry.py` | 5/5 |

Target: **80/80**, useful NumPy-style documentation, module docstrings on all
15 files, and a CI `ruff --select D` step covering the literal slice.

## Literal path allowlist

Only these 19 paths may change:

1. `.github/workflows/actions.yml`
2. `bsm3/core/projections/function_set_closest_distance_custom_op.py`
3. `bsm3/core/projections/function_set_evaluation_custom_op.py`
4. `bsm3/core/projections/function_set_projection_custom_op.py`
5. `bsm3/core/projections/orthogonality_projection_numpy.py`
6. `bsm3/core/projections/warm_start_candidate_projection_numpy.py`
7. `bsm3/core/projections/warm_start_projections.py`
8. `bsm3/preprocessing/__init__.py`
9. `bsm3/preprocessing/components.py`
10. `bsm3/preprocessing/gmsh.py`
11. `bsm3/preprocessing/intersections.py`
12. `bsm3/preprocessing/mesh_io.py`
13. `bsm3/preprocessing/movement.py`
14. `bsm3/preprocessing/quad_conversion.py`
15. `bsm3/preprocessing/stl.py`
16. `bsm3/preprocessing/symmetry.py`
17. `docs/overhaul/PLAN.md`
18. `docs/overhaul/LOG.md`
19. `docs/overhaul/CODEX_NEXT.md`

In the 15 Python modules, only docstrings and comments may change. No import,
constant, annotation, signature, decorator, executable statement, or control
flow may change. In `actions.yml`, add exactly one new doc-lint step for these
15 paths; do not edit existing steps. Stop and report rather than widening the
allowlist or repairing behavior discovered while reading.

## Documentation requirements

Document what the code actually does; follow bodies, call sites, and tests
rather than inferring from names. Use NumPy docstring sections where applicable:
`Parameters`, `Returns`, `Raises`, `Attributes`, and focused `Notes`.

For the projection modules, make these contracts explicit:

- coefficient stacking order and array shapes;
- patch metadata, parametric-coordinate layout, and returned point/distance
  shapes;
- warm-start candidate selection and boundary/degenerate-edge handling;
- Newton convergence/failure results and tolerance semantics;
- which operations are NumPy setup-time computations versus differentiable
  CSDL custom operations;
- first- and second-order VJP inputs/outputs without claiming guarantees the
  implementation does not provide; and
- the purpose of each custom operation's `evaluate` and `compute` boundary.

For preprocessing, document:

- component discovery and the meaning of search names;
- mesh coordinate/connectivity conventions and `MeshData.nodes`;
- ownership, deformation, projection, reevaluation, symmetry, and intersection
  metadata;
- supported file-format behavior and explicit trusted-pickle boundaries;
- quad conversion gates and failure conditions; and
- shapes, indexing conventions, tolerances, and exceptional cases that a
  caller needs to use the public surface safely.

Both `load_function_set_from_pickle` and `load_function_set` must state that
Python pickle is executable and only trusted local input is acceptable. Do not
rename, delete, or redesign them in this slice; M1.8 owns pickle retirement.

Avoid generic filler such as “Compute the result.” Explain the mathematical or
data contract at the level supported by the implementation. Do not invent SI
units where the code is unit-agnostic. Preserve existing useful prose while
converting non-NumPy styles where necessary.

## CI change

Append one step named clearly for projection/preprocessing documentation:

```yaml
- name: Numpydoc checks for projection and preprocessing
  run: |
    python -m ruff check --select D \
      <all 15 literal module paths>
```

Use the existing workflow indentation and pinned `ruff==0.9.10`. It is fine
that `preprocessing/__init__.py` and `mesh_io.py` also appear in the older M0
step; this slice's complete gate must be readable in one place.

## Mechanical enforcement

Before editing, record the handoff commit:

```bash
TURN40_BASE=$(git rev-parse HEAD)
```

After editing, run the slice-1 stripped-AST procedure over all 15 Python files:
recursively remove a leading string-literal docstring from every module,
class, function, and async function, then compare `ast.dump(...,
include_attributes=False)` against `$TURN40_BASE`. Expected: **zero drift**.
Comments naturally disappear from the AST.

Re-run an AST coverage inventory that counts every public module-level
function/class and every public method on a public class. Print per-file counts
and the aggregate. Expected: **80/80**, zero missing names. Also inspect every
changed Python hunk and confirm it is a docstring or comment.

Run:

```bash
conda run -n central_geom python -m pytest -q \
  tests/test_function_set_projection_numpy.py \
  tests/test_warm_start_retry_regression.py \
  tests/test_preprocessing_plotting.py \
  tests/test_curated_assets.py \
  tests/test_boundary_surface_movement.py -m "not integration"

conda run -n central_geom python -m pytest -q \
  tests/test_derivative_gate.py \
  tests/test_ngon_affine_operator.py \
  tests/test_ngon_affine_load_step.py

python -m ruff check --select D \
  bsm3/core/projections/function_set_closest_distance_custom_op.py \
  bsm3/core/projections/function_set_evaluation_custom_op.py \
  bsm3/core/projections/function_set_projection_custom_op.py \
  bsm3/core/projections/orthogonality_projection_numpy.py \
  bsm3/core/projections/warm_start_candidate_projection_numpy.py \
  bsm3/core/projections/warm_start_projections.py \
  bsm3/preprocessing/__init__.py \
  bsm3/preprocessing/components.py \
  bsm3/preprocessing/gmsh.py \
  bsm3/preprocessing/intersections.py \
  bsm3/preprocessing/mesh_io.py \
  bsm3/preprocessing/movement.py \
  bsm3/preprocessing/quad_conversion.py \
  bsm3/preprocessing/stl.py \
  bsm3/preprocessing/symmetry.py

git diff --check -- <the 19 allowlisted paths>
```

The pre-edit baselines are **82 passed, 3 deselected** for the focused
projection/preprocessing command and **6 passed** for the derivative/M1.4
guard command. The post-edit counts must match.

Ruff is currently unavailable in `central_geom`; do not install or change
dependencies. Attempt and record the local result. The new pinned CI step is
the authoritative lint gate. Because stripped executable AST must remain
identical, do not rerun the expensive E175 integrations or a clean-clone full
suite in this documentation slice. The focused projection/preprocessing tests
and derivative/M1.4 guards are sufficient.

## Handoff

Use one source/CI documentation commit and one collaboration-doc commit. Update
M1.6 to **slice 2 ready for Codex review**, not complete. Append Turn 40 to
`LOG.md` without rewriting history. Replace this file with a Codex review
checklist containing commits, exact paths, per-file and aggregate coverage,
stripped-AST result, focused test counts, unchanged numerical guard values, CI
diff, Ruff availability, and deviations. Hand back to Codex.
