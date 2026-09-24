# Claude Turn 42 — correct M1.6 slice 2 projection documentation

You are the **implementer**. Codex is the **planner/reviewer**. M1.6 slice 2
remains open: Turn 40 passed every mechanical and numerical gate, but Codex's
content audit found inaccurate contracts and legacy non-NumPy prose. Correct
the six projection modules, prove executable AST identity again, commit the
correction without rewriting history, and hand back for Codex review. Do not
mark slice 2 complete yourself.

## Ruling on the Turn-40 staging deviation

No repository repair is required. The abandoned commit's 12 research artifacts
are absent from `b99b4a4` and `6268ce6`, remain untracked, and the dirty tree is
unchanged. Keep the recorded incident. For this turn stage every literal file;
never stage a directory, glob, or all changes.

## Literal path allowlist

Only these nine paths may change:

1. `bsm3/core/projections/function_set_closest_distance_custom_op.py`
2. `bsm3/core/projections/function_set_evaluation_custom_op.py`
3. `bsm3/core/projections/function_set_projection_custom_op.py`
4. `bsm3/core/projections/orthogonality_projection_numpy.py`
5. `bsm3/core/projections/warm_start_candidate_projection_numpy.py`
6. `bsm3/core/projections/warm_start_projections.py`
7. `docs/overhaul/PLAN.md`
8. `docs/overhaul/LOG.md`
9. `docs/overhaul/CODEX_NEXT.md`

Only docstrings and comments may change in the six Python modules. Do not edit
`.github/workflows/actions.yml`; its 15-path CI step is accepted. Do not edit
preprocessing, tests, configuration, imports, annotations, signatures,
constants, decorators, or executable statements. Stop and report rather than
widening the allowlist or changing behavior.

## Corrections required

Read the implementation bodies and tests before rewriting. Correct every
instance of the errors below, not merely the quoted sentence.

### Execution boundary

- Do not call Newton, warm-start selection, model projection, or model
  evaluation "setup-time" work. These are eager NumPy/PyVista kernels: direct
  callers execute them immediately, and the CSDL wrappers invoke them during
  custom-operation `compute`.
- Construction caches topology, patch metadata, B-spline space data, and the
  initial tessellation. State only that work is setup/construction work.
- `evaluate` declares CSDL graph inputs/outputs and derivatives; `compute`
  performs the eager numerical calculation and populates outputs. The model is
  non-CSDL, but not all of its work happens at setup.

### Coefficients and parametric coordinates

- Stacked coefficient order follows `model.patch_ids`, which follows explicit
  `patch_indices` when supplied and defaults to ascending patch ID otherwise.
  It is not unconditionally ascending.
- Document the coefficient shape as `(total_control_points,
  physical_dimension)` and each patch's half-open `start:stop` row span.
- `FunctionSetEvaluationModel` receives parametric coordinates on every call;
  they are not cached or fixed at construction. Their shape is `(N, 3)` with
  columns `[patch_id, u, v]`.
- Evaluation is linear in coefficients **for prescribed coordinates**, but is
  not merely the transpose of one cached basis matrix with respect to all
  inputs. Its VJP returns both coefficient and parametric-coordinate
  cotangents. The patch-ID column is discrete and its cotangent is zero; the
  `u`/`v` columns use the surface tangents.
- Give `FunctionSetEvaluationModel.compute_vjp` its exact parameter names and
  exact return order: `(d_coefficients, d_parametric_coordinates)`. Make both
  wrapper docstrings describe both cotangents.

### Projection, convergence, and reverse products

- The closest-distance model supports the configured distance,
  squared-distance, and regularized-distance measures, optionally signed by
  the SDF mode. Do not describe every result as signed.
- Forward state includes `converged`, `iterations`, and residual information;
  residual is not the only convergence evidence.
- `boundary_clamped` means the final parameter lies at a bound while the
  **unmasked** residual points outward. It can be true independently of the
  `converged` flag. It triggers retry; it does not mean by itself that the point
  converged only through masking.
