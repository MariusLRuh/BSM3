# Review prompt for Claude — Turn 31 (audit M1.7a)

Paste this entire prompt into Claude at the repository root.

---

Review Codex Turn 30 and commit `476b10d` against the Turn-30 M1.7a contract
recorded in `docs/overhaul/LOG.md` and `docs/overhaul/PLAN.md`. This is an
independent audit, not an implementation turn.

## Scope and allowlist

The implementation commit must contain exactly:

```
examples/e175_surface_deformation.py
tests/test_e175_example.py
```

For your review turn, you may edit only:

```
docs/overhaul/PLAN.md
docs/overhaul/LOG.md
docs/overhaul/CODEX_NEXT.md
```

Do not edit the example, tests, `bsm3/`, CI, or any pre-existing dirty file.
Claim `## Turn 31` by appending to `LOG.md` before the audit, then close it with
an explicit ACCEPTED or REJECTED ruling and the evidence.

## Implementation claims to verify independently

- The example runs as a direct script from a genuine clone using tracked assets
  only, with no editable source-tree assumption.
- It uses the generalized API and contains none of the retired E175-prefixed
  API names.
- All five pipeline stages are explained in the module docstring and every
  public function/class has a genuine numpydoc section.
- Tri is the default; volume and visualization are off; the setup cache is
  outside the repository.
- `--mesh quad` selects the tracked quad-dominant panel and a nonzero
  `ngon_affine.weight`.
- The integration test executes the tri path and checks stable vertex count,
  the expected public result fields, zero folds, and zero inversions. Its
  600-second timeout is justified by the measured 105.8-second cold run and
  the turn's ten-minute hard stop.
- No library change was needed and no file under `bsm3/` was changed by
  `476b10d`.

Codex reports: cold tri **105.8 s** in the working tree and **100.7 s** in the
clone, cached tri **55.5 s**, each with 16,400 vertices / 32,522 cells and zero
folds/inversions/degeneracies. The quad run was **66.3 s**, used
`ngon_affine.weight=0.3`, and had zero normal-flip folds. It reported 116
orientation inversions both before and after deformation; determine whether
the evidence supports Codex's statement that these belong to the curated
input rather than being introduced by motion. Do not silently strengthen
M1.7a's acceptance criterion: Turn 30 required zero inversions for the tri
smoke test, while final M1.7 still owns the broader “quad clean” acceptance.

Peak memory is intentionally unreported because the sandbox denied the
post-run macOS `sysctl` query. That is not by itself a failure because Task 3
made peak memory optional.

## Mechanical audit

Run at least:

```bash
git show --stat --oneline 476b10d
git diff-tree --no-commit-id --name-only -r 476b10d

grep -nE "E175ModelFiles|E175PipelineConfig|E175GeometryVariables|E175MeshMotionResult|build_e175_mesh_motion_model" examples/e175_surface_deformation.py
grep -nE "ModelFiles|PipelineConfig|ComponentSpec|IntersectionSpec|GeometryParameterization|build_mesh_motion_model" examples/e175_surface_deformation.py

python - <<'PY'
import ast
from pathlib import Path
t = ast.parse(Path("examples/e175_surface_deformation.py").read_text())
assert ast.get_docstring(t)
public = [n for n in ast.walk(t) if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and not n.name.startswith("_")]
sectioned = [n for n in public if (ast.get_docstring(n) or "") and ("\n---" in ast.get_docstring(n) or "Parameters\n" in ast.get_docstring(n) or "Returns\n" in ast.get_docstring(n))]
print(f"example public defs {len(public)}; numpydoc-sectioned {len(sectioned)}")
assert len(sectioned) == len(public)
PY

python -m pytest -q tests/test_derivative_gate.py
python -m pytest -q tests/test_ngon_affine_operator.py tests/test_ngon_affine_load_step.py
python -m pytest -q tests/test_e175_example.py
python -m pytest -q tests
```

Use the validated `central_geom` environment. Review the code itself for API
clarity, truthful documentation, engineering choices, and whether the test is
a meaningful end-to-end guard rather than merely checking configuration.

For clean-clone verification, use a fresh explicit directory (or safely remove
the old verified target first), then run:

```bash
git clone --no-hardlinks --branch production-ready-overhaul \
  "file:///Users/mariusruh/Documents/Research/nasa_uli/mesh_movement/packages/BSM3" \
  /tmp/bsm3-m17a-claude-review
cd /tmp/bsm3-m17a-claude-review
git status --porcelain
PYTHONPATH=/tmp/bsm3-m17a-claude-review python examples/e175_surface_deformation.py
PYTHONPATH=/tmp/bsm3-m17a-claude-review python -m pytest -q tests
```

Expected clone count is **159 passed / 1 skipped**. The existing full-suite CI
step already collects the new test, so leaving `actions.yml` unchanged is the
expected result.

## Ruling and next prompt

If M1.7a is accepted, mark it accepted in `PLAN.md`, record the measured audit
evidence in Turn 31, and replace this file with the next concrete Codex prompt:
**M1.6 slice 2 (projections + preprocessing)**. Preserve the remaining order
M1.6 slice 2, M1.6 slice 3, M1.8, then full M1.7 acceptance.

If rejected, record the exact defect and replace this file with the smallest
corrective Codex prompt, including a literal path allowlist and stop rule. Do
not fix implementation files yourself and do not widen scope silently.
