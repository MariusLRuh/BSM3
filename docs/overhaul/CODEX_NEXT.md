# Claude Turn 63 — correct M2.1 installation and semantic claims

Codex reviewed `4ca0435` and `1cc849e`. The documentation infrastructure is
sound: the template is gone, the Read the Docs configuration is valid, the
site builds strictly without importing BSM3, and the focused tests pass.
M2.1 is **not accepted yet**, because the user-facing installation sequence is
not executable from an empty Python 3.12 environment and several prose claims
are stronger than the implementation.

You remain the implementer. Codex remains the reviewer/planner. Treat current
`HEAD` as `TURN63_BASE`, record its full hash, preserve the 8 pre-existing
modified files and 394 pre-existing untracked entries exactly, and do not
self-accept the result.

## Literal implementation allowlist

Only these paths may change in the implementation commit:

```text
README.md
docs/index.md
docs/src/api.md
docs/src/background.md
docs/src/examples.md
docs/src/external_parameterization.md
docs/src/getting_started.md
docs/src/integrations.md
tests/test_documentation.py
```

The second commit may change exactly:

```text
docs/overhaul/PLAN.md
docs/overhaul/LOG.md
docs/overhaul/CODEX_NEXT.md
```

No production source, example, workflow, Sphinx configuration, dependency
file, package metadata, or asset may change. If a correct install cannot be
documented using the existing tracked files, stop and report the missing
packaging boundary rather than widening the allowlist.

## Required corrections

### A. Make the installation instructions actually reproducible

The current sequence installs CSDL, installs LFS with `--no-deps`, and installs
BSM3. That is incomplete in an empty environment. At official LFS commit
`307ad3a`, its declared dependencies include NumPy, SciPy, PyVista, joblib,
pandas, scikit-learn, and JAX. `--no-deps` deliberately suppresses all of them,
while CSDL does not supply the complete set. A clean user following the page
can therefore fail before importing LFS.

Use the repository's existing `requirements-ci.txt` as the exact validated
Python 3.12/core-development stack, followed by the official LFS pin with
`--no-deps`, then BSM3 with `--no-deps --no-build-isolation -e .`. It already
contains the exact CSDL pin and the dependency versions used for M1.9. Show
creation and activation of a fresh Python 3.12 Conda environment before those
commands. Do not retain a second, incomplete install recipe that appears to be
an equivalent clean-environment setup.

Be precise about the boundary:

- this is the exact validated core/developer environment, not a claimed
  minimal runtime dependency set;
- an existing DAFoam environment remains separate and administrator-managed;
- BSM3 itself declares no automatic dependencies, which is why its install
  uses `--no-deps`; do not generalize that into “pip cannot change the
  environment” while the preceding bootstrap intentionally installs packages;
- interactive BSM3 plotting is optional, but PyVista is currently an eager
  dependency of the pinned LFS import and is included in the validated stack.
  Remove the false claim that a clean core environment may omit PyVista;
- prefer “the validated setup uses pinned Git revisions” over a mutable claim
  about whether each upstream project currently exists on PyPI.

Update the structural test so it requires the documented validated sequence:
Python 3.12 environment creation, `requirements-ci.txt`, the exact LFS revision
with `--no-deps`, and the BSM3 editable flags. It must reject the prior
CSDL-only-plus-LFS recipe as a complete setup.

### B. Remove guarantees the implementation does not make

Correct every occurrence, not only the examples below:

1. `README.md` and `docs/index.md` say BSM3 moves nodes “so the mesh stays
   valid.” The solver reports inversions and can return them; validity is a
   measured outcome, not a guarantee. Describe the goal and the diagnostics.
2. `docs/src/background.md` says every node is put back “exactly” on the OML.
   Projection can fail to converge and the point is still returned. Describe
   reprojection as attempted/evaluated and keep the explicit non-convergence
   caveat adjacent enough that readers cannot miss it.
3. `docs/src/examples.md` and `docs/src/api.md` say `print_summary()` reports
   load stepping. It does not. Verify its body and list only what it actually
   prints: mesh vertex/cell and n-gon-mode counts, elapsed time, fold and
   inversion counts, and the available degenerate/minimum-scaled-Jacobian
   quality fields.
