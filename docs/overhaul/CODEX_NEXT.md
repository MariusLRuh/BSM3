# No Codex implementation turn is available

**M7.1 was accepted in Turn 77 and M7 is closed.** Every milestone either agent
can act on is now complete: M0, M1, M2, M4 — including the GAMMA public
identity and the HTML-only documentation alpha — and M7.

Do not invent a turn from this file. There is no queued implementation work,
and nothing here authorizes starting any of the items below.

## Why nothing is queued

| Remaining work | Why no agent may start it |
| --- | --- |
| External publication: GitHub rename to `GAMMA-MDO`, Read the Docs project and webhook, the `v0.2.0a1` tag, any PyPI reservation | User-authorized by standing ruling. Turn 75 confirmed the repository side is already complete, so there is nothing to prepare. |
| **M5.2** — `bsm3` → `gamma_mdo` namespace migration | Blocked until the user resolves the dirty tree: 304 untracked entries and 6 of 8 modified tracked files live under `bsm3/`, and 57 untracked user scripts import the namespace. No agent may edit any of them. |
| **M3** — archive remote and clean release repository | Gated and deliberately last. The user deferred it again in Turn 77. |

## One stale row to fix whenever M3 is opened

M3's section reads: *"Does not start until M2 is complete and every root in the
manifest has an end-to-end test."*

**The first condition has cleared** — M2 closed in Turn 64 — but the M3.1,
M3.2, and M3.3 rows still read "blocked on M2", which is now inaccurate. The
second condition is unverified: whether every root in the M0.2 manifest is
reached by a passing end-to-end test is M3.1's own task and was not checked in
Turn 77.

Whoever opens M3 should correct those three status cells first, then establish
the manifest-coverage fact before any pruning or archiving is planned.

## Standing constraints, unchanged

- Preserve the user's dirty tree exactly: **8 modified tracked files and 393
  untracked entries**.

  ```bash
  git diff | shasum -a 256
  # 981318561a10dff8e9d723540902b6d2560875b29656a0b59f0803cbff116177
  git status --porcelain | grep '^??' | cut -c4- | sort | shasum -a 256
  # c38fd93dc32ecf7f927fc612c1079bd9786c19f6c1f74b4f8e69d28aaa44da60
  ```

- Do not rename the GitHub repository, push, merge, create or push a tag,
  create the Read the Docs project or webhook, publish or reserve on PyPI,
  start M5.2, or begin M3.
- Do not install dependencies. Do not run DAFoam, OpenFOAM, VortexAD, or MPI.
- Accepted M1, M2, M4, GAMMA, and M7 behavior is settled. Do not reopen it.

## Two items carried forward, recorded not fixed

1. **Upstream VortexAD hazard.** Pinned `PanelMethod.__init__` does
   `options_dict = default_input_dict` with no copy and then mutates it, so
   constructing a solver mutates VortexAD's module-level defaults for the
   process. GAMMA's exposure is low because the adapter passes all 11 keys it
   depends on explicitly. Carry it; do not work around it.
2. **Lint coverage boundary.** `tests/test_panel_aerodynamics.py`,
   `tests/test_fuel_burn.py`, and `examples/e175_fuel_burn_optimization.py`
   have execution coverage but no lint or docstring coverage — the same
   deliberate boundary every non-M0 test file already has. Changing it is a
   standalone policy decision for the user, not a correction to M7.

## If the user gives new direction

Wait for it. When it arrives, the next prompt is written into this file by
whichever agent holds the planner role at that time.
