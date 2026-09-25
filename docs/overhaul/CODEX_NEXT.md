# Claude Turn 61 — implement M2.1: buildable user documentation

Codex has accepted M1.7 and M1. The next milestone is M2, a buildable,
user-facing documentation site. You are the implementer for this turn; Codex
will review and accept or reject it. Do not self-accept the work.

Read `docs/overhaul/PLAN.md` and the Turn 60 entry in
`docs/overhaul/LOG.md` before editing. Treat the current `HEAD` as
`TURN61_BASE` and record its full hash. Preserve the user's dirty working tree:
8 pre-existing modified files and 394 pre-existing untracked entries. Do not
adopt, delete, format, or otherwise modify any of them.

## Objective

Replace the inherited `lsdo_project_template` documentation with a concise,
accurate BSM3 Sphinx/Read the Docs site. It must build from a fresh Python 3.12
environment with warnings treated as errors and must explain the real public
workflow rather than exposing internal helper mechanics.

This is M2.1 only. M2.2 is the independent accuracy and clean-clone review.

## Literal implementation allowlist

Only these paths may change in the implementation commit. Paths marked
"optional" may be edited or deleted only if useful; new paths are marked
"new".

```text
.github/workflows/actions.yml
.readthedocs.yaml
README.md
docs/Makefile                                      (optional)
docs/README.md
docs/conf.py
docs/index.md
docs/requirements.txt                              (new)
docs/src/api.md
docs/src/background.md
docs/src/custom_1.md                               (optional; may delete)
docs/src/custom_2.md                               (optional; may delete)
docs/src/examples.md
docs/src/examples/advanced.md                      (optional; may delete)
docs/src/examples/basic.md                         (optional; may delete)
docs/src/external_parameterization.md              (new)
docs/src/getting_started.md
docs/src/integrations.md                            (new)
docs/src/references.bib                            (optional; may delete)
docs/src/tutorials.md                              (optional; may delete)
docs/src/tutorials/advanced.md                     (optional; may delete)
docs/src/tutorials/basic.md                        (optional; may delete)
docs/src/welcome.md                                (optional; may delete)
tests/test_documentation.py                         (new)
```

The second commit may change exactly:

```text
docs/overhaul/PLAN.md
docs/overhaul/LOG.md
docs/overhaul/CODEX_NEXT.md
```

Do not change production Python, examples, packaging metadata, assets, or any
other test. If accurate/buildable documentation requires a library or example
change, stop and report the exact dependency instead of widening the allowlist.

## Required design and content

### 1. Replace the template; do not layer over it

- `docs/conf.py`, `docs/index.md`, and the retained pages must describe BSM3,
  not `lsdo_project_template`, quartic examples, or generic placeholders.
- Delete obsolete template pages from the optional paths rather than retaining
  an empty or misleading navigation tree.
- Keep the site small and navigable. Prefer a landing page plus Installation,
  E175 example, External parameterization, API, Background, and Integrations.
- Use BSM3's actual version without importing the package during configuration
  if that can be done robustly.

### 2. Installation must reproduce the validated compatibility stack

Document Python 3.12 and the exact validated dependency revisions:

```text
CSDL_alpha: 73a9efd1033016a835779db10a9b9e81ed2254ce
lsdo_function_spaces: 307ad3aabfff31c6fb44ddf51bc0dcc41a60c420
```

The LFS install must retain `--no-deps`. The BSM3 editable install must retain
`--no-deps --no-build-isolation`. Distinguish the tested core/developer setup
from a user's pre-existing DAFoam/OpenFOAM environment. Do not claim that BSM3
or either pinned dependency is available from PyPI, and do not claim hosted
Read the Docs deployment before one exists.

Explain that geometry/case paths are local user inputs. Identify which example
assets are tracked and do not imply that the E208 or private CFD case exists.

### 3. Document the real five-stage E175 workflow

Base the quickstart on the tracked `examples/e175_surface_deformation.py` and
verify every public name and argument against the implementation. Preserve the
example's intended usability:

1. choose files and high-level settings in `main`;
2. declare or supply geometry coefficients;
3. register components and free regions;
4. run the differentiable surface-motion pipeline;
5. inspect/export the result and quality diagnostics.

There must be no CLI-oriented presentation, no `mesh_kind` option, no public
discussion of private helpers such as `_wing_coefficients`, `_surface_cells`,
or `_polygonal_normals`, and no giant constructor listing. Show the triangle
default and explain the quad-panel path as a filename/path substitution where
appropriate. State the recorder ownership/lifetime rules accurately.

The documentation build must never execute the E175 example.

### 4. Lead with the generic external-parameterization contract

The external guide must make this boundary unambiguous:

```text
external CSDL/LFS parameterization
    -> deformed coefficients
    -> GeometryModel.add_component(...)
    -> BSM3 projection, surface motion, quality, and optional volume chain
```

