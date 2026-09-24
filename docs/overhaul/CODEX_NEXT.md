# Codex acceptance checklist — Turn 39 (M1.7a)

Claude implemented Turn 38, a documentation-only correction. Codex owns the
acceptance ruling. Base commit `7083c68`. **M1.7a is not accepted by Claude.**

## Commit and changed paths

| Commit | Paths |
|---|---|
| `6df3ef2` | `geometry_model.py`, `bsm3/mesh_motion.py`, `examples/e175_surface_deformation.py` |
| docs commit | `docs/overhaul/PLAN.md`, `LOG.md`, `CODEX_NEXT.md` |

- [ ] Six paths, inside the allowlist, **zero violations**.

## Mechanical proof that nothing executable changed

Each file's AST was compared against `7083c68` after recursively stripping
leading string-literal docstrings from every module, class, and function scope.
Comments never appear in the AST, so equality proves no executable node moved.

| file | stripped AST |
|---|---|
| `geometry_model.py` | **identical** |
| `bsm3/mesh_motion.py` | **identical** |
| `examples/e175_surface_deformation.py` | **identical** |

- [ ] Reproduce the stripped-AST comparison.
- [ ] Independent hunk classification: all **113** changed Python lines are
      docstring prose, doctest lines, or comments. **Zero** resemble an
      import, definition, statement, or assignment.
- [ ] No signature, annotation, constant, import, or control-flow change.

## Contract wording now published

- [ ] Module and class docstrings lead with the generic path:
      *any differentiable CSDL/LFS-compatible parameterization → deformed
      coefficients → `add_component` → BSM3 intersections, graph motion,
      reprojection, diagnostics.*
- [ ] `add_component` accepts stacked `(N, 3)` in sorted patch-ID order **or**
      a patch-keyed mapping; validation happens after STEP import.
- [ ] External expressions must belong to the caller-owned recorder passed to
      `mm.run` when derivatives are required.
- [ ] Stated limit: the target must keep a compatible component topology and
      coefficient layout; arbitrary topology/patch-layout change is outside
      the contract.
- [ ] `free_region=None` frees the whole component; the axis mapping is the
      optional restriction.
- [ ] `add_lifting_surface`, `add_body`, `design_variable` are described as
      optional conveniences, **not** the universal boundary.
- [ ] Doctest-skipped external example present, with the built-in helper
      example retained as secondary.

**Three rejected claims removed:** that `GeometryModel` owns the differentiable
design variables; that only two component kinds are supported; and that
`add_lifting_surface`/`add_body` are layered on the same mechanism as
`add_component`. They are separate optional conveniences, each building its own
private record.

- [ ] `bsm3/mesh_motion.py` describes `GeometryModel` as a declaration/binding
      envelope in both the module text and the `run(geometry=...)` parameter.
- [ ] The E175 example states it deliberately demonstrates the optional
      helpers, and that an external parameterization replaces stage 2 only
      while stages 3-5 and the downstream pipeline are identical. No second
      implementation, no low-level coefficient construction, no new runtime
      inputs.

## Verification

```bash
python -m pytest -q tests/test_e175_example.py -m "not integration" \
  tests/test_e175_driver_configuration.py
rg -n "owns the differentiable design variables|Two component kinds|layered on the same mechanism" \
  bsm3/core/boundary_surface_movement/geometry_model.py bsm3/mesh_motion.py
git diff --check -- <the six paths>
```

- [ ] Focused tests **22 passed, 6 integration deselected**.
- [ ] Rejection grep **empty**.
- [ ] `git diff --check` **clean** over all six paths.
- [ ] **Ruff unavailable in `central_geom`** (recorded since Turn 18). No
      dependency installed or changed, per the spec. Doc lint therefore
      unverified locally; CI's pinned `ruff==0.9.10` remains authoritative.
- [ ] No E175 integration or clean-clone rerun, as the spec directed: the
      executable AST is proven unchanged and Turn 36 supplied those results
      (external FD rel-error **4.21e-14**, tri at full scale **0/0/0**, quad
      **114/114/114**, clone **178 passed / 1 skipped**, status empty).

## Remaining M1 scope

M1.6 slices 2 and 3, then M1.8 pickle retirement, then full M1.7 acceptance.
M1.7 carry-ins stand: the `GraphDistanceWeighting.summary` `TypedDict` and its
dead `"decay"` key.
