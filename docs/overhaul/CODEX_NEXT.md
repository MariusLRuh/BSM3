# Claude Turn 38 — document the universal external-geometry contract

You are the **implementer**. Codex is the **planner/reviewer**. Turn 37 accepts
the Turn-36 implementation functionally. Make this final documentation-only
correction, verify it mechanically, commit it, update the handoff records, and
leave this file as a concise Codex review checklist. Do not accept M1.7a.

## Ruling and intended architecture

`GeometryModel` stays as the required neutral declaration/binding container;
it is **not** the required source of the geometry parameterization. The public
contract is:

```text
any differentiable CSDL/LFS-compatible parameterization
    -> deformed component coefficients
    -> GeometryModel.add_component(...)
    -> BSM3 intersections, graph motion, reprojection, and diagnostics
```

External packages may own every design variable and deformation operation.
They do not subclass BSM3, provide private callbacks, or use
`GeometryModel.design_variable()`. The built-in `add_lifting_surface` and
`add_body` methods are optional conveniences alongside this generic path.

Turn 36 proves this behavior end to end with an externally constructed,
relative 0.35 m wing deformation and an analytic derivative matching centered
FD to 4.21e-14. Do not change that implementation or its tests in this turn.

## Literal path allowlist

Only these paths may change:

1. `bsm3/core/boundary_surface_movement/geometry_model.py`
2. `bsm3/mesh_motion.py`
3. `examples/e175_surface_deformation.py`
4. `docs/overhaul/PLAN.md`
5. `docs/overhaul/LOG.md`
6. `docs/overhaul/CODEX_NEXT.md`

In the three Python files, only docstrings and comments may change. No import,
constant, expression, annotation, signature, control flow, or executable AST
node may change. Do not widen the allowlist silently.

## Required public narrative

### `geometry_model.py`

Rewrite the module and `GeometryModel` class docstrings so the generic external
path is primary:

- `GeometryModel` binds component coefficient expressions and downstream mesh
  behavior; it does not require ownership of their parameterization or design
  variables.
- `add_component` accepts either a stacked `(N, 3)` CSDL variable/array in
  sorted patch-ID order or a mapping from patch ID to coefficient block.
- An external expression must belong to the same caller-owned active recorder
  passed to `mm.run` if derivatives are required.
- BSM3 imports the baseline STEP geometry, identifies the component through
  `search_name`, and validates patch IDs/shapes after import. The target must
  retain compatible component topology and coefficient layout; arbitrary
  topology/patch-layout changes are outside this contract.
- `free_region=None` makes the entire component free; the plain axis mapping
  provides optional restrictions.
- `add_lifting_surface`, `add_body`, and `design_variable` are conveniences,
  not requirements or the universal boundary.

Include one compact doctest-skipped example of the external path, conceptually:

```python
geometry = GeometryModel()
geometry.add_component(
    name="wing",
    search_name="wing",
    deformed_coefficients=external_coefficients,
)
```

The example must make clear that `external_coefficients` can be produced by
another package and may depend on its own CSDL variables. Also retain a compact
built-in-helper example as the secondary convenience path.

Correct the `add_component` docstring: `add_lifting_surface` and `add_body` are
implemented alongside it and build their own private records. Do not claim
they are layered on or call through the same mechanism.

Remove or rewrite every statement implying that only two component kinds are
supported or that `GeometryModel` necessarily owns the design variables.

### `bsm3/mesh_motion.py`

Clarify in the module documentation and `run(..., geometry=...)` parameter
description that `GeometryModel` is the declaration/binding envelope. It may
contain external differentiable coefficients and does not constrain how they
were parameterized. Keep the concise three-object user model and all existing
API names/signatures.

### E175 example

Clarify only in its module/function comments or docstrings that this script
deliberately demonstrates the optional built-in lifting-surface/body helpers
for readability. State that an external parameterization replaces stage 2
with `GeometryModel.add_component` while stages 3-5 and the downstream BSM3
pipeline remain identical. Do not insert a second implementation, low-level
coefficient construction, or more runtime inputs into the example.

## Mechanical enforcement

Before editing, record the handoff commit with:

```bash
TURN38_BASE=$(git rev-parse HEAD)
```

After editing, compare each of the three Python files with `$TURN38_BASE` using
an AST check that recursively removes leading string-literal docstrings from
modules, classes, and functions before comparing `ast.dump(...)`. Because
comments do not appear in the AST, the stripped trees must be exactly equal.
Also inspect the diff and verify every changed Python hunk is documentation or
comment text.

Run:

```bash
conda run -n central_geom python -m pytest -q \
  tests/test_e175_example.py -m "not integration" \
  tests/test_e175_driver_configuration.py

python -m ruff check --select D \
  bsm3/mesh_motion.py \
  bsm3/core/boundary_surface_movement/geometry_model.py

rg -n "owns the differentiable design variables|Two component kinds|layered on the same mechanism" \
  bsm3/core/boundary_surface_movement/geometry_model.py bsm3/mesh_motion.py

git diff --check -- \
  bsm3/core/boundary_surface_movement/geometry_model.py \
  bsm3/mesh_motion.py examples/e175_surface_deformation.py \
  docs/overhaul/PLAN.md docs/overhaul/LOG.md docs/overhaul/CODEX_NEXT.md
```

The rejection grep and stripped-AST comparison must be empty/equal. If `ruff`
is unavailable in `central_geom`, record that fact; do not install or change
dependencies. No expensive E175 integration or clean-clone rerun is required
because executable Python and test code are forbidden to change, and Turn 36
already supplied those results.

## Handoff

Update the M1.7a status to **ready for Codex acceptance review**, not accepted.
Append a short Turn-38 entry to `LOG.md` without rewriting history. Replace
this file with a review checklist containing the commit, changed paths,
contract wording summary, stripped-AST result, doc-lint result, focused test
count, rejection grep, and diff check. Hand back to Codex.
