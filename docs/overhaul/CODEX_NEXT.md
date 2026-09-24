# Claude Turn 46 — final M1.6 slice 2 semantic correction

You are the **implementer**. Codex is the **planner/reviewer**. Turn 44 closes
the structural documentation work, but M1.6 slice 2 remains open for three
narrow accuracy corrections. Edit only the affected docstrings/comments,
reproduce the established gates, append commits, and hand back for Codex
review. Do not mark slice 2 complete yourself.

## Ruling on the standing rejection gate

Retain whitespace-normalized, case-folded, punctuation-insensitive phrase
matching as a backstop for **known rejected claims**. It is not a semantic
proof and should not grow into the primary review method. AST/signature/return
audits enforce structural facts; semantic accuracy still requires comparing
the prose to implementation bodies and tests.

## Literal six-path allowlist

Only these paths may change:

1. `bsm3/core/projections/function_set_closest_distance_custom_op.py`
2. `bsm3/core/projections/orthogonality_projection_numpy.py`
3. `bsm3/core/projections/warm_start_candidate_projection_numpy.py`
4. `docs/overhaul/PLAN.md`
5. `docs/overhaul/LOG.md`
6. `docs/overhaul/CODEX_NEXT.md`

The Python changes are docstrings/comments only. Do not change imports,
annotations, signatures, constants, decorators, or executable statements. Do
not touch the other three projection modules, preprocessing, workflow, or
tests. Preserve unrelated dirty-tree paths and stage every file literally.

## Exact corrections

### Convergence evidence

1. In `FunctionSetProjectionModel.project`, remove the statement that residual
   is the only convergence evidence. Its state contains `converged`,
   `iterations`, and `residual`; make the return description and note name
   those roles. `converged` is the solver's Boolean decision, while residual
   and iterations are diagnostics. Derivatives remain unsupported where
   `converged` is false.
2. In `SurfaceProjectionResult.uv`, remove the statement that `converged` is
   the only evidence. Say `uv` is the final iterate; `converged` records the
   solver decision, and `residual`, `step_norm`, and `iterations` provide the
   associated diagnostics. Do not call any one field the only evidence.

### Retry ordering and compatibility

The current candidate prose twice claims that a genuinely converged retry can
replace a converged clamped selection even when the retry is farther away.
That is not what the body does.

Document the two sequential gates exactly:

1. `_is_candidate_better` must first rank the retry above the selection.
   Converged outranks non-converged. If both are converged, the retry must have
   smaller `dist2`, with residual only breaking an exact distance tie. If both
   are non-converged, smaller residual wins, with distance as the tie-break.
2. `_is_retry_candidate_compatible` then imposes the finite-distance cap and,
   for different patches, the normal-alignment guard. The factor/absolute cap
   can permit a farther retry when the retry improves convergence rank (or
   residual rank among non-converged candidates); it does **not** authorize a
   farther retry when both candidates are converged.

Apply this correction both in the function's explanatory prose and in the
`retry_accept_distance_factor, retry_accept_distance_atol` parameter text.
Keep `boundary_clamped` as a retry trigger independent of `converged`.

### Eager-cost language

- Replace “higher setup cost” for `warm_start_nu, warm_start_nv` with higher
  eager tessellation-construction cost; this function runs when called.
- Replace the claim that larger `num_samples` makes edge matching “stricter.”
  It samples the comparison more densely and costs more; it can expose an
  interior mismatch missed by a coarser grid, but strictness is not guaranteed
  to vary monotonically as sample locations change.

Do not broaden this turn into another rewrite. Preserve all correct Turn-44
parameter, mapping, return-container, and pickle documentation.

## Verification

Record the base before editing. Re-run:

- recursive stripped-docstring AST identity over the three changed Python
  files: expected **3/3 identical**;
- full slice inventory: **80/80** definitions and **15/15** modules;
- the reproducible Turn-44 signature audit over all six projection modules:
  **36 callables, 124 parameters, 0 missing, 0 extra**;
- the four VJP mapping-key and `unsort` list-return audit unchanged; and
- first-line/NumPy-style checks unchanged.

For the known-claim backstop, normalize all whitespace, lowercase, then strip
punctuation before checking the three source files. These phrases must be
absent:

```text
only convergence evidence
residual in state is the only
even when it is slightly farther
clamped one that is slightly closer
higher setup cost
make matching stricter
```

Then run:

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
  bsm3/core/projections/orthogonality_projection_numpy.py \
  bsm3/core/projections/warm_start_candidate_projection_numpy.py

git diff --check -- <the six literal allowlisted paths>
```

Expected tests remain **82 passed / 3 deselected** and **6 passed**. Ruff is
still unavailable in `central_geom`; attempt it, record the limitation, and do
not install or change dependencies.

## Commit and handoff

Append one source-doc correction commit and one collaboration-doc commit. Do
not amend, reset, rebase, or rewrite history. Stage literal paths only.

Update M1.6 to **slice 2 final correction ready for Codex review**, not
complete. Append Turn 46 to `LOG.md`. Replace this file with a concise Codex
checklist containing hashes, exact paths, corrected semantic statements, AST,
coverage, parameter and return-container audits, normalized backstop result,
test counts, Ruff status, and deviations. Hand back to Codex.
