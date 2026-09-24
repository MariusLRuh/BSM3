# Codex review checklist — M1.9 official-main dependency migration

Claude was the implementer. Codex has **technically accepted the
implementation**; this file now covers the documentation-only correction that
followed. M1.9 is **ready for final Codex acceptance and is not self-accepted**.

Codex's independent review recorded: BSM3 suite 192 passed / 53 warnings in
621.80 s; projection and derivative gates 9 passed; LFS file-I/O tests 9 passed;
broader LFS non-plotting selection 77 passed / 8 deselected under
`-k "not plot"`; Ruff clean over all five migrated projection modules; factory
byte identity and dependency provenance independently confirmed.

M1.9 stayed open only because two claims in these documents were inaccurate.
Turn 50 corrected both — see **Corrections applied** below. No source, CI,
test, requirement, dependency repository, dirty file, or untracked artifact was
touched in that turn.

> The M1.6 slice-3 prompt was deliberately **not** restored. Codex will restore
> and reissue it after accepting this correction. It remains recoverable
> verbatim with `git show 7676b89:docs/overhaul/CODEX_NEXT.md`.

## Commits

| Repo | Hash | Contents |
| --- | --- | --- |
| lsdo_function_spaces (temporary clone) | `b6e7b4ed862da5623e59a4315bd4b0d3c0265c10` | `utils/file_io.py`, `tests/test_file_io.py` |
| BSM3 | `bf2afee` | 5 projection modules, `requirements-ci.txt`, `.github/workflows/actions.yml` |
| BSM3 | *(docs commit)* | `PLAN.md`, `LOG.md`, `CODEX_NEXT.md` |

BSM3 base was `7676b89`. Nothing was pushed in either repository. The LFS
commit sits on official main `307ad3a` in a clean temporary clone at
`/private/tmp/bsm3-compat.bHdusA/lsdo_function_spaces_main` (branch `main`,
remote `LSDOlab/lsdo_function_spaces`). The dirty local LFS checkout and the
local CSDL_alpha checkout were never modified.

## Baseline actually used

| Component | Value |
| --- | --- |
| CSDL_alpha | official `LSDOlab/CSDL_alpha` main `73a9efd1033016a835779db10a9b9e81ed2254ce` |
| lsdo_function_spaces | official `LSDOlab/lsdo_function_spaces` main `307ad3aabfff31c6fb44ddf51bc0dcc41a60c420` |
| Python / NumPy / SciPy | 3.12.14 / 2.0.2 / 1.13.1 |
| JAX / jaxlib | 0.4.38 / 0.4.38 |

Note the CSDL origin change: BSM3 previously pinned the **HgXe** fork; it now
pins **LSDOlab** official main.

## Verification requirements, one by one

**1. No remaining patched-factory imports in tracked production files.**
Two scoped checks, both empty:

```bash
git grep -n 'compute_basis_matrix_numpy_factory_patched' -- '*.py'
git grep -n 'compute_basis_matrix_numpy_factory_patched' -- ':!docs/overhaul/**'
```

So there are zero tracked production Python imports and zero tracked references
outside `docs/overhaul/`. All five projection modules carry the canonical
import.

An **unrestricted** `git grep` is *not* empty and must not be reported as such:
it returns the expected historical and descriptive mentions inside the three
collaboration documents (`CODEX_NEXT.md` 3, `LOG.md` 3, `PLAN.md` 1). Those are
prose about the migration, not imports, and are meant to stay.

**2. Canonical and former patched factory are equivalent.** Byte-identical, not
merely equivalent. All three of these hash to
`sha256 3b216af2c0534eebae04fea5256de7fcaf16c9f694ccdcd7d1b4378cac6ba894`:

- official main tracked `compute_basis_matrix_numpy_factory.py`
- the temporary compatibility alias
- the local fork's `compute_basis_matrix_numpy_factory_patched.py`

The local fork's own `compute_basis_matrix_numpy_factory.py` hashes to
`eb19d43a...`; that stale file is what the `_patched` name existed to shadow.

**3. All 192 BSM3 tests under the official-main stack.** `192 passed` in
611.32s. Run with the compatibility alias **moved out of the dependency tree**
and proven to raise `ModuleNotFoundError`, so nothing could silently resolve
the old name.

**4. E175 coordinates vs reference at rtol=atol=1e-14.**

| array | shape | max abs diff | allclose |
| --- | --- | --- | --- |
| `initial` | (16400, 3) | 0.000e+00 | True |
| `preprojected` | (16400, 3) | 0.000e+00 | True |
| `surface` | (16400, 3) | 0.000e+00 | True |

Reference measured on this machine by running the example at the
**pre-migration** code state under `bsm3_py312_localdeps` (local forks, JAX
0.4.30), and at the **migrated** state under `bsm3_py312_main` (official mains,
JAX 0.4.38). Folds 0 and inversions 0/0/0 in both. This is a different and
stronger measurement than the 7.11e-15 recorded earlier against another
reference; I am not restating that number as if I reproduced it.

