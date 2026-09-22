# Next implementation prompt for Codex — Turn 10 (M1.3)

Paste into a Codex session at the repository root.

---

Read `docs/overhaul/PLAN.md` (the Turn-9 M1.4 audit in section 5, and the M1.3
row), then `docs/overhaul/LOG.md` (Turn 9 is closed).

**M1.4 is ACCEPTED.** Every number you reported was reproduced independently:
`4.0000000000`, `4.3846153846 = 57/13`, `2/13` observability, 117,267 modes,
164 passed / 1 skipped in a genuine clone. `ngon_affine.py` is byte-identical to
the C1 substrate. Test C was mutation-tested — dropped, transposed, sign-flipped
and scale-error adjoints **all fail it**, so it does what it claims.

Two things worth carrying forward: the Turn-7 threshold discrepancy is explained
(the production Laplacian is exactly `0.25x` a unit-weight 6-cycle, so `λP` has
4x the relative influence and the response rose to `2/13`) — you were right not
to lower the threshold. And Test C's reprojection is DV-inert; that is recorded
as an M1.7 item, not a defect.

**This turn is M1.3 only** — delete the `membrane` surface-motion mode. Do not
touch M1.1, M1.2, M1.5, M1.6, M1.7 or M1.8. Specifically: no config
generalization or renaming, no pipeline decomposition, no `LOCAL_ALIAS` block
removal beyond the membrane entries, no meshgen carve-out, no docstring sweep,
no pickle retirement.

Claim `## Turn 10` in `LOG.md` before editing. Close it when done.

**Prohibited:** history rewrite, file deletion other than the membrane code
paths named below, `git add -A` or any broad staging, staging any path outside
the allowlist, and touching the eight excluded dirty files or the three deferred
untracked production files.

---

## Scope, with current line numbers

**`bsm3/core/boundary_surface_movement/e175_mesh_motion_config.py`**
- Seven fields, lines 159-165: `membrane_poisson_ratio`,
  `membrane_area_stiffening`, `membrane_normal_stabilization`,
  `membrane_barrier`, `membrane_barrier_activation`,
  `membrane_barrier_target`, `membrane_barrier_maximum_iterations`.
- `__post_init__` lines 168-169: the `mode not in ("graph", "membrane")` guard.
- The six `mode != "graph"` validation rules that become vacuous once `graph` is
  the only mode. Line 199's error message mentions "membrane-like distortion
  regularization" — reword, since the distortion/affine mutual-exclusion rule
  itself must survive.
- **Decide and state in the log:** does `mode` survive as a one-valued field, or
  is it removed? `VolumeMotionConfig` keeps `mode="elasticity"|"off"`, so an
  asymmetry is defensible either way. Removing it is cleaner; keeping it is
  friendlier to M1.1. Either is acceptable — record the reasoning.

**`bsm3/core/boundary_surface_movement/e175_mesh_motion_pipeline.py`**
- Alias lines 494-500 (`POISSON_RATIO`, `MEMBRANE_*`).
- Branch at line 1069 and its body.
- Diagnostics branch at lines 1521-1526.

**Tests — four, not two.** Turn 3 named only the first pair; commit C2 brought
in the second pair, which Turn 9 found:
- `tests/test_e175_driver_configuration.py` lines 150, 163:
  `test_quad_diagonal_weight_is_validated_as_graph_only` and
  `test_ngon_affine_weight_is_validated_as_graph_only`. **Rewrite, do not
  delete** — keep the `quad_bracing_mode` and negative-weight arms, drop the
  membrane arm.
- `tests/test_boundary_surface_movement.py` lines 878 and 908:
  `test_coupled_membrane_patch_test_and_interleaved_dofs` and
  `test_coupled_membrane_can_pin_one_symmetry_component`. Judge these on their
  merits: if they cover coupled-patch or symmetry-pinning behaviour that
  survives membrane removal, port them to the graph path; if they only exercise
  membrane, delete them and say so. **State which, and why, in the log.**

**`inversion_barrier.py` — verify, do not assume.** PLAN.md's original M1.3 note
said to re-check reachability. Turn 9 found it imported by *both*
`bsm3/core/boundary_surface_movement/__init__.py` line 102 and `motion.py` line
55, so it very likely survives. Confirm by tracing; do not delete it on the
strength of the old note.

## Acceptance

- `grep -ri membrane bsm3/` returns nothing in the live core.
- `grep -rn membrane tests/` returns nothing, or only names you justified.
- All four tests above are green in their final form.
- `python -m pytest -q tests` green.
- The M1.4 tests and the affine-nullspace gate still pass — M1.3 must not
  disturb them.

## Literal file allowlist

```
bsm3/core/boundary_surface_movement/e175_mesh_motion_config.py
bsm3/core/boundary_surface_movement/e175_mesh_motion_pipeline.py
tests/test_e175_driver_configuration.py
tests/test_boundary_surface_movement.py
docs/overhaul/PLAN.md
docs/overhaul/LOG.md
docs/overhaul/CODEX_NEXT.md
```

`bsm3/core/boundary_surface_movement/motion.py` and `inversion_barrier.py` are
**conditionally** allowed, only if the membrane removal leaves genuinely dead
code in them. If you touch either, say so prominently with the evidence — it is
a finding, not routine.

## Acceptance commands

```bash
python -m pytest -q tests/test_e175_driver_configuration.py
python -m pytest -q tests/test_boundary_surface_movement.py
python -m pytest -q tests/test_ngon_affine_operator.py tests/test_ngon_affine_load_step.py
python -m pytest -q tests/test_derivative_gate.py
python -m pytest -q tests
python -m ruff check bsm3/core/boundary_surface_movement/e175_mesh_motion_config.py
grep -ri membrane bsm3/ ; grep -rn membrane tests/
```

## Clean-clone verification

```bash
rm -rf /tmp/bsm3-m13-verify
git clone --no-hardlinks --branch production-ready-overhaul \
  "file:///Users/mariusruh/Documents/Research/nasa_uli/mesh_movement/packages/BSM3" \
  /tmp/bsm3-m13-verify
cd /tmp/bsm3-m13-verify
git status --porcelain            # MUST print nothing
PYTHONPATH=/tmp/bsm3-m13-verify python -m pytest -q tests
```

Use `PYTHONPATH`, not `pip install -e .` — an editable install in the clone
repoints the active environment at it, which you then had to undo in Turn 8.

**Expected:** 164 passed / 1 skipped, minus however many membrane tests you
justifiably delete. Report the actual number and name any test you removed.

## Definition of done

Membrane gone from the live core; all four affected tests in a justified final
state with the reasoning recorded; `mode` decision stated; `inversion_barrier.py`
reachability verified rather than assumed; full suite green from a genuine
clone; nothing outside the allowlist staged; every excluded dirty file still
dirty; actual counts and timings in Turn 10, not prose.
