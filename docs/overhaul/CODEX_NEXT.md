# Claude Turn 64 — review M2.1 correction and close M2 if warranted

Codex temporarily acted as implementer/planner while Claude was unavailable.
Claude now resumes the reviewer/planner role. Independently review the Turn-63
implementation; do not accept its claims from the handoff alone.

## Commits and intended range

```text
TURN63_BASE = 441320380760e75b6e153072523dc5d2afca832b
implementation = ab79087
documentation handoff = current HEAD
```

The implementation commit changes exactly:

```text
README.md
docs/index.md
docs/src/api.md
docs/src/background.md
docs/src/examples.md
docs/src/external_parameterization.md
docs/src/getting_started.md
docs/src/integrations.md
requirements-ci.txt
tests/test_documentation.py
```

The handoff commit must change exactly:

```text
docs/overhaul/PLAN.md
docs/overhaul/LOG.md
docs/overhaul/CODEX_NEXT.md
```

The original Turn-63 implementation allowlist had nine paths and prohibited
dependency-file edits. The empty-environment install gate exposed a genuine
defect, and Codex, acting as planner as well as implementer, explicitly widened
the scope by one path: `requirements-ci.txt`. Review that ruling prominently;
do not treat it as an invisible exception.

## The dependency finding to verify first

Before `ab79087`, a fresh

```bash
python -m pip install -r requirements-ci.txt
```

failed dependency resolution. `requirements-ci.txt` pinned NumPy 2.0.2 and
also installed `lsdo_b_splines_cython` at `9444ea8`; that package's metadata
pins NumPy 1.26.4. The extension has zero tracked references outside the
overhaul history, and official LFS `307ad3a` states in its release notes that
it eliminated the extension in favor of pure Python/NumPy/JAX evaluation.
`ab79087` removes only that stale requirement and corrects the adjacent LFS
comment. No production code changed.

Independently establish all three facts:

1. reproduce or otherwise inspect the NumPy resolver conflict at the base;
2. prove no retained BSM3 source/test/example imports the extension and inspect
   official LFS `307ad3a` for the removal; and
3. prove the corrected `requirements-ci.txt` installs from an empty Python
   3.12 environment before the `--no-deps` LFS and BSM3 installs.

Reject the widening if any live dependency was overlooked. If it is dead and
the clean install reproduces, accept the one-path expansion as a necessary
packaging fix discovered by the mandated gate.

## Documentation accuracy review

Read the rendered/source context and the implementation, not only the new
tests. Verify:

- installation creates a new Python 3.12 Conda environment, installs the full
  tested stack from `requirements-ci.txt`, then official LFS `307ad3a` with
  `--no-deps`, then BSM3 with `--no-deps --no-build-isolation -e .`;
- CSDL remains pinned to
  `73a9efd1033016a835779db10a9b9e81ed2254ce` and the instructions distinguish
  the tested core/developer environment from an administrator-owned DAFoam
  environment;
- the docs no longer claim PyVista can be omitted from a clean core install;
  interactive plotting remains optional, while pinned LFS imports PyVista
  eagerly;
- mesh validity is a measured outcome, not guaranteed;
- reprojection non-convergence is returned and therefore is not called exact;
- `print_summary()` is described from its actual body and does not claim to
  print load-step information;
- recorder ownership is scoped to public `GeometryModel`/`mm.run`, rather than
  all internal BSM3 drivers;
- the README labels its empty-model code as an incomplete call-shape skeleton
  and points to the actually runnable E175 script; and
- `tests/test_documentation.py` uses `ast` to read literal
  `bsm3.mesh_motion.__all__` and compares it by exact set equality with one
  delimited public inventory. Confirm the test is described only as an export
  inventory guard, not semantic API validation.

Preserve the accepted Turn-61 content: generic external coefficients are the
primary contract; the five E175 stages remain clear; component shape/patch-ID
validation occurs after STEP import; NPZ/trusted-pickle language remains
accurate; and DAFoam/MPI/VortexAD status is not overstated.

## Reported verification to reproduce

Codex reports:

| Gate | Result |
| --- | --- |
| Fresh empty environment | Python 3.12.14; install sequence completed |
| Imports | CSDL 0.0.0-a.2, LFS 1.0.0, BSM3 0.1.4 |
| Numerical stack | NumPy 2.0.2, SciPy 1.13.1, JAX 0.4.38, PyVista 0.46.5 |
| Documentation tests | **12 passed** |
| Fast E175 tests | **13 passed, 5 deselected** |
| Full non-integration suite, fresh clone | **212 passed, 9 deselected** |
| Strict Sphinx build | success, **7 source documents** |
| Default Ruff on documentation test | pass |
| Five existing workflow Ruff groups | pass: 53 / 4 / 18 / 15 / 17 paths |
| Fresh clone | docs test, strict build, import smoke pass; status empty |
| Preservation | 8/8 modified-file blob hashes and untracked inventory hash unchanged; 394 status-level untracked entries |

At minimum, run:

```bash
git diff --check 4413203..HEAD
git diff --name-status 4413203..HEAD
python -m pytest -q tests/test_documentation.py
python -m pytest -q tests/test_e175_example.py -m "not integration"
python -m ruff check tests/test_documentation.py
python -m sphinx -W --keep-going -b html docs /tmp/bsm3-docs-claude-review
```

Run the five literal workflow Ruff commands. Use a clean clone for the strict
Sphinx build, documentation test, and import smoke. The central acceptance gate
is a second clean Python 3.12 install using the documented sequence; do not
substitute the pre-populated `bsm3_py312_main` environment for that check.

Do not run the ten-minute E175 integration, DAFoam/OpenFOAM, VortexAD, or real
MPI. Do not edit production source or examples during review.

## Decision and handoff

If all findings and gates hold, accept M2.1 and M2.2 and close M2. Record the
decision in `PLAN.md` and append-only `LOG.md`. Then prepare the next prompt for
Codex, which resumes the implementer role; do not begin M3 implementation in
the review turn.

If any material claim fails, keep M2 open and issue a literal corrective
allowlist. Either way, preserve the 8 pre-existing modified files and 394
status-level untracked entries exactly and report any deviation.
