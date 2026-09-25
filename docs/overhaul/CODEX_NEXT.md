# Codex Turn 71 — M5.1 and M6.1: GAMMA public identity, HTML-only docs alpha

Claude ruled the identity in Turn 70. Codex implements; Claude reviews. Do not
self-accept.

```text
TURN71_BASE = 09cd954
```

Preserve the user's dirty tree exactly: **8 modified tracked files
byte-for-byte and 393 untracked entries.** Do not adopt, delete, format, stage,
or move any of them.

## The rulings you are implementing

```text
Display name:        GAMMA
Expansion:           Geometry Adaptation for Multidisciplinary Modeling and Analysis
Repository slug:     GAMMA-MDO
Python distribution: gamma-mdo
Python import:       bsm3          <-- UNCHANGED, deliberately
Read the Docs slug:  gamma-mdo
Version:             0.2.0a1       <-- not 0.1.0a1
```

**The import namespace does not change and `bsm3/` does not move.** 304 of the
393 untracked entries and 6 of the 8 modified tracked files live under
`bsm3/`; 57 untracked user scripts and 5 modified tracked files import `bsm3`,
and no agent may edit them. A distribution name differing from its import name
is ordinary (`scikit-learn`/`sklearn`, `pillow`/`PIL`). Do not add an alias
module, a shim, a deprecation path, or a `gamma_mdo` package. If you find
yourself renaming a directory, you have misread this turn.

Version is `0.2.0a1`, not `0.1.0a1`: `bsm3` was never published to PyPI and no
tag exists locally or on `origin`, but source installs already report `0.1.4`,
so the prerelease must move forward rather than appear to downgrade.

## Literal implementation allowlist — exactly these paths

```text
setup.py
bsm3/__init__.py
docs/conf.py
.readthedocs.yaml
README.md
docs/README.md
docs/index.md
docs/src/api.md
docs/src/background.md
docs/src/examples.md
docs/src/external_parameterization.md
docs/src/getting_started.md
docs/src/integrations.md
requirements.txt
requirements-ci.txt
MANIFEST.in
HPC_DAFOAM_INSTALL.md
.github/workflows/actions.yml
.gitignore
```

Documentation commit, separately:

```text
docs/overhaul/PLAN.md
docs/overhaul/LOG.md
docs/overhaul/CODEX_NEXT.md
```

### Explicitly prohibited paths

```text
bsm3/**            except bsm3/__init__.py (version line only)
tests/**
examples/**
docs/overhaul/**   except the three handoff documents above
```

`bsm3/__init__.py` is on the allowlist **only** for the `__version__` string.
Do not touch its `__all__`, imports, or docstring. Stop and report rather than
widening this list.

## Part A — public identity

- `setup.py`: `name="bsm3"` becomes `name="gamma-mdo"`; update `url` to the
  `GAMMA-MDO` repository; refresh `description` to the GAMMA one-liner. Keep
  `install_requires=[]` and keep `find_packages()` resolving `bsm3` — the
  distribution ships the `bsm3` import package by design.
- `docs/conf.py`: `project`, `author`, and `html_title` carry GAMMA. Do **not**
  change `_read_version()`; it reads `bsm3/__init__.py` by regex without
  importing, which is what keeps the docs build hermetic.
- `README.md`, `docs/README.md`, `docs/index.md` and the six `docs/src/` pages:
  present the project as GAMMA, state the expansion once where a reader first
  meets the name, and **state plainly that the distribution is `gamma-mdo`
  while the import is `bsm3`**. A reader must not have to discover that by
  failing.
- Where a page shows an install command, it must be the real one.

Do not mechanically replace every occurrence of "BSM3". Prose describing the
historical package, the validated environment name `bsm3_py312_main`, cache
filenames, or the existing directory layout stays accurate as written.

## Part B — version

Set `__version__ = "0.2.0a1"` in `bsm3/__init__.py`. Confirm `setup.py` and
`docs/conf.py` both derive from it and that the built metadata, the Sphinx
`version`/`release`, and the intended tag label agree. Report the version as
seen by `pip show` on a built artifact, not just the source string.

## Part C — HTML-only documentation alpha

`.readthedocs.yaml` declares `formats: [pdf, htmlzip]`. **Neither has ever been
built**, and `fail_on_warning: true` in the same file would apply
warnings-as-errors to an unverified LaTeX toolchain on the first hosted build.
Reduce `formats` to HTML only and update the surrounding comment to say why,
including that PDF and HTMLZIP may be enabled later after independent builds.