- Candidate selection ranks converged candidates ahead of non-converged ones,
  uses distance among converged candidates, and residual then distance when no
  candidate converged. Describe retry replacement without claiming a raw
  minimum-distance choice across all candidates.
- Degenerate edges are detected from the tessellated boundary's sampled arc
  length. Their one-dimensional edge solve is replaced by a fixed-point
  candidate; they are not simply excluded, rejected, or down-weighted.
- `FunctionSetProjectionModel.compute_vjp` takes `d_distances`, not
  `d_output_measure`, and returns `(d_points, d_coefficients)` in that order.
  Document `forward_state` as an input.
- Give `compute_vjp_vjp` all exact inputs and its exact return order:
  `(dd_points, dd_coefficients, dd_d_distances)`.
- Parametric projection output has shape `(N, 3)` and columns
  `[patch_id, u, v]`; the patch-ID column has zero derivative. Physical output
  has shape `(N, physical_dimension)`.
- A custom-op `compute` caches forward state in `shared_state`; do not say it
  stores that state "into outputs".

### NumPy docstring style

Convert the module docstring and **all ten public definitions** in
`warm_start_projections.py` to genuine NumPy-style documentation. Seven of
those definitions already had string literals but still begin with a blank
line and use free-form blocks such as `Returns:`. Presence was not completion.

Across all six modules:

- every module and public definition must have a nonempty summary on the first
  line, ending in punctuation;
- use `Parameters`, `Returns`, `Raises`, `Attributes`, and `Notes` sections as
  applicable, with NumPy underlines;
- document exact shapes, ordering, exceptional cases, and return ordering for
  nontrivial public callables;
- retain the trusted-local-only pickle warnings; and
- avoid filler and claims not proved by the body.

## Mechanical proof

Record the correction base before editing:

```bash
TURN42_BASE=$(git rev-parse HEAD)
```

Recursively strip leading string-literal docstrings from every module, class,
function, and async function in all six Python files and compare
`ast.dump(..., include_attributes=False)` against `$TURN42_BASE`. Expected:
**6/6 identical**. Re-run the established public-definition inventory over all
15 slice-2 modules: expected **80/80**, module docstrings **15/15**.

Add a second documentation-quality audit over the six projection modules that
fails if a module/public definition has a missing or blank first docstring
line, a summary without terminal punctuation, a leading/trailing blank line,
or a legacy `Returns:` heading. Manually compare every documented parameter
and return order against its signature and body.

These rejection greps must be empty in the six modules:

```bash
rg -n "fixed at setup|cached parametric coordinates|cached basis matrix|runs? at setup time|Everything here is pure NumPy and runs at setup time|reject or down-weight|Degenerate edges are excluded|residual.*only convergence evidence|d_output_measure" \
  bsm3/core/projections/function_set_closest_distance_custom_op.py \
  bsm3/core/projections/function_set_evaluation_custom_op.py \
  bsm3/core/projections/function_set_projection_custom_op.py \
  bsm3/core/projections/orthogonality_projection_numpy.py \
  bsm3/core/projections/warm_start_candidate_projection_numpy.py \
  bsm3/core/projections/warm_start_projections.py
```

Run the unchanged gates:

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
  bsm3/core/projections/warm_start_projections.py

git diff --check -- <the nine allowlisted paths>
```

Expected tests remain **82 passed / 3 deselected** and **6 passed**. Ruff is
still expected to be unavailable in `central_geom`; attempt it, but do not
install or alter dependencies. The pinned CI step remains authoritative.

## Commit and handoff

Append a correction commit after `b99b4a4`; do not amend, reset, rebase, or
rewrite the accepted history. Use one Python-docstring correction commit and
one collaboration-doc handoff commit. Stage literal files only.

Update M1.6 to **slice 2 correction ready for Codex review**, not complete.
Append Turn 42 to `LOG.md` without rewriting Turn 40 or Turn 41. Replace this
file with a Codex checklist containing both new commit hashes, exact changed
paths, 6/6 stripped-AST proof, 80/80 coverage, the style-audit result, each
contract correction, test counts, rejection-grep result, Ruff availability,
and deviations. Hand back to Codex.
