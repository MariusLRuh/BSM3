# Codex review checklist — Turn 43 (M1.6 slice 2 correction)

Claude implemented Turn 42, documentation and comments only. Codex owns the
ruling. Base commit `c5728e3`. **Slice 2 is not marked complete by Claude.**

## Commits and changed paths

| Commit | Paths |
|---|---|
| `5c6452e` | the six projection modules |
| docs commit | `docs/overhaul/PLAN.md`, `LOG.md`, `CODEX_NEXT.md` |

- [ ] Six + three paths, **zero allowlist violations**. Every file staged by
      literal path; no directory, glob, or `-A`.
- [ ] Appended after `b99b4a4`; no amend, reset, rebase, or rewrite.
- [ ] `.github/workflows/actions.yml` **untouched** — the accepted 15-path CI
      step is unchanged. Preprocessing modules untouched.

## Mechanical proof

- [ ] **6/6** stripped ASTs identical under
      `ast.dump(..., include_attributes=False)` after recursively removing
      leading string-literal docstrings from every module, class, function,
      and async function.
- [ ] Coverage **80/80** over all 15 slice modules; module docstrings
      **15/15**.
- [ ] **New style audit**: every module and public definition in the six
      projection modules checked for a missing/blank first line, a summary
      without terminal punctuation, a trailing blank line, or a legacy
      `Returns:`/`Args:` heading. **0 failures**, down from 4.
- [ ] Rejection greps **empty** across the six modules.

## Contract corrections — each verified against the body

| Correction | Evidence |
|---|---|
| kernels are **eager**, not setup-only; construction caches topology/metadata/spaces/row spans/tessellation | call sites and `compute` bodies |
| `evaluate` declares graph I/O and derivatives; `compute` calculates and caches state in `shared_state` | wrapper bodies |
| stacked order follows `model.patch_ids` ← `patch_indices`, ascending only by default | lines 420-425 |
| coefficient shape `(total_control_points, physical_dimension)`; half-open `start:stop` spans | `PatchInfo` |
| parametric coordinates are **per-call**, shape `(N, 3)`, columns `[patch_id, u, v]` | `evaluate` signature |
| evaluation VJP returns `(d_coefficients, d_parametric_coordinates)`; patch-ID cotangent zero, `u`/`v` from tangents | return statement; only cols 1-2 written |
| three `output_mode` measures, signed only under an SDF mode | validation at lines 440-443 |
| forward state has `converged`, `iterations` **and** residual | `project` return dict |
| `boundary_clamped` = bound + outward **unmasked** residual, independent of `converged` | computed line 370, before the active set at 372 |
| candidates **ranked**: converged first, then distance; residual then distance otherwise | `rank = 0 if converged else 1` |
| degenerate edges get a **fixed-point candidate**, detected from sampled arc length | `if edge_is_degenerate: _append_candidate_spec(...)` |
| `compute_vjp(d_distances, forward_state) -> (d_points, d_coefficients)` | signature and return |
| `compute_vjp_vjp -> (dd_points, dd_coefficients, dd_d_distances)` | return statement |
| parametric output `(N, 3)` with zero-derivative patch-ID column; physical `(N, physical_dimension)` | projection op |

- [ ] Spot-check any of these against the implementation.
- [ ] Trusted-local-only pickle warnings retained on
      `load_function_set_from_pickle` and `load_function_set`.

## NumPy style

- [ ] `warm_start_projections.py`: module docstring and **all ten** public
      definitions converted from legacy prose (leading blank line, free-form
      `Returns:`) to genuine NumPy sections. Turn 40 counted their presence as
      coverage without checking style; that gap is closed and the audit now
      fails on it.

## Verification

- [ ] Focused suite **82 passed / 3 deselected** — matches baseline.
- [ ] Derivative gate + both M1.4 tests **6 passed** — matches baseline.
- [ ] `git diff --check` clean over all nine paths.
- [ ] **Ruff unavailable in `central_geom`**; attempted and recorded, nothing
      installed. The pinned CI step is authoritative and still **unverified
      locally**.
- [ ] No E175 integration or clean-clone rerun, per the spec.

## Deviations

Two replacement strings in my first pass differed from the file only in line
wrapping, so they silently failed to match and left `d_output_measure` and
"Degenerate edges are excluded" in place. The rejection grep caught both and
they were corrected by exact-span replacement. This is the reason the spec's
rejection greps exist, and they worked.

No stop rule fired. No other deviation.

## Remaining M1 scope

M1.6 slice 3 (drivers, MPI/DAFoam), then M1.8 pickle retirement, then full
M1.7 acceptance. M1.7 carry-ins stand: the
`GraphDistanceWeighting.summary` `TypedDict` and its dead `"decay"` key.
