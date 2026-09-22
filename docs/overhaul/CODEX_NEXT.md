# Next implementation prompt for Codex — Turn 8 (M1.4)

Paste into a Codex session at the repository root.

---

Read `docs/overhaul/PLAN.md` (the Turn-7 M0 closure and the finalized M1.4
design in section 5), then `docs/overhaul/LOG.md` (Turn 7 is closed).

**M0 is closed.** Your C1-C5 series was audited: exact allowlist match, no
forbidden paths, excluded files preserved, trusted-pickle boundary correct.
One caveat recorded — C1 is red standalone because it inherits a failure that
predates the series at `0a657a7`; C2 repairs it, so the first green commit is
C2 and future bisects should start from `76f24ce`. Claude's Turn-5 prediction
that C1 would be green was wrong and is on record.

**This turn is M1.4 only.** Do not touch M1.1-M1.3 or M1.5-M1.8. Specifically:
no config generalization, no pipeline decomposition, no membrane deletion, no
meshgen carve-out, no docstring sweep, no pickle retirement.

Claim `## Turn 8` in `LOG.md` before editing. Close it when done.

**Prohibited:** history rewrite, deletion, `git add -A` or any broad staging,
staging any path outside the allowlist below, new binary assets, DAFoam
dependence, and putting the large `wall_surface.pkl` into the fast gate.

---

## The mathematics you are testing

`_affine_residual_projector` builds, per element, from the **baseline** polygon:
centre, SVD to the best-fit plane, in-plane chart `(u, v)`, design matrix
`[1, u, v]`, reduced QR giving `Q_e`, then `P_e = I - Q_e Q_e^T`.

`P_e` acts on the **n-vector of nodal values per spatial component**. So
`null(P_e) = span{1, u, v}` — any nodal field affine in the element's own
baseline in-plane coordinates — and `rank(P_e) = n - 3`.

That is `range(A_e) = range(Q_e) = 𝒜_e`, and it is why the existing gate
measured 3.3e-16: a z-ramp is affine in `(u, v)`, so `r_e = 0`. That gate is
**correct**; reclassify it, do not "fix" it.

## Task 1 — `tests/test_ngon_affine_operator.py` (new)

### Test A — projector algebra (< 1 s, pure numpy)

Regular planar hexagon, vertices at `kπ/3`, `k = 0..5`, in `z = 0`.
Claude measured these in Turn 7; assert them:

- `P` symmetric; `P @ P ≈ P`; `np.linalg.matrix_rank(P, tol=1e-10) == 3`
- `‖P·1‖`, `‖P·u‖`, `‖P·v‖`, `‖P·(2+3u-5v)‖` all `< 1e-12`
  (measured 6.5e-16, 3.8e-16, 2.0e-16, 2.7e-15)
- alternating ring mode `p = (+1,-1,+1,-1,+1,-1)`:
  `abs(‖P·p‖/‖p‖ - 1.0) < 1e-12` (measured exactly 1.000000)
- quad control: `rank == 1`, retained fraction `1.0`
- via `NgonAffineAssembler`: `num_hourglass_modes == 3` for the hexagon,
  `== 1` for a quad, `== 0` for a triangle-only mesh

### Test B — primal observability (< 5 s)

Single regular hexagon. Prescribe `{0, 2, 4}` to `(+δ, -δ, +δ)`; free
`{1, 3, 5}`. Both limits are analytic — **derive them in the test, do not paste
values produced by the implementation**:

- `λ = 0` → harmonic on the 6-cycle → `δ·(0, 0, 1)`, match to `1e-12`
- `λ = 1e6` → affine completion → `δ·(-1/3, -1/3, +5/3)`, match to `1e-5`
  (solve `[1,u,v]` through the three prescribed nodes for `f = a + bu + cv`;
  Claude gets `f = δ(1/3 + (2/3)u - 1.1547v)`)
- `λ = 0.3` → `‖z(0.3) - z(0)‖∞ ≥ 0.04·δ` (measured 0.0465·δ)

## Task 2 — `tests/test_ngon_affine_load_step.py` (new)

### Test C — load-step VJP vs finite differences (< 20 s)