Keep the build hermetic: `docs/requirements.txt` only, no autodoc, no geometry
stack. Leave the CSDL_alpha and lsdo_function_spaces pin note intact.

## Part D — stale-name checks, scoped precisely

Historical collaboration prose must **not** be rewritten. Run these exact
checks and report each count:

```bash
# 1. Supported-surface branding: expect zero stale project-name references.
git grep -n "BSM3" -- setup.py docs/conf.py README.md docs/README.md \
  docs/index.md docs/src/ .readthedocs.yaml

# 2. Distribution name: expect zero.
git grep -n 'name="bsm3"\|name=.bsm3.' -- setup.py

# 3. The import namespace MUST still be everywhere. Expect the pre-change count.
git grep -c "import bsm3\|from bsm3" -- '*.py' | wc -l

# 4. Historical prose deliberately untouched: report, do not fix.
git grep -c "BSM3" -- docs/overhaul/ | head
```

Check 3 is a guard against an accidental namespace rename: its count must not
fall. Report the before and after numbers.

## Verification

1. `git diff --check "$TURN71_BASE"..HEAD`; changed paths ⊆ the allowlist.
2. **Build and install the distribution, then import from outside the source
   tree.** Build a wheel, install it into a disposable environment, `cd /tmp`,
   and confirm `import bsm3` works and `bsm3.__version__` reports `0.2.0a1`.
   Running this from the checkout proves nothing — a Turn-64 false positive
   came from exactly that mistake. Report the wheel filename, which must carry
   `gamma_mdo-0.2.0a1`.
3. Full non-integration suite; baseline **228 passed, 9 deselected**.
4. `tests/test_boundary_surface_movement.py` **45 passed**;
   `tests/test_e175_example.py -m "not integration"` **16 passed, 5
   deselected**.
5. Derivative / N-gon three-file guard: **exactly 6**.
6. Both E175 integration guards still pass:
   `test_triangle_wall_at_full_deformation_scale` and
   `test_quad_panel_introduces_no_new_inverted_elements`.
7. `tests/test_documentation.py` and the strict Sphinx 9.1.0 build.
8. All five literal workflow Ruff groups, plus default Ruff on changed paths.
9. **Clean clone:** clone the implementation commit, build the docs strictly
   with only `docs/requirements.txt`, run the documentation tests, and end with
   an empty `git status`.
10. Preservation: **8 modified tracked files byte-identical and 393 untracked
    entries**, counted before and after.

No DAFoam, OpenFOAM, VortexAD, or real-MPI run. Do not install project
dependencies; a disposable venv for the wheel-install check is expected and is
not a project dependency install.

## External actions — NOT part of this turn

Prepare the repository only. Every item below is a user-authorized external
mutation that **no agent performs**. List them in the handoff as a checklist
for the user, with the exact values needed:

- rename the GitHub repository `BSM3` → `GAMMA-MDO`;
- import the Read the Docs project under slug `gamma-mdo` and add its webhook;
- create and push the `v0.2.0a1` tag, then activate it on RTD and set the
  default version;
- reserve or publish `gamma-mdo` on PyPI.

Do not create a tag, push, publish, reserve a name, create an RTD project, or
rename anything on GitHub. Two availability facts are **not** reservations and
must be restated as such: PyPI returns 404 for `gamma-mdo`, and the RTD API
reports no project with that slug. The GitHub owner-namespace check was
**inconclusive** — the existing private repository also returns 404
unauthenticated — so the user must confirm `GAMMA-MDO` is free in their
account before renaming.

## Queued behind this turn

M4.2 — the tracked VortexAD and fuel-burn milestone — is planned and preserved
verbatim. Recover it with:

```bash
git show 38cd0bf:docs/overhaul/CODEX_NEXT.md
```

Do not rewrite or weaken it. Order: M5.1/M6.1 (this turn) → M6.2 (user
authorization) → M4.2 → M5.2 namespace migration, blocked on the dirty tree →
M3 archive/history pruning, last.

## Handoff

Two commits: implementation, then the collaboration documents. Report both
hashes, exact changed paths, the four stale-name check counts with before/after
for check 3, the wheel filename and the out-of-tree import result, all gate
results, the clean-clone result, preservation proof, and the external-action
checklist. Mark M5.1 and M6.1 as ready for Claude review, never as
self-accepted.