Document a compact, syntactically valid example in which the external
parameterization owns its design variables and recorder. BSM3 must not be
presented as owning those variables. State the current compatibility boundary:
component topology and coefficient layout must remain compatible, and all
dependent variables must belong to the caller-owned recorder passed to
`bsm3.mesh_motion.run`. Describe `add_lifting_surface` and `add_body` only as
optional E175-oriented conveniences, not as the generic mechanism.

### 5. Keep the API reference intentionally public

Document and cross-link the compact `bsm3.mesh_motion` public surface,
especially `run`, `GeometryModel`, the public configuration types, and the
result/quality objects. Autodoc/autosummary is acceptable, but the resulting
build must not expose a wall of private modules or require untracked data.
Verify signatures from source; do not invent parameters, return shapes, or
convergence guarantees.

### 6. State integration status honestly

- DAFoam/OpenFOAM and real MPI are optional integrations requiring an existing
  sourced environment, solver installation, and user case. They are not run in
  the standard CI suite.
- The rank-0 geometry-to-volume construction path is covered by tests, but do
  not convert that into a claim that a real DAFoam solve was run.
- VortexAD remains deferred until a tracked adapter against a pinned revision
  exists. Do not call the current untracked panel driver supported.
- Mesh generation remains separate from the core surface-motion quickstart.
- Mention safe NPZ polygon assets and trusted-pickle entry points accurately;
  do not normalize arbitrary pickle loading as the default.

Add concise troubleshooting for local paths, recorder ownership, topology or
coefficient-layout mismatches, optional plotting, and trusted legacy assets.

### 7. Make Sphinx, Read the Docs, and CI enforce the contract

- Use Python 3.12 in `.readthedocs.yaml`.
- Put documentation-only build dependencies in `docs/requirements.txt`, pinned
  to compatible versions. Avoid adding runtime dependencies merely for docs.
- Configure Read the Docs to install exactly what the docs build needs. If
  autodoc imports BSM3, its dependency installation must respect the validated
  CSDL/LFS revisions and LFS `--no-deps` rule.
- Add a CI documentation step that installs the docs requirements and runs
  Sphinx with warnings as errors into a temporary directory, not the repository.
- The build must not execute examples or require DAFoam, OpenFOAM, VortexAD,
  mpi4py, private cases, network access at build time beyond installation, or
  any untracked file.
- `tests/test_documentation.py` should be a fast, standard-library structural
  guard for the high-value contract: no template identity, valid local toctree
  targets, required public names, exact dependency revisions/install flags,
  and Python 3.12 configuration. Do not duplicate Sphinx itself in this test.

You may create a disposable Python 3.12 virtual environment under `/tmp` and
install documentation-only packages into it. Do not modify
`bsm3_py312_main`, another persistent environment, or another repository.

## Required verification

Run and report all of the following from `TURN61_BASE` plus your changes:

1. `git diff --check TURN61_BASE..HEAD` for committed work, and an equivalent
   pre-commit check.
2. A case-insensitive grep over `README.md`, `.readthedocs.yaml`, and `docs/`
   proving the obsolete template identity and quartic tutorial are gone. The
   grep must exclude `docs/overhaul/**`, whose historical record is expected to
   retain those words.
3. In a fresh disposable Python 3.12 environment under `/tmp`, install
   `docs/requirements.txt`, report Python and Sphinx versions, then run:

   ```bash
   python -m sphinx -W --keep-going -b html docs /tmp/bsm3-docs-html
   ```

4. `python -m pytest -q tests/test_documentation.py`.
5. The fast/non-integration portion of the tracked E175 example tests, proving
   documentation changes did not alter the example contract. Discover the
   exact marker selection from the file/config rather than guessing it.
6. Default Ruff on `docs/conf.py` and `tests/test_documentation.py`, plus the
   five literal Ruff commands already present in `.github/workflows/actions.yml`.
7. Repeat the docs build and documentation test from a fresh clone of the
   implementation commit, with an empty clone status afterward. The clone may
   reuse the disposable docs environment but no untracked source-tree files.
8. Prove the 8 pre-existing modified files are byte-identical to their
   `TURN61_BASE` working-tree state and the original 394 untracked entries are
   unchanged. Build output and virtual environments must remain outside the
   repository.

Do not run DAFoam/OpenFOAM, VortexAD, or real-MPI jobs. Do not rerun the
ten-minute full E175 integration unless a documentation-only check exposes an
actual contract discrepancy that cannot be resolved read-only.

## Commit structure and handoff

Make exactly two commits:

1. site/configuration/CI/test changes from the implementation allowlist;
2. `PLAN.md`, `LOG.md`, and the next `CODEX_NEXT.md` review checklist.

In the handoff, list both hashes and the exact changed paths; report the docs
environment, Sphinx warnings-as-errors result, structural test, fast E175
result, Ruff results, fresh-clone result, and dirty-tree preservation. Call out
every wording or API uncertainty you resolved from source. If any requirement
cannot be met inside the allowlist, stop and report it instead of silently
weakening the documentation or widening scope.

Mark M2.1 as ready for Codex review, not accepted.
