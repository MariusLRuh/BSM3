# Claude review — Turn 72: GAMMA identity and HTML-only alpha

Codex implemented the corrected Turn-71 prompt. Review independently; do not
accept Codex's report on trust and do not edit production code during the
initial audit. If the implementation is sound, record acceptance in
`docs/overhaul/PLAN.md` and `docs/overhaul/LOG.md`, then issue the next Codex
prompt in this file. If it is not sound, issue one narrow corrective prompt.

## User ruling that supersedes one line of the prompt

The user corrected the expansion during implementation:

```text
GAMMA = Geometry-Aware Mesh Movement Analysis
```

This supersedes *Geometry Adaptation for Multidisciplinary Modeling and
Analysis* wherever Turn 70 or the corrected Turn-71 prompt treated that phrase
as the current ruling. Historical prose may remain with an explicit correction;
the supported product surface must use the user's corrected expansion.

All other identifiers remain:

```text
Display name:        GAMMA
Repository slug:     GAMMA-MDO
Python distribution: gamma-mdo
Python import:       bsm3 (unchanged)
Read the Docs slug:  gamma-mdo
Version:             0.2.0a1
Hosted formats:      HTML only
```

## Commits and scope

```text
Corrected prompt:       a7e0434
Implementation commit: d04dc8f
```

The implementation commit must contain exactly these 16 paths:

```text
.readthedocs.yaml
HPC_DAFOAM_INSTALL.md
README.md
bsm3/__init__.py
docs/README.md
docs/conf.py
docs/index.md
docs/src/api.md
docs/src/background.md
docs/src/external_parameterization.md
docs/src/getting_started.md
docs/src/integrations.md
requirements-ci.txt
requirements.txt
setup.py
tests/test_documentation.py
```

Check that `bsm3/__init__.py` changes only the version line and that
`tests/test_documentation.py` changes only the four authorized identity/guard
locations. No `gamma_mdo` package, alias, namespace move, tag, push,
publication, repository rename, or hosted-project mutation is allowed.

## Review questions

1. Does every supported surface present **Geometry-Aware Mesh Movement
   Analysis**, while the distribution is plainly `gamma-mdo` and imports stay
   plainly `bsm3`?
2. Does `setup.py` package `bsm3` under distribution `gamma-mdo`, point at
   `GAMMA-MDO`, retain `install_requires=[]`, and derive version `0.2.0a1` from
   source?
3. Does `.readthedocs.yaml` request only the default HTML build, retain
   warnings-as-errors and the docs-only install, and avoid claiming PDF or
   HTMLZIP was validated?
4. Does the negative guard now reject the equivalent GAMMA recorder-ownership
   overclaim, rather than silently retiring that protection?
5. Is the line-131 wording correctly treated as an import-namespace statement
   (`bsm3`) rather than current display branding?
6. Is this packaging proof sufficient: the wheel installs into a disposable
   Python 3.12 venv layered on the validated stack and imports from `/tmp`,
   while an empty venv predictably lacks NumPy because the deliberate contract
   keeps `install_requires=[]`? If not, identify a test-only method that does
   not change the dependency policy.

## Reproduce these checks

```bash
git diff --name-only a7e0434 d04dc8f
git diff --check a7e0434 d04dc8f

git grep -n "BSM3" -- setup.py docs/conf.py README.md docs/README.md \
  docs/index.md docs/src/ .readthedocs.yaml
git grep -n 'name="bsm3"\|name=.bsm3.' -- setup.py
git grep -lE "import bsm3|from bsm3" -- '*.py' | wc -l

python -m pytest -q tests -m "not integration"
python -m pytest -q tests/test_boundary_surface_movement.py
python -m pytest -q tests/test_e175_example.py -m "not integration"
python -m pytest -q tests/test_derivative_gate.py \
  tests/test_ngon_affine_operator.py tests/test_ngon_affine_load_step.py
python -m pytest -q tests/test_e175_example.py -k \
  "test_triangle_wall_at_full_deformation_scale or test_quad_panel_introduces_no_new_inverted_elements"
python -m pytest -q tests/test_documentation.py
python -m sphinx -W --keep-going -b html docs /tmp/gamma-turn72-review-html
```

Expected results are 228 passed / 9 deselected, 45 passed, 16 passed / 5
deselected, exactly 6 passed, both full E175 guards passed, and 12 docs tests.
Run the five literal Ruff groups in `.github/workflows/actions.yml` and default
Ruff on the four changed Python files.

Independently build the wheel and verify its filename begins
`gamma_mdo-0.2.0a1`, `pip show gamma-mdo` reports `0.2.0a1`, and an out-of-tree
`import bsm3` reports the same version. Also clone `d04dc8f`, build the docs
strictly with the pinned docs requirements, run the documentation tests, and
confirm the clone stays clean.

## Preservation proof

After the implementation commit, before collaboration-document edits, Codex
recorded:

```text
modified tracked files: 8
untracked entries:       393
dirty diff SHA-256:      981318561a10dff8e9d723540902b6d2560875b29656a0b59f0803cbff116177
untracked-list SHA-256:  c38fd93dc32ecf7f927fc612c1079bd9786c19f6c1f74b4f8e69d28aaa44da60
import-namespace files:  53 before / 53 after
```

Recompute them after the collaboration-doc commit; the two documentation files
being intentionally edited will change the working-tree count only until that
commit is made.

## External actions remain outside agent authority

Do not rename the GitHub repository, create an RTD project/webhook, create or
push `v0.2.0a1`, or reserve/publish `gamma-mdo` on PyPI. Restate them as the
user's next external checklist if this turn is accepted. A 404 on PyPI or RTD
means apparently unoccupied, not reserved; the unauthenticated GitHub result is
inconclusive for the user's private namespace.

M4.2 remains preserved verbatim at
`git show 38cd0bf:docs/overhaul/CODEX_NEXT.md`. Do not start it during this
review. Mark M5.1/M6.1 accepted only after independent reproduction; otherwise
leave them open and hand Codex the smallest satisfiable correction.
