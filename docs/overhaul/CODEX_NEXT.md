# Codex review checklist — M2.1 buildable user documentation

Claude was the implementer. M2.1 is **ready for Codex review and is not
accepted by the implementer**.

## Commits

| Hash | Contents |
| --- | --- |
| `TURN61_BASE` | `33ffbf70f4ff3d07a4e6dfb633e4171af9b627d4` |
| `4ca0435` | site, configuration, CI step, structural test |
| *(docs commit)* | `PLAN.md`, `LOG.md`, `CODEX_NEXT.md` |

## Changed paths (24, all allowlisted)

```text
M  .github/workflows/actions.yml
M  .readthedocs.yaml
M  README.md
M  docs/Makefile
M  docs/README.md
M  docs/conf.py
M  docs/index.md
A  docs/requirements.txt
M  docs/src/api.md
M  docs/src/background.md
M  docs/src/examples.md
A  docs/src/external_parameterization.md
M  docs/src/getting_started.md
A  docs/src/integrations.md
A  tests/test_documentation.py
D  docs/src/custom_1.md
D  docs/src/custom_2.md
D  docs/src/examples/advanced.md
D  docs/src/examples/basic.md
D  docs/src/references.bib
D  docs/src/tutorials.md
D  docs/src/tutorials/advanced.md
D  docs/src/tutorials/basic.md
D  docs/src/welcome.md
```

## Verification

| # | Gate | Result |
| --- | --- | --- |
| 1 | `git diff --check`, pre-commit and `TURN61_BASE..HEAD` | both empty |
| 2 | Template identity / quartic grep outside `docs/overhaul` | **clean** (3 files inside `docs/overhaul` retain them, as expected) |
| 3 | Disposable `/tmp` venv: Python **3.12.14**, Sphinx **9.1.0**; `sphinx -W --keep-going -b html docs` | **build succeeded**, 9 pages |
| 4 | `pytest -q tests/test_documentation.py` | **10 passed** |
| 5 | Fast E175 example tests, `-m "not integration"` (marker read from `pytest.ini`) | **13 passed, 5 deselected** |
| 6 | Default Ruff on `docs/conf.py`, `tests/test_documentation.py`; five literal workflow Ruff commands | all **All checks passed** |
| 7 | Fresh clone of `4ca0435`: docs build + documentation test | **build succeeded**, **10 passed**, clone status empty |
| 8 | Preservation | 8/8 pre-existing modified files byte-identical; 394/394 untracked intact; no build output in the repository |

## Key design decision: no autodoc

The API page is hand-written and verified against source. Autodoc would need
the entire validated geometry stack installed in the docs environment and on
Read the Docs purely to render a reference. Hand-writing keeps
`docs/requirements.txt` to four pinned packages, keeps the build hermetic, and
satisfies the "no wall of private modules" requirement directly.

`conf.py` reads `bsm3.__version__` from `bsm3/__init__.py` with a regex, so the
real version appears without importing the package.
`tests/test_documentation.py` guards both directions: every name in
`bsm3.mesh_motion.__all__` must be documented, no `mm.` name may be promised
that the namespace does not export, and the version regex must still match.

## Facts resolved from source

- `run` is keyword-only and never starts or stops the recorder; the caller owns
  it and the result carries it back.
- `add_component` is the general boundary. `add_lifting_surface` and `add_body`
  build their own private records rather than calling through it, so they are
  documented as optional E175-oriented conveniences.
- Coefficient shapes and patch IDs are validated **after** the STEP component
  is imported, not at the `add_component` call — documented, because a caller
  would otherwise expect declaration-time errors.
- `PolygonRegularization` is inactive on a triangle-only mesh because triangles
  carry no affine hourglass mode, which is why the quad panel is a pure path
  substitution.
- Tracked assets are the STEP body, R1 triangle wall, quad-dominant panel, and
  `wall_surface.npz`. The R4 wall and volume meshes are untracked and the docs
  do not imply otherwise.

## Honest-status claims to spot-check

- No PyPI availability is claimed for BSM3 or either pinned dependency.
- No hosted Read the Docs deployment is claimed; `.readthedocs.yaml` is
  configured and ready.
- DAFoam/OpenFOAM and real MPI are stated as optional and absent from the
  standard suite; the rank-0 construction path is described as tested **without
  implying a real solve**.
- VortexAD is deferred and the untracked panel driver explicitly unsupported.
- Safe `allow_pickle=False` NPZ is the asset format; the two trusted-pickle
  entry points are named as opt-in, not normalized as a default.

## Deviations

`docs/src/images/` and `docs/make.bat` are outside the allowlist and were left
untouched. The images are now unreferenced by any page and `make.bat` is
generic Sphinx boilerplate carrying no template identity; neither affects the
build or the identity grep. You may want them removed under a later allowlist.

No other deviation: nothing outside the implementation allowlist changed, no
production Python, example, packaging metadata, or other test was touched, and
no library change proved necessary.

## Decision requested

Review M2.1 and open M2.2, the independent accuracy and clean-clone review.
