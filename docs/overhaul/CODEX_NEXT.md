# Codex review checklist — M1.9 official-main dependency migration

Claude was the implementer. The migration is **ready for review, not
accepted**. M1.6 slice 3 is paused at the user's instruction and resumes once
this is independently accepted.

> The slice 3 prompt this file previously held is recoverable verbatim with
> `git show 7676b89:docs/overhaul/CODEX_NEXT.md`.

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

**1. No remaining patched-factory imports in tracked files.**
`git grep 'compute_basis_matrix_numpy_factory_patched' -- '*.py'` returns **0
files**; widening to every tracked file of any type also returns nothing. All
five projection modules carry the canonical import.

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

**5. `git diff --check` in both repositories.** Clean in both.

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

## Findings requiring a Codex decision

1. **Two untracked research scripts still import the patched factory** —
   `bsm3/core/projections/gauss_newton_projection.py` and
   `bsm3/core/projections/function_set_sdf_custom_op_wing_test.py`. Untracked,
   outside the release surface and outside the literal allowlist, so untouched.
   They will fail to import wherever the alias is absent. Retire or migrate
   under a later allowlist?
2. **CI does not yet carry the LFS fix.** CI pins official `307ad3a`, which
   predates the unpushed `b6e7b4e`. The BSM3 suite does not depend on the fix,
   but the pin should move only after the LFS change lands upstream.
3. **Plotting did not segfault here**; 5 passed under this macOS/VTK build. The
   hazard is environment-dependent and plotting behavior was not changed.
4. **The compatibility alias was moved aside, not destroyed**, to
   `/tmp/t47_alias_backup/`. It is byte-identical to the canonical module and
   restorable with one copy.

## Deviations

- Ruff was not run; the migration spec did not request it. The pinned CI
  `ruff==0.9.10` step is unchanged.
- Nothing pushed in either repository, by instruction.

## Decision requested

Accept or reject the M1.9 migration, and rule on finding 1 (the two untracked
scripts) and finding 2 (when the CI LFS pin advances). On acceptance, M1.6
slice 3 resumes from `git show 7676b89:docs/overhaul/CODEX_NEXT.md`.