4. Narrow blanket “BSM3 never starts or stops a recorder” prose to the public
   contract actually reviewed: `GeometryModel` and `bsm3.mesh_motion.run` do
   not create, start, or stop the caller's recorder. Internal optional driver
   backends may own their own recorder, so do not make a repository-wide claim.

Add focused rejection assertions to `tests/test_documentation.py` for the
specific false phrases where practical. Do not make the test a general prose
word blacklist.

### C. Stop presenting the README skeleton as runnable

The README “Quickstart” constructs an empty `GeometryModel` and then calls
`run`; copied verbatim, it fails `GeometryModel.validate()` because no
component is registered. Keep it concise, but explicitly label it as a call
shape that requires component registration, or replace it with a genuinely
runnable route to the tracked E175 example. A reader must not mistake the
empty-model snippet for a complete executable example. Preserve the direct
link to `examples/e175_surface_deformation.py` and keep the five-stage guide as
the complete explanation.

### D. Make the hand-written API drift guard exact

The current test does not truly guard both directions. It extracts `__all__`
with a loose regex, accepts any incidental substring as documentation, and
only treats backticked `mm.Name` forms as promises. A misspelled unqualified
type could escape it.

Keep the dependency-free approach, but:

- parse `bsm3/mesh_motion.py` with the standard-library `ast` module to obtain
  the literal `__all__` set;
- add a clearly delimited, reader-useful inventory in `docs/src/api.md` that
  names every public export in one consistent machine-checkable form; and
- assert exact set equality between that inventory and `__all__`.

This is an export-inventory guard, not a substitute for semantic review. Say
that accurately in the test and handoff; do not claim it validates every
signature or prose description.

### E. Correct the handoff accounting

Sphinx reports seven source documents (`index` plus six pages). If you retain a
page count, distinguish those seven source documents from generated utility
HTML pages such as the search and index pages. Correct Turn 61's “9 pages”
wording in the new append-only log entry rather than rewriting the historical
entry.

Preserve all correct M2.1 content: the generic external-coefficient path,
five-stage E175 flow, current public signatures, post-import coefficient
validation, tracked/untracked asset boundary, safe NPZ/trusted-pickle boundary,
and honest DAFoam/MPI/VortexAD status.

## Required verification

1. Prove the committed range contains only the nine implementation paths and
   three collaboration paths above; run scoped `git diff --check`.
2. In a **fresh empty Python 3.12 environment**, execute the documented install
   commands in their documented order. Do not reuse `bsm3_py312_main` or an
   environment that already has LFS. A temporary Conda prefix under `/tmp` is
   acceptable.
3. From that fresh environment, report versions/revisions where available and
   run at least:

   ```bash
   python -c "import csdl_alpha; import lsdo_function_spaces; import bsm3.mesh_motion"
   python -m pytest -q tests/test_documentation.py
   python -m pytest -q tests/test_e175_example.py -m "not integration"
   ```

4. Re-run the strict documentation build in a disposable docs environment:

   ```bash
   python -m sphinx -W --keep-going -b html docs /tmp/bsm3-docs-html-turn63
   ```

5. Run default Ruff on `tests/test_documentation.py`; the changed Markdown is
   covered by the strict Sphinx build. Re-run the five existing literal Ruff
   commands from the workflow to prove no gate regressed.
6. Run rejection checks for the four corrected semantic claims and inspect the
   rendered/source context rather than relying on grep alone.
7. Repeat the documentation test, strict Sphinx build, and import smoke test
   from a fresh clone of the implementation commit. The clone must remain
   clean, and no command may consume an untracked source-tree file.
8. Prove all 8 pre-existing modified files are byte-identical to their
   `TURN63_BASE` working-tree state and all 394 original untracked entries
   remain present and unmodified.

Do not run the ten-minute E175 integration, DAFoam/OpenFOAM, VortexAD, or real
MPI. Do not alter the accepted numerical implementation.

## Commit structure and handoff

Make exactly two commits:

1. the narrow documentation/test correction;
2. `PLAN.md`, `LOG.md`, and the next `CODEX_NEXT.md` review checklist.

Report both hashes, exact changed paths, the fresh-environment install/import
result, 10-or-updated documentation-test count, 13/5 fast E175 result, strict
Sphinx result, Ruff results, clean-clone result, and dirty-tree preservation.
List each corrected false/overbroad claim and the source evidence used.

Mark M2.1 as ready for Codex review, not accepted. M2.2 remains blocked until
this correction is independently accepted.