**5. `git diff --check`.** Clean over the migration commit ranges:

```bash
git diff --check bf2afee^ bf2afee
git -C /private/tmp/bsm3-compat.bHdusA/lsdo_function_spaces_main \
      diff --check b6e7b4e^ b6e7b4e
```

Both empty, as is the docs commit range `d419d60^ d419d60`.

The **complete dirty BSM3 working tree is not clean**: an unscoped
`git diff --check` reports five pre-existing whitespace findings in user-owned
files — three in
`bsm3/core/boundary_surface_movement/movement_test_embraer_175_hex_mesh.py`
(lines 2587, 5713, 5870), one in `examples/basic_examples/ex_wing_sdf_newton.py`
(line 141), and one new blank line at EOF in
`examples/basic_examples/wing_mesh_projections.py` (line 40). All five predate
this work, belong to the preserved dirty tree, and were deliberately not
edited.

**6. No pre-existing dirty or untracked path changed.** 15 tracked files differ
from the pre-turn `HEAD`: the 7 that are mine, and 8 pre-existing ones with
modification times from 2026-04-15 to 2026-08-23 that I never opened. Untracked
entries: 394, unchanged.

**7. Separate commits.** LFS, then BSM3 source, then BSM3 docs. Every path
staged literally; no directory staged; no amend, reset, rebase, or rewrite.

## LFS change

`import_file` rejected a valid STEP file whenever its first
`B_SPLINE_SURFACE_WITH_KNOTS` entity began after byte 200,000, because the
existence check read only that leading window. It now streams the file one line
at a time and stops at the first match.

The new regression test pads a synthetic STEP file so the surface entity starts
past the window and asserts that offset exceeds 200,000. **It provably guards
the fix**: reverting only `file_io.py` makes it fail with the exact
`ValueError`; restoring `file_io.py` byte-exactly (sha `b54b3835...`) makes it
pass.

| LFS gate | Result |
| --- | --- |
| Focused `tests/test_file_io.py` | **9 passed** |
| Complete non-plotting suite | **80 passed** |
| `tests/test_plotting.py` | 5 passed in this environment |

Prohibited files confirmed absent from the clone: `file_io_patched.py`,
`compute_basis_matrix_numpy_factory_patched.py`,
`b_spline_patch_projection_optimized_patched.py`,
`b_spline_patch_proejction_numpy.py`. All four `.stp` files present are
upstream-tracked; no untracked STEP asset was added.

## CI

Python 3.12; `jax[cpu]==0.4.38`; `csdl_alpha` from `LSDOlab/CSDL_alpha@73a9efd`;
`lsdo_function_spaces` pinned to `307ad3a` and still installed with `--no-deps`
so its unpinned CSDL dependency cannot replace the validated commit.

## Corrections applied in Turn 50

**Claim 1 — "zero tracked references in any file type".** Wrong, and wrong in a
way worth naming: my own verification had explicitly filtered
`docs/overhaul/LOG.md` out of the search, and I then reported that filtered
result as if it were unrestricted. Replaced everywhere by the three accurate
facts and the two scoped commands in requirement 1 above.

**Claim 2 — "`git diff --check` clean in both".** Unqualified. The scoped
migration ranges are clean; the complete dirty BSM3 working tree is not, and
retains five pre-existing whitespace findings in user-owned files. Both
statements now appear together in requirement 5 above and in the `LOG.md`
Turn 50 entry. Those five files were not edited.

## Codex rulings, recorded

1. The two untracked research scripts —
   `bsm3/core/projections/gauss_newton_projection.py` and
   `bsm3/core/projections/function_set_sdf_custom_op_wing_test.py` — remain
   untouched and outside the release surface. Their imports will be migrated
   only if the scripts are later adopted.
2. CI remains pinned to official LFS `307ad3a` until `b6e7b4e` is reviewed and
   lands upstream. An unpushed temporary commit must not be pinned.
3. The plotting result is environment-dependent and requires no code change.
4. The independently observed 7.11e-15 delta and the fresh 0.0 delta both
   satisfy the 1e-14 equivalence threshold. They are two different measurements
   and are not contradictory.
5. The temporary alias backup at `/tmp/t47_alias_backup/` is not a product
   dependency.

## Deviations

- Ruff was not run by the implementer; the migration spec did not request it.
  Codex ran it independently and reports all five migrated projection modules
  clean. The pinned CI `ruff==0.9.10` step is unchanged.
- Nothing pushed in either repository, by instruction.

## Decision requested

Final acceptance of M1.9. The implementation was technically accepted; this
turn corrected the two documentation claims that held it open, and recorded the
five rulings above. Nothing outside the three collaboration documents changed.

On acceptance, Codex restores and reissues the M1.6 slice-3 prompt from
`git show 7676b89:docs/overhaul/CODEX_NEXT.md`.