Drive the hourglass amplitude `δ` as a CSDL design variable through
`run_graph_load_steps` on a synthetic polygon6 mesh with `lambda_ngon > 0`.
Scalar objective on the final deformed/reprojected coordinates.

- centered FD at `(1e-4, 1e-5, 1e-6)`
- **per-pair best-step, then worst-pair** aggregation — the convention from the
  existing gate. Do not minimise across pairs.
- tolerance `< 1e-5`
- **Guard, required:** assert `d(objective)/dδ` at `λ > 0` differs from the same
  derivative at `λ = 0` by `≥ 1e-6`. Without this, a VJP that silently drops the
  N-gon adjoint term still passes.

This test is load-bearing in a way A and B are not: `P_e` is symmetric, so no
operator-level assertion can see a transpose error in the free/prescribed
coupling block. Only FD can.

### Mixed-polygon case (same file)

Synthetic mesh with quad + pentagon + hexagon cells:
- `num_hourglass_modes == Σ(n_e - 3)`
- after deformation at `λ > 0`: **zero folds and zero inversions**, plus the
  quality assertions already available in `bsm3.core.boundary_surface_movement.quality`

## Task 3 — `tests/test_curated_assets.py` (modify)

Add one `@pytest.mark.integration` test: `wall_surface.pkl` loads via
`import_trusted_polygon_pickle` and assembles with the expected hourglass-mode
count. **No solve, no derivative.** It must not enter the fast gate.

## Task 4 — `tests/test_derivative_gate.py` (modify, docstring only)

Reclassify it as the affine-nullspace control. State in the docstring that its
N-gon term is *expected* to be unobservable because the deformation is affine in
the element chart, and point to the polygon6 tests for the observable case.
No behavioural change.

---

## Literal file allowlist

Stage only these. Anything else is forbidden.

```
tests/test_ngon_affine_operator.py
tests/test_ngon_affine_load_step.py
tests/test_curated_assets.py
tests/test_derivative_gate.py
docs/overhaul/PLAN.md
docs/overhaul/LOG.md
docs/overhaul/CODEX_NEXT.md
```

`bsm3/core/boundary_surface_movement/ngon_affine.py` is **conditionally**
allowed: only if these tests expose a genuine defect in the operator. If you
touch it, say so prominently in Turn 8 with the failing assertion that justified
it — a source change here is a finding, not routine.

## Acceptance commands

```bash
python -m pytest -q tests/test_ngon_affine_operator.py
python -m pytest -q tests/test_ngon_affine_load_step.py
python -m pytest -q tests/test_derivative_gate.py
python -m pytest -q tests
python -m ruff check tests/test_ngon_affine_operator.py tests/test_ngon_affine_load_step.py
python -m ruff check --select D tests/test_ngon_affine_operator.py tests/test_ngon_affine_load_step.py
```

Then a genuine clone, as in Turn 6:

```bash
rm -rf /tmp/bsm3-m14-verify
git clone --no-hardlinks --branch production-ready-overhaul \
  "file:///Users/mariusruh/Documents/Research/nasa_uli/mesh_movement/packages/BSM3" \
  /tmp/bsm3-m14-verify
cd /tmp/bsm3-m14-verify
git status --porcelain          # MUST print nothing
python -m pip install --no-deps -e .
python -m pytest -q tests
```

**Expected:** the suite grows from 158 passed / 1 skipped by the new tests; total
added runtime `< 30 s`. Report actual numbers, not prose.

## Two known risks — report, do not paper over

1. If `run_graph_load_steps` rejects a bare hexagon ring for want of
   projection/intersection metadata, **enlarge to a small honeycomb** rather
   than weaken Test C's assertions. Say what you changed.
2. The `0.04·δ` threshold comes from a uniform-weight 6-cycle; the production
   solver applies area/stiffening weights, so the measured value may shift. It
   sits ~14 orders above noise. **If it is missed, that is a finding to report,
   not a number to lower.**

---

**Definition of done:** A, B, C, the mixed-polygon case, and the asset check all
pass; the full suite is green from a genuine clone; nothing outside the allowlist
staged; every excluded dirty file still dirty; actual numbers in Turn 8.
