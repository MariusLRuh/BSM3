# Codex review checklist — M1.6 slice 3 (drivers, volume motion, MPI)

Claude was the implementer. Slice 3 is **ready for review and is not accepted
by the implementer**. M1.6 is not marked complete.

## Commits

| Hash | Contents |
| --- | --- |
| `SLICE3_BASE` = `29d53a8` | base recorded before editing |
| `cdcba68` | 16 Python paths + `.github/workflows/actions.yml` |
| *(docs commit)* | `PLAN.md`, `LOG.md`, `CODEX_NEXT.md` |

No amend, reset, rebase, or rewrite. Every path staged literally.

`bsm3/core/boundary_surface_movement/__init__.py` already had a module
docstring and has no public definitions, so it is the one slice path that
needed no edit. That is why the implementation commit holds 16 Python files,
not 17.

## Baseline confirmation

The historical Turn-48 inventory reproduces **exactly** at `29d53a8`, so no
target was adjusted: 8,763 LOC; 15/17 module docstrings; 108/167 definitions
documented (59 missing, matching the historical table file by file and name by
name); 132 callables with 293 parameters at 293 missing / 0 extra; 22
dataclasses with 148 fields at 148 missing / 0 extra.

## Results

| Gate | Before | After |
| --- | --- | --- |
| Module docstrings | 15/17 | **17/17** |
| Public definitions documented | 108/167 | **167/167** |
| `Parameters` coverage | 293 missing / 0 extra | **0 / 0** |
| `Attributes` coverage | 148 missing / 0 extra | **0 / 0** |
| Stripped-AST identity, working tree | — | **17/17** |
| Stripped-AST identity, committed blobs | — | **17/17** |
| `ruff --select D`, exact 17 paths | 161 errors | **All checks passed** |
| `pytest` focused set | 89 passed | **89 passed** |
| `pytest` derivative + n-gon guards | 6 passed | **6 passed** |
| Workflow YAML | — | parses; new step lists 17 paths, each once |
| `git diff --check` over 21 paths | — | clean |

## Reproducible audit

Write `audit_slice3.py` to `/tmp/s3` with `PATHS`, `public_defs`, `sig_params`,
`doc_params`, `doc_attrs`, `is_dataclass`, `local_fields` as committed in
`cdcba68`'s sibling tooling, then run from the repo root:

```bash
python - <<'PY'
import sys, ast; sys.path.insert(0,"/tmp/s3")
from audit_slice3 import *
mods=defs=docd=calls=params=pm=pe=dcs=flds=am=ae=0
for p in PATHS:
    t=ast.parse(open(p).read())
    if ast.get_docstring(t): mods+=1
    for n,nd,k in public_defs(t):
        defs+=1
        if ast.get_docstring(nd): docd+=1
        if k in ("func","method"):
            calls+=1; sp=sig_params(nd); dp=doc_params(ast.get_docstring(nd))
            params+=len(sp)
            pm+=len([x for x in sp if x not in dp]); pe+=len([x for x in dp if x not in sp])
    for n in t.body:
        if isinstance(n,ast.ClassDef) and not n.name.startswith("_") and is_dataclass(n):
            dcs+=1; lf=local_fields(n); da=doc_attrs(ast.get_docstring(n))
            flds+=len(lf)
            am+=len([x for x in lf if x not in da]); ae+=len([x for x in da if x not in lf])
print(f"modules {mods}/17 | defs {docd}/{defs} | callables {calls} params {params}"
      f" -> {pm} missing/{pe} extra | dataclasses {dcs} fields {flds} -> {am} missing/{ae} extra")
PY
```

Expected: `modules 17/17 | defs 167/167 | callables 132 params 293 -> 0
missing/0 extra | dataclasses 22 fields 148 -> 0 missing/0 extra`.

Stripped-AST identity against the base, for both working tree and committed
blobs:

```bash
python - <<'PY'
import ast, subprocess, sys; sys.path.insert(0,"/tmp/s3")
from audit_slice3 import PATHS
def strip(t):
    for n in ast.walk(t):
        if isinstance(n,(ast.Module,ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef)):
            b=n.body
            if b and isinstance(b[0],ast.Expr) and isinstance(b[0].value,ast.Constant) \
               and isinstance(b[0].value.value,str): n.body=b[1:] or [ast.Pass()]
    return t
blob=lambda r,p: subprocess.run(["git","show",f"{r}:{p}"],capture_output=True,text=True,check=True).stdout
ok=sum(ast.dump(strip(ast.parse(blob("29d53a8",p))),include_attributes=False)
       == ast.dump(strip(ast.parse(blob("HEAD",p))),include_attributes=False) for p in PATHS)
print(f"{ok}/{len(PATHS)} identical")
PY
```

## Custom-operation return containers

Resolved by walking each `evaluate` body to the binding its returned name
refers to, not from prose.

| Callable | Body | Documented as |
| --- | --- | --- |
| `DAFoamAnalysisOperation.evaluate` | dict comprehension keyed by `name` over `function_names` | dict keyed by configured aerodynamic function name |
| `DAFoamAnalysisVJP.evaluate` | dict populated at key `name` over `inputs` | dict keyed by primal input name |
| `GeometryVolumeOperation.evaluate` | single `self.create_output(...)` call | one CSDL volume-coordinate variable |
| `GeometryVolumeVJP.evaluate` | dict populated at key `name` over `specs` | dict keyed by design-variable name |

All four `compute(inputs, outputs)` callbacks contain **no** value-returning
`return`; each documents both buffers and `Returns: None`, with no invented
value.

## Deviation requiring a ruling: 69 pre-existing D202 removals

After every docstring was written, 79 `D` errors remained: 4 `D102` and 4
`D105` on `__call__`/`__post_init__` methods the audit convention excludes, 2
`D401`, and **69 `D202`** ("no blank lines allowed after function docstring").

The first ten are docstring content and were fixed as such. The 69 `D202` are
**entirely pre-existing** — count and per-file distribution identical to
`29d53a8`, none introduced here. Fixing one deletes a blank line between a
docstring and the first body statement, which is body whitespace rather than
docstring text, so it sits at the edge of "docstrings and comments only".

I removed them with `ruff check --select D202 --fix`, so the edit is mechanical,
on the grounds that `D202` is a pydocstyle docstring rule, the change is
AST-neutral, and the alternative leaves a mandated gate failing. **Stripped-AST
identity still reports 17/17 in both the working tree and the committed
blobs.** Please rule on whether this was in scope; it is trivially revertible.

## Blocking finding: the existing CI documentation steps already fail

Adding this step does **not** make CI green. With `ruff 0.9.10` in
`bsm3_py312_main` against the repo's `ruff.toml`:

| CI step | `ruff --select D` |
| --- | --- |
| Numpydoc checks for the M0 public surface | All checks passed |
| Numpydoc checks for the surface-motion core | **123 errors** |
| Numpydoc checks for projection and preprocessing | **48 errors** |
| Numpydoc checks for drivers, volume motion, and MPI (new) | All checks passed |

Those files are outside this slice's allowlist, so they were not touched.

This also does not reproduce the M1.9 review line "Ruff passes all five
migrated projection modules": under `--select D` those five report **19
errors**. They do pass the repo's default `ruff check`, whose `ruff.toml`
selects only `E9,F63,F7,F82`, which is the most likely reading of that claim.
Please confirm which command was run, and decide how the two failing steps are
brought green.

## Preservation

- Pre-existing dirty tree intact: 402 entries before, 419 after, the difference
  being exactly the 16 edited Python files and the workflow. No pre-existing
  entry removed or altered.
- `bsm3/core/boundary_surface_movement/e175_panel_opt.py` remains untracked and
  unmodified, as do the two deferred mesh-generation candidates.
- Accepted M1.9 baseline untouched: Python 3.12 in the workflow,
  `jax[cpu]==0.4.38`, official CSDL_alpha `73a9efd`, official LFS `307ad3a`
  installed with `--no-deps`, and canonical LFS factory imports in the five
  projection modules.

## Decision requested

Accept or reject M1.6 slice 3, and rule on the `D202` deviation and on how the
two pre-existing failing CI documentation steps are handled. M1.6 is not
marked complete.
