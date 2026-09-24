# Claude Turn 44 — finish M1.6 slice 2 documentation accurately

You are the **implementer**. Codex is the **planner/reviewer**. M1.6 slice 2
remains open. Turn 42 preserved all behavior and fixed much of the prose, but
the review found wrapped false claims, wrong return containers, one untouched
contradictory class docstring, and incomplete parameter documentation. Finish
the six projection modules, verify with semantic audits that do not depend on
line wrapping, append corrective commits, and hand back to Codex. Do not mark
slice 2 complete yourself.

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

Only docstrings and comments may change in the Python modules. Do not touch
the accepted workflow, preprocessing, tests, imports, annotations, signatures,
constants, decorators, or executable statements. Preserve every unrelated
dirty-tree path. Stage literal files only. Stop and report rather than widening
the allowlist or changing behavior.

## Known semantic errors to correct

Correct all instances, not just these line references:

1. `function_set_evaluation_custom_op.py:99-105` still calls the model
   setup-time state, says coordinates are fixed at construction, and says each
   point uses a cached basis row. Coordinates are supplied per call; only patch
   metadata, spaces, and row spans are cached. Evaluation/VJP run eagerly.
2. `function_set_closest_distance_custom_op.py:1086-1102` still says an edge
   is detected from coincident control points and used to “reject or
   down-weight” a candidate. The body measures sampled tessellation-boundary
   arc length and returns entries only for edges at or below the scale-aware
   threshold. The candidate builder replaces the 1-D edge solve with a
   fixed-point candidate.
3. `orthogonality_projection_numpy.py:101-105` retains a field comment saying
   `boundary_clamped` means convergence occurred only because of masking. Make
   the comment agree with the corrected attribute prose: final bound plus
   outward unmasked residual, independent of `converged`.
4. The `evaluate` methods on `FunctionSetClosestDistanceVJP`,
   `FunctionSetClosestDistanceVJPVJP`, `FunctionSetEvaluationVJP`, and
   `FunctionSetProjectionVJP` return dictionaries keyed by the differentiated
   input names, not tuples. Document the exact keys and value meanings; do not
   invent tuple order for a mapping.
5. `warm_start_projections.unsort` accepts `*arrays_sorted` and returns a
   `list[numpy.ndarray]`, not `*arrays` and not a tuple.
6. Replace “converged parametric coordinates” wherever the result can contain
   a non-converged fallback. Use “final” or “selected” and retain the separate
   `converged` evidence.
7. The candidate module's opening claim that it always keeps the closest
   converged result must acknowledge the minimum-residual fallback when no
   candidate converges.

## Complete the public callable contracts

An AST/signature audit currently finds **36 public callables and 79 signature
parameters absent from NumPy `Parameters` sections**. Bring that to zero
missing and zero extra. This is deliberately stricter than Ruff's presence
rules.

- Document every non-`self`/non-`cls` positional, keyword-only, variadic, and
  mapping-buffer parameter using its exact signature name. Grouped entries
  such as `inputs, outputs` are fine when both names are recoverable.
- For `*arrays_sorted`, retain the leading `*` in the documented name.
- Document shapes, patch/control-point ordering, tolerances, flags, and failure
  behavior where they affect use. The 30-argument
  `project_points_with_warm_start_candidates_numpy` API must explain every
  option rather than listing names without meaning.
- Add all missing fields to `EvaluationPatchInfo`'s `Attributes` section:
  `degrees`, `knot_vectors`, `coefficient_shape`, and `space_cache` as well as
  the fields already described.
- Every value-returning public callable must document its actual container and
  semantic order. Framework `compute(inputs, outputs)` callbacks return
  `None`; document the two buffers but do not add a fictitious return value.
- Preserve the trusted-local pickle warnings.

For the four VJP mappings, pin these return keys:

- closest-distance VJP: `"coefficients"`, `"points"`;
- closest-distance VJP-of-VJP: `"coefficients"`, `"points"`,
  `"d_closest_distance"`;
- evaluation VJP: `"coefficients"`, `"parametric_coordinates"`; and
- point/parametric projection VJP: `"coefficients"`, `"points"`.

## Mechanical and semantic enforcement

Record the base before editing:

```bash
TURN44_BASE=$(git rev-parse HEAD)
```

Run the established recursive stripped-docstring AST comparison over all six
Python files. Expected: **6/6 identical**. Re-run the full slice inventory:
**80/80** public definitions documented and **15/15** module docstrings.

Extend the AST documentation audit so it checks all 36 public callables:

- extract signature parameters excluding `self` and `cls`, including
  keyword-only arguments and `*args`/`**kwargs` with their prefixes;
- parse the NumPy `Parameters` section, splitting grouped names on commas;
- require exact set equality per callable; and
- print every mismatch plus aggregate totals.

Expected after the edit: **0 missing, 0 extra**. Include the audit code or an
exact reproducible command in the handoff checklist, not just the result.

Line-based grep is not authoritative: Turn 42's `reject or` / `down-weight`
wrap proved it can miss a phrase. Run a Python check over each file after
collapsing every whitespace run to one space and lowercasing. It must reject
all of these normalized phrases:

```text
setup-time numpy state
fixed at construction
cached basis row
reject or down-weight
converged only because the active set masked
tuple of csdl_alpha.variable
closest converged result
converged parametric coordinates
```

Also retain the first-line/style audit: cleaned AST docstrings must have no
missing/blank summaries, summaries without terminal punctuation, or legacy
`Returns:`/`Args:` headings. Check the raw string separately for a leading
newline (the legacy opening-blank pattern); do not misclassify indentation
before a closing triple quote as a trailing blank line.

Manually compare every changed return contract against the actual `return`
statement. In the checklist, enumerate the four VJP mapping key sets and the
`unsort` list return explicitly.

## Numerical and lint gates

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
  bsm3/core/projections/warm_start_projections.py

git diff --check -- <the nine literal allowlisted paths>
```

Expected tests remain **82 passed / 3 deselected** and **6 passed**. Ruff is
still unavailable in `central_geom`; attempt it, record that limitation, and
do not install or change dependencies. The pinned CI step remains the final
external lint gate.

## Commit and handoff

Append one Python-docstring correction commit after the current history; do
not amend, reset, rebase, or rewrite prior commits. Then make one collaboration
docs commit. Stage every path literally.

Update M1.6 to **slice 2 second correction ready for Codex review**, not
complete. Append Turn 44 to `LOG.md` without rewriting history. Replace this
file with a Codex checklist containing both new hashes, exact paths, 6/6 AST
identity, 80/80 coverage, the reproducible 36-callable parameter audit with
0/0 results, normalized-source rejection result, exact return-container audit,
test counts, Ruff status, and deviations. Hand back to Codex.
