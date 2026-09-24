# Codex review checklist — M1.6 slice 2, second correction (Claude Turn 44)

Claude was the implementer. Slice 2 is **ready for review, not accepted**. The
implementer did not mark it complete.

## Commits

| Hash | Contents |
| --- | --- |
| `TURN44_BASE` = `10fb4c40920fb3bd1dbcea94b30515c59f2567cf` | base before any Turn 44 edit |
| `c18e282` | `Complete the slice 2 projection contracts` — the six projection modules, docstrings and comments only |
| *(docs commit)* | `PLAN.md`, `LOG.md`, `CODEX_NEXT.md` |

No amend, reset, rebase, or history rewrite. Every path staged literally.

## Exact paths touched

Python (documentation and comments only):

1. `bsm3/core/projections/function_set_closest_distance_custom_op.py`
2. `bsm3/core/projections/function_set_evaluation_custom_op.py`
3. `bsm3/core/projections/function_set_projection_custom_op.py`
4. `bsm3/core/projections/orthogonality_projection_numpy.py`
5. `bsm3/core/projections/warm_start_candidate_projection_numpy.py`
6. `bsm3/core/projections/warm_start_projections.py`

Collaboration docs: `docs/overhaul/PLAN.md`, `docs/overhaul/LOG.md`,
`docs/overhaul/CODEX_NEXT.md`.

Nothing outside the nine-path allowlist changed. `git diff --name-only
10fb4c4 -- .` lists exactly these plus the pre-existing dirty tree, which was
preserved untouched.

## Results to verify

| Gate | Result |
| --- | --- |
| Stripped-docstring AST identity (working tree) | **6/6 identical** |
| Stripped-docstring AST identity (git blobs `10fb4c4..c18e282`) | **6/6 identical** |
| Slice inventory | **80/80** public defs, **15/15** module docstrings |
| 36-callable parameter audit | **36 callables, 124 params, 0 missing, 0 extra** (was 79 missing, 1 extra) |
| Normalized rejection, 8 phrases | **0 present** |
| Rejection, punctuation-insensitive variant | **0 present** |
| First-line/style audit | **0 violations** |
| Return-container audit | **0 mismatches over 13 returns** |
| `pytest` primary set | **82 passed, 3 deselected** |
| `pytest` derivative + n-gon gates | **6 passed** |
| `git diff --check` over the nine paths | clean |
| `ruff --select D` | **unavailable** — not installed in `central_geom` |

## Reproducible parameter audit

Write `audit44.py` to `/tmp`, then run the driver below from the repo root.

```python
# /tmp/audit44.py
import ast, re
P = "bsm3/core/projections/"
SIX = [P+"function_set_closest_distance_custom_op.py", P+"function_set_evaluation_custom_op.py",
       P+"function_set_projection_custom_op.py", P+"orthogonality_projection_numpy.py",
       P+"warm_start_candidate_projection_numpy.py", P+"warm_start_projections.py"]

def public_callables(tree):
    out = []
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and not n.name.startswith("_"):
            out.append((n.name, n))
        elif isinstance(n, ast.ClassDef) and not n.name.startswith("_"):
            for m in n.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and not m.name.startswith("_"):
                    out.append((f"{n.name}.{m.name}", m))
    return out

def sig_params(node):
    a = node.args; names = []
    for x in list(a.posonlyargs) + list(a.args):
        if x.arg not in ("self", "cls"): names.append(x.arg)
    if a.vararg: names.append("*" + a.vararg.arg)
    for x in a.kwonlyargs: names.append(x.arg)
    if a.kwarg: names.append("**" + a.kwarg.arg)
    return names

def doc_params(doc):
    if not doc: return []
    lines = doc.splitlines(); out = []; i = 0
    while i < len(lines):
        if lines[i].strip() == "Parameters" and i+1 < len(lines) and set(lines[i+1].strip()) == {"-"}:
            i += 2; base = None
            while i < len(lines):
                ln = lines[i]
                if ln.strip() and set(ln.strip()) == {"-"}: break
                if ln.strip() in ("Returns","Raises","Notes","Attributes","Examples","Yields"): break
                ind = len(ln) - len(ln.lstrip())
                if ln.strip() and (base is None or ind <= base):
                    base = ind if base is None else base
                    for part in ln.strip().split(":")[0].strip().split(","):
                        p = part.strip()
                        if p and re.match(r"^\*{0,2}[A-Za-z_][A-Za-z0-9_]*$", p): out.append(p)
                i += 1
            break
        i += 1
    return out

REJECT = ["setup-time numpy state", "fixed at construction", "cached basis row",
          "reject or down-weight", "converged only because the active set masked",
          "tuple of csdl_alpha.variable", "closest converged result",
          "converged parametric coordinates"]

def normalized(path):
    return re.sub(r"\s+", " ", open(path).read()).lower()
```

