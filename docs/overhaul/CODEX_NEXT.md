# Codex Turn 76 — M7.1: restore CI lint coverage for the M4.2 modules

Claude accepted **M4.2 in Turn 75 and closed M4**. This is the one narrow
correction that acceptance deferred. Codex implements; Claude reviews. Do not
self-accept.

```text
TURN76_BASE = fb833d5
```

Preserve the user's dirty tree exactly: **8 modified tracked files and 393
untracked entries**, verified with:

```bash
git diff | shasum -a 256
# 981318561a10dff8e9d723540902b6d2560875b29656a0b59f0803cbff116177
git status --porcelain | grep '^??' | cut -c4- | sort | shasum -a 256
# c38fd93dc32ecf7f927fc612c1079bd9786c19f6c1f74b4f8e69d28aaa44da60
```

## The gap

M4.2 added five Python files. **None appears in any of the five literal Ruff
path lists in `.github/workflows/actions.yml`:**

```text
bsm3/core/boundary_surface_movement/panel_aerodynamics.py
bsm3/core/boundary_surface_movement/fuel_burn.py
examples/e175_fuel_burn_optimization.py
tests/test_panel_aerodynamics.py
tests/test_fuel_burn.py
```

All five are clean today under both default Ruff and `--select D` — Claude ran
them directly, which is why this did not block acceptance. The defect is CI
coverage: nothing would catch a future regression in them. The workflow was
correctly outside M4.2's allowlist, so Codex was right to report rather than
silently edit it.

## Literal implementation allowlist — exactly one path

```text
.github/workflows/actions.yml
```

Documentation commit, separately:

```text
docs/overhaul/PLAN.md
docs/overhaul/LOG.md
docs/overhaul/CODEX_NEXT.md
```

Everything else is prohibited. Do not touch source, tests, examples, docs
pages, packaging, or the curated assets. If you believe another path is
required, stop and report instead of widening.

## Part A — required additions

Add both production modules to **two** steps, keeping each list's existing
alphabetical ordering and line-continuation style exactly:

1. **Critical static checks** (default Ruff over the retained production
   manifest) — add `panel_aerodynamics.py` and `fuel_burn.py`.
2. **Numpydoc checks for the surface-motion core** (`--select D`) — add the
   same two files.

Both belong beside their existing neighbours under
`bsm3/core/boundary_surface_movement/`.

## Part B — rule on the other three, do not guess

`examples/` is covered by no Ruff step, and only three of roughly twenty test
files are listed (`test_derivative_gate.py`, `test_curated_assets.py`,
`test_e175_driver_configuration.py`). That selectivity looks deliberate rather
than accidental.

Decide whether `tests/test_panel_aerodynamics.py` and `tests/test_fuel_burn.py`
should join that curated set, and whether the example warrants a step at all.
**State your reasoning and what principle you applied**, then implement your
ruling. Either answer is acceptable if it is argued; silently adding all three,
or silently adding none, is not.

## Verification

1. `git diff --check "$TURN76_BASE"..HEAD`; changed paths ⊆ the allowlist.
2. Run all five workflow Ruff commands **as literally written in the edited
   file** — extract and execute them, do not retype from memory. Report each
   step's result and its path count before and after.
3. Confirm the two production modules now appear in exactly the two intended
   steps, and report where any test file landed under your Part B ruling.
4. Run the workflow's non-Ruff steps that do not need absent dependencies, so
   an editing slip in the YAML cannot pass unnoticed. At minimum, parse the
   file and confirm it is valid YAML with the same step names and count as at
   `TURN76_BASE`.
5. Full non-integration suite: baseline **240 passed, 10 deselected**.
6. `tests/test_documentation.py` (12) and the strict Sphinx 9.1.0 build — both
   should be unaffected, which is the point of checking them.
7. Preservation: both SHA-256 hashes above recomputed and matching, 8 modified,
   393 untracked.

Do not install dependencies. Do not run DAFoam, OpenFOAM, VortexAD, or MPI.

## Out of scope — do not start

- **External publication.** The GitHub rename, Read the Docs project and
  webhook, the `v0.2.0a1` tag, and any PyPI reservation remain user-authorized.
  Claude confirmed in Turn 75 that the repository side of hosting is already
  complete; nothing in this turn changes that.
- **M5.2**, the `bsm3` → `gamma_mdo` namespace migration, stays blocked on the
  user resolving the 304 untracked entries and 8 modified files under `bsm3/`.
- **M3** archive and history pruning remains last.
- Do not reopen any accepted M4.1, M4.2, or GAMMA behavior.

## One item to record while you are here

Claude's Turn-75 review found an upstream hazard worth carrying in `LOG.md`,
not fixing: pinned VortexAD's `PanelMethod.__init__` does
`options_dict = default_input_dict` with **no copy** and then mutates it, so
constructing a solver mutates VortexAD's module-level defaults for the
process. GAMMA's exposure is low because the adapter passes all 11 keys it
depends on explicitly, but a second `build_panel_aerodynamics` call in one
process inherits the first call's unspecified settings. Record it; do not work
around it in this turn.

## Handoff

Two commits: the workflow, then the collaboration documents. Report both
hashes, the Part B ruling and its reasoning, each Ruff step's before/after path
count, the YAML-validity check, the suite and documentation results, and the
preservation hashes. Mark M7.1 ready for Claude review, never self-accepted.
