# Codex review checklist — M1.6 slice 2, final correction (Claude Turn 46)

Claude was the implementer. Slice 2 is **ready for review, not accepted**. The
implementer did not mark it complete.

## Commits

| Hash | Contents |
| --- | --- |
| `TURN46_BASE` = `4e83fa6dc81cd4cef89ef23b2a2dc22b46624a75` | base before any Turn 46 edit |
| `fafc72f` | `Correct the slice 2 convergence, retry, and cost statements` — three projection modules, docstrings and comments only |
| *(docs commit)* | `PLAN.md`, `LOG.md`, `CODEX_NEXT.md` |

No amend, reset, rebase, or history rewrite. Every path staged literally.

## Exact paths touched

1. `bsm3/core/projections/function_set_closest_distance_custom_op.py`
2. `bsm3/core/projections/orthogonality_projection_numpy.py`
3. `bsm3/core/projections/warm_start_candidate_projection_numpy.py`
4. `docs/overhaul/PLAN.md`
5. `docs/overhaul/LOG.md`
6. `docs/overhaul/CODEX_NEXT.md`

The other three projection modules, preprocessing, workflow, and tests are
untouched. The unrelated dirty tree is preserved.

## Corrected semantic statements

### Convergence evidence

| Site | Now says |
| --- | --- |
| `FunctionSetProjectionModel.project` — `state` return and Notes | State carries `converged` as the solver's Boolean decision, with `residual` and `iterations` as diagnostics. No field is called the only evidence. Derivatives unsupported where `converged` is false. |
| `SurfaceProjectionResult.uv` | `uv` is the final iterate; `converged` records the solver decision; `residual`, `step_norm`, `iterations` are the associated diagnostics. No field is called the only evidence. |

### Retry ordering and compatibility

Documented as two sequential gates, in both the explanatory prose and the
`retry_accept_distance_factor, retry_accept_distance_atol` parameter text:

1. **`_is_candidate_better` ranks first.** Converged outranks non-converged.
   Both converged → the retry needs *strictly* smaller `dist2`, residual
   breaking only an exact distance tie. Both non-converged → smaller residual
   wins, distance as tie-break.
2. **`_is_retry_candidate_compatible` then guards.** Finite-distance cap
   `max(factor, 1.0) * selected_distance + max(atol, 0.0)`, plus the
   normal-alignment guard when the retry lands on a different patch.

The cap can admit a farther retry **only** where that retry already won on
rank — converged over non-converged, or smaller residual among two
non-converged candidates. It does **not** authorize a farther retry when both
candidates are converged; the ranking gate has already rejected it.
`boundary_clamped` is retained as a retry trigger independent of `converged`.

Verified against `warm_start_candidate_projection_numpy.py:918-943`.

### Eager cost

| Parameter | Now says |
| --- | --- |
| `warm_start_nu, warm_start_nv` | Higher eager tessellation-construction cost, paid on each call that builds the mesh; the function runs when called. |
| `num_samples` (edge map) | Samples the comparison more densely and costs more; can expose an interior mismatch a coarser grid steps over; strictness not guaranteed to vary monotonically, since the sample locations move with the count. |

## Results to verify

| Gate | Result |
| --- | --- |
| Stripped-AST identity, three changed files (working tree) | **3/3 identical** |
| Stripped-AST identity, git blobs `4e83fa6..fafc72f` | **3/3 identical** |
| Other three projection modules | byte-identical |
| Slice inventory | **80/80** defs, **15/15** modules |
| Turn-44 parameter audit, all six modules | **36 callables, 124 params, 0 missing, 0 extra** |
| Turn-44 rejection list | **0** strict, **0** punctuation-insensitive |
| Turn-46 backstop, 6 phrases | 7 pre-edit → **0** |
| First-line/NumPy-style audit | **0 violations** |
| Return-container audit | **0 mismatches over 6 containers** |
| `pytest` primary set | **82 passed, 3 deselected** |
| `pytest` derivative + n-gon gates | **6 passed** |
| `git diff --check` over the six paths | clean |
| `ruff --select D` | **unavailable** — not installed in `central_geom` |

Return containers are unchanged from Turn 44:
`FunctionSetClosestDistanceVJP.evaluate` → `"coefficients"`, `"points"`;
`FunctionSetClosestDistanceVJPVJP.evaluate` → `"coefficients"`, `"points"`,
`"d_closest_distance"`; `FunctionSetEvaluationVJP.evaluate` →
`"coefficients"`, `"parametric_coordinates"`; `FunctionSetProjectionVJP.evaluate`
→ `"coefficients"`, `"points"`; `unsort` → `list of numpy.ndarray`.

## Backstop command

```bash
python - <<'PY'
import re
P = "bsm3/core/projections/"
THREE = [P+"function_set_closest_distance_custom_op.py",
         P+"orthogonality_projection_numpy.py",
         P+"warm_start_candidate_projection_numpy.py"]
REJECT = ["only convergence evidence", "residual in state is the only",
          "even when it is slightly farther", "clamped one that is slightly closer",
          "higher setup cost", "make matching stricter"]
def norm(p):
    s = re.sub(r"\s+", " ", open(p).read()).lower()
    return re.sub(r"[^\w ]", "", s)
hits = [(f.split("/")[-1], p) for f in THREE for p in REJECT if p in norm(f)]
print(hits or "0 offending phrases")
PY
```

## Note on method

Two of the six phrases were line-wrapped in the source and returned nothing
under a plain `grep`; only whitespace collapsing found them. Consistent with
the Turn 46 ruling, the normalized check served as a backstop for known
rejected claims — it is not what established that the claims were wrong. That
came from reading `_is_candidate_better` and confirming the strict `dist2`
comparison when both candidates are converged.

## Deviations

- **Ruff not run.** Not installed in `central_geom`; dependencies left
  unchanged per the spec. Pinned CI `ruff==0.9.10` remains the authoritative
  external lint gate.
- No other deviations. Scope held to the three specified corrections; all
  correct Turn-44 documentation preserved.

## Decision requested from Codex

Accept or reject M1.6 slice 2. If accepted, the next unit is slice 3 (drivers,
MPI/DAFoam).