```bash
python - <<'PY'
import sys, ast, re; sys.path.insert(0, "/tmp")
from audit44 import SIX, public_callables, sig_params, doc_params, REJECT, normalized
nc = tot = miss = extra = 0
for f in SIX:
    for n, nd in public_callables(ast.parse(open(f).read())):
        nc += 1; sp = sig_params(nd); dp = doc_params(ast.get_docstring(nd))
        m = [x for x in sp if x not in dp]; e = [x for x in dp if x not in sp]
        tot += len(sp); miss += len(m); extra += len(e)
        if m or e: print(f"MISMATCH {f.split('/')[-1]}:{n} missing={m} extra={e}")
print(f"{nc} callables, {tot} params, MISSING {miss}, EXTRA {extra}")
strict = sum(1 for f in SIX for p in REJECT if p in normalized(f))
loose  = sum(1 for f in SIX for p in REJECT if p in re.sub(r"[\"'`*_]", "", normalized(f)))
print(f"rejection: {strict} strict, {loose} punctuation-insensitive")
PY
```

Expected: `36 callables, 124 params, MISSING 0, EXTRA 0` and
`rejection: 0 strict, 0 punctuation-insensitive`.

## Return containers — audited against the actual `return` statements

Four VJP `evaluate` methods return **dictionaries keyed by the differentiated
input name**, documented as mappings with no invented tuple order:

| Callable | Keys in the actual `return` |
| --- | --- |
| `FunctionSetClosestDistanceVJP.evaluate` | `"coefficients"`, `"points"` |
| `FunctionSetClosestDistanceVJPVJP.evaluate` | `"coefficients"`, `"points"`, `"d_closest_distance"` |
| `FunctionSetEvaluationVJP.evaluate` | `"coefficients"`, `"parametric_coordinates"` |
| `FunctionSetProjectionVJP.evaluate` | `"coefficients"`, `"points"` |

`warm_start_projections.unsort(inv_order, *arrays_sorted)` returns a list
comprehension, documented as `list of numpy.ndarray` — one entry per array
passed in, in the same order, always a list even for a single array. The
documented parameter name retains its `*` prefix.

All six `compute(inputs, outputs)` callbacks have no value-returning `return`;
each documents both buffers and `Returns: None`.

## Seven semantic corrections to spot-check

1. `FunctionSetEvaluationModel` — evaluator over caller-supplied coordinates;
   construction caches metadata, spaces and row spans only; stencils built per
   call; linear in coefficients for fixed coordinates, nonlinear in the
   coordinates, hence both cotangents.
2. `build_degenerate_edge_map` — sampled tessellation-boundary arc length
   against `max(atol, rtol * bbox_diagonal)`; entries only at or below the
   threshold; membership test driving fixed-point substitution, not rejection
   or reweighting.
3. `boundary_clamped` field comment — final parameter on a bound with an
   outward unmasked residual, computed before the active set applies,
   independent of `converged`.
4. The four VJP mappings above.
5. `unsort` — `*arrays_sorted`, `list[numpy.ndarray]`.
6. "Final"/"selected" coordinates wherever a non-converged fallback is
   possible, with `converged` retained as separate evidence.
7. Candidate module opening — ranking plus the minimum-residual fallback, no
   claim of always keeping the closest converged result.

## Finding: the specified rejection gate has a hole

The Turn 44 phrase list is normalized for **whitespace and case only**. The
actual defective comment at `orthogonality_projection_numpy.py:101` read

```
# True for points that "converged" only because the active set masked an
```

The quotes around `converged` mean the normalized phrase
`converged only because the active set masked` scored **zero hits even before
the fix** — the specified gate would have reported clean while the defect
stood. The comment is now corrected, and a punctuation-insensitive variant
(stripping `" ' ` * _` before matching) also reports zero across all six
files.

Recommend the punctuation-insensitive form becomes the standing check. This is
the second consecutive turn in which a purely textual gate was defeated by
formatting rather than by content — Turn 42's line-wrapped `reject or
down-weight` was the first.

## Deviations

- **Ruff not run.** Not installed in `central_geom`; dependencies were left
  unchanged per the spec. Pinned CI `ruff==0.9.10` remains the authoritative
  external lint gate for these six files.
- **One change beyond the seven named errors.**
  `FunctionSetClosestDistanceOperation.compute` documented its buffers but,
  unlike the other five `compute` callbacks, had no `Returns` section.
  `Returns: None` was added for consistency with the spec's instruction to
  document the two buffers without inventing a return value. Documentation
  only; AST identity still 6/6.

## Decision requested from Codex

Accept or reject M1.6 slice 2. If accepted, the next unit is slice 3 (drivers,
MPI/DAFoam). Please also rule on whether the punctuation-insensitive rejection
check replaces the whitespace-only form in future turns.
