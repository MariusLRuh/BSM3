# Kickoff prompt for Codex — paste this into a Codex session at the repo root

You are collaborating with Claude on the BSM3 production overhaul described in
`bsm3/core/boundary_surface_movement/production_ready_code_base_overhaul.md`.

**Read these two files first — they are the shared source of truth:**
- `docs/overhaul/PLAN.md` — protocol, locked decisions, M0/M1 task tables with
  acceptance criteria
- `docs/overhaul/LOG.md` — turn history; Turn 1 (Claude, planner) is closed

**Your role for M0 and M1: implementer and reviewer.** Claude is the planner.
Per the protocol, the planner's call breaks ties; you may file one written
objection per decision in `LOG.md` under `Objection:`, and the planner's
response is final. You are permitted to edit code during review, not just
comment.

**Your first turn has two parts.**

Part 1 — review the plan, before writing any code:
1. Answer Q-A, Q-B, Q-C in `PLAN.md` section 6. Q-B (has the n-gon affine
   regularizer ever been exercised on 6-gon cells, or only quads?) is the one
   that most affects scope — the user has made n-gon support for quad and
   higher-edge polygons a mandatory M1 capability, and the current production
   config sets `ngon_affine.weight = 0.0` because the R4 wall is tri-only.
2. Push back where you disagree. Claude's plan makes four ordering calls worth
   scrutiny: the derivative gate (M0.3) blocking all of M1; deletion before
   generalization; M1.3 before M1.2; and one shared worktree rather than two.
3. Verify Claude's reachability figure independently — 45 files / 24,285 LOC
   live out of 211 files / 156,485 LOC. It comes from a static import trace
   from `cfd_mesh_movement_test.py` and will miss dynamic imports. M0.2 deletes
   based on it, so a wrong number deletes live code.

Part 2 — implement M0.1 through M0.4, in order, only after Part 1 is logged.

**Logging.** Append a `## Turn 2 — Codex, implementer, <date>` entry to
`docs/overhaul/LOG.md` using the format at the top of that file. Claim the turn
before editing code; close it when done. Keep it short — the user reads this
file to follow the collaboration.

**Definition of done for every task:** `pytest tests/` passes, the derivative
gate passes (once M0.3 exists), the named example runs end to end, and public
functions you touch carry numpydoc docstrings.
